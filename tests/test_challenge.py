"""Tests for scripts/challenge.py, run through its command line against a temporary record.

They need the challenge core: set BISHOP_AND_BARRISTER_CHALLENGE_BIN to a bab-challenge binary (built with
`lake build` in challenge/, or downloaded from a release or a CI run). Without one they're skipped. They use
a small fixture Comprehensive Rules file and BISHOP_AND_BARRISTER_OFFLINE, so nothing touches the network.

    BISHOP_AND_BARRISTER_CHALLENGE_BIN=challenge/.lake/build/bin/bab-challenge python -m unittest discover -s tests
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHALLENGE = Path(__file__).resolve().parent.parent / "scripts" / "challenge.py"
CORE = os.environ.get("BISHOP_AND_BARRISTER_CHALLENGE_BIN")
HAVE_CORE = bool(CORE) and Path(CORE).exists()

CR = """Magic: The Gathering Comprehensive Rules

These rules are effective as of September 25, 2026.

Contents
100. General

100. General

100.1. These Magic rules apply to any Magic game with two or more players.

100.2. To play, each player needs their own deck of traditional Magic cards.

103. Starting the Game

103.1. At the start of a game, the players determine which one of them will choose who takes the first turn.

103.1a In a match of several games, the loser of the previous game chooses who takes the first turn.

Glossary

Credits
"""


def source(ref, excerpt=None):
    s = {"doc": "cr", "ref": ref}
    if excerpt:
        s["excerpt"] = excerpt
    return s


def step(n, premises, src, assumption=False):
    return {"id": n, "premises": premises, "source": src, "assumption": assumption, "conclusion": f"conclusion {n}"}


def case(steps=None):
    return {
        "facts": [{"id": 1, "text": "Three players; game 2 of a match"}],
        "open_questions": [],
        "rule": "The player who lost game 1 chooses who plays first in game 2",
        "applies_when": ["a three-player match"],
        "challenges": "none: a gap",
        "steps": steps or [step(1, ["F1"], source("103.1a", "the loser of the previous game chooses")),
                           step(2, ["F1", "S1"], source("103.1"))],
    }


CONCEDE = {"type": "file", "round": 1, "refutations": [], "concedes": "I can't refute it"}
REFUTE = {"type": "file", "round": 1, "refutations": [{
    "target": 1, "ground": "counterexample", "argument": "It says nothing about three players",
    "steps": [step(1, ["C1"], source("100.1"))]}]}
VOTE = {"type": "vote", "convinced": True, "reason": "step 1 settled it"}
ANSWER = {"type": "answer", "round": 1, "words": "103.1a covers any match", "replies": [{
    "judge": 1, "index": 1, "kind": "rebut", "words": "103.1a covers any match",
    "steps": [step(1, ["C1"], source("103.1a"))]}]}


@unittest.skipUnless(HAVE_CORE, "set BISHOP_AND_BARRISTER_CHALLENGE_BIN to a bab-challenge binary")
class ChallengeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.cr = self.root / "MagicCompRules.txt"
        self.cr.write_text(CR, encoding="utf-8")
        self.env = {**os.environ, "BISHOP_AND_BARRISTER_HOME": str(self.home), "BISHOP_AND_BARRISTER_CR": str(self.cr),
                    "BISHOP_AND_BARRISTER_OFFLINE": "1", "BISHOP_AND_BARRISTER_DEVICE": "laptop",
                    "BISHOP_AND_BARRISTER_CHALLENGE_BIN": str(Path(CORE).resolve())}

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, str(CHALLENGE), *args], capture_output=True, text=True, encoding="utf-8",
                              env=env or self.env)

    def ok(self, *args, env=None):
        result = self.run_cli(*args, env=env)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def refused(self, *args, env=None):
        result = self.run_cli(*args, env=env)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.stderr + result.stdout

    def write(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def status(self, cid, env=None):
        return json.loads(self.ok("status", cid, "--json", env=env))

    def open_briefed(self, env=None, panel="independent"):
        cid = self.ok("open", "--statement", "Who chooses who plays first in game 2 of a three-player match?",
                      "--panel", panel, env=env).split()[0]
        self.ok("brief", cid, self.write("case.json", case()), env=env)
        return cid

    def to_attack(self):
        cid = self.open_briefed()
        self.ok("confirm", cid, "--user-said", "Yes, that's my case")
        return cid

    def file(self, cid, k, event=CONCEDE, env=None):
        return self.ok("add", cid, self.write(f"filing-{k}.json", event), "--as", f"judge-{k}", env=env)

    def git_log(self):
        return subprocess.run(["git", "-C", str(self.home), "log", "--format=%B%n---"], capture_output=True, text=True,
                              encoding="utf-8").stdout

    # --- the paths -------------------------------------------------------------------------

    def test_a_unanimous_panel_introduces_the_rule(self):
        cid = self.to_attack()
        self.assertRegex(cid, r"^challenge-\d{8}-[0-9a-f]{12}$")
        for k in range(1, 8):
            self.file(cid, k)
        out = self.ok("verify", cid)
        self.assertIn("Case passes; 0 refutation(s) standing", out)
        self.assertEqual(self.status(cid)["state"], "voting")
        for k in range(1, 8):
            self.ok("add", cid, self.write("vote.json", VOTE), "--as", f"judge-{k}")
        self.assertEqual(self.status(cid)["state"], "introduced")
        self.assertIn("traces", self.ok("trace", cid))
        log = self.git_log()
        self.assertIn(f"{cid}: Open a challenge", log)
        self.assertIn('Decided-by: user ("Yes, that\'s my case")', log)
        self.assertIn("Drafted-by: judge-7", log)

    def test_the_brief_pins_its_sources(self):
        cid = self.open_briefed()
        brief = json.loads((self.home / "challenges" / cid / "0001-clerk-laptop.json").read_text(encoding="utf-8"))
        src = brief["case"]["steps"][1]["source"]
        self.assertEqual(len(src["text_sha256"]), 64)
        self.assertIn("determine which one of them", src["excerpt"])

    def test_a_standing_refutation_goes_to_the_user_then_round_2(self):
        cid = self.to_attack()
        self.file(cid, 1, REFUTE)
        for k in range(2, 8):
            self.file(cid, k)
        self.ok("verify", cid)
        state = self.status(cid)
        self.assertEqual(state["state"], "answer")
        self.assertEqual(state["standing"], [{"judge": 1, "index": 1}])
        self.assertIn("answers each verified refutation", self.ok("status", cid))
        self.ok("add", cid, self.write("answer.json", ANSWER), "--as", "user")
        self.ok("verify", cid)
        state = self.status(cid)
        self.assertEqual((state["state"], state["round"]), ("attack", 2))

    def test_a_single_agent_panel_cannot_introduce(self):
        cid = self.open_briefed(panel="single-agent")
        self.ok("confirm", cid, "--user-said", "yes")
        for k in range(1, 8):
            self.file(cid, k)
        self.ok("verify", cid)
        for k in range(1, 8):
            self.ok("add", cid, self.write("vote.json", VOTE), "--as", f"judge-{k}")
        state = self.status(cid)
        self.assertEqual(state["state"], "open")
        self.assertIn("single-agent", state["why"])

    def test_withdraw(self):
        cid = self.to_attack()
        self.refused("withdraw", cid, "--user-said", "never mind")  # only where the user acts
        self.file(cid, 1, REFUTE)
        for k in range(2, 8):
            self.file(cid, k)
        self.ok("verify", cid)
        self.ok("withdraw", cid, "--user-said", "never mind")
        self.assertEqual(self.status(cid)["state"], "withdrawn")
        self.assertIn("isn't allowed", self.refused("add", cid, self.write("answer.json", ANSWER), "--as", "user")
                      .replace("Refused", "isn't allowed"))

    # --- refusals --------------------------------------------------------------------------

    def test_a_forged_quote_is_refused(self):
        cid = self.ok("open", "--statement", "a case").split()[0]
        bad = case([step(1, ["F1"], source("103.1", "the youngest player always goes first"))])
        self.assertIn("the quote isn't in CR 103.1", self.refused("brief", cid, self.write("case.json", bad)))

    def test_a_rule_that_does_not_exist_is_refused(self):
        cid = self.ok("open", "--statement", "a case").split()[0]
        bad = case([step(1, ["F1"], source("999.9"))])
        self.assertIn("doesn't exist in the current CR", self.refused("brief", cid, self.write("case.json", bad)))

    def test_a_step_with_no_source_is_refused(self):
        cid = self.ok("open", "--statement", "a case").split()[0]
        bad = case([step(1, ["F1"], None)])
        self.assertIn("no source; quote one, or label the step an assumption",
                      self.refused("brief", cid, self.write("case.json", bad)))

    def test_a_premise_pointing_nowhere_is_refused(self):
        cid = self.ok("open", "--statement", "a case").split()[0]
        bad = case([step(1, ["S3"], source("103.1"))])
        self.assertIn("premise S3 isn't an earlier step", self.refused("brief", cid, self.write("case.json", bad)))

    def test_a_judge_cannot_vote_during_an_attack(self):
        cid = self.to_attack()
        self.assertIn("each judge files refutations or concedes",
                      self.refused("add", cid, self.write("vote.json", VOTE), "--as", "judge-1"))

    def test_a_source_that_changed_fails_the_verifier(self):
        cid = self.to_attack()
        for k in range(1, 8):
            self.file(cid, k)
        self.cr.write_text(CR.replace("the loser of the previous game chooses", "the winner chooses"), encoding="utf-8")
        out = self.ok("verify", cid)
        self.assertIn("Case fails", out)
        self.assertIn("CR 103.1a has changed since it was pinned", out)
        for k in range(1, 8):
            self.ok("add", cid, self.write("vote.json", VOTE), "--as", f"judge-{k}")
        self.assertEqual(self.status(cid)["state"], "refuted")

    # --- forks, the id and trace -------------------------------------------------------------

    def test_a_fork_from_two_devices_pauses_until_the_user_picks(self):
        cid = self.to_attack()
        phone = self.root / "phone"
        subprocess.run(["git", "clone", "-q", str(self.home), str(phone)], check=True)
        phone_env = {**self.env, "BISHOP_AND_BARRISTER_HOME": str(phone), "BISHOP_AND_BARRISTER_DEVICE": "phone"}
        self.file(cid, 1)
        self.file(cid, 2, env=phone_env)
        # The sync: the laptop takes the phone's commits. Different files, so git merges without a conflict.
        subprocess.run(["git", "-C", str(self.home), "pull", "-q", "--no-rebase", "--no-edit", str(phone), "HEAD"],
                       check=True, capture_output=True)
        out = self.ok("status", cid)
        self.assertIn("Two devices acted in the same state", out)
        self.assertIn("0003-judge-1-laptop.json", out)
        self.assertIn("0003-judge-2-phone.json", out)
        self.assertIn("Two devices acted", self.refused("add", cid, self.write("f.json", CONCEDE), "--as", "judge-3"))
        self.ok("resolve", cid, "--keep", "0003-judge-2-phone.json", "--user-said", "keep the phone's")
        state = self.status(cid)
        self.assertEqual((state["state"], state["filed"]), ("attack", [2]))
        self.assertTrue((self.home / "challenges" / cid / "discarded" / "0003-judge-1-laptop.json").exists())

    def test_trace_fails_when_an_event_is_edited_removed_or_reordered(self):
        cid = self.to_attack()
        self.file(cid, 1)
        folder = self.home / "challenges" / cid
        files = sorted(folder.glob("*.json"))
        original = {p: p.read_bytes() for p in files}
        self.assertIn("traces", self.ok("trace", cid))

        files[1].write_bytes(original[files[1]].replace(b"Three players", b"Four players"))
        self.assertIn("don't form a chain", self.run_cli("trace", cid).stdout)
        files[1].write_bytes(original[files[1]])

        files[2].unlink()
        self.assertIn("don't form a chain", self.run_cli("trace", cid).stdout)
        files[2].write_bytes(original[files[2]])

        files[2].write_bytes(original[files[3]])
        files[3].write_bytes(original[files[2]])
        self.assertIn("contents swapped", self.run_cli("trace", cid).stdout)
        files[2].write_bytes(original[files[2]])
        files[3].write_bytes(original[files[3]])

        files[0].write_bytes(original[files[0]].replace(b"game 2", b"game 3"))
        out = self.run_cli("trace", cid).stdout
        self.assertIn("the opening event gives the id", out)
        files[0].write_bytes(original[files[0]])
        self.assertIn("traces", self.ok("trace", cid))

    def introduce(self, cid=None, convinced=lambda k: True):
        cid = cid or self.to_attack()
        for k in range(1, 8):
            self.file(cid, k)
        self.ok("verify", cid)
        for k in range(1, 8):
            vote = {**VOTE, "convinced": convinced(k)}
            self.ok("add", cid, self.write("vote.json", vote), "--as", f"judge-{k}")
        return cid

    def test_an_introduced_challenge_writes_its_rule(self):
        cid = self.introduce()
        state = self.status(cid)
        rule = json.loads((self.home / "rules" / f"{cid}.json").read_text(encoding="utf-8"))
        self.assertEqual((rule["kind"], rule["state"], rule["challenge"]), ("rule", "current", cid))
        self.assertEqual(rule["final_hash"], state["head"])
        self.assertEqual(len(rule["votes"]), 7)
        self.assertEqual(len(rule["verifier_report_sha256"]), 64)
        self.assertEqual(rule["rule"], case()["rule"])
        self.assertIn("Decided-by: panel", self.git_log())
        self.assertIn("the rule file matches its final event", self.ok("trace", cid))

    def test_trace_catches_a_rule_file_swapped_onto_another_challenge(self):
        cid = self.introduce()
        path = self.home / "rules" / f"{cid}.json"
        rule = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**rule, "challenge": "challenge-20260101-000000000000"}), encoding="utf-8")
        self.assertIn("names the challenge challenge-20260101", self.run_cli("trace", cid).stdout)
        path.write_text(json.dumps({**rule, "final_hash": "0" * 64}), encoding="utf-8")
        self.assertIn("is pinned to", self.run_cli("trace", cid).stdout)

    def test_a_rule_is_searched_as_its_own_kind(self):
        judge_py = [sys.executable, str(CHALLENGE.parent / "judge.py")]
        bulk = self.root / "rulings.json"
        bulk.write_text("[]", encoding="utf-8")
        subprocess.run([*judge_py, "build", "--rulings-file", str(bulk)], env=self.env, check=True, capture_output=True)
        cid = self.introduce()
        out = subprocess.run([*judge_py, "search", "loser previous game", "--agent"], env=self.env, capture_output=True,
                             text=True, encoding="utf-8").stdout
        self.assertIn(f'id="{cid}" kind="rule" level="5" state="current"', out)
        self.assertIn("<rule>The player who lost game 1", out)
        self.assertIn(f"challenge.py trace {cid}", out)
        self.assertIn(cid, subprocess.run([*judge_py, "search", "--rule", "103.1a"], env=self.env, capture_output=True,
                                          text=True, encoding="utf-8").stdout)

    def test_a_refuted_challenge_can_be_kept_as_a_house_rule(self):
        cid = self.introduce(convinced=lambda k: k != 5)
        self.assertFalse((self.home / "rules" / f"{cid}.json").exists())
        self.ok("add", cid, self.write("house.json", {"type": "house-rule", "words": "We play it this way anyway"}),
                "--as", "user")
        rule = json.loads((self.home / "rules" / f"house-{cid}.json").read_text(encoding="utf-8"))
        self.assertTrue(rule["house_rule"])
        self.assertEqual(rule["id"], f"house-{cid}")

    def recheck(self):
        return subprocess.run([sys.executable, str(CHALLENGE.parent / "judge.py"), "recheck", "--offline"], env=self.env,
                              capture_output=True, text=True, encoding="utf-8")

    def test_a_rule_whose_source_changed_must_win_again(self):
        cid = self.introduce()
        self.assertIn("still match", self.recheck().stdout)
        self.cr.write_text(CR.replace("chooses who takes the first turn.\n\nGlossary",
                                      "chooses who takes the first turn, unless the match is multiplayer.\n\nGlossary"),
                           encoding="utf-8")
        out = self.recheck().stdout
        self.assertIn(f"Rule {cid} is stale", out)
        path = self.home / "rules" / f"{cid}.json"
        rule = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rule["state"], "reopened")
        again = rule["reopened_by"]
        opening = json.loads(sorted((self.home / "challenges" / again).glob("*.json"))[0].read_text(encoding="utf-8"))
        self.assertEqual(opening["reopens"], cid)
        self.assertEqual(opening["carried"]["case"]["rule"], case()["rule"])
        self.assertEqual(self.status(again)["state"], "draft")
        # A reopened rule isn't reopened twice, and recheck says it's waiting on its challenge.
        self.assertIn(f"Rule {cid} is still unconfirmed: its challenge {again}", self.recheck().stdout)
        self.assertEqual(len(list((self.home / "challenges").iterdir())), 2)

        self.ok("brief", again, self.write("case.json", case()))
        self.ok("confirm", again, "--user-said", "same case, new text")
        self.introduce(again)
        rule = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rule["state"], "current")
        self.assertEqual(rule["renewals"][0]["challenge"], again)
        self.assertFalse((self.home / "rules" / f"{again}.json").exists())

    def test_a_reopened_rule_that_loses_is_retired(self):
        cid = self.introduce()
        self.cr.write_text(CR.replace("the loser of the previous game chooses", "the loser of the previous game "
                                      "chooses, in two-player games"), encoding="utf-8")
        self.recheck()
        path = self.home / "rules" / f"{cid}.json"
        again = json.loads(path.read_text(encoding="utf-8"))["reopened_by"]
        self.ok("withdraw", again, "--user-said", "the new text settles it")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["state"], "retired")

    def test_migrate_turns_reviewed_rulings_into_challenges(self):
        judge_py = [sys.executable, str(CHALLENGE.parent / "judge.py")]
        subprocess.run([*judge_py, "index"], env=self.env, check=True, capture_output=True)
        rulings = self.home / "rulings"
        base = {"question": "Blood Moon and Urborg?", "ruling": "No Swamps.", "agent_summary": "No Swamps.",
                "level": 5, "status": "current",
                "citations": [], "cards": [], "steps": [], "question_type": "interaction"}
        for rid, kind, house in (("aaaa", "reviewed", False), ("bbbb", "unreviewed", False), ("cccc", "reviewed", True)):
            (rulings / f"{rid}.json").write_text(json.dumps({**base, "id": rid, "kind": kind, "house_rule": house}),
                                                 encoding="utf-8")
        (self.home / "deliberation" / "aaaa.jsonl").write_text(
            json.dumps({"by": "user", "decision": "reviewed", "said": "That's right"}) + "\n", encoding="utf-8")
        out = subprocess.run([*judge_py, "migrate"], env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("aaaa: now challenge challenge-", out.stdout)
        self.assertIn("bbbb: set aside (unreviewed)", out.stdout)
        cid = re.search(r"challenge-\d{8}-[0-9a-f]{12}", out.stdout).group(0)
        state = self.status(cid)
        self.assertEqual(state["state"], "draft")
        opening = json.loads(sorted((self.home / "challenges" / cid).glob("*.json"))[0].read_text(encoding="utf-8"))
        self.assertTrue(opening["statement"].startswith("That's right"))
        self.assertEqual(opening["migrated_from"]["deliberation"][0]["said"], "That's right")
        self.assertTrue((self.home / "rulings-migrated" / "aaaa.json").exists())
        self.assertTrue((self.home / "rulings-retired" / "bbbb.json").exists())
        self.assertTrue((rulings / "cccc.json").exists())
        self.assertIn("Nothing to migrate", subprocess.run([*judge_py, "migrate"], env=self.env, capture_output=True,
                                                           text=True, encoding="utf-8").stdout)

    # --- blindness and resumability ----------------------------------------------------------

    def test_a_judge_sees_no_other_judges_filing_until_all_have_filed(self):
        cid = self.to_attack()
        self.file(cid, 1, REFUTE)
        self.file(cid, 2)
        seen = json.loads(self.ok("show", cid, "--judge", "3"))
        self.assertEqual([e["actor"] for e in seen], ["user", "clerk", "user"])
        seen = json.loads(self.ok("show", cid, "--judge", "1"))
        self.assertEqual([e["actor"] for e in seen], ["user", "clerk", "user", "judge-1"])
        for k in range(3, 8):
            self.file(cid, k)
        seen = json.loads(self.ok("show", cid, "--judge", "3"))
        self.assertEqual(len([e for e in seen if e["type"] == "file"]), 7)

    def test_status_alone_says_what_happens_next(self):
        cid = self.ok("open", "--statement", "a case").split()[0]
        self.assertIn(f"challenge.py brief {cid}", self.ok("status", cid))
        self.ok("brief", cid, self.write("case.json", case()))
        self.assertIn("The user confirms the brief", self.ok("status", cid))
        self.ok("confirm", cid, "--user-said", "yes")
        out = self.ok("status", cid)
        self.assertIn("judges 1, 2, 3, 4, 5, 6, 7 each file", out)
        for k in range(1, 8):
            self.file(cid, k)
        self.assertIn(f"challenge.py verify {cid}", self.ok("status", cid))
        self.ok("verify", cid)
        self.assertIn("vote, blind", self.ok("status", cid))
        self.assertIn(f"{cid}  voting; next: judge-1", self.ok("list"))

    # --- the binary --------------------------------------------------------------------------

    def test_the_core_speaks_json(self):
        result = subprocess.run([CORE, "replay"], input='{"events": []}', capture_output=True, text=True)
        state = json.loads(result.stdout)
        self.assertEqual((state["ok"], state["state"], state["next"]), (True, "unopened", ["user"]))

    def test_a_download_with_the_wrong_sha256_is_refused(self):
        sys.path.insert(0, str(CHALLENGE.parent))
        import challenge  # noqa: PLC0415  (only for the platform's name)
        key = challenge.platform_key()
        name = f"bab-challenge-{key}" + (".exe" if key.startswith("windows") else "")
        release = self.root / "releases" / "v9.9.9"
        release.mkdir(parents=True)
        shutil.copy(CORE, release / name)
        digest = hashlib.sha256((release / name).read_bytes()).hexdigest()
        pins = self.root / "binaries.json"
        env = {k: v for k, v in self.env.items() if k != "BISHOP_AND_BARRISTER_CHALLENGE_BIN"}
        env.update({"BISHOP_AND_BARRISTER_BINARIES": str(pins),
                    "BISHOP_AND_BARRISTER_RELEASES": (self.root / "releases").as_uri()})

        pins.write_text(json.dumps({"release": "v9.9.9", "binaries": {key: {"file": name, "sha256": "0" * 64}}}),
                        encoding="utf-8")
        out = self.refused("open", "--statement", "a case", env=env)
        self.assertIn("refused the challenge core", out)
        self.assertIn(digest, out)

        pins.write_text(json.dumps({"release": "v9.9.9", "binaries": {key: {"file": name, "sha256": digest}}}),
                        encoding="utf-8")
        self.ok("open", "--statement", "a case", env=env)
        self.assertTrue((self.home / "bin" / digest / name).exists())
        self.assertIn("bin/", (self.home / ".gitignore").read_text(encoding="utf-8"))

        pins.write_text(json.dumps({"release": None, "binaries": {}}), encoding="utf-8")
        self.assertIn("no released challenge core", self.refused("open", "--statement", "a case", env=env))


if __name__ == "__main__":
    unittest.main()
