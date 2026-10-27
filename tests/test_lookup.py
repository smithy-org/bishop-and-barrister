"""Tests for scripts/lookup.py: the Comprehensive Rules commands and `--doc` for the tournament documents.

They run lookup's own command line in-process against a small fixture CR and fixture documents.

    python -m unittest discover -s tests
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lookup  # noqa: E402

LONG = "If a creature with deathtouch deals damage to another creature, " + "that creature is destroyed " * 20

CR = f"""Magic: The Gathering Comprehensive Rules

These rules are effective as of September 25, 2026.

Contents
100. General
702. Keyword Abilities

100. General

100.1. These Magic rules apply to any Magic game with two or more players.

100.1a A two-player game is a game that begins with only two players.

702. Keyword Abilities

702.2. Deathtouch

702.2a Deathtouch is a static ability.

702.2b {LONG}
Example: A 1/1 with deathtouch blocks a 5/5. The 5/5 is destroyed.

702.2c Any nonzero amount of combat damage assigned by a creature with deathtouch is lethal.

702.19. Trample

702.19a Trample is a static ability that modifies the rules for assigning an attacking creature's combat damage.

Glossary

Deathtouch
A keyword ability that causes damage dealt by an object to be especially effective.
See rule 702.2, "Deathtouch."

Deathtouch Damage
Not a real term; here to test partial matches.

Trample
A keyword ability that modifies how a creature assigns combat damage.

Credits

Magic: The Gathering Original Game Design: Richard Garfield
"""

IPG = {
    "title": "Infraction Procedure Guide",
    "effective": "September 23, 2024",
    "sections": [
        {"key": "2", "heading": "Game Play Errors", "text": "Game Play Errors are mistakes."},
        {"key": "2.3", "heading": "Game Play Error — Hidden Card Error Warning",
         "text": "Definition\nA player commits an error.\nExamples\nA. A player draws four cards.\nPhilosophy\nThis is hard.\n"
                 "Additional Remedy\nThe opponent chooses a card.\nUpgrade: If it was a morph, the penalty is a Game Loss."},
        {"key": "A", "heading": "Penalty Quick Reference", "text": "Missed Trigger: No penalty."},
    ],
}


class LookupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        cr = root / "MagicCompRules.txt"
        cr.write_text(CR, encoding="utf-8")
        docs = root / "docs"
        docs.mkdir()
        (docs / "ipg.json").write_text(json.dumps(IPG), encoding="utf-8")
        for p in (mock.patch.object(lookup, "RULES_FILE", cr), mock.patch.object(lookup, "DOCS_DIR", docs)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_lookup(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["lookup.py", *args]), redirect_stdout(out), redirect_stderr(err):
            try:
                status = lookup.main()
            except SystemExit as exit:
                status = exit.code
        return status, out.getvalue(), err.getvalue()

    def test_rule_with_subrules_and_examples(self):
        status, out, _ = self.run_lookup("rule", "702.2b")
        self.assertEqual(status, 0)
        self.assertIn("702.2b If a creature", out)
        self.assertIn("Example: A 1/1 with deathtouch", out)
        self.assertNotIn("702.2c", out)

    def test_whole_section_and_several_rules(self):
        status, out, _ = self.run_lookup("rule", "702", "100.1")
        self.assertEqual(status, 0)
        for number in ("702.2a", "702.19a", "100.1.", "100.1a"):
            self.assertIn(number, out)

    def test_limit_truncates(self):
        _, out, _ = self.run_lookup("rule", "702", "--limit", "2")
        self.assertIn("[truncated:", out)

    def test_missing_rule(self):
        status, _, err = self.run_lookup("rule", "999.9")
        self.assertEqual(status, 1)
        self.assertIn("No rule found matching 999.9", err)

    def test_search_snippets_and_full(self):
        status, out, _ = self.run_lookup("search", "destroyed", "--limit", "1")
        self.assertEqual(status, 0)
        self.assertIn("702.2b", out)
        self.assertIn("...", out)  # a long rule is cut to a window around the match
        self.assertIn("snippets only", out)
        _, full, _ = self.run_lookup("search", "destroyed", "--full")
        self.assertNotIn("snippets only", full)
        self.assertIn(LONG.strip()[-40:], full)

    def test_search_skips_the_glossary_and_reports_nothing(self):
        _, out, _ = self.run_lookup("search", "keyword ability")
        self.assertNotIn("especially effective", out)
        status, _, err = self.run_lookup("search", "zebra")
        self.assertEqual(status, 1)
        self.assertIn("No rules mention", err)

    def test_glossary_exact_then_partial(self):
        status, out, _ = self.run_lookup("glossary", "deathtouch")
        self.assertEqual(status, 0)
        self.assertLess(out.index("Deathtouch\n"), out.index("Deathtouch Damage"))
        _, out, _ = self.run_lookup("glossary", "deathtouch", "--limit", "1")
        self.assertIn("more matching entries", out)
        status, _, err = self.run_lookup("glossary", "zebra")
        self.assertEqual(status, 1)

    def test_toc_lists_body_sections_once(self):
        _, out, _ = self.run_lookup("toc")
        self.assertEqual(out.splitlines(), ["100. General", "702. Keyword Abilities"])

    def test_missing_rules_file(self):
        lookup.RULES_FILE.unlink()
        status, _, _ = self.run_lookup("rule", "100.1")
        self.assertIn("Rules file not found", str(status))

    def test_doc_rule_trims_examples_and_philosophy(self):
        status, out, _ = self.run_lookup("--doc", "ipg", "rule", "2.3")
        self.assertEqual(status, 0)
        self.assertIn("[Infraction Procedure Guide, effective September 23, 2024]", out)
        self.assertIn("The opponent chooses a card.", out)
        self.assertIn("Upgrade: If it was a morph", out)
        self.assertNotIn("draws four cards", out)
        self.assertNotIn("This is hard", out)
        self.assertIn("[left out: Examples, Philosophy", out)
        _, everything, _ = self.run_lookup("--doc", "ipg", "rule", "2.3", "--all")
        self.assertIn("draws four cards", everything)

    def test_doc_rule_by_number_heading_and_appendix(self):
        _, out, _ = self.run_lookup("--doc", "ipg", "rule", "2")
        self.assertIn("2.3  Game Play Error", out)  # a number takes its subsections
        _, out, _ = self.run_lookup("--doc", "ipg", "rule", "hidden card", "Appendix A")
        self.assertIn("2.3  Game Play Error", out)
        self.assertIn("A  Penalty Quick Reference", out)
        status, _, err = self.run_lookup("--doc", "ipg", "rule", "9.9")
        self.assertEqual(status, 1)
        self.assertIn("No section", err)

    def test_doc_section_resolution(self):
        self.assertEqual(lookup.doc_section("ipg", "2.3")["key"], "2.3")
        self.assertEqual(lookup.doc_section("ipg", "Hidden Card")["key"], "2.3")
        self.assertIsNone(lookup.doc_section("ipg", "Game Play"))  # names two sections

    def test_doc_search_and_toc(self):
        status, out, _ = self.run_lookup("--doc", "ipg", "search", "opponent")
        self.assertEqual(status, 0)
        self.assertIn("2.3", out)
        _, full, _ = self.run_lookup("--doc", "ipg", "search", "opponent", "--full")
        self.assertIn("The opponent chooses a card.", full)
        status, _, _ = self.run_lookup("--doc", "ipg", "search", "zebra")
        self.assertEqual(status, 1)
        _, toc, _ = self.run_lookup("--doc", "ipg", "toc")
        self.assertIn("(effective September 23, 2024)", toc)
        self.assertIn("A  Penalty Quick Reference", toc)

    def test_doc_not_downloaded_and_glossary_refused(self):
        status, _, _ = self.run_lookup("--doc", "mtr", "toc")
        self.assertIn("isn't downloaded", str(status))
        status, _, err = self.run_lookup("--doc", "ipg", "glossary", "Warning")
        self.assertEqual(status, 2)
        self.assertIn("glossary is only in the CR", err)


if __name__ == "__main__":
    unittest.main()
