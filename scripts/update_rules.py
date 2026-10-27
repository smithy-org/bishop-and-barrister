#!/usr/bin/env python3
"""Download the current Comprehensive Rules text file from Wizards.

Staleness is judged by content, not by filename. Two dates are in play and
they legitimately differ: the filename carries the date Wizards posted the
file (e.g. 20260819), while the document itself states an effective date
(e.g. August 7, 2026). Neither is a reliable version key on its own, because
Wizards sometimes re-posts a corrected file under the same name. So this
records a hash of what was downloaded and compares against that.

Usage:
    python scripts/update_rules.py            # update if the file has changed
    python scripts/update_rules.py --check    # report status, download nothing
    python scripts/update_rules.py --force    # re-download regardless
"""

import argparse
import hashlib
import http.client
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lookup  # noqa: E402  (where the downloaded documents live)

RULES_PAGE = "https://magic.wizards.com/en/rules"
# Outside the skill's folder (see lookup.DATA_DIR), so a plugin update keeps the download.
DATA_DIR = lookup.DATA_DIR
RULES_FILE = lookup.RULES_FILE
META_FILE = DATA_DIR / "version.json"

UA = "Mozilla/5.0 (compatible; bishop-and-barrister/1.0)"
TXT_LINK = re.compile(
    r"https://media\.wizards\.com/[^\"'\s>]*(?:%20|\s)?MagicCompRules[^\"'>]*?\.txt",
    re.IGNORECASE,
)
EFFECTIVE = re.compile(r"effective as of\s+([A-Z][a-z]+ \d{1,2}, \d{4})")


def get(url: str, timeout: int = 60) -> bytes:
    """GET a URL and return its body.

    Raises:
        urllib.error.URLError: When the server can't be reached or answers with an error.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def head(url: str, timeout: int = 30) -> dict:
    """Probe a file's metadata cheaply, so --check doesn't pull a megabyte every time.

    WotC posts the rules under a filename containing a space, and http.client
    rejects a raw space in the request path, so quote before probing exactly as
    the download path does.

    Args:
        url: The rules file's URL, quoted or not.
        timeout: Seconds to wait for the server.

    Returns:
        A dict with "content_length" and "last_modified", each None when the server didn't send it.

    Raises:
        urllib.error.URLError: When the server can't be reached or answers with an error.
    """
    url = urllib.parse.quote(urllib.parse.unquote(url), safe=":/")
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return {
            "content_length": resp.headers.get("Content-Length"),
            "last_modified": resp.headers.get("Last-Modified"),
        }


def find_txt_url() -> str:
    """Find the current Comprehensive Rules .txt link on Wizards' rules page.

    Returns:
        The link; when the page has several, the one that sorts last, which carries the latest date.

    Raises:
        SystemExit: When the page has no such link, which usually means its layout changed.
    """
    html = get(RULES_PAGE).decode("utf-8", errors="replace")
    matches = TXT_LINK.findall(html)
    if not matches:
        raise SystemExit(
            "Could not find a Comprehensive Rules .txt link on the rules page.\n"
            "Wizards may have changed the page layout. Check:\n"
            f"  {RULES_PAGE}"
        )
    return sorted(set(matches))[-1]


def posted_date(url: str) -> str:
    """Return the YYYYMMDD stamp in the filename — when Wizards posted this file — or "unknown"."""
    m = re.search(r"(\d{8})", urllib.parse.unquote(url))
    return m.group(1) if m else "unknown"


def effective_date(text: str) -> str:
    """Return the effective date stated inside the document, or "unknown".

    This is not the same thing as the posted date in the filename.
    """
    m = EFFECTIVE.search(text)
    return m.group(1) if m else "unknown"


def digest(text: str) -> str:
    """Hex SHA-256 of the text's UTF-8 bytes: the version key for the rules."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def decode(raw: bytes) -> str:
    """Decode the downloaded file, trying UTF-8 (with or without a BOM), then cp1252, then Latin-1."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def local_state() -> dict | None:
    """Describe the local copy, reconstructing metadata if version.json is absent.

    A file copied in by hand has no version.json, but it can still be hashed,
    so manual installs get the same staleness checking as downloaded ones.

    Returns:
        The saved metadata when version.json matches the file on disk, metadata rebuilt
        from the file otherwise ("source" says which), or None when there is no local copy.
    """
    if not RULES_FILE.exists():
        return None

    text = RULES_FILE.read_text(encoding="utf-8-sig")
    state = {
        "sha256": digest(text),
        "effective_date": effective_date(text),
        "posted_date": "unknown",
        "content_length": None,
        "last_modified": None,
        "source": "reconstructed from local file",
    }

    if META_FILE.exists():
        try:
            saved = json.loads(META_FILE.read_text())
            if saved.get("sha256") == state["sha256"]:
                saved["source"] = "version.json"
                return saved
            # Metadata doesn't describe the file actually on disk; trust the file.
            state["source"] = "version.json is stale, using the file itself"
        except (ValueError, KeyError):
            pass

    return state


def write_meta(text: str, url: str, probe: dict) -> None:
    """Record what was downloaded in version.json.

    Args:
        text: The rules text, as installed.
        url: Where it was downloaded from.
        probe: The result of head(), stored so a later --check can skip the download; may be empty.
    """
    META_FILE.write_text(
        json.dumps(
            {
                "sha256": digest(text),
                "posted_date": posted_date(url),
                "effective_date": effective_date(text),
                "source_url": url,
                "content_length": probe.get("content_length"),
                "last_modified": probe.get("last_modified"),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "lines": text.count("\n") + 1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def describe(state: dict | None) -> None:
    """Print the local copy's version, as local_state() describes it."""
    if state is None:
        print("Local copy:  none downloaded yet")
        return
    print(f"Local copy:  effective {state['effective_date']}, posted {state['posted_date']}")
    print(f"             sha256 {state['sha256'][:12]}  ({state['source']})")


def main() -> int:
    """Run the command line: compare the local copy with Wizards' file and install it if it changed.

    Returns:
        The exit status, 0 unless something failed.

    Raises:
        SystemExit: When the rules page has no rules link.
        urllib.error.URLError: When the Wizards site can't be reached.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-download even if unchanged")
    parser.add_argument("--check", action="store_true", help="report status without downloading")
    args = parser.parse_args()

    lookup.adopt_legacy_documents()  # a copy downloaded into the skill folder by an earlier version
    url = find_txt_url()
    local = local_state()
    describe(local)
    print(f"Remote file: posted {posted_date(url)}")

    # Try a HEAD first: if size and mtime match what we stored, nothing changed.
    probe = {}
    try:
        probe = head(url)
    except (urllib.error.URLError, http.client.HTTPException, ValueError):
        pass  # Probing is optional; any failure falls through to the full comparison.

    unchanged_by_probe = bool(
        local
        and probe.get("content_length")
        and local.get("content_length") == probe["content_length"]
        and local.get("last_modified") == probe.get("last_modified")
    )

    if unchanged_by_probe and not args.force:
        print("\nUp to date (server reports identical size and modification time).")
        return 0

    # The probe was inconclusive, so compare actual content. This is the check
    # that catches a corrected file re-posted under the same filename.
    safe_url = urllib.parse.quote(urllib.parse.unquote(url), safe=":/")
    if args.check:
        print("\nSize/mtime did not confirm a match; downloading to compare content...")
    text = decode(get(safe_url))
    remote_hash = digest(text)

    if local and local["sha256"] == remote_hash and not args.force:
        print(f"\nUp to date (content identical, sha256 {remote_hash[:12]}).")
        # Refresh the probe values so future --check runs can short-circuit.
        write_meta(text, url, probe)
        return 0

    if args.check:
        print(f"\nUpdate available: remote effective {effective_date(text)}, sha256 {remote_hash[:12]}.")
        print("Run without --check to install it.")
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RULES_FILE.write_text(text, encoding="utf-8")
    write_meta(text, url, probe)

    size_kb = len(text.encode("utf-8")) / 1024
    print(f"\nSaved {RULES_FILE} ({size_kb:.0f} KB)")
    print(f"Effective {effective_date(text)}, posted {posted_date(url)}, sha256 {remote_hash[:12]}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as err:
        print(f"Network error: {err}", file=sys.stderr)
        print("Check your connection or whether the Wizards site is reachable.", file=sys.stderr)
        sys.exit(1)
