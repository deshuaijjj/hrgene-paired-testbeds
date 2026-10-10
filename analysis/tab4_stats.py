#!/usr/bin/env python3
"""Table 4 statistics — uncertainty and paired tests from each formal run's score_rows.jsonl.

Run after collect.py (reads analysis/results.json to find the formal run of every model x condition).
(a) Wilson 95% CIs for every Table 4 proportion, on its own non-null denominator (scored risk or
    scored control; Parsed / Schema valid / Validator flagged / Residual critical on all cases).
    Control claims kept is a mean of per-case fractions, so it gets a case-bootstrap CI instead.
(b) Exact McNemar tests on risk cases, trapFellAny, C0->C4 and C2->C4 per model: repaired
    (failed before, not after), new (not before, failed after), unchanged.
(c) Case-resampling bootstrap 95% CI of the C4 - C2 difference in control claims kept on the
    commonly scorable matched controls (fixed seed).
Family-level results stay descriptive and are not tested here. Writes tab4_stats.md / .json.
"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ORDER = ("C0", "C1", "C2", "C5", "C3", "C4")
SEED = 20260919
B = 10000
Z = 1.959963984540054
RISK, CONTROL = "positive_risk", "matched_clean_control"


def wilson(k, n):
    if not n:
        return None, None
    p = k / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load_rows(run):
    path = ROOT / "experiments" / run / "score_rows.jsonl"
    return {r["caseId"]: r for r in (json.loads(s) for s in path.read_text().splitlines() if s.strip())}


def binary(rows, metric, status=None):
    vals = [r.get(metric) for r in rows.values() if status is None or r["controlStatus"] == status]
    vals = [v for v in vals if v is not None]
    return sum(bool(v) for v in vals), len(vals)


def bootstrap_mean_ci(values, rng):
    if not values:
        return None, None
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return means[int(0.025 * B)], means[int(0.975 * B) - 1]


def proportions(rows, rng):
    n_all = len(rows)
    spec = [("parsed", None, "Parsed"), ("trapFellAny", RISK, "Gold trap failure"),
            ("trapRequirementOverclaimed", RISK, "Req. over-claimed"), ("trapRouted", RISK, "Trap routed"),
            ("validClaimSuppressed", CONTROL, "Controls suppressed"), ("schemaValid", None, "Schema valid"),
            ("validatorFlagged", None, "Validator flagged")]
    out = {}
    for metric, status, label in spec:
        k, n = binary(rows, metric, status)
        lo, hi = wilson(k, n)
        out[metric] = {"label": label, "k": k, "n": n, "p": k / n if n else None, "lo": lo, "hi": hi,
                       "denominator": {RISK: "scored risk", CONTROL: "scored control", None: "all cases"}[status]}
    k = sum(1 for r in rows.values() if r.get("parsed") and (r.get("criticalFails") or 0) > 0)
    lo, hi = wilson(k, n_all)
    out["residualCriticalViolationRate"] = {"label": "Residual critical viol.", "k": k, "n": n_all, "p": k / n_all,
                                            "lo": lo, "hi": hi, "denominator": "all cases (frozen definition)"}
    kept = [r["validClaimPreserved"] for r in rows.values() if r["controlStatus"] == CONTROL and r.get("validClaimPreserved") is not None]
    lo, hi = bootstrap_mean_ci(kept, rng)
    out["validClaimPreserved_matched_clean_control"] = {"label": "Control claims kept", "k": None, "n": len(kept),
                                                        "p": sum(kept) / len(kept) if kept else None, "lo": lo, "hi": hi,
                                                        "denominator": "scored control; mean of per-case fractions; case bootstrap"}
    return out


def paired(before, after):
    ids = sorted(i for i in before if before[i]["controlStatus"] == RISK and i in after
                 and before[i].get("trapFellAny") is not None and after[i].get("trapFellAny") is not None)
    b = sum(before[i]["trapFellAny"] and not after[i]["trapFellAny"] for i in ids)
    c = sum((not before[i]["trapFellAny"]) and after[i]["trapFellAny"] for i in ids)
    both = sum(before[i]["trapFellAny"] and after[i]["trapFellAny"] for i in ids)
    return {"pairedN": len(ids), "repaired": b, "new": c, "unchangedFail": both, "unchangedPass": len(ids) - b - c - both,
            "exactP": mcnemar_exact(b, c)}


def retention_diff(c2, c4, rng):
    ids = sorted(i for i in c2 if c2[i]["controlStatus"] == CONTROL and i in c4
                 and c2[i].get("validClaimPreserved") is not None and c4[i].get("validClaimPreserved") is not None)
    diffs = [c4[i]["validClaimPreserved"] - c2[i]["validClaimPreserved"] for i in ids]
    lo, hi = bootstrap_mean_ci(diffs, rng)
    return {"pairedN": len(ids), "c2": sum(c2[i]["validClaimPreserved"] for i in ids) / len(ids),
            "c4": sum(c4[i]["validClaimPreserved"] for i in ids) / len(ids),
            "diff": sum(diffs) / len(diffs), "lo": lo, "hi": hi, "bootstrap": {"B": B, "seed": SEED, "unit": "case"}}


def pct(v):
    return "–" if v is None else f"{100 * v:.1f}"


def main():
    results = json.loads((HERE / "results.json").read_text())
    models = sorted({r["model"] for r in results})
    report = {"seed": SEED, "bootstrapB": B, "models": {}}
    for model in models:
        runs = {r["condition"]: r for r in results if r["model"] == model}
        # C3 reuses the unchanged C2 outputs; collect.py already verified its reports equal C2's flags.
        rows = {c: load_rows(runs[c]["derivedFrom"] if c == "C3" else runs[c]["run"]) for c in ORDER if c in runs}
        entry = {"runs": {c: runs[c]["run"] for c in rows}, "proportions": {}}
        for cond in ORDER:
            if cond not in rows:
                continue
            props = proportions(rows[cond], random.Random(f"{SEED}|{model}|{cond}|kept"))
            ref = runs[cond]
            for metric, v in props.items():
                key = metric + "_matched_clean_control" if metric == "validClaimSuppressed" else metric
                if ref.get(key) is not None and v["p"] is not None and abs(ref[key] - v["p"]) > 1e-9:
                    raise SystemExit(f"{model} {cond} {metric}: score_rows {v['p']} != results.json {ref[key]}")
            entry["proportions"][cond] = props
        entry["mcnemar"] = {f"{a}->C4": paired(rows[a], rows["C4"]) for a in ("C0", "C2")}
        # C1 -> C2 compares the prose-rules prompt with the contract prompt (they differ in wording, fields, a validator-notice header and length) with no
        # executable validation on either arm; reported because a null here is what localises the gain to C4.
        if "C1" in rows and "C2" in rows:
            entry["mcnemar"]["C1->C2"] = paired(rows["C1"], rows["C2"])
        entry["controlRetentionC2toC4"] = retention_diff(rows["C2"], rows["C4"], random.Random(f"{SEED}|{model}|retention"))
        report["models"][model] = entry
    (HERE / "tab4_stats.json").write_text(json.dumps(report, indent=2) + "\n")

    md = ["# Table 4 statistics (generated by tab4_stats.py)", "",
          "Wilson 95% CIs on each metric's own non-null denominator (Table 4 'Scored risk/control'; Parsed, Schema valid, Validator flagged and Residual critical use all 144 cases). "
          f"Control claims kept is a mean of per-case fractions: case-bootstrap percentile CI (B={B}, seed {SEED}). Values in %.", ""]
    for model, entry in report["models"].items():
        metrics = list(next(iter(entry["proportions"].values())))
        md += [f"## {model}", "", "| Condition | " + " | ".join(entry["proportions"]["C0"][m]["label"] for m in metrics) + " |",
               "|---|" + "---|" * len(metrics)]
        for cond, props in entry["proportions"].items():
            cells = []
            for m in metrics:
                v = props[m]
                count = f" ({v['k']}/{v['n']})" if v["k"] is not None else f" (n={v['n']})"
                cells.append(f"{pct(v['p'])} [{pct(v['lo'])}, {pct(v['hi'])}]{count}")
            md.append(f"| {cond} | " + " | ".join(cells) + " |")
        md += ["", "Paired exact McNemar, risk cases, trapFellAny (repaired = failed before and not after; new = the reverse). "
               "C1->C2 carries no executable validation on either arm; the two prompts differ in wording, fields, a validator-notice header and length, so the contrast does not isolate representation.", "",
               "| Contrast | Paired n | Repaired | New | Unchanged fail | Unchanged pass | Exact p (two-sided) |", "|---|---|---|---|---|---|---|"]
        for name, t in entry["mcnemar"].items():
            p = t["exactP"]
            md.append(f"| {name} | {t['pairedN']} | {t['repaired']} | {t['new']} | {t['unchangedFail']} | {t['unchangedPass']} | {p:.2e} |" if p < 1e-3
                      else f"| {name} | {t['pairedN']} | {t['repaired']} | {t['new']} | {t['unchangedFail']} | {t['unchangedPass']} | {p:.3f} |")
        r = entry["controlRetentionC2toC4"]
        md += ["", f"Common scorable controls, C2 → C4 claims kept: {pct(r['c2'])}% → {pct(r['c4'])}%, difference {100 * r['diff']:+.2f} pp, "
               f"95% bootstrap CI [{100 * r['lo']:+.2f}, {100 * r['hi']:+.2f}] pp (paired n={r['pairedN']}, resampling cases).", ""]
    md += ["Family-level counts (tab4_families) remain descriptive; no tests are run per family (12 risk / 12 control cases each)."]
    (HERE / "tab4_stats.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
