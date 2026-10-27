#!/usr/bin/env python3
"""Challenges: the only way a rule enters the record (plan 029).

A challenge is a folder of event files in the record, each holding the hash of the one before it:
challenges/challenge-<YYYYMMDD>-<12 hex>/<seq>-<actor>-<device>.json. The Lean core, `bab-challenge`,
replays them to find the state and who acts next, and accepts or refuses every new event. This script
stores the events, pins and verifies their citations (through judge.py), and finds and checks the binary.
What may happen next is decided only by the core.

Usage:
    python scripts/challenge.py open --statement "The user's case, in their words" [--panel single-agent]
    python scripts/challenge.py brief <id> case.json                 # the clerk's brief
    python scripts/challenge.py edit <id> case.json --user-said "F2 is wrong: it was game 2"
    python scripts/challenge.py confirm <id> --user-said "Yes, that's my case"
    python scripts/challenge.py add <id> event.json --as judge-3     # a filing, an answer, a vote, the opinion...
    python scripts/challenge.py verify <id>                          # the verifier's report
    python scripts/challenge.py status <id>                          # the state, and who acts next
    python scripts/challenge.py show <id> [--judge 3]                # the events (judge 3's view)
    python scripts/challenge.py list
    python scripts/challenge.py withdraw <id> --user-said "..."
    python scripts/challenge.py resolve <id> --keep <event file> --user-said "..."   # settle a fork
    python scripts/challenge.py trace <id>                           # check the id, the chain, the rule file
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge  # noqa: E402  (the record: git, citations, the index)
import lookup  # noqa: E402

CHALLENGES_DIR = judge.HOME / "challenges"
RULES_DIR = judge.HOME / "rules"
BIN_DIR = judge.HOME / "bin"
BINARIES = Path(os.environ.get("BISHOP_AND_BARRISTER_BINARIES") or judge.SKILL_DIR / "challenge" / "binaries.json")
RELEASES = os.environ.get("BISHOP_AND_BARRISTER_RELEASES") or "https://github.com/smithy-org/bishop-and-barrister/releases/download"
# A locally built core (challenge/.lake/build/bin/bab-challenge), for working on the core itself. Not checked.
DEV_BIN = os.environ.get("BISHOP_AND_BARRISTER_CHALLENGE_BIN")

ID = re.compile(r"challenge-\d{8}-[0-9a-f]{12}")
LEVEL_1_DOCS = {"cr", "oracle", "ruling"}


class Unavailable(Exception):
    """Challenges can't run here: no binary for this platform, or it couldn't be fetched or checked."""


# --- the core binary -------------------------------------------------------------------------


def platform_key() -> str | None:
    system = {"linux": "linux", "darwin": "macos", "win32": "windows"}.get(sys.platform)
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower())
    return f"{system}-{arch}" if system and arch else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def find_binary() -> Path:
    """The core for this platform: downloaded once from the pinned release, and refused unless its SHA-256
    matches challenge/binaries.json."""
    if DEV_BIN:
        return Path(DEV_BIN)
    pins = json.loads(BINARIES.read_text(encoding="utf-8"))
    key = platform_key()
    entry = (pins.get("binaries") or {}).get(key or "")
    if not pins.get("release") or not entry:
        raise Unavailable(f"there's no released challenge core for this platform ({key or platform.platform()}) yet")
    path = BIN_DIR / entry["sha256"] / entry["file"]
    if path.exists() and sha256_file(path) == entry["sha256"]:
        return path
    url = f"{RELEASES}/{pins['release']}/{entry['file']}"
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
    except Exception as err:  # noqa: BLE001  (any failure means the same thing: no core)
        raise Unavailable(f"couldn't download the challenge core from {url} ({err})") from err
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        raise Unavailable(f"refused the challenge core from {url}: its SHA-256 is {digest}, "
                          f"not the {entry['sha256']} pinned in challenge/binaries.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.chmod(0o755)
    tmp.replace(path)
    return path


def core(command: list[str], payload: dict) -> dict:
    """Run bab-challenge: JSON in, JSON out."""
    try:
        binary = find_binary()
    except Unavailable as err:
        judge.die(f"Challenges are unavailable: {err}. Everyday answering is unaffected.")
    result = subprocess.run([str(binary), *command], input=json.dumps(payload), capture_output=True, text=True,
                            encoding="utf-8")
    if result.returncode != 0:
        judge.die(f"The challenge core failed: {result.stderr.strip() or result.stdout.strip()}")
    return json.loads(result.stdout)


# --- the event store -------------------------------------------------------------------------


def ensure_store() -> None:
    judge.ensure_home()
    CHALLENGES_DIR.mkdir(exist_ok=True)
    ignore = judge.HOME / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
    if "bin/" not in lines:
        ignore.write_text("\n".join([*lines, "bin/"]) + "\n", encoding="utf-8")
    # An event's hash is taken over its exact bytes, so git must never change their line endings.
    attributes = judge.HOME / ".gitattributes"
    lines = attributes.read_text(encoding="utf-8").splitlines() if attributes.exists() else []
    if "challenges/** -text" not in lines:
        attributes.write_text("\n".join([*lines, "challenges/** -text"]) + "\n", encoding="utf-8")


def challenge_dir(cid: str) -> Path:
    if not ID.fullmatch(cid):
        judge.die(f"{cid!r} isn't a challenge id (challenge-<YYYYMMDD>-<12 hex>).")
    path = CHALLENGES_DIR / cid
    if not path.is_dir():
        judge.die(f"No challenge {cid} in the record (python scripts/challenge.py list).")
    return path


def event_files(cid: str) -> list[Path]:
    return sorted(challenge_dir(cid).glob("*.json"))


def read_raw(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def raws(cid: str) -> list[str]:
    return [read_raw(p) for p in event_files(cid)]


def events_in_order(cid: str) -> list[dict]:
    """The parsed events, by their place in the chain (only meaningful once replay is ok)."""
    return sorted((json.loads(r) for r in raws(cid)), key=lambda e: e["seq"])


def replay(cid: str) -> dict:
    return core(["replay"], {"events": raws(cid)})


def device() -> str:
    name = os.environ.get("BISHOP_AND_BARRISTER_DEVICE") or socket.gethostname() or "device"
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "device"


def event_text(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False, indent=2) + "\n"


def describe_failure(state: dict) -> str:
    if "fork" in state:
        lines = ["Two devices acted in the same state, so the challenge is paused until the user picks one:"]
        for fork in state["fork"]:
            for e in fork["events"]:
                lines.append(f"  {e['seq']:04d}-{e['actor']}-{e['device']}.json")
        lines.append("Settle it with: python scripts/challenge.py resolve <id> --keep <event file> --user-said \"...\"")
        return "\n".join(lines)
    if "broken" in state:
        return f"The challenge's events don't form a chain: {state['broken']}. Nothing can be added until it's repaired."
    if "refused" in state:
        return f"Event {state['refused']['seq']} isn't allowed: " + "; ".join(state["refused"]["why"])
    return f"The challenge can't be read: {state.get('error', state)}"


def propose(cid: str | None, actor: str, fields: dict, message: str, words: str | None = None) -> tuple[str, dict]:
    """Add one event, if the core accepts it, and commit it. Returns the id and the new state."""
    ensure_store()
    events = raws(cid) if cid else []
    state = core(["replay"], {"events": events})
    if not state.get("ok"):
        judge.die(describe_failure(state))
    event = {"v": 1, "seq": state["next_seq"], "prev": state["head"], "actor": actor, "device": device(),
             "time": judge.now(), **fields}
    text = event_text(event)
    verdict = core(["check"], {"events": events, "proposed": text})
    if not verdict.get("accepted"):
        judge.die("Refused:\n" + "\n".join(f"- {r}" for r in verdict.get("reasons", [verdict])))
    new_state = verdict["state"]
    cid = cid or new_state["id"]
    folder = CHALLENGES_DIR / cid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{event['seq']:04d}-{actor}-{event['device']}.json").write_bytes(text.encode("utf-8"))
    drafted, decided = actor, (f'user ("{words}")' if words else None)
    if new_state["settled"] or new_state["state"] == "open":
        outcome = settle(cid, new_state)
        if outcome:
            message += f"\n\n{outcome}"
            judge.reindex_rules()
        if new_state["state"] == "introduced":
            drafted, decided = "panel", "panel"
    judge.commit(f"{cid}: {message}", drafted_by=drafted, decided_by=decided)
    return cid, new_state


# --- rules: what a challenge leaves in the record ---------------------------------------------


def rule_step(state: str, event: str) -> str:
    """One transition of the rule state machine, decided by the core."""
    result = core(["rule"], {"state": state, "event": event})
    if not result.get("accepted"):
        judge.die(f"The rule can't move: {'; '.join(result.get('reasons', [str(result)]))}")
    return result["state"]


def load_rule(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_rule(rule: dict, path: Path) -> None:
    RULES_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def judge_of(event: dict) -> int:
    return int(event["actor"].removeprefix("judge-"))


def positions(events: list[dict], responses: bool = False) -> list[dict]:
    """Each judge's settled position, with its reasoning and evidence: their last vote, or their last filing (a
    concession is a convinced position, a refutation not). With `responses`, a judge's answer to the draft opinion
    is a later position: a dissent is not convinced; a join or a concurrence is."""
    latest = {}
    for e in events:
        if not e.get("actor", "").startswith("judge-"):
            continue
        k = judge_of(e)
        if e["type"] == "vote":
            latest[k] = {"judge": k, "convinced": e["convinced"], "reason": e["reason"], "evidence": e.get("evidence", []),
                         "how": "vote"}
        elif e["type"] == "file":
            if not e["refutations"]:
                latest[k] = {"judge": k, "convinced": True, "reason": e.get("concedes", ""),
                             "evidence": e.get("concede_evidence", []), "how": "filing"}
            else:
                sources = [st["source"] for r in e["refutations"] for st in r.get("steps", [])
                           if isinstance(st.get("source"), dict)]
                latest[k] = {"judge": k, "convinced": False,
                             "reason": "; ".join(r["argument"] for r in e["refutations"]), "evidence": sources,
                             "how": "filing"}
        elif e["type"] == "respond" and responses:
            latest[k] = {"judge": k, "convinced": e["stance"] != "dissent", "reason": e["reason"],
                         "evidence": e.get("evidence", []), "how": e["stance"]}
    return [latest[k] for k in sorted(latest)]


def opinion_record(events: list[dict]) -> dict | None:
    """The final Opinion of the Court: its holding, reasoning and stipulations, who joined it, and every
    concurrence and dissent a draft drew along the way."""
    drafts = [e for e in events if e["type"] == "opinion"]
    if not drafts:
        return None
    final = drafts[-1]
    record = {"author": judge_of(final), "revision": final["revision"], "revisions": len(drafts) - 1,
              "holding": final["holding"], "steps": final["steps"],
              "stipulations": [st["conclusion"] for st in final["steps"] if st.get("stipulation")],
              "joined": [], "concurrences": [], "dissents": []}
    for e in events:
        if e["type"] != "respond":
            continue
        item = {"judge": judge_of(e), "revision": e["revision"], "reason": e["reason"],
                "evidence": e.get("evidence", [])}
        if e["stance"] == "join":
            if e["seq"] > final["seq"]:
                record["joined"].append(item)
        else:
            record["concurrences" if e["stance"] == "concur" else "dissents"].append(item)
    return record


def cited(sources: list[dict]) -> str:
    return "; ".join(f"{s.get('doc', 'cr').upper()} {s.get('ref')}" for s in sources) or "no sources"


def per_curiam(cid: str, state: dict, events: list[dict]) -> dict:
    """The short record of a refused case, assembled from the judges' settled positions: no agent writes it."""
    case = events[state["case_seq"]]["case"]
    pos = positions(events, responses=True)
    against = [p for p in pos if not p["convinced"]]
    prose = [f"Per curiam. The court refused the rule \"{case['rule']}\": {state.get('why') or state['state']}."]
    for label, group in (("Not convinced", against), ("Convinced", [p for p in pos if p["convinced"]])):
        if group:
            prose.append(f"{label} ({len(group)}): " + " ".join(
                f"Judge {p['judge']}: {p['reason']} [{cited(p['evidence'])}]." for p in group))
    prose.append("The established answer stands." if state["state"] == "refuted" else
                 "The case is unproven; the established answer stands for now.")
    return {"type": "per-curiam", "challenge": cid, "outcome": state["state"], "why": state.get("why"),
            "final_hash": state["head"], "rule": case["rule"], "positions": pos, "text": " ".join(prose)}


def write_per_curiam(cid: str, state: dict) -> Path:
    folder = challenge_dir(cid) / "record"
    folder.mkdir(exist_ok=True)
    path = folder / "per-curiam.json"
    path.write_text(json.dumps(per_curiam(cid, state, events_in_order(cid)), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def rule_from(cid: str, state: dict, house_rule: bool) -> dict:
    """The rule file for a closed challenge, with its provenance: the challenge, the hash of its final event,
    the votes, the verifier's last report, the devices and dates, and the pinned sources."""
    files = {json.loads(read_raw(p))["seq"]: p for p in event_files(cid)}
    events = events_in_order(cid)
    case = events[state["case_seq"]]["case"]
    reports = [e for e in events if e["type"] == "report"]
    opening, last = events[0], events[-1]
    # An introduced rule carries its Opinion of the Court; a house rule departs from the court and has none.
    opinion = None if house_rule else opinion_record(events)
    return {
        "id": f"house-{cid}" if house_rule else cid, "kind": "rule", "level": 5, "house_rule": house_rule,
        "state": "current", "challenge": cid, "final_hash": state["head"],
        "rule": case["rule"], "applies_when": case["applies_when"], "challenges": case["challenges"],
        "facts": case["facts"], "steps": case["steps"],
        "stipulations": [st["conclusion"] for st in case["steps"] if st.get("stipulation")],
        "votes": positions(events),
        "opinion": opinion,
        "verifier_report_sha256": sha256_file(files[reports[-1]["seq"]]) if reports else None,
        "opened": {"device": opening["device"], "time": opening["time"]},
        "introduced": {"device": last["device"], "time": last["time"]},
    }


def settle(cid: str, state: dict) -> str | None:
    """Write what a closed challenge leaves behind. An introduced challenge writes rules/challenge-<id>.json; a
    house rule writes rules/house-challenge-<id>.json. A challenge that reopened a stale rule moves that rule
    instead: introduced again, it is current with the new case; refuted, it is retired."""
    reopens = events_in_order(cid)[0].get("reopens")
    if reopens and state["state"] in ("introduced", "refuted", "withdrawn"):
        path = RULES_DIR / f"{reopens}.json"
        rule = load_rule(path)
        if state["state"] == "introduced":
            fresh = rule_from(cid, state, house_rule=False)
            rule.update({k: fresh[k] for k in ("rule", "applies_when", "challenges", "facts", "steps", "opinion")})
            rule.setdefault("renewals", []).append({"challenge": cid, "final_hash": state["head"],
                                                    "votes": fresh["votes"], "time": fresh["introduced"]["time"]})
            rule["state"] = rule_step(rule["state"], "challenge-introduced")
            rule.pop("recheck_reasons", None)
        else:
            rule["state"] = rule_step(rule["state"], "challenge-refuted")
            rule["retired_by"] = cid
        save_rule(rule, path)
        return f"Rule {reopens} is now {rule['state']}."
    if state["state"] == "introduced":
        save_rule(rule_from(cid, state, house_rule=False), RULES_DIR / f"{cid}.json")
        return f"Introduces rules/{cid}.json."
    if state["state"] == "house-rule":
        save_rule(rule_from(cid, state, house_rule=True), RULES_DIR / f"house-{cid}.json")
        return f"Kept as a house rule: rules/house-{cid}.json."
    if state["state"] in ("refuted", "open"):
        path = write_per_curiam(cid, state)
        return f"Per curiam record: {path.relative_to(judge.HOME).as_posix()}."
    return None


def recheck_rules(offline: bool = False) -> list[tuple[str, list[str], str]]:
    """Every current rule whose sources changed goes stale, and a new challenge opens against the new text,
    carrying the old case for the clerk. Returns (rule, reasons, the new challenge) for each."""
    reopened = []
    for path in sorted(RULES_DIR.glob("challenge-*.json")):
        rule = load_rule(path)
        if rule["state"] != "current":
            continue
        reasons = []
        for label, steps in (("step", rule["steps"]), ("opinion step", (rule.get("opinion") or {}).get("steps", []))):
            for st in steps:
                src = st.get("source")
                if isinstance(src, dict) and not (offline and src.get("doc") == "oracle"):
                    why = verify_source(src)
                    if why:
                        reasons.append(f"{label} {st['id']}: {why}")
        if not reasons:
            continue
        rule["state"] = rule_step(rule["state"], "source-changed")
        rule["recheck_reasons"] = reasons
        statement = (f"The rule from {rule['id']} relied on sources that changed ({'; '.join(reasons)}). It must win "
                     f"its challenge again against the new text: {rule['rule']}")
        case = {k: rule[k] for k in ("facts", "rule", "applies_when", "challenges", "steps")}
        rule["state"] = rule_step(rule["state"], "challenge-reopened")
        cid, _ = propose(None, "user", {"type": "open", "statement": statement, "panel": "independent",
                                        "reopens": rule["id"], "carried": {"case": case}},
                         f"Reopen {rule['id']}: its sources changed")
        rule["reopened_by"] = cid
        save_rule(rule, path)
        judge.commit(f"Rule {rule['id']} is reopened by {cid}\n\n" + "\n".join(f"- {r}" for r in reasons),
                     drafted_by="judge")
        reopened.append((rule["id"], reasons, cid))
    return reopened


# --- citations: pinning and the verifier -----------------------------------------------------


def sources_in(fields: dict) -> list[tuple[str, dict]]:
    """Every source in an event's case, refutations, replies, concessions and votes, with a label for messages."""
    found = []

    def steps(label: str, items: list) -> None:
        for st in items or []:
            if isinstance(st.get("source"), dict):
                found.append((f"{label} step {st.get('id')}", st["source"]))

    if isinstance(fields.get("case"), dict):
        steps("case", fields["case"].get("steps"))
    if fields.get("type") == "opinion":
        steps("the opinion", fields.get("steps"))
    for i, r in enumerate(fields.get("refutations") or [], 1):
        steps(f"refutation {i}", r.get("steps"))
    for rp in fields.get("replies") or []:
        steps(f"reply to judge {rp.get('judge')}'s refutation {rp.get('index')}", rp.get("steps"))
    # A concession, a vote and a response to the draft opinion each rest on the sources the judge checked.
    for key, label in (("concede_evidence", "the concession"),
                       ("evidence", "the response" if fields.get("type") == "respond" else "the vote")):
        for i, src in enumerate(fields.get(key) or [], 1):
            if isinstance(src, dict):
                found.append((f"{label}'s evidence {i}", src))
    return found


def oracle_text(name: str) -> tuple[str, str] | None:
    """A card's exact name and current Oracle text, from Scryfall."""
    if judge.OFFLINE:
        return None
    card = judge.http_json(f"{judge.API}/cards/named?exact={urllib.parse.quote(name)}")
    return card["name"], judge.oracle_text_of(card)


def official_ruling_with(excerpt: str) -> bool:
    """Whether some official ruling in the index contains the excerpt."""
    if not judge.INDEX.exists():
        return False
    needle = " ".join(excerpt.split()).lower()
    probe = max(re.split(r"[%_\"\\]", needle), key=len)[:60]
    conn = sqlite3.connect(judge.INDEX)
    try:
        rows = conn.execute("SELECT json FROM rulings WHERE kind = 'official' AND lower(json) LIKE ?",
                            (f"%{probe}%",)).fetchall()
    finally:
        conn.close()
    return any(needle in " ".join(str(json.loads(row[0]).get("comment") or json.loads(row[0]).get("ruling") or "").split()).lower()
               for row in rows)


def source_text(src: dict) -> tuple[str | None, str | None]:
    """The current text a source cites, or the reason it can't be found."""
    doc = src.get("doc", "cr")
    ref = str(src.get("ref", ""))
    if doc == "cr":
        text = judge.cr_rules().get(ref)
        return (text, None) if text is not None else (None, f"CR {ref} doesn't exist in the current CR")
    if doc in lookup.DOCS:
        if not (lookup.DOCS_DIR / f"{doc}.json").exists():
            return None, f"the {lookup.DOCS[doc]} isn't downloaded (python scripts/sources.py update {doc})"
        section = lookup.doc_section(doc, ref)
        return (section["text"], None) if section else (None, f"{doc.upper()} {ref!r} doesn't name one section")
    if doc == "oracle":
        found = oracle_text(ref)
        return (found[1], None) if found else (None, f"couldn't fetch {ref}'s Oracle text")
    return None, None  # quoted from elsewhere (a ruling, a format file): the excerpt is the text


def quoted(excerpt: str, text: str) -> bool:
    return " ".join(excerpt.split()).lower() in " ".join(text.split()).lower()


def pin(fields: dict) -> list[str]:
    """Check and pin every source in an event, as judge.py pins a ruling's citations. Returns the problems."""
    problems = []
    for label, src in sources_in(fields):
        src.setdefault("doc", "cr")
        if src["doc"] == "oracle":
            found = oracle_text(str(src.get("ref", "")))
            if not found:
                problems.append(f"{label}: couldn't fetch {src.get('ref')}'s Oracle text to pin it")
                continue
            src["ref"], text = found
            src.setdefault("excerpt", text[:300])
            if not quoted(src["excerpt"], text):
                problems.append(f"{label}: the quote isn't in {src['ref']}'s Oracle text")
            src["text_sha256"] = judge.sha256_text(text)
            src.setdefault("level", 1)
            continue
        errors = judge.validate_citation(src, label)
        if errors:
            problems += errors
            continue
        judge.pin_citation(src)
        text, _ = source_text(src)
        if text is not None and not quoted(src["excerpt"], text):
            problems.append(f"{label}: the quote isn't in {src['doc'].upper()} {src['ref']}")
        if src["doc"] == "ruling" and not official_ruling_with(src["excerpt"]):
            problems.append(f"{label}: no official ruling in the index says this")
    return problems


def verify_source(src: dict) -> str | None:
    """None if the source still says what it was pinned to say; otherwise what's wrong."""
    doc = src.get("doc", "cr")
    where = f"{doc.upper()} {src.get('ref')}"
    text, missing = source_text(src)
    if missing:
        return missing
    if text is None:
        if doc == "ruling":
            if not official_ruling_with(src.get("excerpt", "")):
                return "no official ruling in the index says this"
            return None if judge.sha256_text(src.get("excerpt", "")) == src.get("text_sha256") else "the quote was edited after it was pinned"
        return f"{where} isn't a source the verifier can check"
    if judge.sha256_text(text) != src.get("text_sha256"):
        return f"{where} has changed since it was pinned"
    if not quoted(src.get("excerpt", ""), text):
        return f"the quote isn't in {where}"
    return None


def verify_steps(label: str, steps: list) -> list[str]:
    problems = []
    for st in steps or []:
        if isinstance(st.get("source"), dict):
            why = verify_source(st["source"])
            if why:
                problems.append(f"{label} step {st.get('id')}: {why}")
        elif label == "case" and not st.get("stipulation"):
            problems.append(f"case step {st.get('id')}: an assumption, with no source")
    return problems


def overridden_by_level_1(refutation: dict) -> bool:
    return refutation.get("ground") == "overridden" and any(
        (st.get("source") or {}).get("doc") in LEVEL_1_DOCS for st in refutation.get("steps") or [])


def sets_case(e: dict) -> bool:
    return e["type"] in ("brief", "edit", "reopen") or (e["type"] == "answer" and bool(e.get("case")))


def case_before(events: list[dict], seq: int) -> dict:
    return [e for e in events if e["seq"] < seq and sets_case(e)][-1]["case"]


def round_filings(events: list[dict], n: int, before: int) -> dict[int, dict]:
    """Judge -> their filing in the attack round that ended before event `before`. A round starts after the
    user's confirm or the verifier's report on the answers (a reopened challenge starts again at round 1)."""
    start = max(e["seq"] for e in events if e["seq"] < before and
                (e["type"] == "confirm" or (e["type"] == "report" and e["stage"] == "answers")))
    return {int(e["actor"].removeprefix("judge-")): e for e in events
            if e["type"] == "file" and e["round"] == n and start < e["seq"] < before}


def build_report(cid: str, state: dict) -> dict:
    """The verifier's report for the round in progress, from the event files."""
    events = events_in_order(cid)
    n = state["round"]
    case = events[state["case_seq"]]["case"]
    notes, standing, conflict = [], [], False
    if state["state"] == "verify":
        # Every refutation whose sources all check stands, until the user answers it.
        for k, filing in sorted(round_filings(events, n, len(events)).items()):
            for i, r in enumerate(filing["refutations"], 1):
                problems = verify_steps(f"judge {k}'s refutation {i}", r.get("steps"))
                if problems:
                    notes += problems
                else:
                    standing.append({"judge": k, "index": i})
                    conflict = conflict or overridden_by_level_1(r)
        stage = "attack"
    else:
        # A standing refutation falls only to a reply that checks: a rebuttal whose sources verify, or a fix
        # that changes or removes the step it attacked.
        answer = next(e for e in reversed(events) if e["type"] == "answer")
        attack_report = next(e for e in reversed(events) if e["type"] == "report" and e["stage"] == "attack")
        filings = round_filings(events, n, attack_report["seq"])
        replies = {(rp["judge"], rp["index"]): rp for rp in answer["replies"]}
        old_case = case_before(events, answer["seq"])
        for slot in attack_report["standing"]:
            rp = replies[(slot["judge"], slot["index"])]
            refutation = filings[slot["judge"]]["refutations"][slot["index"] - 1]
            holds = False
            if rp["kind"] == "rebut":
                problems = verify_steps(f"the reply to judge {slot['judge']}'s refutation {slot['index']}", rp.get("steps"))
                notes += problems
                holds = not problems and any(isinstance(st.get("source"), dict) for st in rp.get("steps") or [])
            elif rp["kind"] == "fix" and answer.get("case"):
                def step(c):
                    return next((st for st in c["steps"] if st["id"] == refutation["target"]), None)
                holds = step(case) != step(old_case)
            if not holds:
                standing.append(slot)
                conflict = conflict or overridden_by_level_1(refutation)
        stage = "answers"
    case_problems = verify_steps("case", case["steps"])
    notes += case_problems
    return {"type": "report", "round": n, "stage": stage, "passed": not case_problems, "level1_conflict": conflict,
            "standing": standing, "notes": notes}


# --- commands --------------------------------------------------------------------------------


NEXT = {
    "draft": "The clerk writes the brief in the proof standard: challenge.py brief {id} case.json",
    "briefed": "The user confirms the brief (challenge.py confirm {id} --user-said ...) or corrects it (edit)",
    "attack": "Round {round}: {waiting} still to file. Each convened judge files refutations or concedes (challenge.py add {id} "
              "filing.json --as judge-<k>). They can't see each other's filings until all have filed. After a revision "
              "only the judges whose refutation it answered are convened; the others' concessions stand for now",
    "verify": "The verifier checks round {round}'s refutations: challenge.py verify {id}",
    "answer": "The user answers each verified refutation still standing ({standing}): concede, fix the case, or "
              "rebut (challenge.py add {id} answer.json --as user)",
    "verify-answers": "The verifier checks the user's answers to round {round}: challenge.py verify {id}",
    "voting": "The judges settle on the case as it now stands, blind to each other's positions; {waiting} still to "
              "settle (a judge's concession on this very case already counts). Each vote needs its reasoning and "
              "evidence (challenge.py add {id} vote.json --as judge-<k>)",
    "drafting": "All five are settled and convinced. {waiting} writes the Opinion of the Court: the holding (the rule's "
                "text), the reasoning with pinned sources, and the case's stipulations (challenge.py add {id} "
                "opinion.json --as judge-<k>)",
    "joining": "The draft opinion is out; {waiting} still to answer it, blind to each other. Each joins, concurs in the "
               "judgment only, or dissents, with reasoning and evidence (challenge.py add {id} response.json --as "
               "judge-<k>). The rule is introduced only if all five join",
    "open": "Open: the user can return with new facts or sources (a reopen event), keep it as a house rule, or "
            "withdraw it",
}


def status_text(cid: str, state: dict) -> str:
    if not state.get("ok"):
        return f"{cid}\n{describe_failure(state)}"
    lines = [f"{cid}: {state['state']}" + (f", round {state['round']}" if state.get("round") else "") +
             f" ({state['panel']} panel)"]
    if state.get("why"):
        lines.append(f"Why: {state['why']}")
    if state.get("revision"):
        lines.append(f"The opinion is on revision {state['revision']} (at most 2).")
    if state["state"] in ("refuted", "open") and (CHALLENGES_DIR / cid / "record" / "per-curiam.json").exists():
        lines.append(f"A per curiam record of the judges' positions is in challenges/{cid}/record/per-curiam.json.")
    if state["settled"]:
        lines.append("Settled: nothing more happens." if state["state"] != "refuted" else
                     "Settled. The user may still keep the case as a house rule (add a house-rule event).")
    else:
        ks = [a.removeprefix("judge-") for a in state["next"]]
        waiting = f"judge {ks[0]}" if len(ks) == 1 else f"judges {', '.join(ks[:-1])} and {ks[-1]}"
        standing = ", ".join(f"judge {s['judge']}'s refutation {s['index']}" for s in state.get("standing", []))
        lines.append("Next: " + NEXT[state["state"]].format(id=cid, round=state.get("round"), waiting=waiting,
                                                            standing=standing or "none"))
        lines.append("Owed by: " + ", ".join(state["next"]))
    return "\n".join(lines)


def load_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        judge.die(f"Couldn't read {path}: {err}")


def pinned(fields: dict) -> dict:
    problems = pin(fields)
    if problems:
        judge.die("The sources don't check:\n" + "\n".join(f"- {p}" for p in problems))
    return fields


def cmd_open(args) -> int:
    cid, state = propose(None, "user", {"type": "open", "statement": args.statement, "panel": args.panel},
                         f"Open a challenge: {args.statement[:60]}", words=args.statement)
    print(cid)
    print(status_text(cid, state))
    return 0


def cmd_brief(args) -> int:
    fields = pinned({"type": "brief", "case": load_json(args.case)})
    _, state = propose(args.id, "clerk", fields, "The clerk's brief")
    print(status_text(args.id, state))
    return 0


def cmd_edit(args) -> int:
    fields = pinned({"type": "edit", "case": load_json(args.case), "words": args.user_said})
    _, state = propose(args.id, args.actor, fields, "Correct the brief", words=args.user_said)
    print(status_text(args.id, state))
    return 0


def cmd_confirm(args) -> int:
    _, state = propose(args.id, "user", {"type": "confirm", "words": args.user_said}, "The user confirms the brief",
                       words=args.user_said)
    print(status_text(args.id, state))
    return 0


def cmd_add(args) -> int:
    fields = pinned(load_json(args.event))
    for key in ("v", "seq", "prev", "actor", "device", "time"):
        fields.pop(key, None)
    if "type" not in fields:
        judge.die("The event needs a \"type\" (file, answer, vote, opinion, respond, house-rule, reopen...).")
    _, state = propose(args.id, args.actor, fields, f"{args.actor}: {fields['type']}", words=fields.get("words"))
    print(status_text(args.id, state))
    return 0


def cmd_verify(args) -> int:
    state = replay(args.id)
    if not state.get("ok") or state["state"] not in ("verify", "verify-answers"):
        judge.die(status_text(args.id, state) + "\nThere is nothing for the verifier to check now.")
    report = build_report(args.id, state)
    _, new = propose(args.id, "verifier", report, f"Verifier's report, round {report['round']} ({report['stage']})")
    print(f"Case {'passes' if report['passed'] else 'fails'}; {len(report['standing'])} refutation(s) standing"
          + (", with a level 1 conflict" if report["level1_conflict"] else ""))
    for note in report["notes"]:
        print(f"- {note}")
    print(status_text(args.id, new))
    return 0


def cmd_status(args) -> int:
    state = replay(args.id)
    print(json.dumps(state, indent=2) if args.json else status_text(args.id, state))
    return 0


def cmd_show(args) -> int:
    if args.judge is None:
        shown = [json.loads(r) for r in raws(args.id)]
    else:
        view = core(["view", "--judge", str(args.judge)], {"events": raws(args.id)})
        if not view.get("ok"):
            judge.die(describe_failure(view))
        shown = [json.loads(r) for r in view["events"]]
    print(json.dumps(sorted(shown, key=lambda e: e["seq"]), indent=2, ensure_ascii=False))
    return 0


def cmd_list(args) -> int:
    if not CHALLENGES_DIR.exists():
        print("No challenges yet.")
        return 0
    for folder in sorted(p for p in CHALLENGES_DIR.iterdir() if p.is_dir() and ID.fullmatch(p.name)):
        state = replay(folder.name)
        if state.get("ok"):
            owed = "" if state["settled"] else f"; next: {', '.join(state['next'])}"
            print(f"{folder.name}  {state['state']}{owed}")
        else:
            print(f"{folder.name}  {'fork' if 'fork' in state else 'unreadable'}")
    return 0


def cmd_withdraw(args) -> int:
    _, state = propose(args.id, "user", {"type": "withdraw", "words": args.user_said}, "The user withdraws it",
                       words=args.user_said)
    print(status_text(args.id, state))
    return 0


def cmd_resolve(args) -> int:
    """Keep one branch of a fork; move the other branch's files to discarded/, never deleting them."""
    state = replay(args.id)
    if "fork" not in state:
        judge.die("The challenge isn't forked; there's nothing to resolve.")
    folder = challenge_dir(args.id)
    files = {p.name: p for p in event_files(args.id)}
    if args.keep not in files:
        judge.die(f"No event file {args.keep} in {args.id}.")
    hashes = {name: hashlib.sha256(p.read_bytes()).hexdigest() for name, p in files.items()}
    prev = {name: json.loads(read_raw(p)).get("prev") for name, p in files.items()}
    kept_prev = prev[args.keep]
    drop = {name for name in files if prev[name] == kept_prev and name != args.keep}
    if not drop:
        judge.die(f"{args.keep} isn't one of the forked events.")
    while True:  # and everything built on a dropped event
        more = {name for name in files if prev[name] in {hashes[d] for d in drop}} - drop
        if not more:
            break
        drop |= more
    (folder / "discarded").mkdir(exist_ok=True)
    for name in sorted(drop):
        shutil.move(str(files[name]), str(folder / "discarded" / name))
    judge.commit(f"{args.id}: settle a fork, keeping {args.keep}", drafted_by="user", decided_by=f'user ("{args.user_said}")')
    print(f"Kept {args.keep}; moved {len(drop)} event file(s) to discarded/.")
    print(status_text(args.id, replay(args.id)))
    return 0


def cmd_trace(args) -> int:
    """The id recomputes from the opening event, the chain is unbroken, and any rule file matches its challenge."""
    files = event_files(args.id)
    problems = []
    for p in files:
        try:
            e = json.loads(read_raw(p))
            expected = f"{e['seq']:04d}-{e['actor']}-{e['device']}.json"
        except (ValueError, KeyError, TypeError):
            problems.append(f"{p.name} isn't an event file")
            continue
        if p.name != expected:
            problems.append(f"{p.name} holds event {expected}: the file was renamed or its contents swapped")
    opening = next((p for p in files if p.name.startswith("0000-")), None)
    if opening is None:
        problems.append("there's no opening event (0000-...)")
    else:
        event = json.loads(read_raw(opening))
        expected = f"challenge-{event['time'][:10].replace('-', '')}-{hashlib.sha256(opening.read_bytes()).hexdigest()[:12]}"
        if expected != args.id:
            problems.append(f"the opening event gives the id {expected}, not {args.id}")
    state = replay(args.id)
    if not state.get("ok"):
        problems.append(describe_failure(state))
    rule = next((p for p in (RULES_DIR / f"{args.id}.json", RULES_DIR / f"house-{args.id}.json") if p.exists()),
                RULES_DIR / f"{args.id}.json")
    if rule.exists():
        data = json.loads(rule.read_text(encoding="utf-8"))
        if data.get("challenge") != args.id:
            problems.append(f"{rule.name} names the challenge {data.get('challenge')}")
        if state.get("ok") and data.get("final_hash") != state.get("head"):
            problems.append(f"{rule.name} is pinned to {data.get('final_hash')}, but the challenge ends at {state.get('head')}")
        want = "house-rule" if rule.name.startswith("house-") else "introduced"
        if state.get("ok") and state.get("state") != want:
            problems.append(f"{rule.name} exists, but the challenge is {state.get('state')}, not {want}")
    if problems:
        print(f"{args.id}: doesn't trace")
        for p in problems:
            print(f"- {p}")
        return 1
    print(f"{args.id}: traces: the id recomputes from the opening event, the chain of {len(files)} events is unbroken"
          + (", and the rule file matches its final event" if rule.exists() else ""))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Challenges: the only way a rule enters the record.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("open", help="open a challenge with the user's case, in their own words")
    p.add_argument("--statement", required=True)
    p.add_argument("--panel", choices=["independent", "single-agent"], default="independent")
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("brief", help="the clerk's brief: the case in the proof standard")
    p.add_argument("id")
    p.add_argument("case")
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("edit", help="correct the brief, with the user's words")
    p.add_argument("id")
    p.add_argument("case")
    p.add_argument("--user-said", required=True)
    p.add_argument("--as", dest="actor", choices=["user", "clerk"], default="user")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("confirm", help="the user confirms the brief")
    p.add_argument("id")
    p.add_argument("--user-said", required=True)
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser("add", help="add an event: a judge's filing or vote, the user's answer, a reopen...")
    p.add_argument("id")
    p.add_argument("event", help="a JSON file with the event's type and fields")
    p.add_argument("--as", dest="actor", required=True, help="user, clerk, verifier or judge-<k>")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("verify", help="check every citation in the round, and file the verifier's report")
    p.add_argument("id")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("status", help="the state, the next action and who owes it")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("show", help="the events, or what one judge may see")
    p.add_argument("id")
    p.add_argument("--judge", type=int)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("list", help="every challenge and its state")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("withdraw", help="the user withdraws a challenge")
    p.add_argument("id")
    p.add_argument("--user-said", required=True)
    p.set_defaults(func=cmd_withdraw)

    p = sub.add_parser("resolve", help="settle a fork by keeping one of the forked events")
    p.add_argument("id")
    p.add_argument("--keep", required=True, help="the event file to keep, e.g. 0004-judge-2-laptop.json")
    p.add_argument("--user-said", required=True)
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("trace", help="check a challenge's id, its chain and its rule file")
    p.add_argument("id")
    p.set_defaults(func=cmd_trace)

    args = parser.parse_args()
    # With a remote store set, challenges sync like the rest of the record (judge.py's automatic sync).
    name = f"challenge {args.command}"
    if name in judge.READS:
        judge.auto_sync(name)  # bring other devices' events in before reading
    status = args.func(args)
    if name in judge.WRITES and status == 0:
        judge.auto_sync(name)  # send this device's event out
    return status


if __name__ == "__main__":
    sys.exit(main())
