"""Tests for reference/formats/: the headers sources.py reads, and the rule numbers the files cite.

The citation test reads the installed Comprehensive Rules and tournament documents, so it is skipped where
they haven't been downloaded (`python scripts/sources.py update`).

    python -m unittest discover -s tests
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
FORMATS = SCRIPTS.parent / "reference" / "formats"
sys.path.insert(0, str(SCRIPTS))
import lookup  # noqa: E402
import paths  # noqa: E402
import sources  # noqa: E402

DOC_CITE = re.compile(r"\b(CR|MTR|IPG)\s+((?:\d{3}\.\d+[a-z]?|\d+(?:\.\d+)?)(?:-[a-z])?(?:(?:,\s*|\s+and\s+)\d{3}\.\d+[a-z]?(?:-[a-z])?)*)")


def cited(text: str) -> list[tuple[str, str]]:
    """Every (document, number) a file cites, expanding ranges like 103.8a-c and lists like 903.6, 903.8."""
    out = []
    for doc, refs in DOC_CITE.findall(text):
        for ref in re.split(r",\s*|\s+and\s+", refs):
            m = re.fullmatch(r"(\d{3}\.\d+)([a-z])-([a-z])", ref)
            if m:
                out += [(doc, m.group(1) + chr(c)) for c in range(ord(m.group(2)), ord(m.group(3)) + 1)]
            else:
                out.append((doc, ref))
    return out


class HeaderTest(unittest.TestCase):
    def test_every_format_file_has_a_header(self):
        files = [p for p in FORMATS.glob("*.md") if p.name != "README.md"]
        self.assertGreaterEqual(len(files), 7)
        for path in files:
            self.assertIn("cr", sources.format_header(path), path.name)

    def test_header_lists_every_document_the_file_cites(self):
        for path in FORMATS.glob("*.md"):
            if path.name == "README.md":
                continue
            docs = {doc.lower() for doc, _ in cited(path.read_text(encoding="utf-8"))}
            self.assertLessEqual(docs, set(sources.format_header(path)), path.name)

    def test_stale_files_are_named_with_the_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.md").write_text("---\nchecked: 2026-10-26\nsources:\n  cr: September 25, 2026\n  mtr: February 27, 2026\n---\n", encoding="utf-8")
            (d / "b.md").write_text("---\nchecked: 2026-10-26\nsources:\n  cr: September 25, 2026\n---\n", encoding="utf-8")
            stale = sources.stale_formats(d, {"cr": "September 25, 2026", "mtr": "June 1, 2026"})
        self.assertEqual(stale, [("a.md", ["MTR February 27, 2026 → June 1, 2026"])])


@unittest.skipUnless(paths.rules_file().exists() and (paths.docs_dir() / "mtr.json").exists(),
                     "needs the downloaded CR and MTR (sources.py update)")
class CitationTest(unittest.TestCase):
    def test_every_cited_number_exists(self):
        lines = lookup.load()
        rules = {m.group(1) for line in lines[lookup.body_start(lines):] if (m := lookup.RULE_LINE.match(line))}
        rules |= {m.group(1) for line in lines if (m := lookup.SECTION_LINE.match(line))}
        missing = []
        for path in FORMATS.glob("*.md"):
            for doc, ref in cited(path.read_text(encoding="utf-8")):
                if doc == "CR":
                    ok = ref in rules
                else:
                    ok = bool(lookup.find_sections(doc.lower(), ref))
                if not ok:
                    missing.append(f"{path.name}: {doc} {ref}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
