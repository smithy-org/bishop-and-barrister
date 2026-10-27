"""Tests for the tournament documents: sources.py's conversion, lookup.py --doc, and judge.py citing them.

The conversion tests feed sources.py lines shaped like pypdf's output from the real PDFs, so they need
neither pypdf nor the network. The judge tests use a small converted IPG and run offline.

    python -m unittest discover -s tests
"""

import gzip
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import sources  # noqa: E402

IPG_LINES = [
    "MAGIC INFRACTION PROCEDURE GUIDE",
    "Effective September 23, 2024",
    "1.  General Philosophy ........................................ 3",
    "1.1.  Definition of Penalties ................................. 3",
    "2. Game Play Errors ........................................... 7",
    "2.2.      Game Play Error — Looking at Extra Cards ............ 10",
    "2.3.      Game Play Error — Hidden Card Error ................. 10",
    "Appendix A — Penalty Quick Reference .......................... 30",
    "1.  GENERAL PHILOSOPHY",
    "Penalties exist to educate.",
    "1.1.  DEFINITION OF PENALTIES",
    "A Warning is used in situations of minor infractions.",
    "2.  GAME PLAY ERRORS",
    "2.2.      Game Play Error — Looking at Extra Cards Warning",
    "A player takes an action that may have allowed them to see the faces of cards.",
    "2.3.      Game Play Error — Hidden Card Error Warning",
    "Definition",
    "A player commits an error in the game that cannot be corrected by only publicly available information.",
    "Additional Remedy",
    "The opponent may choose a card that was not previously known and shuffle it into the library.",
    "APPENDIX A — PENALTY QUICK REFERENCE",
    "Missed Trigger: No penalty.",
]

JAR_LINES = [
    ("Most Magic players play for fun.", False),
    ("Common Issues", True),
    ("A player forgets a triggered ability (one that uses the words “when,” “whenever,” or “at the", True),
    ("beginning”, usually at the start of the ability's text)", True),
    ("These abilities are considered missed if the player did not acknowledge the ability.", False),
    ("A player accidentally draws more cards or has more cards in their hand than they were supposed to", True),
    ("If the identity of the card(s) were known to all players, return them to their proper location.", False),
    ("Serious Problems", True),
    ("Certain actions will not be tolerated.", False),
]


class ConversionTest(unittest.TestCase):
    def test_numbered_document_splits_by_its_contents(self):
        with redirect_stderr(io.StringIO()) as err:
            sections = sources.by_contents(IPG_LINES)
        self.assertEqual([s["key"] for s in sections], ["1", "1.1", "2", "2.2", "2.3", "A"])
        self.assertEqual(err.getvalue(), "")
        hidden = sections[4]
        self.assertEqual(hidden["heading"], "Game Play Error — Hidden Card Error Warning")  # the penalty is kept
        self.assertIn("shuffle it into the library", hidden["text"])
        self.assertNotIn("Missed Trigger", hidden["text"])

    def test_missing_heading_is_reported(self):
        lines = [line for line in IPG_LINES if not line.startswith("2.2.      Game Play Error — Looking at Extra Cards W")]
        with redirect_stderr(io.StringIO()) as err:
            sections = sources.by_contents(lines)
        self.assertNotIn("2.2", [s["key"] for s in sections])
        self.assertIn("2.3", [s["key"] for s in sections])
        self.assertIn("weren't found in the body: 2.2", err.getvalue())

    def test_unnumbered_document_splits_at_bold_headings(self):
        sections = sources.by_bold_headings(JAR_LINES)
        headings = [s["heading"] for s in sections]
        self.assertEqual(headings[0], "Introduction")
        self.assertEqual(headings[1], "Common Issues")  # a short group heading isn't merged into the next
        self.assertTrue(headings[2].endswith("usually at the start of the ability's text)"))  # a wrapped one is
        self.assertEqual(sections[3]["key"], "3")
        self.assertIn("proper location", sections[3]["text"])


IPG_JSON = {
    "title": "Infraction Procedure Guide",
    "effective": "September 23, 2024",
    "sections": [
        {"key": "2", "heading": "Game Play Errors", "text": "Game play errors are..."},
        {"key": "2.2", "heading": "Game Play Error — Looking at Extra Cards Warning", "text": "A player sees extra cards."},
        {"key": "2.3", "heading": "Game Play Error — Hidden Card Error Warning",
         "text": "The opponent may choose a card that was not previously known and shuffle it into the library."},
    ],
}

CR = """Magic: The Gathering Comprehensive Rules

These rules are effective as of September 25, 2026.

100. General

100.1. These Magic rules apply to any Magic game with two or more players.

Glossary

Credits
"""


def ruling(ref):
    return {
        "question_type": "tournament",
        "question": "At Competitive REL I drew an extra card. What's the fix?",
        "aliases": [], "mechanics": [],
        "agent_summary": "Hidden Card Error (IPG 2.3): Warning; the opponent shuffles in a card not previously known.",
        "applies_when": [{"fact": "Competitive REL", "why": "The IPG applies"}],
        "answer_changes_if": [], "ask_if_unknown": [], "misconceptions": [],
        "ruling": "Warning; reveal the hand, the opponent picks a card not previously known, shuffle it in.",
        "steps": [{"n": 1, "text": "Drawing an extra card is a Hidden Card Error.", "refs": ["c1"]}],
        "citations": [{"id": "c1", "doc": "ipg", "ref": ref}],
        "cards": [], "confidence": "certain",
    }


class JudgeDocTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.docs = root / "docs"
        self.docs.mkdir()
        self.write_ipg(IPG_JSON)
        (root / "cr.txt").write_text(CR, encoding="utf-8")
        bulk = root / "rulings.jsonl.gz"
        bulk.write_bytes(gzip.compress(b""))
        self.env = {**os.environ, "BISHOP_AND_BARRISTER_HOME": str(root / "home"), "BISHOP_AND_BARRISTER_CR": str(root / "cr.txt"),
                    "BISHOP_AND_BARRISTER_DOCS": str(self.docs), "BISHOP_AND_BARRISTER_OFFLINE": "1"}
        self.judge("build", "--rulings-file", str(bulk))

    def tearDown(self):
        self.tmp.cleanup()

    def write_ipg(self, data):
        (self.docs / "ipg.json").write_text(json.dumps(data), encoding="utf-8")

    def judge(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPTS / "judge.py"), *args], capture_output=True, text=True,
                                encoding="utf-8", env=self.env)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def pin(self, ref):
        """Check and pin one IPG citation as challenge.py does, through judge.py's validate_citation/pin_citation."""
        code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import judge; c = {'id': 'c1', 'doc': 'ipg', 'ref': sys.argv[2]}; "
                "errors = judge.validate_citation(c, 'citation c1'); errors or judge.pin_citation(c); "
                "print(json.dumps({'errors': errors, 'citation': c}))")
        result = subprocess.run([sys.executable, "-c", code, str(SCRIPTS), ref], capture_output=True, text=True,
                                encoding="utf-8", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_lookup_reads_a_document(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "lookup.py"), "--doc", "ipg", "rule", "hidden card"],
                             capture_output=True, text=True, encoding="utf-8", env=self.env).stdout
        self.assertIn("2.3  Game Play Error — Hidden Card Error Warning", out)

    def test_citation_by_heading_is_pinned_to_the_section(self):
        c = self.pin("Hidden Card Error")["citation"]
        self.assertEqual((c["ref"], c["level"], c["version"]), ("2.3", 2, "September 23, 2024"))
        self.assertEqual(len(c["text_sha256"]), 64)

    def test_unknown_or_ambiguous_section_is_refused(self):
        for ref in ("9.9", "Game Play Error"):
            self.assertIn("doesn't name exactly one section", " ".join(self.pin(ref)["errors"]), ref)

    def test_recheck_flags_a_changed_section_even_when_renumbered(self):
        # A house rule from before challenges, citing IPG 2.3.
        home = Path(self.tmp.name) / "home"
        rid = "dddd11112222"
        r = {**ruling("2.3"), "id": rid, "kind": "reviewed", "level": 5, "status": "current", "house_rule": True}
        r["citations"] = [self.pin("2.3")["citation"]]
        (home / "rulings" / f"{rid}.json").write_text(json.dumps(r), encoding="utf-8")
        self.assertIn("still match", self.judge("recheck").stdout)
        changed = json.loads(json.dumps(IPG_JSON))
        changed["sections"].insert(1, {"key": "2.1", "heading": "Game Play Error — Missed Trigger", "text": "..."})
        changed["sections"][3]["key"] = "2.4"  # Hidden Card Error moved, its text unchanged
        self.write_ipg(changed)
        self.assertIn("still match", self.judge("recheck").stdout)
        changed["sections"][3]["text"] += " Then the player draws."
        self.write_ipg(changed)
        out = self.judge("recheck").stdout
        self.assertIn(rid, out)
        self.assertIn("IPG 2.3 changed", out)

if __name__ == "__main__":
    unittest.main()
