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
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
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
# Search order: official Wizards rulings, then rules introduced by challenge, then the user's house rules
# (from before challenges), then Scryfall's own rulings (level 4).
RANK = {("official", 1): 0, ("rule", 5): 1, ("reviewed", 5): 2, ("official", 4): 3}
RULES_DIR = HOME / "rules"


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


def rule_sources(rule: dict) -> list[dict]:
    return [st["source"] for st in rule.get("steps", []) if isinstance(st.get("source"), dict)]


def index_rule(conn: sqlite3.Connection, rule: dict) -> None:
    """A rule a challenge introduced (or a house rule a refuted one kept), searchable by text, card and rule."""
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
    """The rules search shows: current, or stale and reopened (flagged as unconfirmed)."""
    rules = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RULES_DIR.glob("*.json"))]
    return [r for r in rules if r.get("state") in ("current", "stale", "reopened")]


def reindex_rules() -> None:
    """Bring the index's rules up to date with rules/, without rebuilding the official rulings."""
    if not INDEX.exists():
        return
    conn = connect()
    for table, column in (("rulings", "id"), ("ruling_cards", "ruling_id"), ("citations", "ruling_id"), ("rulings_fts", "id")):
        conn.execute(f"DELETE FROM {table} WHERE {column} LIKE 'challenge-%' OR {column} LIKE 'house-challenge-%'")
    for rule in live_rules():
        index_rule(conn, rule)
    conn.commit()
    conn.close()


def legacy_rulings() -> list[dict]:
    """Rulings written by the retired `record` that haven't been migrated: everything but house rules."""
    rulings = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RULINGS_DIR.glob("*.json"))]
    return [r for r in rulings if not (r.get("kind") == "reviewed" and r.get("house_rule"))]


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
    # Of the rulings from before challenges, only house rules are still the user's; the rest wait for `migrate`.
    for path in sorted(RULINGS_DIR.glob("*.json")):
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
    """A rule introduced by challenge, as XML for Claude. Unconfirmed while its challenge runs again."""
    out = [f"<ruling {attrs(id=r['id'], kind='rule', level=5, state=r['state'], house_rule=str(r.get('house_rule', False)).lower(), sources_changed=str(r['state'] != 'current').lower())}>"]
    out.append(f"  <rule>{escape(r['rule'])}</rule>")
    out.append("  <applies_when>" + "".join(f"<fact>{escape(a)}</fact>" for a in r.get("applies_when", [])) + "</applies_when>")
    out.append(f"  <challenged>{escape(r.get('challenges', ''))}</challenged>")
    out.append("  <steps>" + "".join(
        f"<step {attrs(n=st['id'], premises=' '.join(st.get('premises', [])), doc=(st.get('source') or {}).get('doc'), ref=(st.get('source') or {}).get('ref'))}>"
        f"{escape((st.get('source') or {}).get('excerpt', ''))} → {escape(st.get('conclusion', ''))}</step>" for st in r.get("steps", [])) + "</steps>")
    how = ("kept as a house rule after its challenge was refuted" if r.get("house_rule")
           else "introduced by a unanimous panel of seven judges")
    out.append(f"  <provenance>{escape(how)}; python scripts/challenge.py trace {escape(r['challenge'])}</provenance>")
    out.append("</ruling>")
    return "\n".join(out)


def render_plain(r: dict, conn: sqlite3.Connection | None = None) -> str:
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
    die(f"judge.py {args.command}: {RETIRED}", code=2)


def cmd_migrate(args) -> int:
    """Move the rulings the retired `record` wrote out of the searched record. A reviewed ruling becomes an open
    challenge carrying its deliberation (it must pass a panel to become a rule); an unreviewed one, the model's
    own answer, is set aside; house rules stay as they are."""
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
            dest, outcome = HOME / "rulings-migrated", f"now challenge {cid}"
        else:
            dest, outcome = HOME / "rulings-retired", "set aside (unreviewed)"
        dest.mkdir(exist_ok=True)
        ruling_path(rid).replace(dest / f"{rid}.json")
        talk = DELIBERATION_DIR / f"{rid}.jsonl"
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
    rule = RULES_DIR / f"{args.id}.json"
    if rule.exists():
        r = json.loads(rule.read_text(encoding="utf-8"))
        print(render_agent(r) if args.agent else json.dumps(r, indent=2, ensure_ascii=False))
        return 0
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
        print(f"{len(changed)} ruling(s) marked needs-recheck:\n{lines}")
    reopened = []
    if any(RULES_DIR.glob("challenge-*.json")):
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
