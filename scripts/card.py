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
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.scryfall.com"
# Scryfall asks API clients to identify themselves and to rate-limit.
HEADERS = {"User-Agent": "bishop-and-barrister/1.0", "Accept": "application/json"}
DELAY = 0.1

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


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render_face(face: dict) -> str:
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

    if rulings and card.get("rulings_uri"):
        time.sleep(DELAY)
        data = get(card["rulings_uri"])
        items = data.get("data", [])
        print(f"\nOfficial rulings ({len(items)}):")
        for r in items:
            print(f"  [{r.get('published_at', '?')}] {r.get('comment', '')}")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="+", help="one or more card names (fuzzy matched)")
    parser.add_argument("--rulings", action="store_true", help="include official Scryfall rulings")
    args = parser.parse_args()

    status = 0
    for i, name in enumerate(args.names):
        if i:
            time.sleep(DELAY)
        status |= show(name, args.rulings)
    return status


if __name__ == "__main__":
    # Windows consoles default to cp1252, which has no loyalty minus sign (U+2212).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except urllib.error.URLError as err:
        print(f"Network error reaching Scryfall: {err}", file=sys.stderr)
        sys.exit(1)
