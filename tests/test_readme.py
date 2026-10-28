"""Tests for the README and its translations: every language links to every other, and no link is broken.

    python -m unittest discover -s tests
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Each README, by the name its switcher line shows, in switcher order.
LANGUAGES = {
    "English": "README.md",
    "Deutsch": "README-de.md",
    "Español": "README-es.md",
    "Français": "README-fr.md",
    "Italiano": "README-it.md",
    "日本語": "README-ja.md",
}
LINK = re.compile(r'\]\(([^)\s]+)\)|href="([^"]+)"')
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def anchor(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


class ReadmeTest(unittest.TestCase):
    def test_every_language_links_to_the_others(self):
        for name, file in LANGUAGES.items():
            text = (ROOT / file).read_text(encoding="utf-8")
            switcher = next((line for line in text.splitlines() if "English" in line and "日本語" in line), "")
            with self.subTest(file=file):
                self.assertTrue(switcher, f"{file} has no language switcher line")
                for other, target in LANGUAGES.items():
                    linked = f'href="{target}">{other}</a>' in switcher
                    self.assertEqual(linked, other != name, f"{file}: {other} should be "
                                     + ("plain text" if other == name else f"a link to {target}"))
                names = re.findall("|".join(map(re.escape, LANGUAGES)), switcher)
                self.assertEqual(names, list(LANGUAGES), f"{file}: switcher order")

    def test_links_and_anchors_resolve(self):
        for file in LANGUAGES.values():
            text = CODE.sub("", (ROOT / file).read_text(encoding="utf-8"))
            anchors = {anchor(h) for h in re.findall(r"^#{1,6} (.+)$", text, re.M)}
            for match in LINK.finditer(text):
                target = match.group(1) or match.group(2)
                if re.match(r"[a-z]+:", target):
                    continue
                path, _, fragment = target.partition("#")
                with self.subTest(file=file, link=target):
                    if path:
                        self.assertTrue((ROOT / path).exists(), f"{file} links to a missing {path}")
                    else:
                        self.assertIn(fragment, anchors, f"{file} links to a missing heading")


if __name__ == "__main__":
    unittest.main()
