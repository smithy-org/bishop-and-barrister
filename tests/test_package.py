"""Tests for the two install routes: the claude.ai zip (tools/package_skill.py) and the Claude Code plugin.

    python -m unittest discover -s tests
"""

import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import package_skill  # noqa: E402


class ZipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "skill.zip"

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_folder_named_after_the_skill(self):
        names = package_skill.build(self.out)
        self.assertEqual({n.split("/")[0] for n in names}, {"bishop-and-barrister"})
        for needed in ("SKILL.md", "CHALLENGE.md", "scripts/judge.py", "scripts/lookup.py", "reference/formats/commander.md",
                       "challenge/binaries.json", "LICENSE", "NOTICE"):
            self.assertIn(f"bishop-and-barrister/{needed}", names)

    def test_only_runtime_files(self):
        names = package_skill.build(self.out)
        for left_out in ("tests/", "evals/", "docs/", ".github/", "tools/", "challenge/Challenge", "__pycache__",
                         "MagicCompRules.txt", "reference/docs/"):
            self.assertFalse([n for n in names if left_out in n], left_out)

    def test_skill_md_meets_claude_ai_limits(self):
        package_skill.build(self.out)
        text = zipfile.ZipFile(self.out).read("bishop-and-barrister/SKILL.md").decode("utf-8")
        fields, body = package_skill.frontmatter(text)
        self.assertEqual(set(fields), {"name", "description"})  # when_to_use is Claude Code's, not claude.ai's
        self.assertEqual(fields["name"], "bishop-and-barrister")
        self.assertLessEqual(len(fields["description"]), 200)
        self.assertIn("Magic: the Gathering", fields["description"])  # a real colon, not &#58;
        self.assertIn("## Answering a rules question", body)

    def test_a_release_ships_its_own_pins(self):
        pins = Path(self.tmp.name) / "pins.json"
        pins.write_text('{"release": "v9.9.9", "binaries": {}}', encoding="utf-8")
        package_skill.build(self.out, pins)
        shipped = json.loads(zipfile.ZipFile(self.out).read("bishop-and-barrister/challenge/binaries.json"))
        self.assertEqual(shipped["release"], "v9.9.9")

    def test_refuses_a_description_claude_ai_would_reject(self):
        long_skill = "---\nname: bishop-and-barrister\ndescription: " + "x" * 201 + "\n---\nbody\n"
        with mock.patch.object(Path, "read_text", return_value=long_skill), self.assertRaises(SystemExit):
            package_skill.skill_md_for_claude_ai()


class PluginTest(unittest.TestCase):
    def test_marketplace_lists_the_plugin_at_the_repository_root(self):
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        entry = market["plugins"][0]
        self.assertEqual(entry["name"], plugin["name"])  # a mismatch breaks install by name
        self.assertEqual(entry["source"], "./")
        self.assertTrue((ROOT / "SKILL.md").exists())  # a root SKILL.md loads as the plugin's one skill

    def test_plugin_version_is_the_release_version(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        main = (ROOT / "challenge" / "Main.lean").read_text(encoding="utf-8")
        program = re.search(r'def version : String := "bab-challenge (\d+\.\d+\.\d+)', main).group(1)
        self.assertEqual(plugin["version"], program, "bump .claude-plugin/plugin.json with challenge/Main.lean")

    def test_skill_md_frontmatter_for_claude_code(self):
        fields, _ = package_skill.frontmatter((ROOT / "SKILL.md").read_text(encoding="utf-8"))
        self.assertLessEqual(len(fields["description"]) + len(fields.get("when_to_use", "")), 1536)


if __name__ == "__main__":
    unittest.main()
