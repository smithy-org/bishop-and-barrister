"""Tests for scripts/judge.py, run through its command line against a temporary record.

They use a small fixture Comprehensive Rules file and a fixture bulk-rulings file, and set
BISHOP_AND_BARRISTER_OFFLINE so nothing touches the network.

    python -m unittest discover -s tests
"""

import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

JUDGE = Path(__file__).resolve().parent.parent / "plugin" / "skills" / "bishop-and-barrister" / "scripts" / "judge.py"

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

    def put_ruling(self, rid="aaaa11112222", kind="reviewed", house_rule=True):
        """A ruling as the retired `judge.py record` and `review` left it in the record."""
        text = "Within a layer or sublayer, determining which order effects are applied in is sometimes done using a dependency system."
        r = ruling(id=rid, kind=kind, level=5, status="current", house_rule=house_rule)
        r["citations"][0].update(text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), excerpt=text)
        (self.home / "rulings" / f"{rid}.json").write_text(json.dumps(r), encoding="utf-8")
        (self.home / "deliberation" / f"{rid}.jsonl").write_text(
            json.dumps({"by": "user", "decision": "reviewed", "said": "Keep it as our table's rule."}) + "\n", encoding="utf-8")
        self.run_ok("index")
        return rid

    def test_build_creates_record_and_index(self):
        self.assertTrue((self.home / ".git").exists())
        self.assertIn("objects/", (self.home / ".gitignore").read_text(encoding="utf-8"))
        self.assertIn("Official rulings", self.git_log())
        out = self.run_ok("search", "blood moon urborg")
        self.assertIn("official (wotc", out)

    def test_official_order_puts_wotc_before_scryfall(self):
        out = self.run_ok("search", "effect")  # in both a wotc and a scryfall ruling
        self.assertLess(out.index("official (wotc"), out.index("official (scryfall"))

    def test_loose_match_keeps_only_close_rulings(self):
        # No ruling has all three words, so the search falls back to any word and says so.
        out = self.run_ok("search", "urborg swamps zebra")
        self.assertIn("No ruling has every word", out)
        self.assertNotIn("Trample", out)

    def test_record_review_and_discuss_are_retired(self):
        for command in (["record", "r.json"], ["review", "x", "--user-said", "yes"], ["discuss", "x", "d.json"]):
            result = self.run_judge(*command)
            self.assertEqual(result.returncode, 2)
            self.assertIn("only through a challenge", result.stderr)
            self.assertIn("CHALLENGE.md", result.stderr)
        self.assertFalse(list((self.home / "rulings").glob("*.json")))

    def test_a_house_rule_is_still_searched(self):
        rid = self.put_ruling()
        brief = self.run_ok("search", "Swamps", "--agent")
        self.assertIn(f'id="{rid}"', brief)
        self.assertIn('kind="reviewed"', brief)
        out = self.run_ok("search", "Swamps", "--agent", "--full")
        self.assertIn('house_rule="true"', out)
        self.assertIn('<quote id="c1" doc="cr" ref="613.8"', out)
        self.assertIn(rid, self.run_ok("search", "--rule", "613.8"))

    def test_an_old_ruling_isnt_searched_until_migrated(self):
        for rid, kind in (("bbbb11112222", "unreviewed"), ("cccc11112222", "reviewed")):
            self.put_ruling(rid, kind=kind, house_rule=False)
        result = self.run_judge("index")
        self.assertIn("2 ruling(s) from the retired `judge.py record`", result.stderr)
        self.assertIn("No rulings match", self.run_judge("search", "--rule", "613.8").stdout)

    def test_recheck_flags_changed_rule(self):
        rid = self.put_ruling()
        self.assertIn("still match", self.run_ok("recheck"))
        self.cr.write_text(CR.replace("dependency system.", "dependency system, revised."), encoding="utf-8")
        out = self.run_ok("recheck")
        self.assertIn(rid, out)
        self.assertIn("CR 613.8 changed", out)
        saved = json.loads((self.home / "rulings" / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "needs-recheck")
        self.assertIn('sources_changed="true"', self.run_ok("show", rid, "--agent"))

    def test_index_rebuilds_from_the_record(self):
        rid = self.put_ruling()
        (self.home / "index.sqlite").unlink()
        self.assertIn("3 official rulings, 1 of your rulings", self.run_ok("index"))
        self.assertIn(rid, self.run_ok("search", "Swamps"))

if __name__ == "__main__":
    unittest.main()
