#!/usr/bin/env python3
"""Build the exact texts that Jev and Sonnet are asked about, from the recorded runs and the eval cases.

Writes, under results/:
  inputs_e1.json, inputs_e2.json, inputs_e3.json   the items with their labels (the answer key stays here)
  sonnet/inputs/<batch>.txt                         what a Sonnet subagent reads: opaque ids, the same text Jev saw
  sonnet/batches.json                               batch name -> list of item keys, in the order shown
Nothing here calls any API. Run it from anywhere:  python evals/jev/build_inputs.py
"""
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data  # noqa: E402

OUT = data.HERE / "results"
SONNET = OUT / "sonnet"
SEED = 20261027
CAP_SOURCE = 600


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- E1
def everyday_cases():
    base = data.REPO / "evals"
    out = []
    for d in sorted(base.iterdir()):
        if not (d / "prompt.md").exists() or d.name == "challenges":
            continue
        out.append(d.name)
    return out


def everyday_rule_numbers(case):
    t = (data.REPO / "evals" / case / "case.yaml").read_text(encoding="utf-8")
    m = re.search(r"Sources:(.*)", t)
    if not m:
        return [], []
    line = m.group(1)
    cr, other = [], []
    for seg in re.finditer(r"\bCR ([^;]*)", line):
        for tok in re.finditer(r"(\d{3}\.\d+)([a-z]?)(?:-([a-z]))?", seg.group(1)):
            base, a, b = tok.groups()
            if a and b:
                cr += [base + chr(c) for c in range(ord(a), ord(b) + 1)]
            else:
                cr.append(base + a)
    for tok in re.finditer(r"(Magic Tournament Rules|Infraction Procedure Guide|Judging at Regular REL|MTR|IPG|JAR) (\d+(?:\.\d+)?)", line):
        d = {"Magic Tournament Rules": "mtr", "MTR": "mtr", "Infraction Procedure Guide": "ipg", "IPG": "ipg",
             "Judging at Regular REL": "jar", "JAR": "jar"}[tok.group(1)]
        other.append((d, tok.group(2)))
    return cr[:5], other[:3]


def clip(t, n=CAP_SOURCE):
    t = t.strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " ..."


def e1_items(runs):
    items = []
    by_case = {}
    for r in runs:
        by_case.setdefault(r["case"], []).append(r)
    label = {}
    for case in by_case:
        exp = data.expected_state(case)
        label[case] = {"introduced": "gap", "open": "contested"}.get(exp, "settled")
    for case, rs in sorted(by_case.items()):
        stmt = data.challenge_statement(case)
        base = 'A player proposes this to a Magic: the Gathering rules panel:\n"%s"' % stmt
        srcs = [data.render_source((d, r, clip(e))) for d, r, e in data.cited_sources(rs)[:10]]
        items.append({"key": "ch/" + case, "group": "challenge", "case": case, "label": label[case],
                      "a": base, "b": base + "\n\nOfficial source text the judges cited:\n" + "\n".join(srcs)})
    for case in everyday_cases():
        q = data.front_matter_body((data.REPO / "evals" / case / "prompt.md").read_text(encoding="utf-8"))
        base = 'A player asks a Magic: the Gathering rules question:\n"%s"' % q
        cr, other = everyday_rule_numbers(case)
        texts = [data.render_source(("cr", n, clip(t))) for n, t in data.rule_texts(cr).items()]
        for d, n in other:
            for _, t in data.rule_texts([n], doc=d).items():
                texts.append(data.render_source((d, n, clip(t))))
        b = base + ("\n\nOfficial source text:\n" + "\n".join(texts) if texts else "\n\n(No rule text could be attached.)")
        lab = "contested" if case == "magar-aftermath-unsettled" else "settled"
        items.append({"key": "ev/" + case, "group": "everyday", "case": case, "label": lab,
                      "a": base, "b": b, "n_sources": len(texts)})
    return items


E1_QUESTION = ("Do the official Magic: the Gathering sources (the Comprehensive Rules, Oracle card text and official "
               "rulings, the tournament documents) already settle the question this text raises?")
E1_CRITERIA = {
    "settled": "An official source answers the question, directly or by plain application, whether for or against what is claimed or asked.",
    "gap": "The official sources are silent on exactly this situation (for example a rule written for a different case); nothing official decides it.",
    "contested": "Official sources apply but support two different readings, and no source says which reading is right.",
}


# ---------------------------------------------------------------- E2
E2_NOUL = ("Would a careful judge be convinced that this proposed rule should be introduced: every step that claims to "
           "follow from a quoted source really does, no quoted official text contradicts the rule, and any gap it fills "
           "is a real gap?")
E2_CHOICE = "What should be done with this case for a rule?"
E2_CRITERIA = {
    "introduce": "The case is sound and fills a real gap: the official sources are silent, no source contradicts the rule, and no step rests on an unsupported assumption.",
    "refuse": "An official source contradicts the rule or the case, or the argument fails against a counterexample or a missing source.",
    "unproven": "The case rests on a step that no source supports, or the sources allow two readings; it is neither shown nor refuted.",
}
PANEL_TO_VERDICT = {"introduced": "introduce", "refuted": "refuse", "open": "unproven"}


def e2_items(runs):
    items = []
    for r in runs:
        c = data.final_case(r)
        a = "A user wants a new rule introduced into Magic: the Gathering's rules record. Their case, as it stands:\n\n" + data.render_case(c)
        b = a + "\n\nThe last position each reviewing judge filed:\n" + data.last_positions(r)
        items.append({
            "key": r["key"], "case": r["case"], "run": r["round"], "panel_state": r["final_state"],
            "panel_verdict": PANEL_TO_VERDICT[r["final_state"]], "expected_state": r["expected"],
            "expected_verdict": PANEL_TO_VERDICT[r["expected"]], "has_assumption": any(s.get("assumption") for s in c["steps"]),
            "has_stipulation": any(s.get("stipulation") for s in c["steps"]), "a": a, "b": b})
    return items


# ---------------------------------------------------------------- E3
def resolve_premises(case, step):
    facts = {"F%s" % f["id"]: f["text"] for f in case.get("facts", [])}
    steps = {"S%s" % s["id"]: s["conclusion"] for s in case.get("steps", [])}
    out = []
    for p in step.get("premises", []):
        out.append("%s: %s" % (p, facts.get(p) or steps.get(p) or "(unresolved)"))
    return out


def step_text(premises, src, conclusion):
    return ("A step in a Magic: the Gathering rules argument.\nPREMISES:\n" + "\n".join("  " + p for p in premises)
            + "\nQUOTED OFFICIAL SOURCE: " + data.render_source((src["doc"], src["ref"], src["excerpt"]))
            + "\nCLAIMED CONCLUSION: " + conclusion)


def e3_steps(runs):
    """Every distinct sourced step in every recorded version of the case; flag the ones in a final case."""
    seen = {}
    for r in runs:
        final = data.final_case(r)
        versions = [e["case"] for e in r["events"] if e["type"] in ("brief", "edit", "answer") and isinstance(e.get("case"), dict)]
        for ci, case in enumerate(versions):
            for s in case.get("steps", []):
                src = s.get("source")
                if not src or not src.get("excerpt") or s.get("assumption") or s.get("stipulation"):
                    continue
                prem = resolve_premises(case, s)
                key = (s["conclusion"], src["doc"], src["ref"], src["excerpt"], tuple(prem))
                rec = seen.setdefault(key, {"case": r["case"], "run": r["round"], "premises": prem, "source": {k: src[k] for k in ("doc", "ref", "excerpt")},
                                            "conclusion": s["conclusion"], "in_final_case": False,
                                            "siblings": [t["conclusion"] for t in case["steps"]
                                                         if t["id"] != s["id"] and t.get("source") and not t.get("assumption") and not t.get("stipulation")]})
                if case is final:
                    rec["in_final_case"] = True
    steps = list(seen.values())
    for i, s in enumerate(steps):
        s["id"] = "s%03d" % i
    return steps


def negate(c):
    return "It is not true that " + c[0].lower() + c[1:] if c else c


def e3_items(steps):
    rng = random.Random(SEED)
    items = []
    for s in steps:
        base = {"step": s["id"], "case": s["case"], "in_final_case": s["in_final_case"]}
        items.append(dict(base, key=s["id"] + "/orig", variant="orig", corrupted=False,
                          text=step_text(s["premises"], s["source"], s["conclusion"])))
        items.append(dict(base, key=s["id"] + "/neg", variant="neg", corrupted=True,
                          text=step_text(s["premises"], s["source"], negate(s["conclusion"]))))
        same = [c for c in s["siblings"] if c != s["conclusion"]]
        other = [t["conclusion"] for t in steps if t["case"] != s["case"]]
        if same:
            sw, kind = rng.choice(same), "same_case"
        else:
            sw, kind = rng.choice(other), "other_case"
        items.append(dict(base, key=s["id"] + "/swap", variant="swap", swap_kind=kind, corrupted=True,
                          text=step_text(s["premises"], s["source"], sw)))
        cands = [t for t in steps if t["case"] != s["case"] and t["source"]["ref"] != s["source"]["ref"]]
        o = rng.choice(cands)
        items.append(dict(base, key=s["id"] + "/excerpt", variant="excerpt", corrupted=True,
                          text=step_text(s["premises"], o["source"], s["conclusion"])))
    return items


E3_QUESTION = ("Does the claimed conclusion follow from the premises and the quoted official source, saying nothing that "
               "they do not support?")
E3_TRUE = "The conclusion is a correct reading of the premises and the quoted official text, no stronger than they support."
E3_FALSE = "The conclusion contradicts, goes beyond, or has nothing to do with the premises and the quoted official text."


# ---------------------------------------------------------------- Sonnet batches
E1_HEAD = """You are taking part in an evaluation. Use no tools except: Read on the one input file named below, and Write once for the results file named below. Do not search, browse or read anything else. Answer from the text of each item only; judge every item independently.

Question for every item: """ + E1_QUESTION + """
Answer with exactly one word per item:
""" + "\n".join("- %s: %s" % (k, v) for k, v in E1_CRITERIA.items()) + """

Give a confidence between 0 and 1: your probability that your label is the right one.
"""

E2_HEAD = """You are taking part in an evaluation. Use no tools except: Read on the one input file named below, and Write once for the results file named below. Do not search, browse or read anything else. Answer from the text of each item only; judge every item independently.

Each item is a user's case for a new Magic: the Gathering rule (the quoted sources are exact). Two questions per item:
1. convinced: """ + E2_NOUL + """ Give a probability between 0 and 1 (1 = surely convinced).
2. verdict: """ + E2_CHOICE + """ Exactly one word:
""" + "\n".join("- %s: %s" % (k, v) for k, v in E2_CRITERIA.items()) + "\n"

E3_HEAD = """You are taking part in an evaluation. Use no tools except: Read on the one input file named below, and Write once for the results file named below. Do not search, browse or read anything else. Answer from the text of each item only; judge every item independently.

Question for every item: """ + E3_QUESTION + """
Give a probability between 0 and 1 that it does follow (1 = it surely follows; 0 = surely not). True means: """ + E3_TRUE + " False means: " + E3_FALSE + "\n"

TAILS = {
    "e1": 'Results file: a JSON list, one object per item: {"id": "...", "label": "settled|gap|contested", "confidence": 0.0-1.0}.',
    "e2": 'Results file: a JSON list, one object per item: {"id": "...", "convinced": 0.0-1.0, "verdict": "introduce|refuse|unproven"}.',
    "e3": 'Results file: a JSON list, one object per item: {"id": "...", "follows": 0.0-1.0}.',
}


def write_batches(name, items, text_of, n_batches, assign=None):
    rng = random.Random(SEED + sum(map(ord, name)))
    ids = list(range(len(items)))
    rng.shuffle(ids)
    batches = [[] for _ in range(n_batches)]
    for pos, i in enumerate(ids):
        b = assign(i, items[i]) if assign else pos % n_batches
        batches[b].append(i)
    out = {}
    for bi, members in enumerate(batches):
        rng.shuffle(members)
        bname = "%s_%d" % (name, bi)
        lines = []
        keys = []
        for j, i in enumerate(members):
            qid = "q%d%02d" % (bi + 1, j + 1)
            lines.append("=== ITEM %s ===\n%s\n" % (qid, text_of(items[i])))
            keys.append({"id": qid, "key": items[i]["key"]})
        (SONNET / "inputs").mkdir(parents=True, exist_ok=True)
        (SONNET / "inputs" / (bname + ".txt")).write_text("\n".join(lines), encoding="utf-8")
        out[bname] = keys
    return out


def main():
    runs = data.load_runs()
    batches = {}
    e1 = e1_items(runs)
    dump(OUT / "inputs_e1.json", e1)
    batches.update(write_batches("e1a", e1, lambda it: it["a"], 4))
    batches.update(write_batches("e1b", e1, lambda it: it["b"], 8))
    e2 = e2_items(runs)
    dump(OUT / "inputs_e2.json", e2)
    batches.update(write_batches("e2a", e2, lambda it: it["a"], 3))
    batches.update(write_batches("e2b", e2, lambda it: it["b"], 3))
    steps = e3_steps(runs)
    items3 = e3_items(steps)
    dump(OUT / "inputs_e3.json", {"steps": steps, "items": items3})
    # Sonnet sample: at most 40 steps, every step in a final case first, then a seeded draw of the rest.
    rng = random.Random(SEED)
    final = [s for s in steps if s["in_final_case"]]
    rest = [s for s in steps if not s["in_final_case"]]
    rng.shuffle(rest)
    sample = (final + rest)[:40]
    sample_ids = {s["id"] for s in sample}
    sample_items = [it for it in items3 if it["step"] in sample_ids]
    sidx = {s["id"]: i for i, s in enumerate(sample)}
    vidx = {"orig": 0, "neg": 1, "swap": 2, "excerpt": 3}
    nb = 8
    batches.update(write_batches("e3", sample_items, lambda it: it["text"], nb,
                                 assign=lambda i, it: (sidx[it["step"]] + 2 * vidx[it["variant"]]) % nb))
    dump(SONNET / "batches.json", batches)
    dump(SONNET / "heads.json", {"e1": E1_HEAD + TAILS["e1"], "e2": E2_HEAD + TAILS["e2"], "e3": E3_HEAD + TAILS["e3"]})
    print("runs", len(runs), "e1 items", len(e1), "e2 items", len(e2), "e3 steps", len(steps),
          "(final-case %d)" % len(final), "e3 items", len(items3), "sonnet sample steps", len(sample),
          "sample items", len(sample_items))
    for k in ("a", "b"):
        print("e1", k, "chars max/mean", max(len(i[k]) for i in e1), sum(len(i[k]) for i in e1) // len(e1))
    print("e2 chars max", max(len(i["b"]) for i in e2))


if __name__ == "__main__":
    main()
