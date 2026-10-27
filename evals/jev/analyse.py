#!/usr/bin/env python3
"""Score Jev and Sonnet on the three experiments. Prints the tables used in README.md; writes results/summary.json."""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

R = Path(__file__).resolve().parent / "results"
PRICE_IN = 0.042 / 1e6  # published, USD per input token; output is free


def J(p):
    return json.loads((R / p).read_text(encoding="utf-8"))


def wilson(k, n, z=1.96):
    if n == 0:
        return (0, 0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def fr(k, n):
    lo, hi = wilson(k, n)
    return "%d/%d (%.0f%%, 95%% CI %.0f-%.0f%%)" % (k, n, 100 * k / n if n else 0, 100 * lo, 100 * hi)


def sonnet(prefix):
    """Merge the Sonnet output files of one experiment into key -> answer."""
    batches = J("sonnet/batches.json")
    out = {}
    missing = 0
    for b, ids in batches.items():
        if not b.startswith(prefix):
            continue
        f = R / "sonnet" / "out" / (b + ".json")
        if not f.exists():
            missing += len(ids)
            continue
        ans = {a["id"]: a for a in json.loads(f.read_text(encoding="utf-8"))}
        for m in ids:
            if m["id"] in ans:
                out[m["key"]] = ans[m["id"]]
            else:
                missing += 1
    return out, missing


def auc(pos, neg):
    """P(score of a random positive > score of a random negative), ties count half."""
    if not pos or not neg:
        return float("nan")
    s = 0
    for p in pos:
        for n in neg:
            s += 1 if p > n else 0.5 if p == n else 0
    return s / (len(pos) * len(neg))


def usage_stats(stores):
    lat = sorted(v["latency_ms"] for s in stores for v in s.values())
    tok = [v["usage"]["input_tokens"] for s in stores for v in s.values()]
    out = [v["usage"]["output_tokens"] for s in stores for v in s.values()]
    n = len(lat)
    models = Counter(v["model"] for s in stores for v in s.values())
    return {"calls": n, "latency_ms_median": lat[n // 2], "latency_ms_p95": lat[int(n * 0.95) - 1], "latency_ms_max": lat[-1],
            "latency_ms_mean": round(sum(lat) / n), "input_tokens_mean": round(sum(tok) / n), "input_tokens_total": sum(tok),
            "output_tokens_mean": round(sum(out) / n), "cost_usd_total": round(sum(tok) * PRICE_IN, 5),
            "cost_usd_per_call": round(sum(tok) * PRICE_IN / n, 7), "models": dict(models)}


def sonnet_cost(prefixes):
    led = J("sonnet/ledger.json")
    ks = [k for k in led if any(k.startswith(p) for p in prefixes)]
    return {"agents": len(ks), "tokens": sum(led[k][0] for k in ks), "seconds_mean_per_agent": round(sum(led[k][1] for k in ks) / len(ks) / 1000, 1)}


LABELS = ["settled", "gap", "contested"]


def matrix(rows):
    m = {a: Counter() for a in LABELS}
    for lab, pred in rows:
        m[lab][pred] += 1
    return m


def show_matrix(m):
    s = "| true \\ predicted | settled | gap | contested |\n| --- | --- | --- | --- |\n"
    for a in LABELS:
        s += "| %s | %d | %d | %d |\n" % (a, m[a]["settled"], m[a]["gap"], m[a]["contested"])
    return s


def calib(rows, edges):
    """rows: (confidence, correct). Accuracy by confidence band."""
    s = ""
    for lo, hi in edges:
        b = [c for conf, c in rows if lo <= conf < hi]
        s += "| %.2f-%.2f | %s |\n" % (lo, hi, fr(sum(b), len(b)) if b else "0/0")
    return s


def e1(summary):
    items = J("inputs_e1.json")
    lab = {i["key"]: i["label"] for i in items}
    grp = {i["key"]: i["group"] for i in items}
    out = ""
    for v in ("a", "b"):
        jev = J("jev_e1%s.json" % v)
        son, miss = sonnet("e1" + v)
        res = {}
        for name, getter in (("Jev", lambda k: (jev[k]["answers"]["settlement"]["choice"], jev[k]["answers"]["settlement"]["confidence"], jev[k]["answers"]["settlement"]["probabilities"])),
                             ("Sonnet 5.5", lambda k: (son[k]["label"], float(son[k]["confidence"]), None) if k in son else None)):
            rows = []
            for k in lab:
                g = getter(k)
                if g is None:
                    continue
                rows.append((k, g[0], g[1]))
            res[name] = rows
            n = len(rows)
            ok = sum(1 for k, p, c in rows if p == lab[k])
            out += "\n#### E1%s %s: %s\n\n" % (v, name, fr(ok, n))
            for gname in ("challenge", "everyday"):
                rr = [(k, p, c) for k, p, c in rows if grp[k] == gname]
                out += "- %s cases: %s\n" % (gname, fr(sum(1 for k, p, c in rr if p == lab[k]), len(rr)))
            # false alarm on everyday cases: anything but settled
            ev = [(k, p, c) for k, p, c in rows if grp[k] == "everyday" and lab[k] == "settled"]
            out += "- false alarms (an everyday settled case called gap/contested): %s\n" % fr(sum(1 for k, p, c in ev if p != "settled"), len(ev))
            ch = [(k, p, c) for k, p, c in rows if grp[k] == "challenge"]
            out += "- per challenge case: " + "; ".join("%s: %s%s" % (k[3:], p, "" if p == lab[k] else " (WRONG, should be %s)" % lab[k]) for k, p, c in ch) + "\n\n"
            out += show_matrix(matrix([(lab[k], p) for k, p, c in rows])) + "\n"
            out += "Calibration (accuracy by stated confidence):\n\n| confidence | accuracy |\n| --- | --- |\n"
            out += calib([(c, p == lab[k]) for k, p, c in rows], [(0, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)]) + "\n"
            # separation: mean confidence right vs wrong
            r_ = [c for k, p, c in rows if p == lab[k]]
            w_ = [c for k, p, c in rows if p != lab[k]]
            out += "Mean confidence when right %.2f (n=%d), when wrong %.2f (n=%d)\n" % (sum(r_) / max(len(r_), 1), len(r_), sum(w_) / max(len(w_), 1), len(w_))
            summary.setdefault("e1", {}).setdefault(v, {})[name] = {"correct": sum(1 for k, p, c in rows if p == lab[k]), "n": n}
        if miss:
            out += "\n(Sonnet missing %d answers)\n" % miss
    # always-settled baseline
    base = sum(1 for k in lab if lab[k] == "settled")
    out += "\nBaseline 'always settled': %s\n" % fr(base, len(lab))
    summary["e1_usage"] = {"a": usage_stats([J("jev_e1a.json")]), "b": usage_stats([J("jev_e1b.json")])}
    return out


PANEL = {"introduced": "introduce", "refuted": "refuse", "open": "unproven"}


def e2(summary):
    items = J("inputs_e2.json")
    out = ""
    preds = {}
    for v in ("a", "b"):
        jev = J("jev_e2%s.json" % v)
        son, miss = sonnet("e2" + v)
        preds[("Jev", v)] = {i["key"]: (jev[i["key"]]["answers"]["verdict"]["choice"], jev[i["key"]]["answers"]["verdict"]["confidence"], jev[i["key"]]["answers"]["convinced"]["noul"]) for i in items}
        preds[("Sonnet", v)] = {i["key"]: (son[i["key"]]["verdict"], None, float(son[i["key"]]["convinced"])) for i in items if i["key"] in son}
    # structural baseline: what the verifier's flags alone decide
    def baseline(i):
        return "refuse" if i["has_assumption"] else "introduce"
    out += "| run | panel | expected | structural flag rule | Jev A | Jev B | Sonnet A | Sonnet B |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n"
    for i in items:
        k = i["key"]
        cell = lambda who, v: ("%s" % preds[(who, v)][k][0]) if k in preds[(who, v)] else "-"
        out += "| %s | %s | %s | %s | %s (%.2f) | %s (%.2f) | %s | %s |\n" % (
            k.replace("challenges-", "c"), i["panel_verdict"], i["expected_verdict"], baseline(i),
            preds[("Jev", "a")][k][0], preds[("Jev", "a")][k][2], preds[("Jev", "b")][k][0], preds[("Jev", "b")][k][2], cell("Sonnet", "a"), cell("Sonnet", "b"))
    out += "\n(Jev cells show the verdict and the 'convinced' value.)\n\n"
    n = len(items)
    rows = []
    summary["e2"] = {}
    for who in ("Jev", "Sonnet"):
        for v in ("a", "b"):
            p = preds[(who, v)]
            ok_exp = sum(1 for i in items if i["key"] in p and p[i["key"]][0] == i["expected_verdict"])
            ok_panel = sum(1 for i in items if i["key"] in p and p[i["key"]][0] == i["panel_verdict"])
            wrong_panel = [i for i in items if i["panel_verdict"] != i["expected_verdict"] and i["key"] in p]
            caught = sum(1 for i in wrong_panel if p[i["key"]][0] == i["expected_verdict"])
            right_panel = [i for i in items if i["panel_verdict"] == i["expected_verdict"] and i["key"] in p]
            overturn = sum(1 for i in right_panel if p[i["key"]][0] != i["panel_verdict"])
            nn = sum(1 for i in items if i["key"] in p)
            rows.append("| %s %s | %s | %s | %s | %s |" % (who, "A (case only)" if v == "a" else "B (case + judges' last evidence)", fr(ok_exp, nn), fr(ok_panel, nn),
                                                          "%d/%d" % (caught, len(wrong_panel)), "%d/%d" % (overturn, len(right_panel))))
            summary["e2"]["%s_%s" % (who, v)] = {"matches_expected": ok_exp, "matches_panel": ok_panel, "n": nn, "catches_panel_errors": caught, "panel_errors": len(wrong_panel), "wrongly_overturns_correct_panel": overturn, "correct_panels": len(right_panel)}
    base_ok = sum(1 for i in items if baseline(i) == i["expected_verdict"])
    out += "| rater | agrees with expected outcome | agrees with the panel's final state | catches the panel's wrong outcomes | disagrees with a correct panel |\n| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
    out += "| Flag rule alone (any assumption step => refuse, else introduce) | %s | - | - | - |\n" % fr(base_ok, n)
    out += "\nPanel itself vs expected: %s\n" % fr(sum(1 for i in items if i["panel_verdict"] == i["expected_verdict"]), n)
    # confusion for Jev B and Sonnet B vs expected
    for who, v in (("Jev", "a"), ("Jev", "b"), ("Sonnet", "a"), ("Sonnet", "b")):
        p = preds[(who, v)]
        c = Counter((i["expected_verdict"], p[i["key"]][0]) for i in items if i["key"] in p)
        out += "\n%s %s, expected (rows) vs verdict (columns):\n\n| expected | introduce | refuse | unproven |\n| --- | --- | --- | --- |\n" % (who, v.upper())
        for e in ("introduce", "refuse", "unproven"):
            out += "| %s | %d | %d | %d |\n" % (e, c[(e, "introduce")], c[(e, "refuse")], c[(e, "unproven")])
    # convinced as score: AUC for expected==introduce
    for who, v in (("Jev", "a"), ("Jev", "b"), ("Sonnet", "a"), ("Sonnet", "b")):
        p = preds[(who, v)]
        pos = [p[i["key"]][2] for i in items if i["expected_verdict"] == "introduce" and i["key"] in p]
        neg = [p[i["key"]][2] for i in items if i["expected_verdict"] != "introduce" and i["key"] in p]
        out += "\n%s %s 'convinced' separates should-introduce (n=%d) from the rest (n=%d): AUC %.2f; mean %.2f vs %.2f" % (
            who, v.upper(), len(pos), len(neg), auc(pos, neg), sum(pos) / max(len(pos), 1), sum(neg) / max(len(neg), 1))
    out += "\n"
    summary["e2_usage"] = {"a": usage_stats([J("jev_e2a.json")]), "b": usage_stats([J("jev_e2b.json")])}
    return out


def e3(summary):
    d = J("inputs_e3.json")
    items = d["items"]
    jev = J("jev_e3.json")
    son, miss = sonnet("e3")
    out = ""
    for who, get in (("Jev", lambda k: jev[k]["answers"]["follows"]["noul"]), ("Sonnet 5.5", lambda k: float(son[k]["follows"]) if k in son else None)):
        for scope, flt in (("all %d steps in any recorded case version" % len({i["step"] for i in items}), lambda i: True),
                           ("the %d steps of the final cases" % len({i["step"] for i in items if i["in_final_case"]}), lambda i: i["in_final_case"])):
            sel = [i for i in items if flt(i) and get(i["key"]) is not None]
            orig = [get(i["key"]) for i in sel if i["variant"] == "orig"]
            out += "\n#### E3 %s, %s\n\n" % (who, scope)
            out += "| threshold (flag when value below) | false alarms on originals | detected: negated | detected: swapped conclusion | detected: unrelated excerpt | detected: all corrupted |\n| --- | --- | --- | --- | --- | --- |\n"
            for t in (0.3, 0.5, 0.7, 0.9):
                fa = sum(1 for x in orig if x < t)
                cells = []
                tot = 0
                totn = 0
                for var in ("neg", "swap", "excerpt"):
                    vals = [get(i["key"]) for i in sel if i["variant"] == var]
                    k = sum(1 for x in vals if x < t)
                    tot += k
                    totn += len(vals)
                    cells.append(fr(k, len(vals)))
                out += "| %.1f | %s | %s | %s | %s | %s |\n" % (t, fr(fa, len(orig)), cells[0], cells[1], cells[2], fr(tot, totn))
            cor = [get(i["key"]) for i in sel if i["corrupted"]]
            out += "\nAUC (original ranks above corrupted): %.2f. Mean value: originals %.2f, corrupted %.2f.\n" % (auc(orig, cor), sum(orig) / len(orig), sum(cor) / len(cor))
            if scope.startswith("all") and who == "Jev":
                sw = [i for i in sel if i["variant"] == "swap"]
                for kind in ("same_case", "other_case"):
                    vals = [get(i["key"]) for i in sw if i.get("swap_kind") == kind]
                    if vals:
                        out += "- swapped conclusion, %s: %s detected at 0.5\n" % (kind, fr(sum(1 for x in vals if x < 0.5), len(vals)))
            summary.setdefault("e3", {})["%s | %s" % (who, scope)] = {"auc": round(auc(orig, cor), 3), "n_orig": len(orig), "n_corrupt": len(cor)}
    if miss:
        out += "\n(Sonnet missing %d)\n" % miss
    # which originals did Jev flag?
    flagged = [(i["key"], jev[i["key"]]["answers"]["follows"]["noul"]) for i in items if i["variant"] == "orig" and jev[i["key"]]["answers"]["follows"]["noul"] < 0.5]
    out += "\nOriginals Jev flagged below 0.5: %s\n" % flagged
    summary["e3_usage"] = usage_stats([jev])
    return out


def main():
    summary = {}
    txt = {}
    txt["e1"] = e1(summary)
    txt["e2"] = e2(summary)
    txt["e3"] = e3(summary)
    summary["sonnet_cost"] = {"e1": sonnet_cost(["e1"]), "e2": sonnet_cost(["e2"]), "e3": sonnet_cost(["e3"])}
    (R / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    (R / "tables.md").write_text("\n\n".join("## %s\n%s" % (k, v) for k, v in txt.items()), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for k, v in txt.items():
        print("=====", k)
        print(v)
    print(json.dumps({k: summary[k] for k in summary if "usage" in k or "cost" in k}, indent=1))


if __name__ == "__main__":
    main()
