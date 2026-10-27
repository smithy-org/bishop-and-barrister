"""CHALLENGE.md stays true to challenge.py: every command it names exists, and every JSON example parses.

    python -m unittest discover -s tests
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "CHALLENGE.md").read_text(encoding="utf-8")


class ChallengeDocTest(unittest.TestCase):
    def test_every_command_named_exists(self):
        help_text = subprocess.run([sys.executable, str(ROOT / "scripts" / "challenge.py"), "--help"],
                                   capture_output=True, text=True, encoding="utf-8").stdout
        commands = set(re.findall(r"challenge\.py (\w+)", DOC))
        self.assertTrue(commands)
        for command in commands:
            self.assertRegex(help_text, rf"\b{command}\b", f"CHALLENGE.md uses `challenge.py {command}`")

    def test_every_json_example_parses(self):
        blocks = re.findall(r"```json\n(.*?)```", DOC, re.S)
        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            json.loads(block)

    def test_five_lenses(self):
        lenses = re.findall(r"^(\d)\. \*\*", DOC.split("**The five lenses**")[1].split("### 4.")[0], re.M)
        self.assertEqual(lenses, [str(k) for k in range(1, 6)])


if __name__ == "__main__":
    unittest.main()
