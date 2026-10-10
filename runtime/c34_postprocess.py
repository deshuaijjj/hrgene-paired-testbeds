#!/usr/bin/env python3
"""Derive C3 and C4 from a C2 (or any) generation run.

  python3 c34_postprocess.py validate --run ../experiments/<run> --cases ../benchmark/v4/cases --out ../experiments/<run>-C3
      -> <out>/validations/<request_id>.json (C3: validation report per output; no repair)
  python3 c34_postprocess.py repair --run ../experiments/<run> --cases ../benchmark/v4/cases --out ../experiments/<run>-C4
      -> <out>/stage1/<request_id>.json (repaired bundle + logs) and <out>/regen_requests.jsonl for outputs still BLOCK
  (run the regen requests with ollama_runner.py / api_runner.py into <out>/regen, then)
  python3 c34_postprocess.py finalize --run ../experiments/<run> --cases ../benchmark/v4/cases --out ../experiments/<run>-C4
      -> <out>/final/<request_id>.json (final bundle, aggregate, stages) + <out>/summary.json"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hrgene.validator import Validator  # noqa: E402
from hrgene.rules import RuleSet  # noqa: E402
from hrgene import pipeline, prompts  # noqa: E402


def load_outputs(run_dir):
    """{request_id: (raw_text, record)} from a runner output directory (first repeat only)."""
    out = {}
    for f in sorted(glob.glob(os.path.join(run_dir, "outputs", "*.r0.json"))) or sorted(glob.glob(os.path.join(run_dir, "outputs", "*.json"))):
        rec = json.load(open(f, encoding="utf-8"))
        rid = rec.get("request_id") or os.path.basename(f).split(".r")[0]
        raw = rec.get("content") if isinstance(rec.get("content"), str) else json.dumps(rec.get("parsed")) if rec.get("parsed") is not None else ""
        out[rid] = (raw, rec)
    return out


def load_cases(cases_dir):
    cases = {}
    for f in glob.glob(os.path.join(cases_dir, "*.json")):
        c = json.load(open(f, encoding="utf-8"))
        cases[c["caseId"]] = c
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["validate", "repair", "finalize"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    v = Validator()
    rs = RuleSet()
    cases = load_cases(args.cases)
    outputs = load_outputs(args.run)
    os.makedirs(args.out, exist_ok=True)
    if args.mode == "validate":
        d = os.path.join(args.out, "validations")
        os.makedirs(d, exist_ok=True)
        agg = {}
        for rid, (raw, rec) in outputs.items():
            case = cases[rec.get("case_id") or rid.split(".")[0]]
            res = pipeline.stage_c3(v, case, raw)
            json.dump({"request_id": rid, "case_id": case["caseId"], **res}, open(os.path.join(d, f"{rid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            agg[res["aggregate"]] = agg.get(res["aggregate"], 0) + 1
        json.dump({"mode": "C3", "sourceRun": args.run, "aggregate": agg, "rulesetDigest": v.rs.digest}, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
        print("C3 aggregate:", agg)
    elif args.mode == "repair":
        d = os.path.join(args.out, "stage1")
        os.makedirs(d, exist_ok=True)
        n_regen = 0
        with open(os.path.join(args.out, "regen_requests.jsonl"), "w", encoding="utf-8") as rq:
            for rid, (raw, rec) in outputs.items():
                case = cases[rec.get("case_id") or rid.split(".")[0]]
                first = pipeline.stage_c4_repair(v, case, raw)
                json.dump({"request_id": rid, "case_id": case["caseId"], **first}, open(os.path.join(d, f"{rid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                if first["needsRegeneration"]:
                    findings = (first["after"] or first["before"])["findings"]
                    msgs = prompts.build_regeneration_messages(case, "C4", rs, raw, findings)
                    rq.write(json.dumps({"request_id": rid, "case_id": case["caseId"], "condition": "C4regen", "messages": msgs, "format": "json",
                                         "meta": {"regenerationOf": rid, "rulesetDigest": rs.digest}}, ensure_ascii=False) + "\n")
                    n_regen += 1
        print(f"C4 stage 1 done for {len(outputs)} outputs; {n_regen} regeneration requests written to {args.out}/regen_requests.jsonl")
    else:
        d = os.path.join(args.out, "final")
        os.makedirs(d, exist_ok=True)
        regen = load_outputs(os.path.join(args.out, "regen")) if os.path.isdir(os.path.join(args.out, "regen")) else {}
        agg, esc = {}, {"nonEscalating": 0, "escalating": 0, "regenerated": 0, "notRepairable": 0}
        for f in sorted(glob.glob(os.path.join(args.out, "stage1", "*.json"))):
            first = json.load(open(f, encoding="utf-8"))
            rid = first["request_id"]
            case = cases[first["case_id"]]
            regen_raw = regen[rid][0] if rid in regen else None
            final = pipeline.stage_c4_finalize(v, case, first, regen_raw)
            ne = pipeline.repair_escalation(first["before"], final["validation"])
            if ne is not None:
                esc["nonEscalating" if ne else "escalating"] += 1
            esc["regenerated"] += final["regenerated"]
            esc["notRepairable"] += final["notRepairable"]
            agg[final["aggregate"]] = agg.get(final["aggregate"], 0) + 1
            json.dump({"request_id": rid, "case_id": case["caseId"], **final, "repairNonEscalating": ne}, open(os.path.join(d, f"{rid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump({"mode": "C4", "sourceRun": args.run, "aggregate": agg, "repair": esc, "rulesetDigest": v.rs.digest}, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
        print("C4 final aggregate:", agg, esc)


if __name__ == "__main__":
    main()
