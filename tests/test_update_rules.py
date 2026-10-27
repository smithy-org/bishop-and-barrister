"""Tests for scripts/update_rules.py: finding, checking and installing the Comprehensive Rules.

Wizards' site is replaced by fakes, so nothing touches the network.

    python -m unittest discover -s tests
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import update_rules  # noqa: E402

URL = "https://media.wizards.com/2026/downloads/MagicCompRules 20260925.txt"
PAGE = f'<a href="{URL}">TXT</a> <a href="https://media.wizards.com/2025/downloads/MagicCompRules 20250101.txt">old</a>'
CR = "Magic: The Gathering Comprehensive Rules\n\nThese rules are effective as of September 25, 2026.\n\n100.1. Rules.\n"
NEWER = CR.replace("September 25, 2026", "November 14, 2026")


class FakeSite:
    """Wizards' rules page, the .txt file, and its HEAD probe."""

    def __init__(self, text=CR, length="1000", modified="Thu, 25 Sep 2026 00:00:00 GMT"):
        self.text, self.length, self.modified = text, length, modified
        self.downloads = 0

    def get(self, url, timeout=60):
        if url == update_rules.RULES_PAGE:
            return PAGE.encode("utf-8")
        self.downloads += 1
        return self.text.encode("utf-8")

    def head(self, url, timeout=30):
        return {"content_length": self.length, "last_modified": self.modified}


class UpdateRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ref = Path(self.tmp.name) / "reference"
        for name, value in (("DATA_DIR", ref), ("RULES_FILE", ref / "MagicCompRules.txt"),
                            ("META_FILE", ref / "version.json")):
            p = mock.patch.object(update_rules, name, value)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, site, *args):
        out = io.StringIO()
        with mock.patch.object(update_rules, "get", site.get), mock.patch.object(update_rules, "head", site.head), \
                mock.patch.object(sys, "argv", ["update_rules.py", *args]), redirect_stdout(out):
            status = update_rules.main()
        return status, out.getvalue()

    def test_dates_and_decoding(self):
        self.assertEqual(update_rules.posted_date(URL), "20260925")
        self.assertEqual(update_rules.posted_date("https://x/rules.txt"), "unknown")
        self.assertEqual(update_rules.effective_date(CR), "September 25, 2026")
        self.assertEqual(update_rules.effective_date("no date"), "unknown")
        self.assertEqual(update_rules.decode("café".encode("cp1252")), "café")
        self.assertEqual(update_rules.decode(b"\xef\xbb\xbfrules"), "rules")

    def test_finds_the_newest_txt_link(self):
        with mock.patch.object(update_rules, "get", FakeSite().get):
            self.assertEqual(update_rules.find_txt_url(), URL)
        with mock.patch.object(update_rules, "get", lambda url, timeout=60: b"<html>no link</html>"):
            with self.assertRaises(SystemExit):
                update_rules.find_txt_url()

    def test_first_install_then_up_to_date_by_probe(self):
        site = FakeSite()
        status, out = self.run_main(site)
        self.assertEqual(status, 0)
        self.assertIn("Saved", out)
        meta = json.loads(update_rules.META_FILE.read_text())
        self.assertEqual((meta["effective_date"], meta["posted_date"]), ("September 25, 2026", "20260925"))
        _, out = self.run_main(site)
        self.assertIn("identical size and modification time", out)
        self.assertEqual(site.downloads, 1)  # the probe settled it without a download

    def test_same_content_reposted_is_up_to_date(self):
        self.run_main(FakeSite())
        site = FakeSite(modified="Fri, 26 Sep 2026 00:00:00 GMT")  # re-posted, same text
        _, out = self.run_main(site)
        self.assertIn("content identical", out)

    def test_check_reports_an_update_without_installing(self):
        self.run_main(FakeSite())
        site = FakeSite(text=NEWER, length="1001")
        _, out = self.run_main(site, "--check")
        self.assertIn("Update available: remote effective November 14, 2026", out)
        self.assertEqual(update_rules.effective_date(update_rules.RULES_FILE.read_text(encoding="utf-8")),
                         "September 25, 2026")
        _, out = self.run_main(site)
        self.assertIn("Effective November 14, 2026", out)

    def test_force_reinstalls(self):
        site = FakeSite()
        self.run_main(site)
        self.run_main(site, "--force")
        self.assertEqual(site.downloads, 2)

    def test_local_state_without_or_with_stale_metadata(self):
        self.assertIsNone(update_rules.local_state())
        update_rules.DATA_DIR.mkdir(parents=True)
        update_rules.RULES_FILE.write_text(CR, encoding="utf-8")
        state = update_rules.local_state()
        self.assertEqual(state["source"], "reconstructed from local file")
        update_rules.META_FILE.write_text(json.dumps({"sha256": "something else"}))
        self.assertIn("stale", update_rules.local_state()["source"])
        out = io.StringIO()
        with redirect_stdout(out):
            update_rules.describe(None)
            update_rules.describe(update_rules.local_state())
        self.assertIn("none downloaded yet", out.getvalue())
        self.assertIn("effective September 25, 2026", out.getvalue())


if __name__ == "__main__":
    unittest.main()
