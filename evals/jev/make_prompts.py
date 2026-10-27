#!/usr/bin/env python3
"""Write one prompt file per Sonnet batch: the instructions, the input file and the results file. No API calls."""
import json
from pathlib import Path

S = Path(__file__).resolve().parent / "results" / "sonnet"
heads = json.loads((S / "heads.json").read_text(encoding="utf-8"))
batches = json.loads((S / "batches.json").read_text(encoding="utf-8"))
(S / "prompts").mkdir(exist_ok=True)
(S / "out").mkdir(exist_ok=True)
for name in batches:
    exp = name.split("_")[0][:2]
    text = heads[exp] + "\nInput file (Read it): %s\nResults file (Write it, once, JSON only): %s\n" % (
        (S / "inputs" / (name + ".txt")).as_posix(), (S / "out" / (name + ".json")).as_posix())
    (S / "prompts" / (name + ".md")).write_text(text, encoding="utf-8")
print(len(batches), "prompts")
