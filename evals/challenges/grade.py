#!/usr/bin/env python3
"""Grade a finished challenge from the record: its final state against the case's expected one, and what the
verifier made of every refutation. Prints one JSON object; exits 0 when the state is the expected one.

    python evals/challenges/grade.py urborg-still-swamps --home <record> [--id challenge-...]

The record is a BISHOP_AND_BARRISTER_HOME used for that one run. Graders 01 and 02 of each case come from here;
03 and 04 are read from the report to the user.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHALLENGE = HERE.parent.parent / "plugin/skills/bishop-and-barrister" / "scripts" / "challenge.py"


def expected_state(case: str) -> str:
    text = (HERE / case / "case.yaml").read_text(encoding="utf-8")
    return re.search(r"^expected_state: (\S+)", text, re.M).group(1)


def run(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "BISHOP_AND_BARRISTER_HOME": str(home)}
    return subprocess.run([sys.executable, str(CHALLENGE), *args], capture_output=True, text=True, encoding="utf-8", env=env)


def grade(case: str, home: Path, cid: str | None = None) -> dict:
    folders = sorted(p.name for p in (home / "challenges").iterdir() if p.is_dir()) if (home / "challenges").exists() else []
    cid = cid or (folders[-1] if folders else None)
    want = expected_state(case)
    if not cid:
        return {"case": case, "expected": want, "state": None, "outcome_ok": False, "why": "no challenge in the record"}
    status = run(home, "status", cid, "--json")
    state = json.loads(status.stdout) if status.returncode == 0 else {"ok": False}
    events = sorted((json.loads(p.read_text(encoding="utf-8")) for p in (home / "challenges" / cid).glob("*.json")),
                    key=lambda e: e["seq"])
    filed = sum(len(e["refutations"]) for e in events if e["type"] == "file")
    attack_reports = [e for e in events if e["type"] == "report" and e["stage"] == "attack"]
    verified = sum(len(r["standing"]) for r in attack_reports)
    dropped = [n for r in attack_reports for n in r.get("notes", []) if "refutation" in n]
    votes = [e for e in events if e["type"] == "vote"]
    final = state.get("state")
    rule_file = {"introduced": home / "rules" / f"{cid}.json", "house-rule": home / "rules" / f"house-{cid}.json"}.get(final)
    traces = run(home, "trace", cid).returncode == 0
    return {
        "case": case, "challenge": cid, "expected": want, "state": final, "why": state.get("why"),
        "outcome_ok": final == want and traces and (rule_file is None or rule_file.exists()),
        "rounds": max([e["round"] for e in events if e["type"] == "file"] or [0]),
        "refutations_filed": filed, "refutations_verified": verified, "refutations_dropped": dropped,
        "concessions": sum(1 for e in events if e["type"] == "file" and not e["refutations"]),
        "votes": [{"judge": e["actor"], "convinced": e["convinced"], "reason": e["reason"]} for e in votes],
        "every_vote_has_a_reason": all(v["reason"].strip() for v in votes),
        "opinion_drafts": sum(1 for e in events if e["type"] == "opinion"),
        "responses": {s: sum(1 for e in events if e["type"] == "respond" and e["stance"] == s)
                      for s in ("join", "concur", "dissent")},
        "traces": traces, "events": len(events),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case")
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--id")
    args = parser.parse_args()
    result = grade(args.case, args.home, args.id)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["outcome_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
