#!/usr/bin/env python3
"""Table 3 — detector precision / recall per rule, from benchmark/v4/detector_pr.json (mutation injection only).

This paper reports no human annotation (RECORDS 2026-09-22 D6), so the table carries no human columns:
an empty column would imply a validation that was not performed. Mutation injection measures whether the
nine rules are implemented correctly, NOT precision/recall on real model output."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.join(HERE, "..", "benchmark", "v4", "detector_pr.json")


def main():
    pr = json.load(open(PR, encoding="utf-8"))
    md = ["| Rule | Mutants | P (mutation) | R (mutation) |", "|---|---|---|---|"]
    for rule, s in pr["perRule"].items():
        md.append(f"| {rule.split('.')[-1]} | {s['tp'] + s['fn']} | {s['precision']:.2f} | {s['recall']:.2f} |")
    md.append(f"\nClean oracles flagged: {pr['cleanOraclesFlagged']}/{pr['cleanOracles']}; "
              f"near-miss edits flagged: {pr.get('nearMissesFlagged', 0)}/{pr.get('nearMisses', 0)}.")
    md.append("Mutation injection only: variants are built from the validator's own lexicons, so for lexicon-driven "
              "rules this is a self-consistency check of the implementation, not independent evidence. "
              "Precision/recall on real model output is not estimated in this paper (see PAPER_SPEC section 7).")
    open(os.path.join(HERE, "tab3_detector.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
