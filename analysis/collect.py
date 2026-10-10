#!/usr/bin/env python3
"""Collect every experiments/<run>/score.json into analysis/results.json + results.csv.

A run is identified by its directory name (YYYYMMDD-<model>-<condition>-<n>) and its config.json (model, digest).
Usage: python3 collect.py [--experiments ../experiments] [--out results] [--pattern '*-full']"""
import argparse
import csv
import glob
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "runtime"))
from hrgene.scoring import aggregate  # noqa: E402
METRICS = ["parsed", "schemaValid", "residualCriticalViolationRate", "trapFellAny", "trapFellStrict", "trapRequirementOverclaimed", "trapRouted",
           "validClaimPreserved", "validClaimSuppressed", "requirementStatusExact", "requirementNoOverclaim", "subjectiveRouted", "boundaryViolation",
           "validatorFlagged", "catchRateOnFallenTraps", "supportedCount"]


def model_of(run_dir):
    cfg = os.path.join(run_dir, "config.json")
    if os.path.exists(cfg):
        c = json.load(open(cfg, encoding="utf-8"))
        ident = c.get("identity") or {}
        return c.get("model") or ident.get("model"), (ident.get("digest") or c.get("system_fingerprint") or "")
    summ = os.path.join(run_dir, "summary.json")
    if os.path.exists(summ):
        s = json.load(open(summ, encoding="utf-8"))
        src = s.get("sourceRun")
        if src:
            # Run metadata was written on Mac Studio; resolve the copied sibling.
            local_src = os.path.join(os.path.dirname(run_dir), os.path.basename(src))
            if os.path.isdir(local_src):
                return model_of(local_src)
    name = os.path.basename(run_dir.rstrip("/"))
    parts = name.split("-")
    return ("-".join(parts[1:-2]) if len(parts) > 3 else name), ""


def c3_summary(run_dir):
    """C3 exposes validation reports but reuses the unchanged C2 output scores."""
    meta = json.loads((run_dir / "summary.json").read_text())
    source = run_dir.parent / Path(meta["sourceRun"]).name
    source_summary = json.loads((source / "score.json").read_text())
    source_rows = [json.loads(line) for line in (source / "score_rows.jsonl").read_text().splitlines() if line.strip()]
    reports = [json.loads(p.read_text()) for p in sorted((run_dir / "validations").glob("*.json"))]
    by_request = {r["request_id"]: r for r in reports}
    if len(by_request) != len(reports) or set(by_request) != {r["requestId"] for r in source_rows}:
        raise ValueError(f"{run_dir.name}: C3 report coverage differs from C2 scores")
    if len(source_rows) != source_summary["n"] or meta["rulesetDigest"] != source_summary["rulesetDigest"]:
        raise ValueError(f"{run_dir.name}: inconsistent source score metadata")
    rows = []
    for original in source_rows:
        report = by_request[original["requestId"]]
        flagged = report["validation"]["aggregate"] in ("BLOCK", "HUMAN_REVIEW")
        if report["case_id"] != original["caseId"] or flagged != original["validatorFlagged"]:
            raise ValueError(f"{run_dir.name}: C2/C3 validation differs for {original['caseId']}")
        rows.append({**original, "condition": "C3", "validatorFlagged": flagged})
    return {"n": len(rows), "rulesetDigest": meta["rulesetDigest"], "derivedFrom": source.name,
            "byCondition": {"C3": aggregate(rows)},
            "byConditionControl": {f"C3|{cs}": aggregate([r for r in rows if r["controlStatus"] == cs])
                                   for cs in ("positive_risk", "matched_clean_control")}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiments", default=os.path.join(HERE, "..", "experiments"))
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--pattern", default="*-full", help="run directory glob (default '*-full': the formal benchmark runs; pilots/smokes excluded)")
    args = ap.parse_args()
    rows = []
    for run_dir in sorted(glob.glob(os.path.join(args.experiments, args.pattern))):
        path = Path(run_dir)
        if not path.is_dir() or path.name.split("-")[-2] not in {f"C{i}" for i in range(6)}:
            continue  # C3b/C4b are version checks, not additional conditions.
        if path.name.split("-")[-2] == "C3":
            s = c3_summary(path)
        elif (path / "score.json").exists():
            s = json.loads((path / "score.json").read_text())
            score_rows = [json.loads(line) for line in (path / "score_rows.jsonl").read_text().splitlines() if line.strip()]
            if len(score_rows) != s["n"]:
                raise ValueError(f"{path.name}: score row count differs from summary")
            cfg = path / "config.json"
            expected = json.loads(cfg.read_text()).get("n_requests") if cfg.exists() else None
            if expected is not None and s["n"] != expected:
                raise ValueError(f"{path.name}: incomplete score ({s['n']}/{expected})")
        else:
            continue
        model, digest = model_of(run_dir)
        for cond, agg in s["byCondition"].items():
            row = {"run": os.path.basename(run_dir), "model": model, "digest": (digest or "")[:12], "condition": cond, "n": agg["n"], "rulesetDigest": s.get("rulesetDigest", "")[:19], "derivedFrom": s.get("derivedFrom", "")}
            for m in METRICS:
                v = agg.get(m)
                row[m] = v["mean"] if isinstance(v, dict) else v
                row[f"{m}_n"] = v.get("n") if isinstance(v, dict) else None
            for key, agg2 in s.get("byConditionControl", {}).items():
                c2, cs = key.split("|")
                if c2 == cond:
                    row[f"n_{cs}"] = agg2["n"]
                    for metric in ("trapFellAny", "validClaimPreserved", "validClaimSuppressed"):
                        value = agg2.get(metric) or {}
                        row[f"{metric}_{cs}"] = value.get("mean")
                        row[f"{metric}_{cs}_n"] = value.get("n")
            rows.append(row)
    json.dump(rows, open(args.out + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in ("run", "model", "condition", "n"), k))
    with open(args.out + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} run×condition rows -> {args.out}.json / .csv")
    for r in rows:
        print(f"  {r['run']:40s} {str(r['model']):18s} {r['condition']:3s} n={r['n']:3d} trapFellAny={r['trapFellAny']} residual={r['residualCriticalViolationRate']} preserved={r['validClaimPreserved']}")


if __name__ == "__main__":
    main()
