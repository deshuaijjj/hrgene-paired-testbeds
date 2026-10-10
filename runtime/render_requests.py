#!/usr/bin/env python3
"""Render generation requests for benchmark/v4 cases.

Usage:
  python3 render_requests.py --cases ../benchmark/v4/cases --out ../benchmark/v4/requests [--conditions C0,C1,C2,C5] [--limit N] [--ids id1,id2]
Writes <out>/<condition>.jsonl (one request per case) plus <out>/manifest.json with prompt-length statistics
(word / character counts per condition, for the prompt-length sensitivity analysis)."""
import argparse
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hrgene.rules import RuleSet  # noqa: E402
from hrgene import prompts  # noqa: E402

SCHEMA = os.path.normpath(os.path.join(HERE, "..", "schema", "paired-review-bundle.v2.schema.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--conditions", default="C0,C1,C2,C5")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    args = ap.parse_args()
    rs = RuleSet()
    schema = json.load(open(SCHEMA, encoding="utf-8"))
    files = sorted(glob.glob(os.path.join(args.cases, "*.json")))
    if args.ids:
        want = set(args.ids.split(","))
        files = [f for f in files if os.path.basename(f)[:-5] in want or any(os.path.basename(f).startswith(w) for w in want)]
    if args.limit:
        files = files[: args.limit]
    os.makedirs(args.out, exist_ok=True)
    manifest = {"rulesetDigest": rs.digest, "schema": os.path.basename(SCHEMA), "conditions": {}, "cases": [os.path.basename(f)[:-5] for f in files]}
    for cond in args.conditions.split(","):
        cond = cond.strip()
        if cond not in prompts.GENERATION_CONDITIONS:
            sys.exit(f"{cond} is not a generation condition (C3/C4 are derived from C2 by c34_postprocess.py)")
        words, chars, n = [], [], 0
        with open(os.path.join(args.out, f"{cond}.jsonl"), "w", encoding="utf-8") as out:
            for f in files:
                case = json.load(open(f, encoding="utf-8"))
                rec = prompts.build_request(case, cond, rs, schema=schema)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                words.append(rec["meta"]["promptWords"])
                chars.append(rec["meta"]["promptChars"])
                n += 1
        manifest["conditions"][cond] = {"requests": n, "promptWords": {"median": statistics.median(words), "min": min(words), "max": max(words)},
                                        "promptChars": {"median": statistics.median(chars), "min": min(chars), "max": max(chars)}}
        print(f"{cond}: {n} requests; prompt words median {statistics.median(words):.0f} (min {min(words)}, max {max(words)})")
    json.dump(manifest, open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
