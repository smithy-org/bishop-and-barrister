#!/usr/bin/env python3
"""Ask Jev the three experiments' questions. Usage: python evals/jev/run_jev.py e1|e2|e3 [--force]

Reads results/inputs_e*.json (made by build_inputs.py), writes results/jev_e*.json with the raw answers, usage,
version string and latency for every call. Resumable: items already answered are skipped.
Only Magic rules text is sent. The API key never touches a file or the output.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_inputs as B  # noqa: E402
import jev_client as J  # noqa: E402

OUT = B.OUT


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(path, obj):
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def ask(store, path, key, state, questions):
    if key in store:
        return
    r = J.call(state, questions)
    resp = r["response"]
    store[key] = {"model": resp.get("model"), "answers": resp.get("answers"), "usage": resp.get("usage"),
                  "latency_ms": r["latency_ms"], "state_chars": len(state)}
    save(path, store)


def e1():
    items = json.loads((OUT / "inputs_e1.json").read_text(encoding="utf-8"))
    for v in ("a", "b"):
        path = OUT / ("jev_e1%s.json" % v)
        store = load(path)
        for it in items:
            ask(store, path, it["key"], it[v], {"settlement": J.choice(B.E1_QUESTION, B.E1_CRITERIA)})
        print("e1", v, len(store))


def e2():
    items = json.loads((OUT / "inputs_e2.json").read_text(encoding="utf-8"))
    qs = {"convinced": J.noul(B.E2_NOUL), "verdict": J.choice(B.E2_CHOICE, B.E2_CRITERIA)}
    for v in ("a", "b"):
        path = OUT / ("jev_e2%s.json" % v)
        store = load(path)
        for it in items:
            ask(store, path, it["key"], it[v], qs)
        print("e2", v, len(store))


def e3():
    items = json.loads((OUT / "inputs_e3.json").read_text(encoding="utf-8"))["items"]
    path = OUT / "jev_e3.json"
    store = load(path)
    q = {"follows": J.noul(B.E3_QUESTION, true=B.E3_TRUE, false=B.E3_FALSE)}
    for it in items:
        ask(store, path, it["key"], it["text"], q)
    print("e3", len(store))


if __name__ == "__main__":
    {"e1": e1, "e2": e2, "e3": e3}[sys.argv[1]]()
