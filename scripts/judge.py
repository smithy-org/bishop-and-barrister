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
import sqlite3
import subprocess
import sys
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


def ensure_home() -> None:
    """Create the store and its git repository on first use."""
    for d in (RULINGS_DIR, DELIBERATION_DIR, OBJECTS_DIR, MANIFEST.parent):
        d.mkdir(parents=True, exist_ok=True)
    if not (HOME / ".git").exists():
        subprocess.run(["git", "init", "-q", str(HOME)], check=True)
        (HOME / ".gitignore").write_text("objects/\nindex.sqlite\n", encoding="utf-8")
        if not MANIFEST.exists():
            MANIFEST.write_text(json.dumps({"objects": {}}, indent=2) + "\n", encoding="utf-8")
        commit("Start the rulings record", drafted_by="judge")


def commit(message: str, drafted_by: str | None = None, decided_by: str | None = None) -> bool:
    """Commit everything in the record. Returns False when there was nothing to commit."""
    # A commit needs an identity; fall back to a local one only if the user has none configured.
    if not git("config", "user.email", check=False).stdout.strip():
        git("config", "user.name", "Bishop & Barrister")
        git("config", "user.email", "bishop-and-barrister@localhost")
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


def validate_citation(c: dict, label: str) -> list[str]:
    """One citation: what it cites exists in the current documents, or it carries its own excerpt."""
    doc = c.get("doc", "cr")
    if doc == "cr":
        if c.get("ref") not in cr_rules():
            return [f"{label} cites CR {c.get('ref')}, which doesn't exist in the current CR"]
    elif doc in lookup.DOCS:
        if not (lookup.DOCS_DIR / f"{doc}.json").exists():
            return [f"{label} cites the {lookup.DOCS[doc]}, which isn't downloaded (python scripts/sources.py update {doc})"]
        if not lookup.doc_section(doc, str(c.get("ref", ""))):
            return [f"{label} cites {doc.upper()} {c.get('ref')!r}, which doesn't name exactly one section of the current "
                    f"{lookup.DOCS[doc]} (see lookup.py --doc {doc} toc)"]
    elif not c.get("excerpt"):
        return [f"{label} ({doc}) needs an 'excerpt'"]
    return []


def pin_citation(c: dict) -> None:
    """Pin one valid citation to the exact text it relies on (text_sha256), with an excerpt of it."""
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
        errors += validate_citation(c, f"citation {c.get('id')}")
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
    for c in r["citations"]:
        pin_citation(c)
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

    args = parser.parse_args()
    return args.func(args)


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
