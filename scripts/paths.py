"""Where the skill keeps the user's data: the one place every script asks.

Everything the skill writes lives outside its own folder, in its home: ~/.claude/bishop-and-barrister/, or
$BISHOP_AND_BARRISTER_HOME. A plugin update replaces the skill's folder, so the downloaded documents and the
rulings record must not live there.

Every path is worked out when it is asked for, never once at import, so setting $BISHOP_AND_BARRISTER_HOME
(as the tests do, with a temporary folder) moves all of them together.
"""

import os
from pathlib import Path


def home() -> Path:
    """The skill's home: the rulings record, and the documents under documents/."""
    return Path(os.environ.get("BISHOP_AND_BARRISTER_HOME") or Path.home() / ".claude" / "bishop-and-barrister")


# --- the downloaded documents (Wizards' material, which each device downloads for itself) ---------------


def documents() -> Path:
    """The folder sources.py downloads into."""
    return home() / "documents"


def rules_file() -> Path:
    """The Comprehensive Rules as downloaded."""
    return documents() / "MagicCompRules.txt"


def version_file() -> Path:
    """The installed CR's version: its dates, size and SHA-256."""
    return documents() / "version.json"


def registry() -> Path:
    """sources.py's record of the tournament documents it has downloaded."""
    return documents() / "sources.json"


def docs_dir() -> Path:
    """The tournament documents, each as <key>.pdf and its converted <key>.json; $BISHOP_AND_BARRISTER_DOCS overrides."""
    return Path(os.environ.get("BISHOP_AND_BARRISTER_DOCS") or documents() / "docs")


def cr_file() -> Path:
    """The CR that citations are pinned against; $BISHOP_AND_BARRISTER_CR points at another copy."""
    return Path(os.environ.get("BISHOP_AND_BARRISTER_CR") or rules_file())


def cr_version() -> Path:
    """The version.json beside cr_file()."""
    return cr_file().parent / "version.json"


# --- the rulings record (a git repository at home()) ----------------------------------------------------


def rulings() -> Path:
    """One JSON file per official or house ruling."""
    return home() / "rulings"


def deliberation() -> Path:
    """The reasoning behind each ruling, kept apart from the ruling itself."""
    return home() / "deliberation"


def objects() -> Path:
    """Source texts that citations are pinned to, by SHA-256."""
    return home() / "objects"


def manifest() -> Path:
    """Which version of each source the record was built against."""
    return home() / "sources" / "manifest.json"


def index() -> Path:
    """The SQLite search index, rebuilt from the record."""
    return home() / "index.sqlite"


def rules() -> Path:
    """Rules introduced by challenge, one rules/challenge-<id>.json each."""
    return home() / "rules"


def challenges() -> Path:
    """Each challenge's event files, challenges/challenge-<id>/."""
    return home() / "challenges"


def bin_dir() -> Path:
    """The downloaded bab-challenge binary."""
    return home() / "bin"


def config() -> Path:
    """The optional remote store's settings."""
    return home() / "config.json"


def sync_state() -> Path:
    """Sync bookkeeping, inside .git so it is never committed."""
    return home() / ".git" / "bishop-and-barrister-sync.json"
