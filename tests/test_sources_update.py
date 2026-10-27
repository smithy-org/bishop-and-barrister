"""Tests for scripts/sources.py's downloading side: finding each PDF, reading it, installing it, and its commands.

Wizards' pages and PDFs are replaced by fakes; the PDF is a small one built here, so pypdf reads a real file.

    python -m unittest discover -s tests
"""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lookup  # noqa: E402
import sources  # noqa: E402

try:
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False


def make_pdf(lines: list[tuple[str, bool]]) -> bytes:
    """A one-page PDF with each (text, bold) line set in Helvetica or Helvetica-Bold."""
    content = "".join(f"BT /{'F2' if bold else 'F1'} 12 Tf 72 {740 - 20 * i} Td ({text}) Tj ET\n"
                      for i, (text, bold) in enumerate(lines)).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


JAR_PDF = make_pdf([
    ("Judging at Regular Rules Enforcement Level", True),
    ("Updated August 5, 2024", False),
    ("Most players play for fun.", False),
    ("Common Issues", True),
    ("A player sees a card in a library that they should not have seen", True),
    ("Shuffle the card seen into the unknown portion of the library.", False),
    ("7", False),
])
WPN_PAGE = ('{"link":"https:\\u002F\\u002Fmedia.wizards.com\\u002FContentResources\\u002FWPN\\u002FMTG_IPG_2024Sep23_EN.pdf"}'
            '<a href="https://media.wizards.com/ContentResources/WPN/MTG_MTR_2026_Feb27_EN.pdf">MTR</a>')


class SourcesUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ref = Path(self.tmp.name) / "reference"
        (ref / "formats").mkdir(parents=True)
        patches = [
            mock.patch.object(lookup, "REFERENCE_DIR", ref),
            mock.patch.object(lookup, "DATA_DIR", ref),
            mock.patch.object(lookup, "DOCS_DIR", ref / "docs"),
            mock.patch.object(lookup, "RULES_FILE", ref / "MagicCompRules.txt"),
            mock.patch.object(sources, "REGISTRY", ref / "sources.json"),
            mock.patch.object(sources, "FORMATS_DIR", ref / "formats"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.ref = ref

    def tearDown(self):
        self.tmp.cleanup()

    def fake_get(self, pages: dict):
        def get(url, timeout=120):
            for key, value in pages.items():
                if key in url:
                    return value
            raise AssertionError(f"unexpected download: {url}")
        return mock.patch.object(sources, "get", get)

    def run_cmd(self, *args):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["sources.py", *args]), redirect_stdout(out):
            status = sources.main()
        return status, out.getvalue()

    def test_finds_links_only_on_wizards_host(self):
        with self.fake_get({"wpn.wizards.com": WPN_PAGE.encode()}):
            self.assertEqual(sources.find_pdf_url("ipg"), "https://media.wizards.com/ContentResources/WPN/MTG_IPG_2024Sep23_EN.pdf")
            self.assertTrue(sources.find_pdf_url("mtr").endswith("MTG_MTR_2026_Feb27_EN.pdf"))
        with self.fake_get({"magicjudges": b"<p>no link here</p>"}), self.assertRaises(SystemExit):
            sources.find_pdf_url("jar")

    @unittest.skipUnless(HAVE_PYPDF, "needs pypdf")
    def test_reads_bold_headings_and_drops_page_numbers(self):
        pdf = self.ref / "jar.pdf"
        pdf.write_bytes(JAR_PDF)
        lines = sources.pdf_lines(pdf)
        self.assertIn(("Common Issues", True), lines)
        self.assertIn(("Shuffle the card seen into the unknown portion of the library.", False), lines)
        self.assertNotIn("7", [t for t, _ in lines])
        converted = sources.convert("jar", pdf)
        self.assertEqual(converted["effective"], "August 5, 2024")
        self.assertEqual([s["heading"] for s in converted["sections"]],
                         ["Introduction", "Common Issues", "A player sees a card in a library that they should not have seen"])

    @unittest.skipUnless(HAVE_PYPDF, "needs pypdf")
    def test_update_installs_then_is_up_to_date_then_check(self):
        jar_url = "https://media.wizards.com/ContentResources/WPN/MTG_JAR_2024Aug2_EN.pdf"
        page = f'<a href="{jar_url}">JAR</a>'.encode()
        with self.fake_get({"magicjudges": page, "MTG_JAR": JAR_PDF}), \
                mock.patch.object(sources, "recheck") as recheck:
            status, out = self.run_cmd("update", "jar")
            self.assertEqual(status, 0)
            self.assertIn("Judging at Regular REL: installed, effective August 5, 2024", out)
            recheck.assert_called_once()  # a new version flags rulings that cite it
            self.assertTrue((self.ref / "docs" / "jar.json").exists())
            _, out = self.run_cmd("update", "jar")
            self.assertIn("up to date", out)
        changed = make_pdf([("Judging at Regular Rules Enforcement Level", True), ("Updated May 1, 2026", False),
                            ("Common Issues", True), ("Text.", False)])
        with self.fake_get({"magicjudges": page, "MTG_JAR": changed}):
            _, out = self.run_cmd("update", "jar", "--check")
        self.assertIn("update available", out)
        self.assertEqual(sources.load_registry()["jar"]["effective"], "August 5, 2024")  # --check installs nothing

    @unittest.skipUnless(HAVE_PYPDF, "needs pypdf")
    def test_list_and_convert(self):
        (self.ref / "version.json").write_text(json.dumps({"effective_date": "September 25, 2026", "sha256": "ab" * 32}))
        _, out = self.run_cmd("list")
        self.assertIn("cr   Comprehensive Rules: effective September 25, 2026", out)
        self.assertIn("mtr  Magic Tournament Rules: not downloaded", out)
        _, out = self.run_cmd("convert", "jar")
        self.assertIn("no PDF kept", out)
        (self.ref / "docs").mkdir()
        (self.ref / "docs" / "jar.pdf").write_bytes(JAR_PDF)
        _, out = self.run_cmd("convert", "jar")
        self.assertIn("Judging at Regular REL: 3 sections.", out)

    def test_update_cr_runs_update_rules_and_reports_change(self):
        calls = []

        def fake_run(args, check):
            calls.append(args)
            lookup.RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
            lookup.RULES_FILE.write_text("new rules", encoding="utf-8")
        with mock.patch.object(subprocess, "run", fake_run):
            self.assertTrue(sources.update_cr(check=True, force=False))
            self.assertFalse(sources.update_cr(check=False, force=True))  # same text again: unchanged
        self.assertIn("--check", calls[0])
        self.assertIn("--force", calls[1])

    def test_stale_format_files_are_reported(self):
        (self.ref / "version.json").write_text(json.dumps({"effective_date": "November 14, 2026"}))
        (self.ref / "formats" / "commander.md").write_text("---\nchecked: 2026-10-26\nsources:\n  cr: September 25, 2026\n---\n",
                                                            encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            sources.report_stale_formats()
        self.assertIn("reference/formats/commander.md: CR September 25, 2026 → November 14, 2026", out.getvalue())

    def test_recheck_runs_the_judge(self):
        result = subprocess.CompletedProcess([], 0, stdout="All rulings still match their sources.\n", stderr="")
        out = io.StringIO()
        with mock.patch.object(subprocess, "run", return_value=result) as run, redirect_stdout(out):
            sources.recheck()
        self.assertIn("recheck", run.call_args.args[0])
        self.assertIn("All rulings still match", out.getvalue())


if __name__ == "__main__":
    unittest.main()
