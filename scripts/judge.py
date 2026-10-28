#!/usr/bin/env python3
"""The judge's rulings store: official rulings, and the rules challenges introduced, searchable and traceable.

Everything lives in ~/.claude/bishop-and-barrister/ (or $BISHOP_AND_BARRISTER_HOME), which is a git
repository. Git is the record: every change is a commit that says what changed, why, and who drafted
or decided it. The SQLite index is only a search index, rebuilt from the record at any time. Large
downloads (Scryfall's bulk rulings) live in objects/<sha256>, outside git.

Nothing the skill answers is stored. A rule enters the record only through a challenge (CHALLENGE.md,
scripts/challenge.py), which writes it to rules/challenge-<id>.json.

Usage:
    python scripts/judge.py build                       # set up, download official rulings, index
    python scripts/judge.py search "humility opalescence" --agent
    python scripts/judge.py search --card "Blood Artist" --rule 603.10a
    python scripts/judge.py show <id> --agent
    python scripts/judge.py recheck                     # flag rulings and rules whose sources changed
    python scripts/judge.py index                       # rebuild the search index
    python scripts/judge.py migrate                     # move rulings from the retired `record` into challenges
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402  (where the user's data lives)
import card as scryfall  # noqa: E402  (the skill's Scryfall client, card.py)
import lookup  # noqa: E402  (the skill's own CR reader)
import s3  # noqa: E402  (the optional remote store's client)

SKILL_DIR = Path(__file__).resolve().parent.parent
OFFLINE = os.environ.get("BISHOP_AND_BARRISTER_OFFLINE") == "1"


API = scryfall.API

QUESTION_TYPES = {"interaction", "legality-check", "sequence", "card-text", "deck-legality", "format-rule", "tournament"}
CONFIDENCE = {"certain", "likely", "unsure"}
# Search order: official Wizards rulings, then rules introduced by challenge, then the user's house rules
# (from before challenges), then Scryfall's own rulings (level 4).
RANK = {("official", 1): 0, ("rule", 5): 1, ("reviewed", 5): 2, ("official", 4): 3}


def now() -> str:
    """Return the current UTC time as an ISO 8601 string to the second, ending in Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    """Hex SHA-256 of the text's UTF-8 bytes: how a citation is pinned to the text it relies on."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def die(message: str, code: int = 1):
    """Print a message to stderr and exit.

    Args:
        message: What went wrong, for the user.
        code: The exit status.

    Raises:
        SystemExit: Always.
    """
    print(message, file=sys.stderr)
    sys.exit(code)


# --- git: the record -------------------------------------------------------------------------


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run git in the record, capturing its output.

    Args:
        *args: The git arguments.
        check: Raise when git fails.

    Returns:
        The finished process, with stdout and stderr as text.

    Raises:
        subprocess.CalledProcessError: When git fails and check is set.
    """
    return subprocess.run(["git", "-C", str(paths.home()), *args], capture_output=True, text=True, encoding="utf-8", check=check)


# Kept out of the record: the object store (synced by hash, not git), the rebuildable index, the sync
# settings, which name the user's own endpoint and must never be committed or uploaded, and the downloaded
# rules documents (paths.documents()), which are Wizards' material and each device downloads its own.
IGNORED = ("objects/", "index.sqlite", "config.json", "documents/")


def ensure_home() -> None:
    """Create the store and its git repository on first use.

    A record made before a pattern joined IGNORED gets that pattern added to its .gitignore.
    """
    for d in (paths.rulings(), paths.deliberation(), paths.objects(), paths.manifest().parent):
        d.mkdir(parents=True, exist_ok=True)
    if not (paths.home() / ".git").exists():
        subprocess.run(["git", "init", "-q", str(paths.home())], check=True)
        (paths.home() / ".gitignore").write_text("".join(f"{p}\n" for p in IGNORED), encoding="utf-8")
        if not paths.manifest().exists():
            paths.manifest().write_text(json.dumps({"objects": {}}, indent=2) + "\n", encoding="utf-8")
        commit("Start the rulings record", drafted_by="judge")
    ignore = paths.home() / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
    missing = [p for p in IGNORED if p not in lines]
    if missing:  # a record made before a pattern was added
        ignore.write_text("".join(f"{p}\n" for p in lines + missing), encoding="utf-8")
        commit(f"Keep {', '.join(missing)} out of the record", drafted_by="judge")


def ensure_identity() -> None:
    """Make sure git has an identity to commit with.

    A commit needs one; fall back to a local one only if the user has none configured.
    """
    if not git("config", "user.email", check=False).stdout.strip():
        git("config", "user.name", "Bishop & Barrister")
        git("config", "user.email", "bishop-and-barrister@localhost")


def commit(message: str, drafted_by: str | None = None, decided_by: str | None = None) -> bool:
    """Commit everything in the record.

    Args:
        message: The commit message.
        drafted_by: Who drafted the change, recorded as a Drafted-by trailer.
        decided_by: Who decided it, recorded as a Decided-by trailer.

    Returns:
        False when there was nothing to commit.

    Raises:
        subprocess.CalledProcessError: When git fails.
    """
    ensure_identity()
    git("add", "-A")
    if not git("status", "--porcelain").stdout.strip():
        return False
    trailers = []
    if drafted_by:
        trailers.append(f"Drafted-by: {drafted_by}")
    if decided_by:
        trailers.append(f"Decided-by: {decided_by}")
    body = message + ("\n\n" + "\n".join(trailers) if trailers else "")
    subprocess.run(["git", "-C", str(paths.home()), "commit", "-q", "-F", "-"], input=body, text=True, encoding="utf-8", check=True)
    return True


def load_manifest() -> dict:
    """Read sources/manifest.json, which records each object downloaded and which one is current."""
    return json.loads(paths.manifest().read_text(encoding="utf-8")) if paths.manifest().exists() else {"objects": {}}


def save_manifest(manifest: dict) -> None:
    """Write sources/manifest.json."""
    paths.manifest().write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def store_object(data: bytes) -> str:
    """Keep data in objects/<sha256>, outside git, and return its hash."""
    digest = hashlib.sha256(data).hexdigest()
    path = paths.objects() / digest
    if not path.exists():
        path.write_bytes(data)
    return digest


# --- Scryfall --------------------------------------------------------------------------------


# All Scryfall traffic goes through card.py's client, which keeps to Scryfall's API terms:
# the required headers, the rate limits shared by every process, the 30-second lockout after a
# 429, and a 24-hour cache.


def http_json(url: str) -> dict:
    """GET JSON from Scryfall through card.py's client, cached for 24 hours."""
    return scryfall.get(url)


def http_bytes(url: str) -> bytes:
    """Download a large Scryfall file, such as a bulk data file, through card.py's client."""
    return scryfall.fetch(url, timeout=300, accept="*/*")


def oracle_text_of(card: dict) -> str:
    """Return a card's Oracle text, its faces joined by a "//" line."""
    faces = card.get("card_faces") or [card]
    return "\n//\n".join(f.get("oracle_text", "") for f in faces)


def resolve_card(name: str) -> dict | None:
    """Look a card up on Scryfall: name, Oracle ID and the hash of its current Oracle text.

    Args:
        name: The card name, fuzzy matched.

    Returns:
        A dict with "name", "oracle_id" and "oracle_sha256", or None when offline or no card matches.

    Raises:
        urllib.error.HTTPError: When Scryfall is still rate-limiting (429) after card.py's retries.
    """
    if OFFLINE:
        return None
    try:
        card = http_json(f"{API}/cards/named?fuzzy={urllib.parse.quote(name)}")
    except urllib.error.HTTPError as err:
        if err.code == 429:
            raise
        return None
    return {"name": card["name"], "oracle_id": card.get("oracle_id"), "oracle_sha256": sha256_text(oracle_text_of(card))}


# --- the Comprehensive Rules -----------------------------------------------------------------

_RULES: dict[str, str] | None = None


def cr_rules() -> dict[str, str]:
    """Map each rule number to the rule's text, from the downloaded CR (the body, not the table of contents).

    The map is read once per process.

    Raises:
        SystemExit: Via die() when the CR isn't downloaded.
    """
    global _RULES
    if _RULES is None:
        lookup.adopt_legacy_documents()
        if not paths.cr_file().exists():
            die("The Comprehensive Rules aren't downloaded. Run: python scripts/sources.py update")
        lines = paths.cr_file().read_text(encoding="utf-8-sig").splitlines()
        _RULES = {}
        for line in lines[lookup.body_start(lines):]:
            m = lookup.RULE_LINE.match(line)
            if m:
                _RULES.setdefault(m.group(1), m.group(2).strip())
    return _RULES


def cr_effective() -> str | None:
    """Return the downloaded CR's effective date, as update_rules.py recorded it, or None."""
    if paths.cr_version().exists():
        return json.loads(paths.cr_version().read_text(encoding="utf-8")).get("effective_date")
    return None


# --- rulings in the record -------------------------------------------------------------------


def ruling_path(rid: str) -> Path:
    """Return where a ruling's file lives in the record."""
    return paths.rulings() / f"{rid}.json"


def load_ruling(rid: str) -> dict:
    """Read a ruling from the record.

    Raises:
        SystemExit: Via die() when there is no such ruling.
    """
    path = ruling_path(rid)
    if not path.exists():
        die(f"No ruling {rid} in the record.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_ruling(ruling: dict) -> None:
    """Write a ruling to its file in the record; the caller commits."""
    ruling_path(ruling["id"]).write_text(json.dumps(ruling, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_deliberation(rid: str) -> list[dict]:
    """Read a ruling's deliberation log, one entry per line; empty when it has none."""
    path = paths.deliberation() / f"{rid}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_citation(c: dict, label: str) -> list[str]:
    """Check one citation: what it cites exists in the current documents, or it carries its own excerpt.

    Args:
        c: The citation: doc (default "cr"), ref, and perhaps an excerpt.
        label: Names the citation in messages.

    Returns:
        The problems found; empty when the citation is valid.

    Raises:
        SystemExit: Via die() when it cites the CR and the CR isn't downloaded.
    """
    doc = c.get("doc", "cr")
    if doc == "cr":
        if c.get("ref") not in cr_rules():
            return [f"{label} cites CR {c.get('ref')}, which doesn't exist in the current CR"]
    elif doc in lookup.DOCS:
        if not (paths.docs_dir() / f"{doc}.json").exists():
            return [f"{label} cites the {lookup.DOCS[doc]}, which isn't downloaded (python scripts/sources.py update {doc})"]
        if not lookup.doc_section(doc, str(c.get("ref", ""))):
            return [f"{label} cites {doc.upper()} {c.get('ref')!r}, which doesn't name exactly one section of the current "
                    f"{lookup.DOCS[doc]} (see lookup.py --doc {doc} toc)"]
    elif not c.get("excerpt"):
        return [f"{label} ({doc}) needs an 'excerpt'"]
    return []


def pin_citation(c: dict) -> None:
    """Pin one valid citation to the exact text it relies on (text_sha256), with an excerpt of it.

    The citation is changed in place. A tournament document citation also gains the section's own key,
    its heading and the document's version. Call validate_citation() first.

    Args:
        c: The citation.
    """
    c.setdefault("doc", "cr")
    if c["doc"] == "cr":
        text = cr_rules()[c["ref"]]
        c["text_sha256"] = sha256_text(text)
        c.setdefault("excerpt", text[:300])
    elif c["doc"] in lookup.DOCS:
        # Store the section's own key, so a heading quoted in 'ref' still finds it after an update.
        section = lookup.doc_section(c["doc"], str(c["ref"]))
        c["ref"] = section["key"]
        c["heading"] = section["heading"]
        c["text_sha256"] = sha256_text(section["text"])
        c["version"] = lookup.load_doc(c["doc"]).get("effective")
        c.setdefault("level", 2)
        c.setdefault("excerpt", section["text"][:300])
    elif c.get("excerpt"):
        c["text_sha256"] = sha256_text(c["excerpt"])


# --- the search index ------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS rulings (
    id TEXT PRIMARY KEY, kind TEXT, level INTEGER, rank INTEGER, status TEXT,
    question_type TEXT, oracle_id TEXT, source TEXT, published_at TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS ruling_cards (ruling_id TEXT, oracle_id TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS citations (ruling_id TEXT, doc TEXT, ref TEXT);
CREATE TABLE IF NOT EXISTS card_names (oracle_id TEXT PRIMARY KEY, name TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS rulings_fts USING fts5(id UNINDEXED, body);
CREATE INDEX IF NOT EXISTS rulings_oracle ON rulings(oracle_id);
CREATE INDEX IF NOT EXISTS cards_oracle ON ruling_cards(oracle_id);
CREATE INDEX IF NOT EXISTS citations_ref ON citations(ref);
"""


def connect() -> sqlite3.Connection:
    """Open the search index, creating its tables if they're missing."""
    conn = sqlite3.connect(paths.index())
    conn.executescript(SCHEMA)
    return conn


def index_user_ruling(conn: sqlite3.Connection, r: dict) -> None:
    """Index one of the user's rulings from before challenges, replacing any earlier entry for it.

    Its full text includes the deliberation, so a search finds what was said along the way.

    Args:
        conn: The search index.
        r: The ruling.
    """
    rid = r["id"]
    for table, col in (("rulings", "id"), ("rulings_fts", "id"), ("ruling_cards", "ruling_id"), ("citations", "ruling_id")):
        conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (rid,))
    conn.execute(
        "INSERT INTO rulings VALUES (?,?,?,?,?,?,?,?,?,?)",
        (rid, r["kind"], r["level"], RANK.get((r["kind"], r["level"]), 9), r["status"], r["question_type"],
         None, "user", r.get("created_at"), json.dumps(r, ensure_ascii=False)),
    )
    for card in r["cards"]:
        conn.execute("INSERT INTO ruling_cards VALUES (?,?,?)", (rid, card.get("oracle_id"), card["name"]))
        if card.get("oracle_id"):
            conn.execute("INSERT OR REPLACE INTO card_names VALUES (?,?)", (card["oracle_id"], card["name"]))
    for c in r["citations"]:
        conn.execute("INSERT INTO citations VALUES (?,?,?)", (rid, c.get("doc", "cr"), c.get("ref")))
    talk = " ".join(e.get("said", "") for e in load_deliberation(rid))
    body = " ".join([
        r["question"], " ".join(r.get("aliases", [])), " ".join(r.get("mechanics", [])), r["agent_summary"], r["ruling"],
        " ".join(s.get("text", "") for s in r["steps"]), " ".join(c["name"] for c in r["cards"]),
        r.get("deliberation_summary", ""), talk,
    ])
    conn.execute("INSERT INTO rulings_fts VALUES (?,?)", (rid, body))


def rule_sources(rule: dict) -> list[dict]:
    """Return the sources a rule's steps cite, leaving out stipulations."""
    return [st["source"] for st in rule.get("steps", []) if isinstance(st.get("source"), dict)]


def index_rule(conn: sqlite3.Connection, rule: dict) -> None:
    """Index a rule a challenge introduced (or a house rule a refuted one kept), by text, card and rule.

    Args:
        conn: The search index.
        rule: The rule file's contents.
    """
    rid = rule["id"]
    conn.execute(
        "INSERT OR REPLACE INTO rulings VALUES (?,?,?,?,?,?,?,?,?,?)",
        (rid, "rule", 5, RANK[("rule", 5)] + (1 if rule.get("house_rule") else 0), rule["state"], None, None,
         "challenge", rule.get("introduced", {}).get("time"), json.dumps(rule, ensure_ascii=False)),
    )
    for src in rule_sources(rule):
        if src.get("doc") == "oracle":
            conn.execute("INSERT INTO ruling_cards VALUES (?,?,?)", (rid, None, src.get("ref")))
        conn.execute("INSERT INTO citations VALUES (?,?,?)", (rid, src.get("doc", "cr"), src.get("ref")))
    body = " ".join([rule["rule"], " ".join(rule.get("applies_when", [])), rule.get("challenges", ""),
                     " ".join(f["text"] for f in rule.get("facts", [])),
                     " ".join(st.get("conclusion", "") for st in rule.get("steps", [])),
                     " ".join(s.get("ref", "") for s in rule_sources(rule))])
    conn.execute("INSERT INTO rulings_fts VALUES (?,?)", (rid, body))


def live_rules() -> list[dict]:
    """Return the rules search shows: current, or stale and reopened (flagged as unconfirmed)."""
    rules = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(paths.rules().glob("*.json"))]
    return [r for r in rules if r.get("state") in ("current", "stale", "reopened")]


def reindex_rules() -> None:
    """Bring the index's rules up to date with rules/, without rebuilding the official rulings."""
    if not paths.index().exists():
        return
    conn = connect()
    for table, column in (("rulings", "id"), ("ruling_cards", "ruling_id"), ("citations", "ruling_id"), ("rulings_fts", "id")):
        conn.execute(f"DELETE FROM {table} WHERE {column} LIKE 'challenge-%' OR {column} LIKE 'house-challenge-%'")
    for rule in live_rules():
        index_rule(conn, rule)
    conn.commit()
    conn.close()


def legacy_rulings() -> list[dict]:
    """Return the rulings written by the retired `record` that haven't been migrated: everything but house rules."""
    rulings = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(paths.rulings().glob("*.json"))]
    return [r for r in rulings if not (r.get("kind") == "reviewed" and r.get("house_rule"))]


def official_id(row: dict) -> str:
    """Give an official ruling a stable id: its source and a hash of its card, date and text.

    Scryfall's rulings have no id of their own, and the id must stay the same across downloads.
    """
    key = f"{row['oracle_id']}|{row['published_at']}|{row['comment']}"
    return f"{row['source']}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"


def index_official(conn: sqlite3.Connection, data: bytes) -> int:
    """Replace the index's official rulings with those in a Scryfall bulk rulings file.

    Rulings with source wotc load as level 1, source scryfall as level 4.

    Args:
        conn: The search index.
        data: The bulk file: a JSON array or JSON lines, gzipped or not.

    Returns:
        How many rulings were indexed.
    """
    conn.execute("DELETE FROM rulings WHERE source IN ('wotc', 'scryfall')")
    conn.execute("DELETE FROM rulings_fts WHERE id LIKE 'wotc-%' OR id LIKE 'scryfall-%'")
    count = 0
    text = gzip.decompress(data).decode("utf-8") if data[:2] == b"\x1f\x8b" else data.decode("utf-8")
    rows = json.loads(text) if text.lstrip().startswith("[") else (json.loads(line) for line in text.splitlines() if line.strip())
    for row in rows:
        rid = official_id(row)
        level = 1 if row["source"] == "wotc" else 4
        conn.execute(
            "INSERT OR REPLACE INTO rulings VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, "official", level, RANK[("official", level)], "current", None, row["oracle_id"], row["source"],
             row["published_at"], json.dumps(row, ensure_ascii=False)),
        )
        conn.execute("INSERT INTO rulings_fts VALUES (?,?)", (rid, row["comment"]))
        count += 1
    return count


def rebuild_index() -> tuple[int, int]:
    """Throw the index away and rebuild it from the record and the current official rulings.

    Card names learned earlier are carried over, since they can't be rebuilt without Scryfall.

    Returns:
        (official rulings indexed, the user's house rules and rules indexed).
    """
    names = {}
    if paths.index().exists():
        old = sqlite3.connect(paths.index())
        try:
            names = dict(old.execute("SELECT oracle_id, name FROM card_names"))
        except sqlite3.DatabaseError:
            pass
        old.close()
        paths.index().unlink()
    conn = connect()
    conn.executemany("INSERT OR REPLACE INTO card_names VALUES (?,?)", names.items())
    official = 0
    current = load_manifest().get("scryfall_rulings")
    if current and (paths.objects() / current).exists():
        official = index_official(conn, (paths.objects() / current).read_bytes())
    user = 0
    # Of the rulings from before challenges, only house rules are still the user's; the rest wait for `migrate`.
    for path in sorted(paths.rulings().glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        if r.get("kind") == "reviewed" and r.get("house_rule"):
            index_user_ruling(conn, r)
            user += 1
    for rule in live_rules():
        index_rule(conn, rule)
        user += 1
    conn.commit()
    conn.close()
    if legacy_rulings():
        print(f"[{len(legacy_rulings())} ruling(s) from the retired `judge.py record` aren't searched any more. "
              "Run: python scripts/judge.py migrate]", file=sys.stderr)
    return official, user


# --- rendering -------------------------------------------------------------------------------


def card_name(conn: sqlite3.Connection, oracle_id: str | None) -> str | None:
    """Return the card name the index knows for an Oracle ID, or None."""
    if not oracle_id:
        return None
    row = conn.execute("SELECT name FROM card_names WHERE oracle_id = ?", (oracle_id,)).fetchone()
    return row[0] if row else None


def attrs(**kw) -> str:
    """Format keyword arguments as XML attributes, quoted and escaped, leaving out None."""
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in kw.items() if v is not None)


def render_agent(r: dict, conn: sqlite3.Connection | None = None, with_deliberation: bool = False) -> str:
    """Render one ruling as XML for Claude: quotes before reasoning, empty fields left out.

    Args:
        r: An official ruling, a rule, or one of the user's rulings.
        conn: The search index, to name an official ruling's card; None leaves the Oracle ID instead.
        with_deliberation: Include the ruling's deliberation log.

    Returns:
        The XML.
    """
    if r.get("kind") == "official":
        name = card_name(conn, r.get("oracle_id")) if conn else None
        # The Oracle ID is only shown when the card's name isn't known: it's noise to the reader otherwise.
        return (f"<ruling {attrs(id=r['id'], kind='official', level=r['level'], source=r['source'], card=name, oracle_id=None if name else r.get('oracle_id'), published=r.get('published_at'))}>"
                f"{escape(r['comment'])}</ruling>")
    if r.get("kind") == "rule":
        return render_rule(r)
    out = [f"<ruling {attrs(id=r['id'], type=r['question_type'], kind=r['kind'], level=r['level'], confidence=r['confidence'], house_rule=str(r.get('house_rule', False)).lower(), sources_changed=str(r['status'] == 'needs-recheck').lower())}>"]
    out.append(f"  <question>{escape(r['question'])}</question>")
    out.append(f"  <summary>{escape(r['agent_summary'])}</summary>")
    out.append("  <applies_when>" + "".join(f"<fact>{escape(a['fact'])}</fact>" for a in r["applies_when"]) + "</applies_when>")
    if r["ask_if_unknown"]:
        out.append("  <ask_if_unknown>" + "".join(f"<question>{escape(q)}</question>" for q in r["ask_if_unknown"]) + "</ask_if_unknown>")
    if r["answer_changes_if"]:
        out.append("  <answer_changes_if>" + "".join(f"<case {attrs(**{'if': c.get('if', '')})}>{escape(c.get('then', ''))}</case>" for c in r["answer_changes_if"]) + "</answer_changes_if>")
    if r["misconceptions"]:
        out.append("  <misconceptions>" + "".join(f"<wrong {attrs(why=m.get('why_wrong', ''))}>{escape(m.get('wrong', ''))}</wrong>" for m in r["misconceptions"]) + "</misconceptions>")
    out.append("  <citations>" + "".join(
        f"<quote {attrs(id=c['id'], doc=c.get('doc', 'cr'), ref=c.get('ref'), level=c.get('level'))}>{escape(c.get('excerpt', ''))}</quote>" for c in r["citations"]) + "</citations>")
    out.append("  <steps>" + "".join(f"<step {attrs(n=i, refs=' '.join(s.get('refs', [])))}>{escape(s.get('text', ''))}</step>" for i, s in enumerate(r["steps"], 1)) + "</steps>")
    out.append(f"  <ruling_text>{escape(r['ruling'])}</ruling_text>")
    if r.get("outcome"):
        out.append(f"  <outcome>{escape(json.dumps(r['outcome'], ensure_ascii=False))}</outcome>")
    if r.get("deliberation_summary"):
        out.append(f"  <deliberation_summary>{escape(r['deliberation_summary'])}</deliberation_summary>")
    if with_deliberation:
        out.append("  <deliberation>" + "".join(
            f"<entry {attrs(by=e.get('by'), at=e.get('at'), decision=e.get('decision'))}>{escape(e.get('said', ''))}</entry>" for e in load_deliberation(r["id"])) + "</deliberation>")
    out.append("</ruling>")
    return "\n".join(out)


def render_rule(r: dict) -> str:
    """Render a rule introduced by challenge as XML for Claude.

    A rule is unconfirmed (sources_changed="true") while its challenge runs again.
    """
    out = [f"<ruling {attrs(id=r['id'], kind='rule', level=5, state=r['state'], house_rule=str(r.get('house_rule', False)).lower(), sources_changed=str(r['state'] != 'current').lower())}>"]
    out.append(f"  <rule>{escape(r['rule'])}</rule>")
    out.append("  <applies_when>" + "".join(f"<fact>{escape(a)}</fact>" for a in r.get("applies_when", [])) + "</applies_when>")
    out.append(f"  <challenged>{escape(r.get('challenges', ''))}</challenged>")
    if r.get("stipulations"):
        # The part of the rule no official source says: what the judges agreed to adopt.
        out.append("  <stipulations>" + "".join(f"<stipulation>{escape(t)}</stipulation>" for t in r["stipulations"]) + "</stipulations>")
    out.append("  <steps>" + "".join(
        f"<step {attrs(n=st['id'], premises=' '.join(st.get('premises', [])), doc=(st.get('source') or {}).get('doc'), ref=(st.get('source') or {}).get('ref'))}>"
        f"{escape((st.get('source') or {}).get('excerpt', ''))} → {escape(st.get('conclusion', ''))}</step>" for st in r.get("steps", [])) + "</steps>")
    op = r.get("opinion")
    if op:
        out.append(f"  <opinion {attrs(author=op['author'], revision=op['revision'])}>")
        out.append(f"    <holding>{escape(op['holding'])}</holding>")
        out.append("    <reasoning>" + "".join(
            f"<step {attrs(n=st['id'], doc=(st.get('source') or {}).get('doc'), ref=(st.get('source') or {}).get('ref'), stipulation='true' if st.get('stipulation') else None)}>"
            f"{escape((st.get('source') or {}).get('excerpt', ''))} → {escape(st.get('conclusion', ''))}</step>" for st in op["steps"]) + "</reasoning>")
        out.append("    <joined>" + "".join(
            f"<judge {attrs(n=j['judge'])}>{escape(j['reason'])}</judge>" for j in op.get("joined", [])) + "</joined>")
        for tag, key in (("concurrence", "concurrences"), ("dissent", "dissents")):
            out += [f"    <{tag} {attrs(judge=j['judge'], revision=j['revision'])}>{escape(j['reason'])}</{tag}>" for j in op.get(key, [])]
        out.append("  </opinion>")
    how = ("kept as a house rule after its challenge was refuted" if r.get("house_rule")
           else "introduced by an opinion of the court that all five judges joined")
    out.append(f"  <provenance>{escape(how)}; python scripts/challenge.py trace {escape(r['challenge'])}</provenance>")
    out.append("</ruling>")
    return "\n".join(out)


def render_plain(r: dict, conn: sqlite3.Connection | None = None) -> str:
    """Render one ruling as a short plain-text entry for people.

    Args:
        r: An official ruling, a rule, or one of the user's rulings.
        conn: The search index, to name an official ruling's card.

    Returns:
        The id and kind on one line, then the ruling.
    """
    if r.get("kind") == "rule":
        flag = "" if r["state"] == "current" else f" [{r['state']}: unconfirmed]"
        return f"[{r['id']}] {'house rule' if r.get('house_rule') else 'rule'}{flag}\n  {r['rule']}"
    if r.get("kind") == "official":
        name = (card_name(conn, r.get("oracle_id")) if conn else None) or f"oracle_id {r.get('oracle_id')}"
        return f"[{r['id']}] official ({r['source']}, {r.get('published_at')}) {name}\n  {r['comment']}"
    flag = " [needs recheck]" if r["status"] == "needs-recheck" else ""
    return f"[{r['id']}] {r['kind']} {r['question_type']}, {r['confidence']}{flag}\n  Q: {r['question']}\n  A: {r['ruling']}"


# --- commands --------------------------------------------------------------------------------


def cmd_build(args) -> int:
    """Run `build`: set up the record, download the official rulings if they changed, and rebuild the index.

    The record is tagged with the CR's effective date, so it can be read as of a CR version.

    Args:
        args: The parsed command line: rulings_file and force.

    Returns:
        The exit status.

    Raises:
        SystemExit: Via die() when offline without --rulings-file.
    """
    ensure_home()
    manifest = load_manifest()
    if args.rulings_file:
        data = Path(args.rulings_file).read_bytes()
        info = {"kind": "scryfall-rulings", "source": str(args.rulings_file), "updated_at": None}
    else:
        if OFFLINE:
            die("Offline: pass --rulings-file to build from a local copy.")
        meta = http_json(f"{API}/bulk-data/rulings")
        current = manifest.get("scryfall_rulings")
        if current and manifest["objects"].get(current, {}).get("updated_at") == meta.get("updated_at") and not args.force:
            print(f"Official rulings are current (Scryfall {meta.get('updated_at')}).")
            data, info = None, None
        else:
            url = meta.get("download_uri") or meta.get("jsonl_download_uri")
            print(f"Downloading Scryfall's bulk rulings ({meta.get('updated_at')})...")
            data = http_bytes(url)
            info = {"kind": "scryfall-rulings", "source": url, "updated_at": meta.get("updated_at")}
    if data is not None:
        digest = store_object(data)
        info["downloaded_at"] = now()
        info["bytes"] = len(data)
        manifest["objects"][digest] = info
        manifest["scryfall_rulings"] = digest
        save_manifest(manifest)
        commit(f"Official rulings: Scryfall bulk file {info.get('updated_at') or 'from ' + info['source']}\n\n"
               f"Object {digest[:12]}, {len(data)} bytes. Rulings with source wotc load as level 1, source scryfall as level 4.",
               drafted_by="judge")
    eff = cr_effective()
    if eff and paths.cr_file().exists():
        tag = "cr-" + datetime.strptime(eff, "%B %d, %Y").strftime("%Y-%m-%d")
        if not git("tag", "--list", tag).stdout.strip():
            git("tag", "-a", tag, "-m", f"Rulings as of the Comprehensive Rules effective {eff}")
    official, user = rebuild_index()
    print(f"Index built: {official} official rulings, {user} of your rulings. Record: {paths.home()}")
    return 0


def cmd_index(args) -> int:
    """Run `index`: rebuild the search index from the record.

    Args:
        args: The parsed command line (unused).

    Returns:
        The exit status.
    """
    ensure_home()
    official, user = rebuild_index()
    print(f"Index rebuilt: {official} official rulings, {user} of your rulings.")
    return 0


def fts_query(text: str, mode: str) -> str | None:
    """Turn free text into an FTS5 query of quoted words.

    Only word characters are kept, and each word is quoted, so a word like NOT or NEAR isn't read as an operator.

    Args:
        text: The search text.
        mode: How to join the words: "AND" or "OR".

    Returns:
        The query, or None when the text has no words.
    """
    words = re.findall(r"\w+", text.lower())
    if not words:
        return None
    return f" {mode} ".join(f'"{w}"' for w in words)


def cmd_search(args) -> int:
    """Run `search`: find rulings by text, card and cited rule, most authoritative first.

    Cards and rules narrow the candidates; text ranks them. When no ruling has every word, the closest
    matches on any word are shown instead, ranked by relevance, with a warning.

    Args:
        args: The parsed command line: text, card, rule, type, limit, agent and full.

    Returns:
        0 when some ruling matches, 1 otherwise.

    Raises:
        SystemExit: Via die() when there is no index yet.
    """
    if not paths.index().exists():
        die("No index yet. Run: python scripts/judge.py build")
    conn = connect()
    oracle_ids, by_name = set(), set()
    for name in args.card:
        # Rules quote cards by name.
        by_name |= {r[0] for r in conn.execute("SELECT ruling_id FROM ruling_cards WHERE lower(name) = lower(?)", (name,))}
        row = conn.execute("SELECT oracle_id FROM card_names WHERE lower(name) = lower(?)", (name,)).fetchone()
        if row:
            oracle_ids.add(row[0])
            continue
        found = resolve_card(name)
        if not found:
            print(f"(Couldn't resolve card '{name}' on Scryfall; searching by text instead.)", file=sys.stderr)
            args.text = (args.text or "") + " " + name
            continue
        conn.execute("INSERT OR REPLACE INTO card_names VALUES (?,?)", (found["oracle_id"], found["name"]))
        oracle_ids.add(found["oracle_id"])
    conn.commit()

    candidates = None
    if oracle_ids:
        marks = ",".join("?" * len(oracle_ids))
        candidates = {r[0] for r in conn.execute(f"SELECT id FROM rulings WHERE oracle_id IN ({marks})", tuple(oracle_ids))}
        candidates |= {r[0] for r in conn.execute(f"SELECT ruling_id FROM ruling_cards WHERE oracle_id IN ({marks})", tuple(oracle_ids))}
    if by_name:
        candidates = (candidates or set()) | by_name
    for ref in args.rule:
        hits = {r[0] for r in conn.execute("SELECT ruling_id FROM citations WHERE ref = ? OR ref LIKE ?", (ref, ref + "%"))}
        candidates = hits if candidates is None else candidates & hits

    scores, loose = {}, False
    if args.text and args.text.strip():
        for mode in ("AND", "OR"):
            q = fts_query(args.text, mode)
            rows = conn.execute("SELECT id, bm25(rulings_fts) FROM rulings_fts WHERE rulings_fts MATCH ? ORDER BY bm25(rulings_fts) LIMIT 500", (q,)).fetchall()
            if candidates is not None:
                rows = [r for r in rows if r[0] in candidates]
            if rows and mode == "OR":
                # No ruling has every word. Keep only the close matches (bm25 is negative; lower is better),
                # so a search doesn't fill up with rulings that share one common word.
                best = rows[0][1]
                rows = [r for r in rows if r[1] <= best * 0.6]
                loose = True
            if rows:
                scores = dict(rows)
                break
        ids = set(scores)
    else:
        ids = candidates or set()
    if ids and args.type:
        marks = ",".join("?" * len(ids))
        ids = {r[0] for r in conn.execute(f"SELECT id FROM rulings WHERE id IN ({marks}) AND question_type = ?", (*ids, args.type))}
    if not ids:
        print("No rulings match.")
        return 1

    marks = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT id, rank, json, oracle_id, source, level, kind, published_at FROM rulings WHERE id IN ({marks})", tuple(ids)).fetchall()
    # A text search ranks by relevance first when only some words matched; otherwise by authority first.
    rows.sort(key=(lambda r: (scores.get(r[0], 0), r[1])) if loose else (lambda r: (r[1], scores.get(r[0], 0))))
    if loose:
        print("[No ruling has every word; these are the closest. Check each one fits before relying on it.]\n")
    shown = rows[: args.limit]
    for r in shown:
        data = json.loads(r[2])
        if r[6] == "official":
            data = {**data, "id": r[0], "kind": "official", "level": r[5], "oracle_id": r[3], "source": r[4]}
        if args.agent and r[6] not in ("official", "rule") and not args.full:
            # A user ruling is long; list it briefly, and `show` prints the one that fits.
            print(f"<ruling {attrs(id=data['id'], type=data['question_type'], kind=data['kind'], level=data['level'], confidence=data['confidence'], sources_changed=str(data['status'] == 'needs-recheck').lower())}>"
                  f"<question>{escape(data['question'])}</question><summary>{escape(data['agent_summary'])}</summary></ruling>")
        else:
            print(render_agent(data, conn) if args.agent else render_plain(data, conn))
        print()
    if args.agent and not args.full and any(r[6] not in ("official", "rule") for r in shown):
        print("[Your rulings are listed briefly. For one that may fit: judge.py show <id> --agent]")
    if len(rows) > len(shown):
        print(f"[{len(rows) - len(shown)} more; raise --limit or narrow the search]")
    return 0


RETIRED = ("Retired: nothing the skill answers is stored any more. A rule enters the record only through a "
           "challenge; read CHALLENGE.md (python scripts/challenge.py). Rulings recorded before are moved with: "
           "python scripts/judge.py migrate")


def cmd_retired(args) -> int:
    """Refuse a retired command (record, discuss, review) and say what replaced it.

    Args:
        args: The parsed command line: command.

    Raises:
        SystemExit: Always, with status 2.
    """
    die(f"judge.py {args.command}: {RETIRED}", code=2)


def cmd_migrate(args) -> int:
    """Run `migrate`: move the rulings the retired `record` wrote out of the searched record.

    A reviewed ruling becomes an open challenge carrying its deliberation (it must pass a panel to
    become a rule); an unreviewed one, the model's own answer, is set aside; house rules stay as they are.

    Args:
        args: The parsed command line (unused).

    Returns:
        The exit status.
    """
    ensure_home()
    import challenge  # noqa: PLC0415  (challenge.py imports this module)

    done = []
    for r in legacy_rulings():
        rid = r["id"]
        entries = load_deliberation(rid)
        if r.get("kind") == "reviewed":
            said = next((e["said"] for e in reversed(entries) if e.get("by") == "user" and e.get("decision") == "reviewed"), "")
            statement = f"{said} (Reviewed ruling {rid}: {r['question']} {r['ruling']})".strip()
            cid, _ = challenge.propose(None, "user", {
                "type": "open", "statement": statement, "panel": "independent",
                "migrated_from": {"ruling": r, "deliberation": entries}}, f"Open from reviewed ruling {rid}", words=said or None)
            dest, outcome = paths.home() / "rulings-migrated", f"now challenge {cid}"
        else:
            dest, outcome = paths.home() / "rulings-retired", "set aside (unreviewed)"
        dest.mkdir(exist_ok=True)
        ruling_path(rid).replace(dest / f"{rid}.json")
        talk = paths.deliberation() / f"{rid}.jsonl"
        if talk.exists():
            talk.replace(dest / f"{rid}.jsonl")
        done.append(f"- {rid}: {outcome}")
    if not done:
        print("Nothing to migrate.")
        return 0
    commit("Migrate rulings from the retired `judge.py record`\n\n" + "\n".join(done), drafted_by="judge")
    rebuild_index()
    print("\n".join(done))
    return 0


def cmd_show(args) -> int:
    """Run `show`: print one rule, ruling of the user's, or official ruling, looked for in that order.

    Args:
        args: The parsed command line: id, agent and deliberation.

    Returns:
        The exit status.

    Raises:
        SystemExit: Via die() when no ruling has that id.
    """
    rule = paths.rules() / f"{args.id}.json"
    if rule.exists():
        r = json.loads(rule.read_text(encoding="utf-8"))
        print(render_agent(r) if args.agent else json.dumps(r, indent=2, ensure_ascii=False))
        return 0
    if ruling_path(args.id).exists():
        r = load_ruling(args.id)
        conn = connect() if paths.index().exists() else None
        if args.agent:
            print(render_agent(r, conn, with_deliberation=args.deliberation))
        else:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            if args.deliberation:
                for e in load_deliberation(r["id"]):
                    print(json.dumps(e, ensure_ascii=False))
        return 0
    if paths.index().exists():
        conn = connect()
        row = conn.execute("SELECT json, oracle_id, source, level FROM rulings WHERE id = ?", (args.id,)).fetchone()
        if row:
            data = {**json.loads(row[0]), "id": args.id, "kind": "official", "oracle_id": row[1], "source": row[2], "level": row[3]}
            print(render_agent(data, conn) if args.agent else render_plain(data, conn))
            return 0
    die(f"No ruling {args.id}.")


def cmd_recheck(args) -> int:
    """Run `recheck`: flag rulings whose cited text changed, and reopen rules whose sources changed.

    Args:
        args: The parsed command line: offline, which checks document citations only and skips Oracle text.

    Returns:
        The exit status.

    Raises:
        SystemExit: Via die() when the CR isn't downloaded.
    """
    ensure_home()
    rules = cr_rules()
    changed = []
    for path in sorted(paths.rulings().glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        reasons = []
        for c in r["citations"]:
            doc = c.get("doc", "cr")
            if doc == "cr":
                text = rules.get(c["ref"])
            elif doc in lookup.DOCS and (paths.docs_dir() / f"{doc}.json").exists():
                # Find the section by its heading first: numbers shift when sections are added.
                section = (lookup.doc_section(doc, c["heading"]) if c.get("heading") else None) or lookup.doc_section(doc, c["ref"])
                text = section["text"] if section else None
            else:
                continue
            if text is None:
                reasons.append(f"{doc.upper()} {c['ref']} no longer exists")
            elif sha256_text(text) != c.get("text_sha256"):
                reasons.append(f"{doc.upper()} {c['ref']} changed")
        if not args.offline and not OFFLINE:
            for card in r["cards"]:
                found = resolve_card(card["name"])
                if found and card.get("oracle_sha256") and found["oracle_sha256"] != card["oracle_sha256"]:
                    reasons.append(f"Oracle text of {card['name']} changed")
        if reasons and r["status"] != "needs-recheck":
            r["status"] = "needs-recheck"
            r["recheck_reasons"] = reasons
            r["updated_at"] = now()
            save_ruling(r)
            changed.append((r["id"], reasons))
    if changed:
        lines = "\n".join(f"- {rid}: {'; '.join(why)}" for rid, why in changed)
        commit(f"Recheck: {len(changed)} ruling(s) need review\n\n{lines}\n\nAgainst CR {cr_effective() or 'unknown'}.", drafted_by="judge")
        print(f"{len(changed)} ruling(s) marked needs-recheck:\n{lines}")
    reopened = []
    if any(paths.rules().glob("challenge-*.json")):
        import challenge  # noqa: PLC0415  (challenge.py imports this module)
        reopened = challenge.recheck_rules(offline=args.offline or OFFLINE)
        for rid, why, cid in reopened:
            print(f"Rule {rid} is stale ({'; '.join(why)}); it must win its challenge again: {cid} is open")
    if changed or reopened:
        rebuild_index()
    else:
        print("All rulings and rules still match their sources.")
    for rule in live_rules():
        if rule["state"] != "current" and rule["id"] not in {rid for rid, _, _ in reopened}:
            print(f"Rule {rule['id']} is still unconfirmed: its challenge {rule.get('reopened_by')} is running again.")
    return 0


# --- sync: the optional remote store (experimental) -------------------------------------------------
#
# Local only is the default. With an endpoint set, a RustFS bucket the user chooses holds a synced copy:
# record/<device>.bundle is each device's whole git history. The local record stays the working copy; sync
# merges the other devices' bundles in (never rebases, so commits and their trailers keep one identity) and
# uploads this device's. No two devices write the same key, so no locking is needed.



def load_config() -> dict | None:
    """Read the store settings, with BISHOP_AND_BARRISTER_S3_ENDPOINT / _S3_BUCKET overriding the file.

    Returns:
        The settings, or None when no endpoint and bucket are set (local only).

    Raises:
        OSError: When config.json can't be read.
        ValueError: When config.json isn't JSON.
    """
    cfg = json.loads(paths.config().read_text(encoding="utf-8")) if paths.config().exists() else {}
    for key in ("endpoint", "bucket"):
        if os.environ.get(f"BISHOP_AND_BARRISTER_S3_{key.upper()}"):
            cfg[key] = os.environ[f"BISHOP_AND_BARRISTER_S3_{key.upper()}"]
    return cfg if cfg.get("endpoint") and cfg.get("bucket") else None


class SyncStop(Exception):
    """Syncing can't go on until the user acts: no keys, a public bucket, or a conflict to settle."""


def store_client(cfg: dict, timeout: float = 60) -> s3.S3:
    """Make a client for the remote store.

    Args:
        cfg: The store settings, from load_config().
        timeout: Seconds to wait for the server on each request.

    Returns:
        The client.

    Raises:
        SyncStop: When there are no keys.
        ValueError: When the endpoint fails s3.check_endpoint().
    """
    keys = s3.credentials(cfg.get("profile"))
    if not keys:
        raise SyncStop("No keys for the store. Set BISHOP_AND_BARRISTER_S3_ACCESS_KEY and "
                       "BISHOP_AND_BARRISTER_S3_SECRET_KEY, or a profile in ~/.aws/credentials (--profile). "
                       "Keys never go in config.json.")
    return s3.S3(cfg["endpoint"], cfg["bucket"], *keys, region=cfg.get("region", "us-east-1"),
                 addressing=cfg.get("addressing", "path"), timeout=timeout)


def device_name(name: str | None = None) -> str:
    """Make a device name safe for a store key: the name given, or the host name, as a slug."""
    name = re.sub(r"[^a-z0-9-]+", "-", (name or socket.gethostname()).lower()).strip("-")
    return name or "device"


def refuse_if_public(client: s3.S3, key: str | None = None) -> None:
    """Stop if anyone without keys can list the bucket or read the key.

    A public bucket would republish Scryfall's and Wizards' files and expose the user's rulings.

    Args:
        client: The store client.
        key: An object to try reading anonymously too, or None to check only listing.

    Raises:
        SyncStop: When the bucket or the key is readable without keys.
    """
    found = client.anonymous_access(key)
    if found:
        raise SyncStop(f"Stopped: anyone without keys can {' and '.join(found)} in bucket {client.bucket!r}. Make "
                       "the bucket private (no anonymous access), then sync again. A public bucket would expose "
                       "your rulings and republish Scryfall's and Wizards' files, which their terms forbid.")


def cmd_sync(args) -> int:
    """Run `sync`: set up the remote store with --setup, or sync with it now.

    Args:
        args: The parsed command line: setup, and the --setup options.

    Returns:
        The exit status.
    """
    ensure_home()
    return sync_setup(args) if args.setup else sync_now()


def sync_setup(args) -> int:
    """Check a remote store and save its settings.

    Nothing is saved unless the keys can list the bucket and the bucket is private.

    Args:
        args: The parsed command line: endpoint, bucket, region, addressing, device, profile and create.

    Returns:
        The exit status.

    Raises:
        SystemExit: Via die() when the settings are incomplete or the store fails a check.
    """
    if not args.endpoint or not args.bucket:
        die("--setup needs --endpoint and --bucket.")
    try:
        endpoint = s3.check_endpoint(args.endpoint)
    except ValueError as err:
        die(f"Not saved: {err}.")
    cfg = {"endpoint": endpoint, "bucket": args.bucket, "region": args.region, "addressing": args.addressing,
           "device": device_name(args.device)}
    if args.profile:
        cfg["profile"] = args.profile
    try:
        client = store_client(cfg)
        if not client.bucket_exists():
            if not args.create:
                die(f"Bucket {args.bucket!r} doesn't exist at {endpoint}. Add --create to create it.")
            client.create_bucket()
            print(f"Created bucket {args.bucket!r}.")
        others = client.keys("record/")  # proves the keys can list, not just reach the server
        refuse_if_public(client)
    except SyncStop as err:
        die(f"Not saved. {err}")
    except s3.S3Error as err:
        die(f"Not saved: {endpoint} refused the request ({err}). Check the endpoint, bucket and keys.")
    except OSError as err:
        die(f"Not saved: couldn't reach {endpoint} ({err}).")
    paths.config().write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    devices = [o["key"][len("record/"):-len(".bundle")] for o in others if o["key"].endswith(".bundle")]
    print(f"Saved {paths.config()}: {endpoint}, bucket {args.bucket!r}, this device {cfg['device']!r}.")
    print(f"The bucket is private. Devices already syncing there: {', '.join(devices) or 'none'}.")
    server = client.server()
    print(f"Server: {server}. Make sure it's RustFS 1.0.4 or later." if server else
          "The server doesn't report its version: make sure it's RustFS 1.0.4 or later.")
    print("Mode: local plus a remote store. The local record stays the working copy. It syncs by itself as the "
          "skill is used; `judge.py sync` forces one now.")
    return 0


def merge_manifests(ours: dict, theirs: dict) -> dict:
    """Merge two devices' manifests.

    Both devices downloaded their own Scryfall file: keep every object, and the newest bulk file.

    Args:
        ours: This device's manifest.
        theirs: The other device's manifest.

    Returns:
        The merged manifest.
    """
    merged = {**ours, "objects": {**theirs.get("objects", {}), **ours.get("objects", {})}}
    candidates = [h for h in (ours.get("scryfall_rulings"), theirs.get("scryfall_rulings")) if h]
    if candidates:
        merged["scryfall_rulings"] = max(candidates, key=lambda h: merged["objects"].get(h, {}).get("updated_at") or "")
    return merged


def merge_device(device: str, ref: str) -> bool:
    """Merge one device's history in.

    Conflicts in the manifest and .gitignore, which two records started apart both have, are merged
    mechanically. Any other conflict is aborted, leaving nothing half-done, for a person to settle.

    Args:
        device: The other device's name, for messages.
        ref: The fetched branch to merge.

    Returns:
        True when the history was merged.

    Raises:
        SyncStop: On a conflict a person must settle.
    """
    result = git("merge", "--no-edit", "--allow-unrelated-histories", "-m", f"Sync: merge {device}\n\nDrafted-by: judge",
                 ref, check=False)
    if result.returncode == 0:
        return True
    conflicted = git("diff", "--name-only", "--diff-filter=U").stdout.split()
    # Two records started apart each have their own manifest and .gitignore; those merge mechanically.
    if conflicted and set(conflicted) <= {"sources/manifest.json", ".gitignore"}:
        if "sources/manifest.json" in conflicted:
            ours = json.loads(git("show", ":2:sources/manifest.json").stdout)
            theirs = json.loads(git("show", ":3:sources/manifest.json").stdout)
            save_manifest(merge_manifests(ours, theirs))
        if ".gitignore" in conflicted:
            lines = []
            for stage in (":2:.gitignore", ":3:.gitignore"):
                lines += [l for l in git("show", stage).stdout.splitlines() if l and l not in lines]
            (paths.home() / ".gitignore").write_text("".join(f"{l}\n" for l in lines), encoding="utf-8")
        git("add", *conflicted)
        subprocess.run(["git", "-C", str(paths.home()), "commit", "-q", "--no-edit"], check=True, capture_output=True)
        return True
    git("merge", "--abort", check=False)
    raise SyncStop(f"Sync stopped: {device} changed the same ruling(s) as this device: {', '.join(conflicted)}. "
                   f"Nothing was merged or uploaded. Settle it with the user: compare `git -C {paths.home()} diff HEAD {ref}`, "
                   "edit the ruling to the version they choose, then run `judge.py sync` again.")


def load_state() -> dict:
    """Read this device's sync state: the bundle ETags it has merged, what it last uploaded, and when it last pulled."""
    return json.loads(paths.sync_state().read_text(encoding="utf-8")) if paths.sync_state().exists() else {"fetched": {}}


def save_state(state: dict) -> None:
    """Write this device's sync state."""
    paths.sync_state().write_text(json.dumps(state, indent=2), encoding="utf-8")


def remote_bundles(client: s3.S3) -> dict:
    """List each device syncing through the store, with its bundle's ETag.

    Raises:
        s3.S3Error: When the listing fails.
    """
    return {o["key"][len("record/"):-len(".bundle")]: o["etag"] for o in client.keys("record/")
            if o["key"].endswith(".bundle")}


def pull(client: s3.S3, device: str, state: dict, remote: dict) -> list[str]:
    """Merge in every other device whose bundle changed since the last pull.

    Tags the record lacks are copied too, and the index is rebuilt if anything was merged.

    Args:
        client: The store client.
        device: This device's name, whose own bundle is skipped.
        state: The sync state; updated with each bundle merged.
        remote: Each device's bundle ETag, from remote_bundles().

    Returns:
        The devices merged.

    Raises:
        SyncStop: On a conflict a person must settle.
        s3.S3Error: When a download fails.
    """
    ensure_identity()
    merged = []
    for other, etag in sorted(remote.items()):
        if other == device or state["fetched"].get(other) == etag:
            continue  # our own copy, or nothing new since the last sync
        data = client.get(f"record/{other}.bundle")
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / f"{other}.bundle"
            bundle.write_bytes(data)
            git("fetch", "-q", "--no-tags", str(bundle), f"+refs/heads/*:refs/remotes/{other}/*")
            git("fetch", "-q", "--no-tags", str(bundle), f"+refs/tags/*:refs/remotes/{other}/tags/*", check=False)
        for ref in git("for-each-ref", "--format=%(refname)", f"refs/remotes/{other}/").stdout.split():
            if "/tags/" in ref:
                tag = ref.rsplit("/tags/", 1)[1]
                if not git("tag", "--list", tag).stdout.strip():
                    git("tag", tag, ref)  # each device tags its own CR installs; keep only names we lack
            else:
                merge_device(other, ref)
        merged.append(other)
        state["fetched"][other] = etag
    if merged:
        rebuild_index()
    return merged


def push(client: s3.S3, device: str, state: dict, remote: dict | None = None) -> bool:
    """Upload this device's bundle if its history moved since the last upload.

    Args:
        client: The store client.
        device: This device's name.
        state: The sync state; updated with the head uploaded.
        remote: Each device's bundle ETag; when given, a bundle missing from it is uploaded even if the head hasn't moved.

    Returns:
        Whether it uploaded.

    Raises:
        s3.S3Error: When the upload fails.
    """
    head = git("rev-parse", "HEAD").stdout.strip()
    if state.get("uploaded_head") == head and (remote is None or device in remote):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "record.bundle"
        git("bundle", "create", "-q", str(bundle), "--all")
        client.put(f"record/{device}.bundle", bundle.read_bytes())
    state["uploaded_head"] = head
    return True


def sync_now() -> int:
    """Sync fully now, whatever the throttle says, reporting every problem (`judge.py sync`).

    Returns:
        0 when synced or local only, 1 when syncing stopped for the user to act.

    Raises:
        SystemExit: Via die() when the store refuses a request or can't be reached.
    """
    cfg = load_config()
    if not cfg:
        print("Local only: no remote store is set. To add one: judge.py sync --setup --endpoint <url> --bucket <name>")
        return 0
    device, state = cfg.get("device") or device_name(), load_state()
    try:
        client = store_client(cfg)
        refuse_if_public(client)
        remote = remote_bundles(client)
        merged = pull(client, device, state, remote)
        uploaded = push(client, device, state, remote)
        if uploaded:
            refuse_if_public(client, f"record/{device}.bundle")
    except SyncStop as err:
        save_state(state)
        print(err, file=sys.stderr)
        return 1
    except s3.S3Error as err:
        die(f"Sync failed: {err}. The local record is unchanged and still works; try again later.")
    except OSError as err:
        die(f"Sync failed: couldn't reach {cfg['endpoint']} ({err}). The local record still works offline.")
    state["pulled_at"] = time.time()
    state.pop("notice", None)
    save_state(state)
    print(f"Synced with {cfg['endpoint']} as {device!r}: "
          f"{'merged ' + ', '.join(merged) if merged else 'nothing new from other devices'}; "
          f"{'uploaded this device' if uploaded else 'nothing new to upload'}.")
    return 0


# Automatic sync: with a store set, reads pull first (at most once per interval) and writes push after.
# Neither ever stops the command: a problem is noted once on stderr, and the local record carries on.
SYNC_INTERVAL = float(os.environ.get("BISHOP_AND_BARRISTER_SYNC_INTERVAL") or 600)
AUTO_TIMEOUT = 5
READS = {"search", "show", "challenge status", "challenge show", "challenge list", "challenge trace"}
WRITES = {"build", "migrate", "recheck", "challenge open", "challenge brief", "challenge edit", "challenge confirm",
          "challenge add", "challenge verify", "challenge withdraw", "challenge resolve"}


def auto_sync(command: str) -> None:
    """Sync automatically around a command, when a store is set: pull before a read, push after a write.

    Pulls happen at most once per SYNC_INTERVAL. A problem never stops the command: it is noted once on
    stderr, and the local record carries on.

    Args:
        command: The command, as named in READS and WRITES (such as "search" or "challenge add").
    """
    if command not in READS | WRITES or os.environ.get("BISHOP_AND_BARRISTER_AUTO_SYNC") == "0":
        return
    try:
        cfg = load_config()
    except (OSError, ValueError):
        return
    if not cfg or cfg.get("auto_sync") is False or not (paths.home() / ".git").exists():
        return
    state = load_state()
    if command in READS and time.time() - state.get("pulled_at", 0) < SYNC_INTERVAL:
        return
    device = cfg.get("device") or device_name()
    try:
        client = store_client(cfg, timeout=AUTO_TIMEOUT)
        refuse_if_public(client)
        remote = remote_bundles(client)
        if command in READS:
            state["pulled_at"] = time.time()
            merged = pull(client, device, state, remote)
            if merged:
                print(f"[synced: merged rulings from {', '.join(merged)}]", file=sys.stderr)
        else:
            push(client, device, state, remote)
        state.pop("notice", None)
    except (SyncStop, s3.S3Error, OSError, subprocess.CalledProcessError) as err:
        notice = str(err) if isinstance(err, SyncStop) else f"couldn't reach the store at {cfg['endpoint']} ({err})"
        if command in READS:
            state["pulled_at"] = time.time()  # don't retry on every search; `judge.py sync` forces it
        if state.get("notice") != notice:
            print(f"[sync paused: {notice}. Working from the local record.]", file=sys.stderr)
            state["notice"] = notice
    save_state(state)


def main() -> int:
    """Run the command line, syncing with the remote store before reads and after writes when one is set.

    Returns:
        The exit status of the chosen command.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="set up the record, download official rulings, build the index")
    p.add_argument("--rulings-file", help="load official rulings from a local bulk file instead of downloading")
    p.add_argument("--force", action="store_true", help="download even if Scryfall's file hasn't changed")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("index", help="rebuild the search index from the record")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="find rulings by text, card or rule number")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--card", action="append", default=[], help="card name (repeatable)")
    p.add_argument("--rule", action="append", default=[], help="CR rule number cited (repeatable)")
    p.add_argument("--type", choices=sorted(QUESTION_TYPES),
                   help="only your rulings of this question type (official card rulings have none), e.g. tournament")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--agent", action="store_true", help="print rulings as XML for Claude")
    p.add_argument("--full", action="store_true", help="with --agent, print your rulings in full, not briefly")
    p.set_defaults(func=cmd_search)

    for retired in ("record", "discuss", "review"):
        p = sub.add_parser(retired, help="retired: a rule enters the record only through a challenge (CHALLENGE.md)")
        p.add_argument("rest", nargs=argparse.REMAINDER)
        p.set_defaults(func=cmd_retired)

    p = sub.add_parser("migrate", help="move rulings from the retired `record`: reviewed ones become challenges")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("show", help="print one ruling")
    p.add_argument("id")
    p.add_argument("--agent", action="store_true")
    p.add_argument("--deliberation", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("recheck", help="flag rulings whose cited rules or Oracle text changed")
    p.add_argument("--offline", action="store_true", help="check CR citations only")
    p.set_defaults(func=cmd_recheck)

    p = sub.add_parser("sync", help="sync the record with the remote store, if one is set (local only otherwise)")
    p.add_argument("--setup", action="store_true", help="set the remote store, after checking it")
    p.add_argument("--endpoint", help="with --setup: the RustFS URL, e.g. https://rustfs.example.net")
    p.add_argument("--bucket", help="with --setup: the bucket name")
    p.add_argument("--region", default="us-east-1", help="with --setup: the signing region (default us-east-1)")
    p.add_argument("--addressing", choices=["path", "virtual"], default="path",
                   help="with --setup: path-style (RustFS, default) or virtual-hosted (hosted S3)")
    p.add_argument("--device", help="with --setup: this device's name in the store (default: the host name)")
    p.add_argument("--profile", help="with --setup: the ~/.aws/credentials profile holding the keys")
    p.add_argument("--create", action="store_true", help="with --setup: create the bucket if it doesn't exist")
    p.set_defaults(func=cmd_sync)

    args = parser.parse_args()
    if args.command in READS:
        auto_sync(args.command)  # bring other devices' rulings in before reading
    status = args.func(args)
    if args.command in WRITES and status == 0:
        auto_sync(args.command)  # send this device's change out
    return status


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except urllib.error.URLError as err:
        if getattr(err, "code", None) == 429:
            # Scryfall's terms forbid ignoring 429s: stop rather than loop.
            print("Scryfall is still rate-limiting after waiting out its lockout. Try again in a few minutes, "
                  "not in a loop.", file=sys.stderr)
            sys.exit(1)
        print(f"Network error reaching Scryfall: {err}", file=sys.stderr)
        sys.exit(1)
