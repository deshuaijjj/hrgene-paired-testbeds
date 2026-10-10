#!/usr/bin/env python3
"""Table 4 — condition comparison per model, from analysis/results.json (run collect.py first).
Writes tab4_conditions.md and tab4_conditions.tex."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = [("parsed", "Parsed"), ("trapFellAny", "Gold trap failure"), ("trapRequirementOverclaimed", "Req. over-claimed"), ("trapRouted", "Trap routed"),
        ("residualCriticalViolationRate", "Residual critical viol."), ("validClaimPreserved_matched_clean_control", "Control claims kept"),
        ("validClaimSuppressed_matched_clean_control", "Controls suppressed"), ("schemaValid", "Schema valid"),
        ("validatorFlagged", "Validator flagged"), ("requirementNoOverclaim", "Req. status ≤ gold")]
ORDER = ["C0", "C1", "C2", "C5", "C3", "C4"]


def fmt(v):
    return "–" if v is None else f"{100 * v:.1f}%"


def main():
    rows = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
    models = sorted({r["model"] for r in rows}, key=str)
    md = ["| Model | Condition | n | Scored risk/control | " + " | ".join(c[1] for c in COLS) + " |", "|" + "---|" * (4 + len(COLS))]
    tex = ["\\begin{tabular}{ll r c " + "r" * len(COLS) + "}", "\\toprule", "Model & Condition & $n$ & Scored risk/control & " + " & ".join(c[1] for c in COLS) + " \\\\", "\\midrule"]
    for m in models:
        for cond in ORDER:
            rs = [r for r in rows if r["model"] == m and r["condition"] == cond]
            if not rs:
                continue
            r = rs[-1]  # latest run wins
            vals = [fmt(r.get(c[0])) for c in COLS]
            counts = f"{r['trapFellAny_positive_risk_n']}/{r['validClaimPreserved_matched_clean_control_n']}"
            md.append(f"| {m} | {cond} | {r['n']} | {counts} | " + " | ".join(vals) + " |")
            tex.append(f"{m} & {cond} & {r['n']} & {counts} & " + " & ".join(v.replace('%', '\\%') for v in vals) + " \\\\")
    tex += ["\\bottomrule", "\\end{tabular}"]
    notes = ["Each run contains 72 risk cases and 72 matched controls. Scored risk/control gives the non-null denominators for trap failure and control preservation; unparsed outputs are excluded from semantic metrics and reported separately under Parsed.",
             "Gold trap failure is trapFellAny: explicit trap matches, requirement-status overclaim, or family-specific gold failures. It is broader than an explicit supported assertion. Trap routed is a separate metric and is not its complement.",
             "Control claims kept is the mean fraction of valid signatures retained on the supported side per parsed matched control. Controls suppressed is the fraction with at least one missing valid signature explicitly moved to unsupportedClaims; omission alone does not count, so the two columns are not complements.",
             "C3 reuses the C2 outputs and scores; its stored validation reports are checked against C2. Validator flagged is BLOCK or HUMAN_REVIEW (all cases); for generation-only conditions this is offline scoring, not an intervention delivered to the model. C4 uses the original C4-full run, excluding C4b.",
             "Residual critical violation follows the frozen scorer: parsed bundles with one or more critical findings divided by all 144 cases. Parse failures are therefore not counted as residual critical violations. No metric is evidence of complete semantic correctness."]
    md += ["", *notes]
    tex += ["% " + note for note in notes]
    open(os.path.join(HERE, "tab4_conditions.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    open(os.path.join(HERE, "tab4_conditions.tex"), "w", encoding="utf-8").write("\n".join(tex) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
