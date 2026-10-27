#!/usr/bin/env python3
"""The judge's rulings store: official rulings plus the user's own, searchable and traceable.

Everything lives in ~/.claude/bishop-and-barrister/ (or $BISHOP_AND_BARRISTER_HOME), which is a git
repository. Git is the record: every change is a commit that says what changed, why, and who drafted
or decided it. The SQLite index is only a search index, rebuilt from the record at any time. Large
downloads (Scryfall's bulk rulings) live in objects/<sha256>, outside git.

Usage:
    python scripts/judge.py build                       # set up, download official rulings, index
    python scripts/judge.py search "humility opalescence" --agent
    python scripts/judge.py search --card "Blood Artist" --rule 603.10a
    python scripts/judge.py record ruling.json          # store a new unreviewed ruling
    python scripts/judge.py discuss <id> entries.json   # add to a ruling's deliberation
    python scripts/judge.py review <id> --user-said "Yes, that's right"
    python scripts/judge.py show <id> --agent
    python scripts/judge.py recheck                     # flag rulings whose sources changed
    python scripts/judge.py index                       # rebuild the search index
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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card as scryfall  # noqa: E402  (the skill's Scryfall client, card.py)
import lookup  # noqa: E402  (the skill's own CR reader)
import s3  # noqa: E402  (the optional remote store's client)

SKILL_DIR = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("BISHOP_AND_BARRISTER_HOME") or Path.home() / ".claude" / "bishop-and-barrister")
CR_FILE = Path(os.environ.get("BISHOP_AND_BARRISTER_CR") or lookup.RULES_FILE)
CR_VERSION = CR_FILE.parent / "version.json"
OFFLINE = os.environ.get("BISHOP_AND_BARRISTER_OFFLINE") == "1"

RULINGS_DIR = HOME / "rulings"
DELIBERATION_DIR = HOME / "deliberation"
OBJECTS_DIR = HOME / "objects"
MANIFEST = HOME / "sources" / "manifest.json"
INDEX = HOME / "index.sqlite"

API = scryfall.API

QUESTION_TYPES = {"interaction", "legality-check", "sequence", "card-text", "deck-legality", "format-rule", "tournament"}
CONFIDENCE = {"certain", "likely", "unsure"}
# Search order: official Wizards rulings, then the user's reviewed rulings, then Scryfall's own
# rulings (level 4), then unreviewed ones.
RANK = {("official", 1): 0, ("reviewed", 5): 1, ("official", 4): 2, ("unreviewed", 5): 3}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def die(message: str, code: int = 1):
    print(message, file=sys.stderr)
    sys.exit(code)


# --- git: the record -------------------------------------------------------------------------


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(HOME), *args], capture_output=True, text=True, encoding="utf-8", check=check)


# Kept out of the record: the object store (synced by hash, not git), the rebuildable index, and the sync
# settings, which name the user's own endpoint and must never be committed or uploaded.
IGNORED = ("objects/", "index.sqlite", "config.json")


def ensure_home() -> None:
    """Create the store and its git repository on first use."""
    for d in (RULINGS_DIR, DELIBERATION_DIR, OBJECTS_DIR, MANIFEST.parent):
        d.mkdir(parents=True, exist_ok=True)
    if not (HOME / ".git").exists():
        subprocess.run(["git", "init", "-q", str(HOME)], check=True)
        (HOME / ".gitignore").write_text("".join(f"{p}\n" for p in IGNORED), encoding="utf-8")
        if not MANIFEST.exists():
            MANIFEST.write_text(json.dumps({"objects": {}}, indent=2) + "\n", encoding="utf-8")
        commit("Start the rulings record", drafted_by="judge")
    ignore = HOME / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
    missing = [p for p in IGNORED if p not in lines]
    if missing:  # a record made before a pattern was added
        ignore.write_text("".join(f"{p}\n" for p in lines + missing), encoding="utf-8")
        commit(f"Keep {', '.join(missing)} out of the record", drafted_by="judge")


def ensure_identity() -> None:
    """A commit needs an identity; fall back to a local one only if the user has none configured."""
    if not git("config", "user.email", check=False).stdout.strip():
        git("config", "user.name", "Bishop & Barrister")
        git("config", "user.email", "bishop-and-barrister@localhost")


def commit(message: str, drafted_by: str | None = None, decided_by: str | None = None) -> bool:
    """Commit everything in the record. Returns False when there was nothing to commit."""
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
    subprocess.run(["git", "-C", str(HOME), "commit", "-q", "-F", "-"], input=body, text=True, encoding="utf-8", check=True)
    return True


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"objects": {}}


def save_manifest(manifest: dict) -> None:
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def store_object(data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    path = OBJECTS_DIR / digest
    if not path.exists():
        path.write_bytes(data)
    return digest


# --- Scryfall --------------------------------------------------------------------------------


# All Scryfall traffic goes through card.py's client, which keeps to Scryfall's API terms:
# the required headers, the rate limits shared by every process, the 30-second lockout after a
# 429, and a 24-hour cache.


def http_json(url: str) -> dict:
    return scryfall.get(url)


def http_bytes(url: str) -> bytes:
    return scryfall.fetch(url, timeout=300, accept="*/*")


def oracle_text_of(card: dict) -> str:
    faces = card.get("card_faces") or [card]
    return "\n//\n".join(f.get("oracle_text", "") for f in faces)


def resolve_card(name: str) -> dict | None:
    """Look a card up on Scryfall: name, Oracle ID and the hash of its current Oracle text."""
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
    """Rule number -> the rule's text, from the downloaded CR (the body, not the table of contents)."""
    global _RULES
    if _RULES is None:
        if not CR_FILE.exists():
            die("The Comprehensive Rules aren't downloaded. Run: python scripts/update_rules.py")
        lines = CR_FILE.read_text(encoding="utf-8-sig").splitlines()
        _RULES = {}
        for line in lines[lookup.body_start(lines):]:
            m = lookup.RULE_LINE.match(line)
            if m:
                _RULES.setdefault(m.group(1), m.group(2).strip())
    return _RULES


def cr_sha256() -> str | None:
    if CR_VERSION.exists():
        return json.loads(CR_VERSION.read_text(encoding="utf-8")).get("sha256")
    return sha256_text(CR_FILE.read_text(encoding="utf-8-sig")) if CR_FILE.exists() else None


def cr_effective() -> str | None:
    if CR_VERSION.exists():
        return json.loads(CR_VERSION.read_text(encoding="utf-8")).get("effective_date")
    return None


# --- rulings in the record -------------------------------------------------------------------


def ruling_path(rid: str) -> Path:
    return RULINGS_DIR / f"{rid}.json"


def load_ruling(rid: str) -> dict:
    path = ruling_path(rid)
    if not path.exists():
        die(f"No ruling {rid} in the record.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_ruling(ruling: dict) -> None:
    ruling_path(ruling["id"]).write_text(json.dumps(ruling, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_deliberation(rid: str) -> list[dict]:
    path = DELIBERATION_DIR / f"{rid}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_deliberation(rid: str, entries: list[dict]) -> None:
    with (DELIBERATION_DIR / f"{rid}.jsonl").open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def validate(r: dict) -> list[str]:
    """The fields an agent relies on must be there. Empty lists are fine: they mean 'none'."""
    errors = []

    def need(key, kind, nonempty=False):
        if key not in r:
            errors.append(f"missing '{key}'")
        elif not isinstance(r[key], kind):
            errors.append(f"'{key}' must be a {kind.__name__}")
        elif nonempty and not r[key]:
            errors.append(f"'{key}' can't be empty")

    for key in ("question", "ruling", "agent_summary"):
        need(key, str, nonempty=True)
    for key in ("applies_when", "steps", "citations"):
        need(key, list, nonempty=True)
    for key in ("answer_changes_if", "ask_if_unknown", "misconceptions", "cards"):
        need(key, list)
    if r.get("question_type") not in QUESTION_TYPES:
        errors.append(f"'question_type' must be one of {sorted(QUESTION_TYPES)}")
    if r.get("confidence") not in CONFIDENCE:
        errors.append(f"'confidence' must be one of {sorted(CONFIDENCE)}")

    # Check inside each list that is well formed, so one pass reports every problem.
    def items(key):
        value = r.get(key)
        return value if isinstance(value, list) else []

    ids = [c.get("id") for c in items("citations")]
    if len(set(ids)) != len(ids) or not all(ids):
        errors.append("every citation needs a unique 'id'")
    for c in items("citations"):
        doc = c.get("doc", "cr")
        if doc == "cr":
            if c.get("ref") not in cr_rules():
                errors.append(f"citation {c.get('id')} cites CR {c.get('ref')}, which doesn't exist in the current CR")
        elif doc in lookup.DOCS:
            if not (lookup.DOCS_DIR / f"{doc}.json").exists():
                errors.append(f"citation {c.get('id')} cites the {lookup.DOCS[doc]}, which isn't downloaded "
                              f"(python scripts/sources.py update {doc})")
            elif not lookup.doc_section(doc, str(c.get("ref", ""))):
                errors.append(f"citation {c.get('id')} cites {doc.upper()} {c.get('ref')!r}, which doesn't name exactly one "
                              f"section of the current {lookup.DOCS[doc]} (see lookup.py --doc {doc} toc)")
        elif not c.get("excerpt"):
            errors.append(f"citation {c.get('id')} ({doc}) needs an 'excerpt'")
    for i, step in enumerate(items("steps"), 1):
        refs = step.get("refs") or []
        if not refs:
            errors.append(f"step {i} has no 'refs'")
        for ref in refs:
            if ref not in ids:
                errors.append(f"step {i} refers to citation '{ref}', which doesn't exist")
    for item in items("applies_when"):
        if not isinstance(item, dict) or not item.get("fact"):
            errors.append("each 'applies_when' entry needs a 'fact'")
    for card in items("cards"):
        if not card.get("name"):
            errors.append("each card needs a 'name'")
    return errors


def fill_sources(r: dict) -> list[str]:
    """Pin each rules citation and card to the exact text it relied on. Returns warnings."""
    warnings = []
    rules = cr_rules()
    for c in r["citations"]:
        c.setdefault("doc", "cr")
        if c["doc"] == "cr":
            text = rules[c["ref"]]
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
    for card in r["cards"]:
        found = resolve_card(card["name"])
        if found:
            card.update(found)
        elif not OFFLINE:
            warnings.append(f"couldn't find '{card['name']}' on Scryfall; its Oracle text isn't pinned")
    return warnings


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
    conn = sqlite3.connect(INDEX)
    conn.executescript(SCHEMA)
    return conn


def index_user_ruling(conn: sqlite3.Connection, r: dict) -> None:
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


def official_id(row: dict) -> str:
    key = f"{row['oracle_id']}|{row['published_at']}|{row['comment']}"
    return f"{row['source']}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"


def index_official(conn: sqlite3.Connection, data: bytes) -> int:
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
    """Throw the index away and rebuild it from the record and the current official rulings."""
    names = {}
    if INDEX.exists():
        old = sqlite3.connect(INDEX)
        try:
            names = dict(old.execute("SELECT oracle_id, name FROM card_names"))
        except sqlite3.DatabaseError:
            pass
        old.close()
        INDEX.unlink()
    conn = connect()
    conn.executemany("INSERT OR REPLACE INTO card_names VALUES (?,?)", names.items())
    official = 0
    current = load_manifest().get("scryfall_rulings")
    if current and (OBJECTS_DIR / current).exists():
        official = index_official(conn, (OBJECTS_DIR / current).read_bytes())
    user = 0
    for path in sorted(RULINGS_DIR.glob("*.json")):
        index_user_ruling(conn, json.loads(path.read_text(encoding="utf-8")))
        user += 1
    conn.commit()
    conn.close()
    return official, user


def reindex_one(r: dict) -> None:
    if not INDEX.exists():
        rebuild_index()
        return
    conn = connect()
    index_user_ruling(conn, r)
    conn.commit()
    conn.close()


# --- rendering -------------------------------------------------------------------------------


def card_name(conn: sqlite3.Connection, oracle_id: str | None) -> str | None:
    if not oracle_id:
        return None
    row = conn.execute("SELECT name FROM card_names WHERE oracle_id = ?", (oracle_id,)).fetchone()
    return row[0] if row else None


def attrs(**kw) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in kw.items() if v is not None)


def render_agent(r: dict, conn: sqlite3.Connection | None = None, with_deliberation: bool = False) -> str:
    """One ruling as XML for Claude: quotes before reasoning, empty fields left out."""
    if r.get("kind") == "official":
        name = card_name(conn, r.get("oracle_id")) if conn else None
        # The Oracle ID is only shown when the card's name isn't known: it's noise to the reader otherwise.
        return (f"<ruling {attrs(id=r['id'], kind='official', level=r['level'], source=r['source'], card=name, oracle_id=None if name else r.get('oracle_id'), published=r.get('published_at'))}>"
                f"{escape(r['comment'])}</ruling>")
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


def render_plain(r: dict, conn: sqlite3.Connection | None = None) -> str:
    if r.get("kind") == "official":
        name = (card_name(conn, r.get("oracle_id")) if conn else None) or f"oracle_id {r.get('oracle_id')}"
        return f"[{r['id']}] official ({r['source']}, {r.get('published_at')}) {name}\n  {r['comment']}"
    flag = " [needs recheck]" if r["status"] == "needs-recheck" else ""
    return f"[{r['id']}] {r['kind']} {r['question_type']}, {r['confidence']}{flag}\n  Q: {r['question']}\n  A: {r['ruling']}"


# --- commands --------------------------------------------------------------------------------


def cmd_build(args) -> int:
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
    if eff and CR_FILE.exists():
        tag = "cr-" + datetime.strptime(eff, "%B %d, %Y").strftime("%Y-%m-%d")
        if not git("tag", "--list", tag).stdout.strip():
            git("tag", "-a", tag, "-m", f"Rulings as of the Comprehensive Rules effective {eff}")
    official, user = rebuild_index()
    print(f"Index built: {official} official rulings, {user} of your rulings. Record: {HOME}")
    return 0


def cmd_index(args) -> int:
    ensure_home()
    official, user = rebuild_index()
    print(f"Index rebuilt: {official} official rulings, {user} of your rulings.")
    return 0


def fts_query(text: str, mode: str) -> str | None:
    words = re.findall(r"\w+", text.lower())
    if not words:
        return None
    return f" {mode} ".join(f'"{w}"' for w in words)


def cmd_search(args) -> int:
    if not INDEX.exists():
        die("No index yet. Run: python scripts/judge.py build")
    conn = connect()
    oracle_ids = set()
    for name in args.card:
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
        if args.agent and r[6] != "official" and not args.full:
            # A user ruling is long; list it briefly, and `show` prints the one that fits.
            print(f"<ruling {attrs(id=data['id'], type=data['question_type'], kind=data['kind'], level=data['level'], confidence=data['confidence'], sources_changed=str(data['status'] == 'needs-recheck').lower())}>"
                  f"<question>{escape(data['question'])}</question><summary>{escape(data['agent_summary'])}</summary></ruling>")
        else:
            print(render_agent(data, conn) if args.agent else render_plain(data, conn))
        print()
    if args.agent and not args.full and any(r[6] != "official" for r in shown):
        print("[Your rulings are listed briefly. For one that may fit: judge.py show <id> --agent]")
    if len(rows) > len(shown):
        print(f"[{len(rows) - len(shown)} more; raise --limit or narrow the search]")
    return 0


def cmd_record(args) -> int:
    ensure_home()
    r = json.loads(Path(args.file).read_text(encoding="utf-8"))
    errors = validate(r)
    if errors:
        print("Not recorded:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2
    for warning in fill_sources(r):
        print(f"Warning: {warning}", file=sys.stderr)
    stamp = now()
    r.update({
        "id": r.get("id") or uuid.uuid4().hex[:12], "kind": "unreviewed", "level": 5, "status": "current",
        "cr_sha256": cr_sha256(), "created_at": stamp, "updated_at": stamp,
    })
    r.setdefault("house_rule", False)
    for key in ("aliases", "mechanics", "related", "formats"):
        r.setdefault(key, [])
    if ruling_path(r["id"]).exists():
        die(f"A ruling {r['id']} already exists.")
    save_ruling(r)
    (DELIBERATION_DIR / f"{r['id']}.jsonl").touch()
    cites = ", ".join(f"{c.get('doc', 'cr').upper()} {c.get('ref')}" for c in r["citations"])
    commit(f"Record unreviewed ruling {r['id']}: {r['question'][:60]}\n\n{r['ruling']}\n\nSources: {cites}. CR {cr_effective() or 'unknown'}.",
           drafted_by="model")
    reindex_one(r)
    print(f"Recorded {r['id']} (unreviewed).")
    return 0


def cmd_discuss(args) -> int:
    ensure_home()
    r = load_ruling(args.id)
    entries = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if isinstance(entries, dict):
        entries = [entries]
    for e in entries:
        if e.get("by") not in ("user", "model") or not e.get("said"):
            die("Each entry needs 'by' (user or model) and 'said'.")
        e.setdefault("at", now())
    append_deliberation(r["id"], entries)
    if args.summary:
        r["deliberation_summary"] = args.summary
    r["updated_at"] = now()
    save_ruling(r)
    commit(f"Discuss {r['id']}: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}", drafted_by="model")
    reindex_one(r)
    print(f"Added {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} to {r['id']}.")
    return 0


def cmd_review(args) -> int:
    ensure_home()
    r = load_ruling(args.id)
    if not args.user_said.strip():
        die("A ruling becomes reviewed only on the user's say-so: pass their words with --user-said.")
    append_deliberation(r["id"], [{"by": "user", "at": now(), "decision": "reviewed", "said": args.user_said}])
    r["kind"] = "reviewed"
    if args.house_rule:
        r["house_rule"] = True
    r["updated_at"] = now()
    save_ruling(r)
    commit(f"Review {r['id']}: accepted by the user\n\nThe user said: \"{args.user_said}\"", drafted_by="model", decided_by="user")
    reindex_one(r)
    print(f"{r['id']} is now reviewed.")
    return 0


def cmd_show(args) -> int:
    if ruling_path(args.id).exists():
        r = load_ruling(args.id)
        conn = connect() if INDEX.exists() else None
        if args.agent:
            print(render_agent(r, conn, with_deliberation=args.deliberation))
        else:
            print(json.dumps(r, indent=2, ensure_ascii=False))
            if args.deliberation:
                for e in load_deliberation(r["id"]):
                    print(json.dumps(e, ensure_ascii=False))
        return 0
    if INDEX.exists():
        conn = connect()
        row = conn.execute("SELECT json, oracle_id, source, level FROM rulings WHERE id = ?", (args.id,)).fetchone()
        if row:
            data = {**json.loads(row[0]), "id": args.id, "kind": "official", "oracle_id": row[1], "source": row[2], "level": row[3]}
            print(render_agent(data, conn) if args.agent else render_plain(data, conn))
            return 0
    die(f"No ruling {args.id}.")


def cmd_recheck(args) -> int:
    ensure_home()
    rules = cr_rules()
    changed = []
    for path in sorted(RULINGS_DIR.glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        reasons = []
        for c in r["citations"]:
            doc = c.get("doc", "cr")
            if doc == "cr":
                text = rules.get(c["ref"])
            elif doc in lookup.DOCS and (lookup.DOCS_DIR / f"{doc}.json").exists():
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
        rebuild_index()
        print(f"{len(changed)} ruling(s) marked needs-recheck:\n{lines}")
    else:
        print("All rulings still match their sources.")
    return 0


# --- sync: the optional remote store (plan 028, storage modes) ----------------------------------
#
# Local only is the default. With an endpoint set, a RustFS bucket the user chooses holds a synced copy:
# record/<device>.bundle is each device's whole git history. The local record stays the working copy; sync
# merges the other devices' bundles in (never rebases, so commits and their trailers keep one identity) and
# uploads this device's. No two devices write the same key, so no locking is needed.

CONFIG = HOME / "config.json"
SYNC_STATE = HOME / ".git" / "bishop-and-barrister-sync.json"  # inside .git, so never committed


def load_config() -> dict | None:
    """The store settings, with BISHOP_AND_BARRISTER_S3_ENDPOINT / _S3_BUCKET overriding the file."""
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    for key in ("endpoint", "bucket"):
        if os.environ.get(f"BISHOP_AND_BARRISTER_S3_{key.upper()}"):
            cfg[key] = os.environ[f"BISHOP_AND_BARRISTER_S3_{key.upper()}"]
    return cfg if cfg.get("endpoint") and cfg.get("bucket") else None


class SyncStop(Exception):
    """Syncing can't go on until the user acts: no keys, a public bucket, or a conflict to settle."""


def store_client(cfg: dict, timeout: float = 60) -> s3.S3:
    keys = s3.credentials(cfg.get("profile"))
    if not keys:
        raise SyncStop("No keys for the store. Set BISHOP_AND_BARRISTER_S3_ACCESS_KEY and "
                       "BISHOP_AND_BARRISTER_S3_SECRET_KEY, or a profile in ~/.aws/credentials (--profile). "
                       "Keys never go in config.json.")
    return s3.S3(cfg["endpoint"], cfg["bucket"], *keys, region=cfg.get("region", "us-east-1"),
                 addressing=cfg.get("addressing", "path"), timeout=timeout)


def device_name(name: str | None = None) -> str:
    name = re.sub(r"[^a-z0-9-]+", "-", (name or socket.gethostname()).lower()).strip("-")
    return name or "device"


def refuse_if_public(client: s3.S3, key: str | None = None) -> None:
    """A public bucket would republish Scryfall's and Wizards' files and expose the user's rulings."""
    found = client.anonymous_access(key)
    if found:
        raise SyncStop(f"Stopped: anyone without keys can {' and '.join(found)} in bucket {client.bucket!r}. Make "
                       "the bucket private (no anonymous access), then sync again. A public bucket would expose "
                       "your rulings and republish Scryfall's and Wizards' files, which their terms forbid.")


def cmd_sync(args) -> int:
    ensure_home()
    return sync_setup(args) if args.setup else sync_now()


def sync_setup(args) -> int:
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
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    devices = [o["key"][len("record/"):-len(".bundle")] for o in others if o["key"].endswith(".bundle")]
    print(f"Saved {CONFIG}: {endpoint}, bucket {args.bucket!r}, this device {cfg['device']!r}.")
    print(f"The bucket is private. Devices already syncing there: {', '.join(devices) or 'none'}.")
    server = client.server()
    print(f"Server: {server}. Make sure it's RustFS 1.0.4 or later." if server else
          "The server doesn't report its version: make sure it's RustFS 1.0.4 or later.")
    print("Mode: local plus a remote store. The local record stays the working copy. It syncs by itself as the "
          "skill is used; `judge.py sync` forces one now.")
    return 0


def merge_manifests(ours: dict, theirs: dict) -> dict:
    """Both devices downloaded their own Scryfall file: keep every object, and the newest bulk file."""
    merged = {**ours, "objects": {**theirs.get("objects", {}), **ours.get("objects", {})}}
    candidates = [h for h in (ours.get("scryfall_rulings"), theirs.get("scryfall_rulings")) if h]
    if candidates:
        merged["scryfall_rulings"] = max(candidates, key=lambda h: merged["objects"].get(h, {}).get("updated_at") or "")
    return merged


def merge_device(device: str, ref: str) -> bool:
    """Merge one device's history in. Returns False, leaving nothing half-done, on a conflict a person must settle."""
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
            (HOME / ".gitignore").write_text("".join(f"{l}\n" for l in lines), encoding="utf-8")
        git("add", *conflicted)
        subprocess.run(["git", "-C", str(HOME), "commit", "-q", "--no-edit"], check=True, capture_output=True)
        return True
    git("merge", "--abort", check=False)
    raise SyncStop(f"Sync stopped: {device} changed the same ruling(s) as this device: {', '.join(conflicted)}. "
                   f"Nothing was merged or uploaded. Settle it with the user: compare `git -C {HOME} diff HEAD {ref}`, "
                   "edit the ruling to the version they choose, then run `judge.py sync` again.")


def load_state() -> dict:
    return json.loads(SYNC_STATE.read_text(encoding="utf-8")) if SYNC_STATE.exists() else {"fetched": {}}


def save_state(state: dict) -> None:
    SYNC_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def remote_bundles(client: s3.S3) -> dict:
    """Each device syncing through the store, with its bundle's ETag."""
    return {o["key"][len("record/"):-len(".bundle")]: o["etag"] for o in client.keys("record/")
            if o["key"].endswith(".bundle")}


def pull(client: s3.S3, device: str, state: dict, remote: dict) -> list[str]:
    """Merge in every other device whose bundle changed since the last pull. Returns the devices merged."""
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
    """Upload this device's bundle if its history moved since the last upload. Returns whether it did."""
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
    """`judge.py sync`: a full sync now, whatever the throttle says, reporting every problem."""
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
READS = {"search", "show"}
WRITES = {"build", "record", "discuss", "review", "recheck"}


def auto_sync(command: str) -> None:
    if command not in READS | WRITES or os.environ.get("BISHOP_AND_BARRISTER_AUTO_SYNC") == "0":
        return
    try:
        cfg = load_config()
    except (OSError, ValueError):
        return
    if not cfg or cfg.get("auto_sync") is False or not (HOME / ".git").exists():
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

    p = sub.add_parser("record", help="store a new unreviewed ruling from a JSON file")
    p.add_argument("file")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("discuss", help="add entries to a ruling's deliberation")
    p.add_argument("id")
    p.add_argument("file", help='JSON: [{"by": "user"|"model", "said": "..."}]')
    p.add_argument("--summary", help="replace the ruling's deliberation_summary")
    p.set_defaults(func=cmd_discuss)

    p = sub.add_parser("review", help="mark a ruling reviewed, only on the user's say-so")
    p.add_argument("id")
    p.add_argument("--user-said", required=True, help="the user's own words accepting the ruling")
    p.add_argument("--house-rule", action="store_true", help="record it as a house rule (it contradicts level 1)")
    p.set_defaults(func=cmd_review)

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
