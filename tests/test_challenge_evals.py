"""The challenge eval set is well formed: every case has its prompt, simulated user, expected state and graders.

    python -m unittest discover -s tests
"""

import re
import unittest
from pathlib import Path

CASES = Path(__file__).resolve().parent.parent / "evals" / "challenges"
STATES = {"introduced", "refuted", "open", "house-rule", "withdrawn"}


class ChallengeEvalsTest(unittest.TestCase):
    def test_every_case_is_complete(self):
        cases = sorted(p for p in CASES.iterdir() if p.is_dir())
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            for name in ("prompt.md", "user.md", "case.yaml"):
                self.assertTrue((case / name).exists(), f"{case.name}/{name}")
            yaml = (case / "case.yaml").read_text(encoding="utf-8")
            self.assertIn(f"name: {case.name}\n", yaml)
            state = re.search(r"^expected_state: (\S+)", yaml, re.M).group(1)
            self.assertIn(state, STATES, case.name)
            self.assertTrue(list((case / "graders").glob(f"01-the-challenge-ends-{state}.md")), case.name)

    def test_the_set_covers_every_outcome(self):
        states = [re.search(r"^expected_state: (\S+)", (p / "case.yaml").read_text(encoding="utf-8"), re.M).group(1)
                  for p in CASES.iterdir() if p.is_dir()]
        for state in ("introduced", "refuted", "open", "house-rule"):
            self.assertIn(state, states)

    def test_every_case_is_in_the_readme(self):
        readme = (CASES / "README.md").read_text(encoding="utf-8")
        for case in (p.name for p in CASES.iterdir() if p.is_dir()):
            self.assertIn(f"`{case}`", readme)


if __name__ == "__main__":
    unittest.main()
