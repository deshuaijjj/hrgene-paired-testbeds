#!/usr/bin/env python3
"""Score generated bundles against benchmark/v4 gold (PAPER_SPEC §5 metrics).

  python3 score.py --run ../../experiments/<run>            # C0/C1/C2/C5 generation run (outputs/*.r0.json)
  python3 score.py --run ../../experiments/<run>-C4 --c4    # C4 post-processed run (final/*.json)
  python3 score.py --mutations                              # detector precision/recall on oracle mutants
Writes <run>/score.json (aggregate by condition and by family) and <run>/score_rows.jsonl (one row per bundle)."""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
from hrgene.validator import Validator  # noqa: E402
from hrgene import scoring, pipeline  # noqa: E402


def load_dir(d):
    out = {}
    for f in glob.glob(os.path.join(d, "*.json")):
        o = json.load(open(f, encoding="utf-8"))
        out[o["caseId"]] = o
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run")
    ap.add_argument("--c4", action="store_true")
    ap.add_argument("--mutations", action="store_true")
    ap.add_argument("--cases", default=os.path.join(HERE, "cases"))
    ap.add_argument("--gold", default=os.path.join(HERE, "gold"))
    args = ap.parse_args()
    v = Validator()
    cases, gold = load_dir(args.cases), load_dir(args.gold)
    if args.mutations:
        from hrgene.mutations import precision_recall
        pr = precision_recall(v, [(cases[c], gold[c]) for c in sorted(cases) if c in gold])
        out = os.path.join(HERE, "detector_pr.json")
        json.dump({"rulesetDigest": v.rs.digest, **pr}, open(out, "w"), indent=1)
        for r, s in pr["perRule"].items():
            print(f"{r.split('.')[-1]:36s} tp={s['tp']:3d} fn={s['fn']:3d} fp={s['fp']:3d} P={s['precision']} R={s['recall']}")
        print(f"clean oracles flagged: {pr['cleanOraclesFlagged']} / {pr['cleanOracles']}; written {out}")
        return
    rows = []
    if args.c4:
        files = sorted(glob.glob(os.path.join(args.run, "final", "*.json")))
        for f in files:
            rec = json.load(open(f, encoding="utf-8"))
            case = cases[rec["case_id"]]
            bundle = rec.get("bundle")
            val = rec.get("validation") or v.validate(case, bundle)
            row = scoring.score_bundle(case, gold[case["caseId"]], bundle, val, v.rs.lex)
            row.update(condition="C4", requestId=rec["request_id"], regenerated=rec.get("regenerated"), notRepairable=rec.get("notRepairable"), repairNonEscalating=rec.get("repairNonEscalating"))
            rows.append(row)
    else:
        files = sorted(glob.glob(os.path.join(args.run, "outputs", "*.r0.json")))
        for f in files:
            rec = json.load(open(f, encoding="utf-8"))
            case = cases.get(rec.get("case_id") or rec["request_id"].split(".")[0])
            if case is None:
                continue
            bundle = pipeline.parse_output(rec.get("content", ""))
            val = v.validate(case, bundle, raw_text=rec.get("content"))
            row = scoring.score_bundle(case, gold[case["caseId"]], bundle, val, v.rs.lex)
            row.update(condition=rec.get("condition"), requestId=rec["request_id"], outTokens=rec.get("eval_count"))
            rows.append(row)
    if not rows:
        sys.exit("no outputs found")
    with open(os.path.join(args.run, "score_rows.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    conds = sorted({r["condition"] for r in rows})
    summary = {"rulesetDigest": v.rs.digest, "run": os.path.abspath(args.run), "n": len(rows), "byCondition": {}, "byConditionFamily": {}, "byConditionControl": {}}
    for c in conds:
        sub = [r for r in rows if r["condition"] == c]
        summary["byCondition"][c] = scoring.aggregate(sub)
        for fam in sorted({r["family"] for r in sub}):
            summary["byConditionFamily"][f"{c}|{fam}"] = scoring.aggregate([r for r in sub if r["family"] == fam])
        for cs in ("positive_risk", "matched_clean_control"):
            summary["byConditionControl"][f"{c}|{cs}"] = scoring.aggregate([r for r in sub if r["controlStatus"] == cs])
    json.dump(summary, open(os.path.join(args.run, "score.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for c in conds:
        a = summary["byCondition"][c]
        print(f"{c}: n={a['n']} parsed={a['parsed']['mean']:.2f} schemaValid={a['schemaValid']['mean']:.2f} residualCritical={a['residualCriticalViolationRate']['mean']:.2f} "
              f"trapFellAny={a['trapFellAny']['mean']} strict={a['trapFellStrict']['mean']} trapRouted={a['trapRouted']['mean']} validPreserved={a['validClaimPreserved']['mean']} catch={a['catchRateOnFallenTraps']['mean']}")


if __name__ == "__main__":
    main()
