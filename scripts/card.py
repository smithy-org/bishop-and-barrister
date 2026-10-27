#!/usr/bin/env python3
"""Fetch current Oracle text for a card from Scryfall.

Printed card text is often out of date — Oracle text is the version that
actually governs play, so always check here rather than relying on memory
of what a card says.

Usage:
    python scripts/card.py "Lightning Bolt"
    python scripts/card.py "Ulamog" --rulings
    python scripts/card.py "Blood Moon" "Urborg, Tomb of Yawgmoth"
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Scryfall's API terms (https://scryfall.com/docs/api and /docs/api/rate-limits):
# - every request to api.scryfall.com sends a User-Agent naming the application,
#   and an Accept header;
# - /cards/named, /cards/search, /cards/random and /cards/collection allow 2
#   requests a second, everything else 10;
# - a 429 limits access for 30 seconds, and ignoring 429s risks a ban;
# - data should be cached for at least 24 hours.
# Several agents can run these scripts at once, so pacing and the lockout are
# shared between processes through a lock in CACHE_DIR.
API = "https://api.scryfall.com"
HEADERS = {"User-Agent": "bishop-and-barrister/1.0", "Accept": "application/json"}
CARD_ENDPOINTS = ("/cards/named", "/cards/search", "/cards/random", "/cards/collection")
CARD_INTERVAL = 0.5
OTHER_INTERVAL = 0.1
LOCKOUT = 30.0
RETRIES = 2
CACHE_TTL = 24 * 60 * 60
CACHE_DIR = Path(os.environ.get("BISHOP_AND_BARRISTER_CACHE") or Path(tempfile.gettempdir()) / "bishop-and-barrister")
STALE_LOCK = 60.0

# The formats the skill covers, in Scryfall's legality keys. Scryfall's "brawl"
# is the 100-card Arena format; the CR's 60-card Brawl is "standardbrawl".
FORMATS = {
    "standard": "Standard",
    "pioneer": "Pioneer",
    "modern": "Modern",
    "legacy": "Legacy",
    "vintage": "Vintage",
    "pauper": "Pauper",
    "commander": "Commander",
    "standardbrawl": "Brawl (CR, 60 cards)",
    "brawl": "Brawl (Arena, 100 cards)",
    "oathbreaker": "Oathbreaker",
}


class _Lock:
    """A lock shared by every process on this machine.

    The lock is a directory, since mkdir is atomic everywhere.
    """

    def __enter__(self):
        """Take the lock, waiting while another process holds it.

        A lock older than STALE_LOCK seconds was left by a killed process and is removed.

        Returns:
            This lock.
        """
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.path = CACHE_DIR / "scryfall.lock"
        while True:
            try:
                self.path.mkdir()
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > STALE_LOCK:
                        shutil.rmtree(self.path, ignore_errors=True)  # left by a killed process
                except FileNotFoundError:
                    pass
                time.sleep(0.05)

    def __exit__(self, *exc):
        """Release the lock, whether or not the block raised."""
        shutil.rmtree(self.path, ignore_errors=True)


def _state() -> dict:
    """Read the shared pacing state, or an empty one if it's missing or unreadable."""
    try:
        return json.loads((CACHE_DIR / "scryfall-pacing.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    """Write the shared pacing state; call it only while holding _Lock."""
    (CACHE_DIR / "scryfall-pacing.json").write_text(json.dumps(state), encoding="utf-8")


def _wait_turn(url: str) -> None:
    """Hold until this machine may send its next request to url, then claim the slot.

    Args:
        url: The request about to be sent; its path decides which rate limit applies.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname != urllib.parse.urlparse(API).hostname:
        return  # the *.scryfall.io file origins have no rate limit
    interval = CARD_INTERVAL if parsed.path.startswith(CARD_ENDPOINTS) else OTHER_INTERVAL
    while True:
        # Reserve the next free slot, then sleep outside the lock until it comes.
        with _Lock():
            state = _state()
            slot = max(time.time(), state.get("next", 0), state.get("locked_until", 0))
            state["next"] = slot + interval
            _save_state(state)
        time.sleep(max(0.0, slot - time.time()))
        # A 429 recorded while this process slept starts a lockout it must also wait out.
        if time.time() >= _state().get("locked_until", 0):
            return


def _locked_out(retry_after: str | None) -> float:
    """Record a 429 so every process waits out the lockout.

    Args:
        retry_after: The response's Retry-After header, if any. A value shorter than
            LOCKOUT, or one that isn't a number, gives LOCKOUT.

    Returns:
        The seconds to wait.
    """
    try:
        wait = max(LOCKOUT, float(retry_after or 0))
    except ValueError:
        wait = LOCKOUT
    with _Lock():
        state = _state()
        state["locked_until"] = max(state.get("locked_until", 0), time.time() + wait)
        _save_state(state)
    return wait


def fetch(url: str, timeout: float = 30, accept: str = HEADERS["Accept"]) -> bytes:
    """GET a Scryfall URL with the required headers, paced to its limits.

    After a 429, waits out the 30-second lockout before trying again, at most RETRIES times.

    Args:
        url: The URL to fetch.
        timeout: Seconds to wait for the server on each attempt.
        accept: The Accept header to send.

    Returns:
        The response body.

    Raises:
        urllib.error.HTTPError: For any error status, or a 429 that outlasts the retries.
        urllib.error.URLError: When the server can't be reached.
    """
    req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"], "Accept": accept})
    for attempt in range(RETRIES + 1):
        _wait_turn(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code != 429:
                raise
            wait = _locked_out(err.headers.get("Retry-After"))  # recorded even when giving up
            if attempt == RETRIES:
                raise
            print(f"Scryfall is rate-limiting (429); waiting {wait:g} s before trying again.", file=sys.stderr)
    raise AssertionError("unreachable")


def get(url: str) -> dict:
    """GET JSON from Scryfall, from a cache kept for 24 hours as Scryfall asks.

    Args:
        url: The Scryfall API URL.

    Returns:
        The decoded JSON object.

    Raises:
        urllib.error.HTTPError: When Scryfall answers with an error, as from fetch().
    """
    path = CACHE_DIR / "responses" / hashlib.sha256(url.encode("utf-8")).hexdigest()
    try:
        if time.time() - path.stat().st_mtime < CACHE_TTL:
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    body = fetch(url).decode("utf-8")
    data = json.loads(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return data


def render_face(face: dict) -> str:
    """Format one card face as text: name and cost, type line, Oracle text and stats.

    Args:
        face: A Scryfall card object, or one entry of its card_faces.

    Returns:
        The face as lines of text, leaving out whatever the face doesn't have.
    """
    parts = [f"{face.get('name', '?')}  {face.get('mana_cost', '') or ''}".rstrip()]
    if face.get("type_line"):
        parts.append(face["type_line"])
    if face.get("oracle_text"):
        parts.append(face["oracle_text"])
    if face.get("power") is not None:
        parts.append(f"{face['power']}/{face['toughness']}")
    if face.get("loyalty"):
        parts.append(f"Loyalty: {face['loyalty']}")
    if face.get("defense"):
        parts.append(f"Defense: {face['defense']}")
    return "\n".join(parts)


def show(name: str, rulings: bool) -> int:
    """Print a card's Oracle text and its legality in the formats the skill covers.

    Args:
        name: The card name, fuzzy matched by Scryfall.
        rulings: Whether to print the card's rulings too.

    Returns:
        0 when the card was found, 1 when it wasn't or the name was ambiguous.

    Raises:
        urllib.error.URLError: When Scryfall can't be reached or answers with an error other than 404.
    """
    url = f"{API}/cards/named?fuzzy={urllib.parse.quote(name)}"
    try:
        card = get(url)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            # Scryfall also answers 404 when the name matches too many cards,
            # and says so in the body; pass that on rather than "not found".
            try:
                details = json.loads(err.read().decode("utf-8")).get("details")
            except ValueError:
                details = None
            print(details or f"No card found matching {name!r}.", file=sys.stderr)
            return 1
        raise

    print("=" * 60)
    if card.get("card_faces"):
        print("\n\n---\n\n".join(render_face(f) for f in card["card_faces"]))
    else:
        print(render_face(card))

    # Every format, grouped by status, so a banned or restricted card says so
    # instead of just being missing from a list of legal formats.
    legal = card.get("legalities", {})
    by_status: dict[str, list[str]] = {}
    for key, label in FORMATS.items():
        by_status.setdefault(legal.get(key, "unknown").replace("_", " "), []).append(label)
    print()
    for status in ("legal", "restricted", "banned", "not legal", "unknown"):
        if status in by_status:
            print(f"{status.capitalize()}: {', '.join(by_status.pop(status))}")
    for status, labels in by_status.items():
        print(f"{status.capitalize()}: {', '.join(labels)}")
    print("(Legality from Scryfall is informational; the official banned and restricted list decides.)")

    if rulings and card.get("rulings_uri"):
        data = get(card["rulings_uri"])
        items = data.get("data", [])
        print(f"\nRulings ({len(items)}; wotc = Wizards' official ruling, scryfall = Scryfall's own note):")
        for r in items:
            print(f"  [{r.get('published_at', '?')}, {r.get('source', '?')}] {r.get('comment', '')}")
    print()
    return 0


def main() -> int:
    """Run the command line.

    Returns:
        The exit status: 0 when every card was found, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="+", help="one or more card names (fuzzy matched)")
    parser.add_argument("--rulings", action="store_true", help="include official Scryfall rulings")
    args = parser.parse_args()

    status = 0
    for name in args.names:
        status |= show(name, args.rulings)
    return status


if __name__ == "__main__":
    # Windows consoles default to cp1252, which has no loyalty minus sign (U+2212).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except urllib.error.URLError as err:
        if getattr(err, "code", None) == 429:
            # Scryfall's terms forbid ignoring 429s: stop rather than loop.
            print("Scryfall is still rate-limiting after waiting out its lockout. Don't retry in a loop; "
                  "answer without the live card text, and say so.", file=sys.stderr)
            sys.exit(1)
        print(f"Network error reaching Scryfall: {err}", file=sys.stderr)
        sys.exit(1)
