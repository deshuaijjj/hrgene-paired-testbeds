#!/usr/bin/env python3
"""Pre-registered analysis of the v5 de-confounded testbed (DECONFOUND_PLAN.md section 4; ANALYSIS_PLAN_V5.md).

This file is frozen (hashed and registered on OSF) before any v5 generation. It reuses, unchanged, the frozen v4
scorer (runtime/hrgene/scoring.py), the source-type policies and the content-blind S transform of
redactor_frontier.py, and the Newcombe method-10 paired interval of tab4_contrasts.py.

Inputs (per model): experiments/<prefix>-C2-v5/ (outputs, score_rows.jsonl) and experiments/<prefix>-C4-v5/
(final/*.json, score_rows.jsonl), benchmark/v5/cases and benchmark/v5/gold.
Bait location of a risk case = sourceType of its gold bait source; a control is "note-only-valid" when one of its gold
valid-claim signatures occurs only in note sources. Both are read from cases + gold, so the script also runs on v4.

  P1 (primary)  per model: trap-failure rate of each source-type policy minus C4, paired over risk cases scored under
                both (Newcombe method 10); the primary comparison is the policy with the lowest failure rate (ties: the
                first in redactor_frontier.SOURCE_POLICIES order); also within non-note and note bait subsets.
  P2            per model: C2->C4 clearance by bait location (Wilson), note minus non-note (Newcombe hybrid score
                interval for independent proportions); repair-log rules on cleared cases by location (descriptive).
  P3            per model: retention on controls, each source-type policy minus C4 (case bootstrap, B = 10000);
                also within note-only-valid controls.
  P4            per model: trap-failure rate of the content-blind S relabel curve interpolated at C4's supported-side
                items per case (seed means), against C4; all families and non-decision families.
Usage: python3 analysis/v5_preregistered.py [--bench v5] [--suffix v5] [--out analysis/v5_preregistered]"""
import argparse
import glob
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import redactor_frontier as RF  # noqa: E402  (helpers and constants only; main() is not called)
import tab4_contrasts as TC  # noqa: E402  (wilson / newcombe_paired only)
from hrgene import bundle as B, scoring, pipeline  # noqa: E402
from hrgene.validator import Validator  # noqa: E402

RISK, CONTROL = "positive_risk", "matched_clean_control"
SEED, NBOOT = 20261009, 10000
Z = 1.959963984540054
DECISION_RULE = RF.DECISION_RULE


def load_rows(run_dir):
    p = os.path.join(run_dir, "score_rows.jsonl")
    return {r["caseId"]: r for r in (json.loads(s) for s in open(p, encoding="utf-8") if s.strip())}


def discover(suffix):
    runs = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "experiments", f"*-C2-{suffix}"))):
        cfg = json.load(open(os.path.join(d, "config.json"), encoding="utf-8"))
        model = (cfg.get("identity") or {}).get("model") or cfg.get("model")
        pre = os.path.basename(d)[: -len(f"-C2-{suffix}")]
        if os.path.isdir(os.path.join(ROOT, "experiments", f"{pre}-C4-{suffix}")):
            runs[model] = pre
    return runs


def bait_location(case, gold):
    t = gold.get("trap") or {}
    types = {e["sourceId"]: e["sourceType"] for e in case["candidate"]["evidence"]}
    locs = {types.get(s) for s in t.get("baitSourceIds", [])}
    return locs.pop() if len(locs) == 1 else "mixed"


def note_only_valid(case, gold):
    for sig in gold.get("validClaimSignatures", []):
        hits = [e["sourceType"] for e in case["candidate"]["evidence"] if sig.lower() in e["text"].lower()]
        if hits and all(t == "note" for t in hits):
            return True
    return False


def newcombe_unpaired(k1, n1, k2, n2):
    """Newcombe (1998b) hybrid score interval for p1 - p2 (independent proportions), Wilson limits without correction."""
    if not n1 or not n2:
        return None, None, None
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = TC.wilson(k1, n1)
    l2, u2 = TC.wilson(k2, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def paired_policy_vs_c4(pol, c4, ids):
    """Paired 2x2 over risk ids scored under both: first = policy, second = C4; theta = policy rate - C4 rate."""
    ids = [i for i in ids if pol.get(i, {}).get("trapFellAny") is not None and c4.get(i, {}).get("trapFellAny") is not None]
    e = sum(1 for i in ids if pol[i]["trapFellAny"] and c4[i]["trapFellAny"])
    f = sum(1 for i in ids if pol[i]["trapFellAny"] and not c4[i]["trapFellAny"])
    g = sum(1 for i in ids if (not pol[i]["trapFellAny"]) and c4[i]["trapFellAny"])
    h = len(ids) - e - f - g
    out = {"n": len(ids), "both": e, "policyOnly": f, "c4Only": g, "neither": h,
           "policyRate": (e + f) / len(ids) if ids else None, "c4Rate": (e + g) / len(ids) if ids else None}
    if ids:
        lo, hi = TC.newcombe_paired(e, f, g, h)  # interval for (e+f)/n - (e+g)/n = policy - C4
        out.update({"diff": out["policyRate"] - out["c4Rate"], "lo": lo, "hi": hi})
    return out


def boot_mean(vals, rng):
    if not vals:
        return None, None, None
    n = len(vals)
    means = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(NBOOT))
    return sum(vals) / n, means[int(0.025 * NBOOT)], means[int(0.975 * NBOOT) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="v5")
    ap.add_argument("--suffix", default="v5")
    ap.add_argument("--out", default=os.path.join(HERE, "v5_preregistered"))
    args = ap.parse_args()
    bench = os.path.join(ROOT, "benchmark", args.bench)
    cases, gold = RF.load_dir(os.path.join(bench, "cases")), RF.load_dir(os.path.join(bench, "gold"))
    v = Validator()
    lex = v.rs.lex
    safe_flags = RF.repairer_safe_flags(v.rs)
    loc = {c: bait_location(cases[c], gold[c]) for c in gold if gold[c]["controlStatus"] == RISK}
    nov = {c: note_only_valid(cases[c], gold[c]) for c in gold if gold[c]["controlStatus"] == CONTROL}
    runs = discover(args.suffix)
    report = {"bench": args.bench, "suffix": args.suffix, "rulesetDigest": v.rs.digest, "runs": runs,
              "design": {"baitLocations": {k: sum(1 for x in loc.values() if x == k) for k in sorted(set(loc.values()))},
                         "noteOnlyValidControls": sum(nov.values()), "controls": len(nov),
                         "sourcePolicies": list(RF.SOURCE_POLICIES), "sFractions": RF.FRACTIONS, "sSeeds": RF.SEEDS,
                         "bootstrap": {"B": NBOOT, "seed": SEED}}, "models": {}}
    for model, pre in runs.items():
        c2_dir = os.path.join(ROOT, "experiments", f"{pre}-C2-{args.suffix}")
        c4_dir = os.path.join(ROOT, "experiments", f"{pre}-C4-{args.suffix}")
        c2, c4 = load_rows(c2_dir), load_rows(c4_dir)
        base = []
        for f in sorted(glob.glob(os.path.join(c2_dir, "outputs", "*.r0.json"))):
            rec = json.load(open(f, encoding="utf-8"))
            case = cases.get(rec.get("case_id"))
            if case is None:
                continue
            b = pipeline.parse_output(rec.get("content", ""))
            base.append((case, gold[case["caseId"]], B.lift_string_items(b) if isinstance(b, dict) else b))
        # source-type policies (definitions unchanged from redactor_frontier.py)
        pol_rows = {}
        for name in RF.SOURCE_POLICIES:
            base_name, with_x = (name[:-2], True) if name.endswith("+X") else (name, False)
            rows = {}
            for case, g, b in base:
                if isinstance(b, dict):
                    bb = RF.apply(b, RF.note_pick(case, b, base_name == "drop_note_or_unsourced"), "relabel")
                    if with_x:
                        bb = RF.blind_X(bb, RF.NOTE_X_R, RF.SEEDS[0], case["caseId"], safe_flags)
                else:
                    bb = b
                rows[case["caseId"]] = scoring.score_bundle(case, g, bb, None, lex)
            pol_rows[name] = rows
        risk_ids = sorted(i for i in loc if i in c4)
        nonnote = [i for i in risk_ids if loc[i] != "note"]
        note = [i for i in risk_ids if loc[i] == "note"]
        # P1
        p1 = {name: {"all": paired_policy_vs_c4(r, c4, risk_ids), "nonNote": paired_policy_vs_c4(r, c4, nonnote),
                     "note": paired_policy_vs_c4(r, c4, note)} for name, r in pol_rows.items()}
        best = min(RF.SOURCE_POLICIES, key=lambda n: (p1[n]["all"]["policyRate"] if p1[n]["all"]["policyRate"] is not None else 2,
                                                       RF.SOURCE_POLICIES.index(n)))
        # P2
        def clear(ids):
            fails = [i for i in ids if c2.get(i, {}).get("trapFellAny") and c4.get(i, {}).get("trapFellAny") is not None]
            k = sum(1 for i in fails if not c4[i]["trapFellAny"])
            lo, hi = TC.wilson(k, len(fails))
            return {"c2Fail": len(fails), "cleared": k, "rate": k / len(fails) if fails else None, "lo": lo, "hi": hi, "ids": fails}
        p2 = {"byLocation": {l: clear([i for i in risk_ids if loc[i] == l]) for l in sorted(set(loc.values()))},
              "note": clear(note), "nonNote": clear(nonnote)}
        d = newcombe_unpaired(p2["note"]["cleared"], p2["note"]["c2Fail"], p2["nonNote"]["cleared"], p2["nonNote"]["c2Fail"])
        p2["noteMinusNonNote"] = {"diff": d[0], "lo": d[1], "hi": d[2]}
        finals = {}
        for f in glob.glob(os.path.join(c4_dir, "final", "*.json")):
            rec = json.load(open(f, encoding="utf-8"))
            finals[rec["case_id"]] = rec
        trig = {}
        for l, x in p2["byLocation"].items():
            counts = {}
            for i in x["ids"]:
                if not c4[i]["trapFellAny"]:
                    for r in sorted({e["rule"] for e in (finals.get(i, {}).get("repairLog") or [])}):
                        counts[r] = counts.get(r, 0) + 1
            trig[l] = counts
        p2["repairRulesOnClearedCases"] = trig
        fam = {}
        for i in risk_ids:
            key = f"{gold[i]['family']}|{loc[i]}"
            x = fam.setdefault(key, {"n": 0, "c2Fail": 0, "cleared": 0})
            x["n"] += 1
            if c2.get(i, {}).get("trapFellAny") and c4[i].get("trapFellAny") is not None:
                x["c2Fail"] += 1
                x["cleared"] += int(not c4[i]["trapFellAny"])
        p2["byFamilyLocation"] = fam
        # P3
        rng = random.Random(SEED)
        def ret(rows, ids):
            ids = [i for i in ids if rows.get(i, {}).get("validClaimPreserved") is not None and c4.get(i, {}).get("validClaimPreserved") is not None]
            m, lo, hi = boot_mean([rows[i]["validClaimPreserved"] - c4[i]["validClaimPreserved"] for i in ids], rng)
            return {"n": len(ids), "diff": m, "lo": lo, "hi": hi,
                    "policy": sum(rows[i]["validClaimPreserved"] for i in ids) / len(ids) if ids else None,
                    "c4": sum(c4[i]["validClaimPreserved"] for i in ids) / len(ids) if ids else None}
        ctl = sorted(i for i in nov if i in c4)
        p3 = {name: {"all": ret(r, ctl), "noteOnlyValid": ret(r, [i for i in ctl if nov[i]])} for name, r in pol_rows.items()}
        # P4
        decision_fams = {gold[i]["family"] for i in gold if (gold[i].get("trap") or {}).get("rule") == DECISION_RULE}
        def s_rows(frac, seed):
            out = []
            for case, g, b in base:
                bb = RF.apply(b, RF.s_pick(b, case["caseId"], "relabel", frac, seed), "relabel") if isinstance(b, dict) else b
                out.append(scoring.score_bundle(case, g, bb, None, lex))
            return out
        pts, nd_pts = [], []
        for frac in RF.FRACTIONS:
            seeds = RF.SEEDS if 0 < frac < 1 else [RF.SEEDS[0]]
            got = [s_rows(frac, s) for s in seeds]
            pts.append(RF.curve_point(frac, [RF.point(r) for r in got]))
            nd_pts.append(RF.curve_point(frac, [RF.point([x for x in r if x["family"] not in decision_fams]) for r in got]))
        c4_list = list(c4.values())
        c4_nd = [x for x in c4_list if x["family"] not in decision_fams]
        c4pt, c4nd = RF.point(c4_list), RF.point(c4_nd)
        p4 = {"c4": c4pt, "sAtC4Attrition": RF.interp(pts, c4pt["supportedCount"], "supportedCount", "trap"),
              "nonDecision": {"c4": c4nd, "sAtC4Attrition": RF.interp(nd_pts, c4nd["supportedCount"], "supportedCount", "trap")},
              "curve": pts}
        # descriptive: C2 -> C4 paired contrast on risk cases
        ids = [i for i in risk_ids if c2.get(i, {}).get("trapFellAny") is not None and c4[i].get("trapFellAny") is not None]
        e = sum(1 for i in ids if c2[i]["trapFellAny"] and c4[i]["trapFellAny"])
        f = sum(1 for i in ids if c2[i]["trapFellAny"] and not c4[i]["trapFellAny"])
        g = sum(1 for i in ids if (not c2[i]["trapFellAny"]) and c4[i]["trapFellAny"])
        lo, hi = TC.newcombe_paired(e, g, f, len(ids) - e - f - g)  # interval for C4 rate - C2 rate
        report["models"][model] = {"P1": {"primaryPolicy": best, "byPolicy": p1}, "P2": p2, "P3": p3, "P4": p4,
                                   "c2toc4": {"n": len(ids), "c2Fail": e + f, "c4Fail": e + g, "cleared": f, "new": g,
                                              "diff": (g - f) / len(ids) if ids else None, "lo": lo, "hi": hi}}
    for m in report["models"].values():
        for x in m["P2"]["byLocation"].values():
            x.pop("ids", None)
        for k in ("note", "nonNote"):
            m["P2"][k].pop("ids", None)
    json.dump(report, open(args.out + ".json", "w", encoding="utf-8"), indent=1, default=str)
    lines = [f"# v5 pre-registered analysis ({args.bench}, runs: {', '.join(f'{k}={v}' for k, v in runs.items()) or 'none found'})", ""]
    for model, m in report["models"].items():
        p = m["P1"]["byPolicy"][m["P1"]["primaryPolicy"]]
        lines += [f"## {model}",
                  f"- P1 primary policy {m['P1']['primaryPolicy']}: policy {p['all']['policyRate']} vs C4 {p['all']['c4Rate']} "
                  f"(n {p['all']['n']}); diff {p['all'].get('diff')} [{p['all'].get('lo')}, {p['all'].get('hi')}]; non-note diff {p['nonNote'].get('diff')}",
                  f"- P2 clearance note {m['P2']['note']['rate']} ({m['P2']['note']['cleared']}/{m['P2']['note']['c2Fail']}), "
                  f"non-note {m['P2']['nonNote']['rate']} ({m['P2']['nonNote']['cleared']}/{m['P2']['nonNote']['c2Fail']}); "
                  f"diff {m['P2']['noteMinusNonNote']}",
                  f"- P3 retention (policy - C4): " + "; ".join(f"{n} {x['all']['diff']}" for n, x in m["P3"].items()),
                  f"- P4 C4 trap {m['P4']['c4']['trap']} vs S at C4 attrition {m['P4']['sAtC4Attrition']}", ""]
    open(args.out + ".md", "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
