"""Tests for the parts of scripts/challenge.py that don't need the bab-challenge binary.

They cover fetching the binary itself (pinned by SHA-256) and the verifier's source checks: a quote that's
missing, a rule that changed after it was pinned, an assumption in the case, an official ruling that isn't
in the index. Everything runs offline against fixtures.

    python -m unittest discover -s tests
"""

import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "skills" / "bishop-and-barrister" / "scripts"))
import challenge  # noqa: E402
import judge  # noqa: E402

CR = """Magic: The Gathering Comprehensive Rules

These rules are effective as of September 25, 2026.

100. General

100.1. These Magic rules apply to any Magic game with two or more players.

613. Interaction of Continuous Effects

613.8. Within a layer or sublayer, determining which order effects are applied in is sometimes done using a dependency system.

Glossary

Credits
"""
DEPENDENCY = "determining which order effects are applied in is sometimes done using a dependency system"


def cr_source(excerpt=DEPENDENCY, text=None):
    text = text or "Within a layer or sublayer, " + DEPENDENCY + "."
    return {"doc": "cr", "ref": "613.8", "excerpt": excerpt, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}


class BinaryTest(unittest.TestCase):
    """Fetching bab-challenge: once, from the pinned release, refused unless its SHA-256 matches."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data = b"#!/bin/sh\necho core\n"
        self.pins = root / "binaries.json"
        self.pin(hashlib.sha256(self.data).hexdigest())
        for p in (mock.patch.object(challenge, "BINARIES", self.pins), mock.patch.dict(os.environ, {"BISHOP_AND_BARRISTER_HOME": str(root)}),
                  mock.patch.object(challenge, "DEV_BIN", None), mock.patch.object(challenge, "platform_key", lambda: "linux-x64")):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def pin(self, digest, release="v1.0.0"):
        self.pins.write_text(json.dumps({"release": release, "binaries": {
            "linux-x64": {"file": "bab-challenge-linux-x64", "sha256": digest}}}), encoding="utf-8")

    def serve(self, data):
        downloads = []

        def urlopen(url, timeout=120):
            downloads.append(url)
            if isinstance(data, Exception):
                raise data
            return io.BytesIO(data)
        return mock.patch("urllib.request.urlopen", urlopen), downloads

    def test_downloads_once_and_checks_the_hash(self):
        patch, downloads = self.serve(self.data)
        with patch:
            path = challenge.find_binary()
            self.assertEqual(path.read_bytes(), self.data)
            self.assertEqual(challenge.find_binary(), path)  # already there with the right hash: no download
        self.assertEqual(len(downloads), 1)
        self.assertTrue(downloads[0].endswith("/v1.0.0/bab-challenge-linux-x64"))

    def test_a_wrong_hash_is_refused(self):
        patch, _ = self.serve(b"tampered")
        with patch, self.assertRaises(challenge.Unavailable) as caught:
            challenge.find_binary()
        self.assertIn("refused", str(caught.exception))

    def test_no_release_or_no_network(self):
        self.pin("ab" * 32, release="")
        with self.assertRaises(challenge.Unavailable):
            challenge.find_binary()
        self.pin("ab" * 32)
        patch, _ = self.serve(OSError("offline"))
        with patch, self.assertRaises(challenge.Unavailable) as caught:
            challenge.find_binary()
        self.assertIn("couldn't download", str(caught.exception))

    def test_a_development_binary_wins(self):
        with mock.patch.object(challenge, "DEV_BIN", "/tmp/bab-challenge"):
            self.assertEqual(challenge.find_binary(), Path("/tmp/bab-challenge"))

class PlatformTest(unittest.TestCase):
    def test_platform_names(self):
        with mock.patch.object(challenge.sys, "platform", "darwin"), mock.patch("platform.machine", return_value="arm64"):
            self.assertEqual(challenge.platform_key(), "macos-arm64")
        with mock.patch.object(challenge.sys, "platform", "win32"), mock.patch("platform.machine", return_value="AMD64"):
            self.assertEqual(challenge.platform_key(), "windows-x64")
        with mock.patch.object(challenge.sys, "platform", "sunos5"):
            self.assertIsNone(challenge.platform_key())


class VerifierTest(unittest.TestCase):
    """The checks the verifier runs on every source in a case, refutation or reply."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        cr = root / "MagicCompRules.txt"
        cr.write_text(CR, encoding="utf-8")
        docs = root / "docs"
        docs.mkdir()
        (docs / "ipg.json").write_text(json.dumps({"title": "Infraction Procedure Guide", "effective": "September 23, 2024",
            "sections": [{"key": "2.3", "heading": "Hidden Card Error", "text": "The opponent chooses a card."}]}), encoding="utf-8")
        index = root / "index.sqlite"
        conn = sqlite3.connect(index)
        conn.execute("CREATE TABLE rulings (id TEXT, kind TEXT, json TEXT)")
        conn.execute("INSERT INTO rulings VALUES ('w1', 'official', ?)",
                     (json.dumps({"comment": "Blood Moon's effect applies before Urborg's."}),))
        conn.commit()
        conn.close()
        patches = [mock.patch.dict(os.environ, {"BISHOP_AND_BARRISTER_HOME": str(root), "BISHOP_AND_BARRISTER_CR": str(cr),
                                                "BISHOP_AND_BARRISTER_DOCS": str(docs)}),
                   mock.patch.object(judge, "_RULES", None),
                   mock.patch.object(judge, "OFFLINE", True)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sources_are_found_everywhere_in_an_event(self):
        fields = {"case": {"steps": [{"id": "s1", "source": cr_source()}, {"id": "s2"}]},
                  "refutations": [{"steps": [{"id": "r1", "source": cr_source()}]}],
                  "replies": [{"judge": 3, "index": 1, "steps": [{"id": "p1", "source": cr_source()}]}]}
        labels = [label for label, _ in challenge.sources_in(fields)]
        self.assertEqual(labels, ["case step s1", "refutation 1 step r1", "reply to judge 3's refutation 1 step p1"])

    def test_a_good_source_passes(self):
        self.assertIsNone(challenge.verify_source(cr_source()))

    def test_a_rule_that_changed_or_a_misquote_fails(self):
        self.assertIn("has changed since it was pinned", challenge.verify_source(cr_source(text="something else")))
        self.assertIn("the quote isn't in", challenge.verify_source(cr_source(excerpt="a timestamp system")))
        self.assertIn("doesn't exist", challenge.verify_source({"doc": "cr", "ref": "999.9"}))

    def test_documents_oracle_and_other_sources(self):
        good = {"doc": "ipg", "ref": "2.3", "excerpt": "chooses a card",
                "text_sha256": hashlib.sha256(b"The opponent chooses a card.").hexdigest()}
        self.assertIsNone(challenge.verify_source(good))
        self.assertIn("doesn't name one section", challenge.verify_source({"doc": "ipg", "ref": "9.9"}))
        self.assertIn("isn't downloaded", challenge.verify_source({"doc": "mtr", "ref": "2.2"}))
        self.assertIn("couldn't fetch", challenge.verify_source({"doc": "oracle", "ref": "Blood Moon"}))  # offline
        self.assertIn("isn't a source the verifier can check", challenge.verify_source({"doc": "formats", "ref": "x"}))

    def test_official_rulings_must_be_in_the_index(self):
        quote = "Blood Moon's effect applies before Urborg's."
        ruling = {"doc": "ruling", "ref": "w1", "excerpt": quote, "text_sha256": hashlib.sha256(quote.encode()).hexdigest()}
        self.assertIsNone(challenge.verify_source(ruling))
        self.assertEqual(challenge.verify_source({**ruling, "excerpt": "Blood Moon wins."}),
                         "no official ruling in the index says this")
        edited = {**ruling, "text_sha256": "0" * 64}
        self.assertIn("edited after it was pinned", challenge.verify_source(edited))

    def test_steps_report_failures_and_case_assumptions(self):
        steps = [{"id": "s1", "source": cr_source()}, {"id": "s2", "source": cr_source(excerpt="nonsense")}, {"id": "s3"}]
        problems = challenge.verify_steps("case", steps)
        self.assertEqual(len(problems), 2)
        self.assertIn("case step s2: the quote isn't in", problems[0])
        self.assertIn("case step s3: an assumption", problems[1])
        self.assertEqual(len(challenge.verify_steps("refutation 1", steps)), 1)  # assumptions only matter in the case

    def test_quoting_ignores_spacing_and_case(self):
        self.assertTrue(challenge.quoted("DEPENDENCY   system", "a dependency\nsystem"))
        self.assertFalse(challenge.quoted("timestamp", "a dependency system"))

    def test_quoting_ignores_typography(self):
        self.assertTrue(challenge.quoted("can't be cast", "This half can’t be cast"))
        self.assertTrue(challenge.quoted("“the player”", 'says "the player" twice'))
        self.assertTrue(challenge.quoted("A - B", "A — B"))
        self.assertTrue(challenge.quoted("no new games", "no new games"))

    def test_quoting_mends_words_a_pdf_broke_across_lines(self):
        self.assertTrue(challenge.quoted("the exception applies", "the excep-\ntion applies"))
        self.assertTrue(challenge.quoted("state-based actions", "check state-\nbased actions"))
        self.assertFalse(challenge.quoted("statebased", "state-based"))

    def test_level_1_overrides(self):
        self.assertTrue(challenge.overridden_by_level_1({"ground": "overridden", "steps": [{"source": {"doc": "cr"}}]}))
        self.assertFalse(challenge.overridden_by_level_1({"ground": "misread", "steps": [{"source": {"doc": "cr"}}]}))


if __name__ == "__main__":
    unittest.main()
