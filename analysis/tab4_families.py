#!/usr/bin/env python3
"""Descriptive family breakdown and paired C2/C4 preservation, from frozen scores."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parent / "experiments"


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def score_rows(run):
    return [json.loads(s) for s in (EXPERIMENTS / run / "score_rows.jsonl").read_text().splitlines() if s.strip()]


def pct(value):
    return "–" if value is None else f"{100 * value:.1f}%"


def main():
    runs = json.loads((HERE / "results.json").read_text())
    rows, transitions = [], []
    for run in runs:
        scores = score_rows(run["derivedFrom"] or run["run"])
        for family in sorted({s["family"] for s in scores}):
            risk = [s for s in scores if s["family"] == family and s["controlStatus"] == "positive_risk"]
            controls = [s for s in scores if s["family"] == family and s["controlStatus"] == "matched_clean_control"]
            rows.append({"model": run["model"], "condition": run["condition"], "family": family,
                         "riskN": len(risk), "riskScored": sum(s["trapFellAny"] is not None for s in risk),
                         "trapFailures": sum(s["trapFellAny"] is True for s in risk),
                         "trapFellAny": mean([s["trapFellAny"] for s in risk]),
                         "trapFellStrict": mean([s["trapFellStrict"] for s in risk]),
                         "trapRouted": mean([s["trapRouted"] for s in risk]),
                         "controlN": len(controls), "controlScored": sum(s["validClaimPreserved"] is not None for s in controls),
                         "controlPreserved": mean([s["validClaimPreserved"] for s in controls]),
                         "controlsSuppressed": sum(s["validClaimSuppressed"] is True for s in controls)})
        if run["condition"] != "C4":
            continue
        c2 = next(r for r in runs if r["model"] == run["model"] and r["condition"] == "C2")
        before = {r["caseId"]: r for r in score_rows(c2["run"])}
        if set(before) != {s["caseId"] for s in scores}:
            raise ValueError("C2/C4 case sets differ")
        controls = [s for s in scores if s["controlStatus"] == "matched_clean_control"]
        paired = [s for s in controls if before[s["caseId"]]["validClaimPreserved"] is not None and s["validClaimPreserved"] is not None]
        affected = []
        for after in controls:
            old = before[after["caseId"]]
            if any(old[k] != after[k] for k in ("parsed", "validClaimPreserved", "validClaimSuppressed")):
                affected.append({"caseId": after["caseId"], "family": after["family"],
                                 "before": {k: old[k] for k in ("parsed", "validClaimPreserved", "validClaimSuppressed")},
                                 "after": {k: after[k] for k in ("parsed", "validClaimPreserved", "validClaimSuppressed")}})
        p2 = mean([before[s["caseId"]]["validClaimPreserved"] for s in paired])
        p4 = mean([s["validClaimPreserved"] for s in paired])
        transitions.append({"model": run["model"], "controlN": len(controls), "pairedEvaluableN": len(paired),
                            "pairedPreservedC2": p2, "pairedPreservedC4": p4, "pairedDeltaPP": 100 * (p4 - p2),
                            "newSuppressed": sum(s["validClaimSuppressed"] is True and before[s["caseId"]]["validClaimSuppressed"] is False for s in controls),
                            "recoveredSuppressed": sum(s["validClaimSuppressed"] is False and before[s["caseId"]]["validClaimSuppressed"] is True for s in controls),
                            "affectedControls": affected})
    with (HERE / "tab4_families.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    md = ["| Model | Condition | Family | Trap failures/scored risk | Strict | Routed | Control kept | Controls scored | Suppressed controls |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['model']} | {r['condition']} | {r['family']} | {r['trapFailures']}/{r['riskScored']} | {pct(r['trapFellStrict'])} | {pct(r['trapRouted'])} | {pct(r['controlPreserved'])} | {r['controlScored']} | {r['controlsSuppressed']} |")
    md += ["", "Each family contains 12 risk cases and 12 controls; semantic metrics exclude unparsed outputs. These are descriptive case-level rates, with one generation per case. C3 reuses C2; family comparisons are not independent replications."]
    (HERE / "tab4_families.md").write_text("\n".join(md) + "\n")
    (HERE / "c4_transitions.json").write_text(json.dumps(transitions, indent=2) + "\n")
    print(f"{len(rows)} family rows; {len(transitions)} paired C2/C4 summaries")
    for t in transitions:
        print(t["model"], "paired n=", t["pairedEvaluableN"], "preservation delta (pp)=", t["pairedDeltaPP"], "new suppressed=", t["newSuppressed"])


if __name__ == "__main__":
    main()
