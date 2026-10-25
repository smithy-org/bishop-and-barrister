"""Tests for scripts/judge.py, run through its command line against a temporary record.

They use a small fixture Comprehensive Rules file and a fixture bulk-rulings file, and set
BISHOP_AND_BARRISTER_OFFLINE so nothing touches the network.

    python -m unittest discover -s tests
"""

import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

JUDGE = Path(__file__).resolve().parent.parent / "scripts" / "judge.py"

CR = """Magic: The Gathering Comprehensive Rules

These rules are effective as of September 25, 2026.

Contents
100. General

100. General

100.1. These Magic rules apply to any Magic game with two or more players.

613. Interaction of Continuous Effects

613.8. Within a layer or sublayer, determining which order effects are applied in is sometimes done using a dependency system.

702. Keyword Abilities

702.19b The controller of an attacking creature with trample first assigns damage to the creature(s) blocking it.

Glossary

Trample
A keyword ability that modifies how a creature assigns combat damage.

Credits
"""

OFFICIAL = [
    {"object": "ruling", "oracle_id": "aaaa", "source": "wotc", "published_at": "2021-03-19",
     "comment": "Urborg's ability causes each land on the battlefield to have the land type Swamp."},
    {"object": "ruling", "oracle_id": "aaaa", "source": "wotc", "published_at": "2021-03-19",
     "comment": "If an effect such as Blood Moon sets Urborg to a basic land type, it won't turn lands into Swamps."},
    {"object": "ruling", "oracle_id": "bbbb", "source": "scryfall", "published_at": "2020-01-01",
     "comment": "Trample damage is assigned before any effect changes how much is dealt."},
]


def ruling(**overrides):
    r = {
        "question_type": "interaction",
        "question": "Blood Moon and Urborg, Tomb of Yawgmoth: are my lands Swamps?",
        "aliases": ["blood moon urborg"],
        "mechanics": ["layers", "dependency"],
        "agent_summary": "No. Blood Moon removes Urborg's ability through dependency (CR 613.8), whatever the timestamps.",
        "applies_when": [{"fact": "Blood Moon and Urborg are both on the battlefield", "why": "Both change land types"}],
        "answer_changes_if": [{"if": "Urborg is a basic land", "then": "Blood Moon doesn't affect it", "refs": ["c1"]}],
        "ask_if_unknown": [],
        "misconceptions": [{"wrong": "Timestamps decide it", "why_wrong": "Dependency comes first", "refs": ["c1"]}],
        "ruling": "No land is a Swamp because of Urborg; Urborg taps for R.",
        "steps": [{"n": 1, "text": "Urborg's effect depends on Blood Moon's, so Blood Moon applies first.", "refs": ["c1"]}],
        "citations": [{"id": "c1", "level": 1, "doc": "cr", "ref": "613.8"}],
        "cards": [{"name": "Blood Moon"}, {"name": "Urborg, Tomb of Yawgmoth"}],
        "confidence": "certain",
    }
    r.update(overrides)
    return r


class JudgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.cr = root / "MagicCompRules.txt"
        self.cr.write_text(CR, encoding="utf-8")
        self.bulk = root / "rulings.jsonl.gz"
        self.bulk.write_bytes(gzip.compress("\n".join(json.dumps(r) for r in OFFICIAL).encode("utf-8")))
        self.env = {**os.environ, "BISHOP_AND_BARRISTER_HOME": str(self.home), "BISHOP_AND_BARRISTER_CR": str(self.cr),
                    "BISHOP_AND_BARRISTER_OFFLINE": "1"}
        self.run_ok("build", "--rulings-file", str(self.bulk))

    def tearDown(self):
        self.tmp.cleanup()

    def run_judge(self, *args):
        return subprocess.run([sys.executable, str(JUDGE), *args], capture_output=True, text=True, encoding="utf-8", env=self.env)

    def run_ok(self, *args):
        result = self.run_judge(*args)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def write(self, name, data):
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def git_log(self):
        return subprocess.run(["git", "-C", str(self.home), "log", "--format=%B%n---"], capture_output=True, text=True, encoding="utf-8").stdout

    def record(self, data=None):
        out = self.run_ok("record", self.write("r.json", data or ruling()))
        return out.split()[1]

    def test_build_creates_record_and_index(self):
        self.assertTrue((self.home / ".git").exists())
        self.assertIn("objects/", (self.home / ".gitignore").read_text(encoding="utf-8"))
        self.assertIn("Official rulings", self.git_log())
        out = self.run_ok("search", "blood moon urborg")
        self.assertIn("official (wotc", out)

    def test_official_order_puts_wotc_before_scryfall(self):
        self.record()
        out = self.run_ok("search", "trample OR urborg")
        self.assertLess(out.index("official (wotc"), out.index("official (scryfall"))

    def test_record_pins_sources_and_commits(self):
        rid = self.record()
        saved = json.loads((self.home / "rulings" / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["kind"], "unreviewed")
        self.assertEqual(saved["level"], 5)
        self.assertEqual(len(saved["citations"][0]["text_sha256"]), 64)
        self.assertIn("dependency system", saved["citations"][0]["excerpt"])
        log = self.git_log()
        self.assertIn(f"Record unreviewed ruling {rid}", log)
        self.assertIn("Drafted-by: model", log)

    def test_record_rejects_missing_agent_fields(self):
        bad = ruling(agent_summary="", steps=[{"text": "no refs"}])
        del bad["ask_if_unknown"]
        bad["citations"].append({"id": "c2", "doc": "cr", "ref": "999.9"})
        result = self.run_judge("record", self.write("bad.json", bad))
        self.assertEqual(result.returncode, 2)
        for expected in ("agent_summary", "ask_if_unknown", "step 1 has no 'refs'", "999.9"):
            self.assertIn(expected, result.stderr)

    def test_search_and_agent_rendering(self):
        rid = self.record()
        out = self.run_ok("search", "Swamps", "--agent")
        self.assertIn(f'id="{rid}"', out)
        self.assertIn('<quote id="c1" doc="cr" ref="613.8"', out)
        self.assertIn("<applies_when><fact>", out)
        self.assertNotIn("<ask_if_unknown>", out)  # empty lists are left out
        self.assertIn(rid, self.run_ok("search", "--rule", "613.8"))

    def test_review_needs_the_users_words(self):
        rid = self.record()
        self.assertNotEqual(self.run_judge("review", rid, "--user-said", "  ").returncode, 0)
        self.run_ok("discuss", rid, self.write("d.json", [{"by": "user", "said": "Even if Urborg came down later?"},
                                                          {"by": "model", "said": "Yes: dependency, not timestamps."}]),
                    "--summary", "Timestamp order was raised and rejected: dependency decides.")
        self.run_ok("review", rid, "--user-said", "Makes sense, mark it reviewed.")
        saved = json.loads((self.home / "rulings" / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["kind"], "reviewed")
        lines = (self.home / "deliberation" / f"{rid}.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[-1])["decision"], "reviewed")
        log = self.git_log()
        self.assertIn("Decided-by: user", log)
        self.assertIn("Makes sense, mark it reviewed.", log)
        self.assertIn('kind="reviewed"', self.run_ok("show", rid, "--agent", "--deliberation"))

    def test_recheck_flags_changed_rule(self):
        rid = self.record()
        self.assertIn("still match", self.run_ok("recheck"))
        self.cr.write_text(CR.replace("dependency system.", "dependency system, revised."), encoding="utf-8")
        out = self.run_ok("recheck")
        self.assertIn(rid, out)
        self.assertIn("CR 613.8 changed", out)
        saved = json.loads((self.home / "rulings" / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "needs-recheck")
        self.assertIn('sources_changed="true"', self.run_ok("show", rid, "--agent"))

    def test_index_rebuilds_from_the_record(self):
        rid = self.record()
        (self.home / "index.sqlite").unlink()
        self.assertIn("3 official rulings, 1 of your rulings", self.run_ok("index"))
        self.assertIn(rid, self.run_ok("search", "Swamps"))


if __name__ == "__main__":
    unittest.main()
