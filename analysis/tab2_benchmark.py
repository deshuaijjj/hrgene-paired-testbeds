#!/usr/bin/env python3
"""Table 2 — benchmark composition, generated from the frozen benchmark/v4/{cases,gold} files.

No manifest file exists; the composition is derived directly from the frozen artifacts so the table
is reproducible rather than hand-copied. Writes tab2_benchmark.md / .json."""
import collections
import glob
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BM = os.path.join(HERE, "..", "benchmark", "v4")


def load():
    cases, gold = {}, {}
    for p in sorted(glob.glob(os.path.join(BM, "cases", "*.json"))):
        c = json.load(open(p, encoding="utf-8"))
        cases[c["caseId"]] = c
    for p in sorted(glob.glob(os.path.join(BM, "gold", "*.json"))):
        g = json.load(open(p, encoding="utf-8"))
        gold[g["caseId"]] = g
    if set(cases) != set(gold):
        raise SystemExit("cases and gold cover different caseIds")
    return cases, gold


def digest(pattern):
    """Stable digest over a frozen directory, so the table can be tied to a benchmark version."""
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(BM, pattern))):
        h.update(os.path.basename(p).encode())
        h.update(open(p, "rb").read())
    return h.hexdigest()


def main():
    cases, gold = load()
    ids = sorted(cases)
    fam = collections.Counter(gold[i]["family"] for i in ids)
    ctrl = collections.Counter(gold[i]["controlStatus"] for i in ids)
    by = collections.Counter((gold[i]["family"], gold[i]["controlStatus"]) for i in ids)
    rules = collections.Counter(gold[i]["trap"]["rule"] for i in ids if gold[i].get("trap"))
    anywhere = sum(1 for i in ids if (gold[i].get("trap") or {}).get("anywhereSignatures"))
    per_case = {
        "requirements": collections.Counter(len(gold[i]["requirementStatus"]) for i in ids),
        "propositions": collections.Counter(len(gold[i]["propositions"]) for i in ids),
        "evidence": collections.Counter(len(cases[i]["candidate"]["evidence"]) for i in ids),
    }
    report = {
        "n": len(ids), "families": dict(sorted(fam.items())), "controlStatus": dict(sorted(ctrl.items())),
        "familyByControl": {f"{f}|{c}": n for (f, c), n in sorted(by.items())},
        "trapRule": dict(sorted(rules.items())), "casesWithAnywhereSignatures": anywhere,
        "perCase": {k: dict(sorted(v.items())) for k, v in per_case.items()},
        "casesDigest": digest("cases/*.json")[:16], "goldDigest": digest("gold/*.json")[:16],
    }
    json.dump(report, open(os.path.join(HERE, "tab2_benchmark.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    md = [f"| Stress family | Risk | Matched control | Total | Anchoring rule |", "|---|---|---|---|---|"]
    for f in sorted(fam):
        rule = ", ".join(sorted({gold[i]["trap"]["rule"].split(".")[-1] for i in ids
                                 if gold[i]["family"] == f and gold[i].get("trap")}))
        md.append(f"| {f} | {by[(f, 'positive_risk')]} | {by[(f, 'matched_clean_control')]} | {fam[f]} | {rule} |")
    md.append(f"| **All** | **{ctrl['positive_risk']}** | **{ctrl['matched_clean_control']}** | **{len(ids)}** | |")
    fixed = lambda k: (list(per_case[k])[0] if len(per_case[k]) == 1 else dict(per_case[k]))
    md += ["", f"Per case: {fixed('requirements')} requirements, {fixed('propositions')} gold propositions, "
               f"{fixed('evidence')} evidence sources. {anywhere} cases carry `anywhereSignatures` "
               f"(protected-attribute phrases counted anywhere in the output).",
           f"Frozen: cases digest `{report['casesDigest']}`, gold digest `{report['goldDigest']}`."]
    open(os.path.join(HERE, "tab2_benchmark.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
