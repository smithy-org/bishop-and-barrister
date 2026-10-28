#!/usr/bin/env python3
"""Loaders for the recorded challenge runs and the eval cases. Read-only, standard library only.

Paths are read from the environment so that the scripts run on any checkout:
  BAB_WORKSPACE  the folder holding challenges-2, challenges-3 and challenges-4
                 (default: ../bishop-and-barrister-workspace next to the repository)
  BAB_REPO       the repository whose evals/ folder holds the cases (default: this one)
  BAB_MAIN       a checkout that has reference/ (needed only for rule text; default: BAB_REPO)
"""
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("BAB_REPO") or HERE.parent.parent)
WORKSPACE = Path(os.environ.get("BAB_WORKSPACE") or REPO.parent / "bishop-and-barrister-workspace")
MAIN = Path(os.environ.get("BAB_MAIN") or REPO)
HOME = WORKSPACE / "challenges-4" / "base-home"
CHALLENGE_ROUNDS = ["challenges-2", "challenges-3", "challenges-4"]


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def front_matter_body(text):
    text = text.replace("\r\n", "\n")
    m = re.match(r"^---\n.*?\n---\n(.*)$", text, re.S)
    return (m.group(1) if m else text).strip()


def expected_state(case):
    t = (REPO / "evals" / "challenges" / case / "case.yaml").read_text(encoding="utf-8")
    return re.search(r"expected_state:\s*(\S+)", t).group(1)


def norm_state(s):
    return {"house-rule": "refuted"}.get(s, s)


def challenge_statement(case):
    return front_matter_body((REPO / "evals" / "challenges" / case / "prompt.md").read_text(encoding="utf-8"))


def load_runs():
    """All recorded runs with a complete event record: {key, round, case, events, final_state, expected}."""
    runs = []
    for rnd in CHALLENGE_ROUNDS:
        for d in sorted(glob.glob(str(WORKSPACE / rnd / "*" / "panel" / "home" / "challenges" / "*"))):
            d = Path(d)
            case = d.parents[3].name
            events = [read_json(f) for f in sorted(d.glob("*.json"))]
            grade = d.parents[2] / "grade.json"
            state = read_json(grade).get("state") if grade.exists() else None
            if not events or state is None:
                continue
            runs.append({"key": "%s/%s" % (rnd, case), "round": rnd, "case": case, "events": events,
                         "final_state": norm_state(state), "raw_state": state,
                         "expected": norm_state(expected_state(case))})
    return runs


def final_case(run):
    case = None
    for e in run["events"]:
        if e["type"] in ("brief", "edit", "answer") and isinstance(e.get("case"), dict):
            case = e["case"]
    return case


def walk_sources(o, out):
    if isinstance(o, dict):
        if "doc" in o and "excerpt" in o and "ref" in o:
            out.append((o["doc"], o["ref"], o["excerpt"]))
        for v in o.values():
            walk_sources(v, out)
    elif isinstance(o, list):
        for v in o:
            walk_sources(v, out)


def cited_sources(runs):
    """Every (doc, ref, excerpt) the judges and clerk cited in these runs, most-cited first."""
    from collections import Counter
    c = Counter()
    for r in runs:
        found = []
        walk_sources(r["events"], found)
        for s in found:
            c[s] += 1
    return [s for s, _ in c.most_common()]


def src_label(doc, ref):
    if doc == "oracle":
        return "Oracle text of %s" % ref
    if doc == "ruling":
        return "Official ruling (%s)" % ref
    return "%s %s" % (doc.upper(), ref)


def render_source(s):
    return '[%s] "%s"' % (src_label(s[0], s[1]), s[2])


def render_case(case):
    """The case as the judges see it: rule, applies_when, facts, steps with their quotes."""
    facts = {f["id"]: f["text"] for f in case.get("facts", [])}
    steps = {s["id"]: s for s in case.get("steps", [])}
    lines = ["PROPOSED RULE: " + case.get("rule", "")]
    for a in case.get("applies_when", []) or []:
        lines.append("APPLIES WHEN: " + a)
    lines.append("CLAIM CHALLENGES: " + str(case.get("challenges", "")))
    lines.append("FACTS:")
    for i, t in facts.items():
        lines.append("  F%s: %s" % (i, t))
    lines.append("DERIVATION:")
    for s in case.get("steps", []):
        prem = ", ".join(s.get("premises", []))
        if s.get("stipulation"):
            kind = "STIPULATION (the rule's own new content, no source)"
        elif s.get("assumption"):
            kind = "ASSUMPTION (no source)"
        else:
            src = s.get("source", {})
            kind = "per %s" % render_source((src.get("doc", ""), src.get("ref", ""), src.get("excerpt", "")))
        lines.append("  Step %s (from %s) %s => %s" % (s["id"], prem, kind, s["conclusion"]))
    return "\n".join(lines)


def last_positions(run, cap=650):
    """Each judge's last filing: concession text or refutations, and the evidence quoted in a last vote.

    The verdict flag and the reason of a vote are left out on purpose; only arguments and quoted sources remain.
    """
    last_file, last_vote = {}, {}
    for e in run["events"]:
        a = e.get("actor", "")
        if not a.startswith("judge-"):
            continue
        if e["type"] == "file":
            last_file[a] = e
        elif e["type"] == "vote":
            last_vote[a] = e
    out = []
    for a in sorted(last_file):
        e = last_file[a]
        parts = []
        if e.get("concedes"):
            parts.append("conceded, no refutation left: " + str(e["concedes"])[:cap])
            for ev in e.get("concede_evidence") or []:
                if isinstance(ev, dict) and "excerpt" in ev:
                    parts.append("  evidence " + render_source((ev.get("doc", ""), ev.get("ref", ""), ev["excerpt"])))
        for r in e.get("refutations") or []:
            parts.append("refutes step %s (%s): %s" % (r.get("target"), r.get("ground"), str(r.get("argument", ""))[:cap]))
        v = last_vote.get(a)
        if v:
            for ev in v.get("evidence") or []:
                if isinstance(ev, dict) and "excerpt" in ev:
                    parts.append("  settling-pass evidence " + render_source((ev.get("doc", ""), ev.get("ref", ""), ev["excerpt"])))
        out.append("%s: %s" % (a, "\n  ".join(parts) if parts else "(nothing filed)"))
    reps = [e for e in run["events"] if e["type"] == "report"]
    if reps:
        r = reps[-1]
        out.append("VERIFIER (last report): %d refutations still standing; notes: %s"
                   % (len(r.get("standing") or []), "; ".join(r.get("notes") or []) or "none"))
    return "\n".join(out)


def rule_texts(numbers, doc=None):
    """Rule text from plugin/skills/bishop-and-barrister/scripts/lookup.py in the main checkout, one dict number -> text."""
    script = MAIN / "plugin/skills/bishop-and-barrister" / "scripts" / "lookup.py"
    out = {}
    for n in numbers:
        cmd = [sys.executable, str(script)] + (["--doc", doc] if doc else []) + ["rule", n]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, BISHOP_AND_BARRISTER_HOME=str(HOME), PYTHONIOENCODING="utf-8"))
        if r.returncode == 0 and r.stdout.strip():
            out[n] = r.stdout.strip()
    return out
