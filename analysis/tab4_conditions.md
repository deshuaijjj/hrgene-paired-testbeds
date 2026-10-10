| Model | Condition | n | Scored risk/control | Parsed | Gold trap failure | Req. over-claimed | Trap routed | Residual critical viol. | Control claims kept | Controls suppressed | Schema valid | Validator flagged | Req. status ≤ gold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-oss:20b | C0 | 144 | 71/71 | 98.6% | 60.6% | 8.5% | 32.4% | 98.6% | 92.3% | 0.0% | 0.0% | 100.0% | 77.3% |
| gpt-oss:20b | C1 | 144 | 72/72 | 100.0% | 20.8% | 0.0% | 75.0% | 100.0% | 95.8% | 0.0% | 1.4% | 100.0% | 84.9% |
| gpt-oss:20b | C2 | 144 | 72/71 | 99.3% | 26.4% | 4.2% | 69.4% | 98.6% | 95.8% | 0.0% | 2.8% | 100.0% | 83.9% |
| gpt-oss:20b | C5 | 144 | 71/70 | 97.9% | 59.2% | 15.5% | 43.7% | 92.4% | 96.4% | 0.0% | 97.9% | 96.5% | 82.1% |
| gpt-oss:20b | C3 | 144 | 72/71 | 99.3% | 26.4% | 4.2% | 69.4% | 98.6% | 95.8% | 0.0% | 2.8% | 100.0% | 83.9% |
| gpt-oss:20b | C4 | 144 | 72/72 | 100.0% | 5.6% | 2.8% | 88.9% | 0.0% | 88.9% | 9.7% | 100.0% | 4.9% | 88.3% |
| qwen3:30b-a3b | C0 | 144 | 72/72 | 100.0% | 58.3% | 2.8% | 44.4% | 82.6% | 98.6% | 0.0% | 93.1% | 92.4% | 83.8% |
| qwen3:30b-a3b | C1 | 144 | 70/71 | 97.9% | 27.1% | 2.9% | 75.7% | 31.9% | 97.9% | 0.0% | 95.1% | 45.1% | 86.5% |
| qwen3:30b-a3b | C2 | 144 | 72/72 | 100.0% | 23.6% | 1.4% | 77.8% | 36.8% | 97.9% | 0.0% | 97.9% | 45.8% | 86.4% |
| qwen3:30b-a3b | C5 | 144 | 72/72 | 100.0% | 58.3% | 4.2% | 45.8% | 80.6% | 98.6% | 0.0% | 100.0% | 91.7% | 86.1% |
| qwen3:30b-a3b | C3 | 144 | 72/72 | 100.0% | 23.6% | 1.4% | 77.8% | 36.8% | 97.9% | 0.0% | 97.9% | 45.8% | 86.4% |
| qwen3:30b-a3b | C4 | 144 | 72/72 | 100.0% | 4.2% | 1.4% | 97.2% | 0.0% | 97.9% | 0.0% | 100.0% | 0.0% | 87.8% |
| qwen3:8b | C0 | 144 | 72/72 | 100.0% | 56.9% | 27.8% | 45.8% | 50.0% | 95.1% | 0.0% | 93.8% | 66.0% | 85.7% |
| qwen3:8b | C1 | 144 | 72/72 | 100.0% | 45.8% | 22.2% | 55.6% | 29.2% | 93.1% | 0.0% | 97.9% | 42.4% | 86.5% |
| qwen3:8b | C2 | 144 | 72/72 | 100.0% | 47.2% | 13.9% | 54.2% | 32.6% | 93.8% | 0.0% | 94.4% | 52.1% | 86.9% |
| qwen3:8b | C5 | 144 | 72/72 | 100.0% | 54.2% | 27.8% | 48.6% | 45.8% | 95.1% | 0.0% | 100.0% | 64.6% | 85.6% |
| qwen3:8b | C3 | 144 | 72/72 | 100.0% | 47.2% | 13.9% | 54.2% | 32.6% | 93.8% | 0.0% | 94.4% | 52.1% | 86.9% |
| qwen3:8b | C4 | 144 | 72/72 | 100.0% | 15.3% | 6.9% | 86.1% | 0.0% | 91.7% | 1.4% | 100.0% | 7.6% | 87.5% |

Each run contains 72 risk cases and 72 matched controls. Scored risk/control gives the non-null denominators for trap failure and control preservation; unparsed outputs are excluded from semantic metrics and reported separately under Parsed.
Gold trap failure is trapFellAny: explicit trap matches, requirement-status overclaim, or family-specific gold failures. It is broader than an explicit supported assertion. Trap routed is a separate metric and is not its complement.
Control claims kept is the mean fraction of valid signatures retained on the supported side per parsed matched control. Controls suppressed is the fraction with at least one missing valid signature explicitly moved to unsupportedClaims; omission alone does not count, so the two columns are not complements.
C3 reuses the C2 outputs and scores; its stored validation reports are checked against C2. Validator flagged is BLOCK or HUMAN_REVIEW (all cases); for generation-only conditions this is offline scoring, not an intervention delivered to the model. C4 uses the original C4-full run, excluding C4b.
Residual critical violation follows the frozen scorer: parsed bundles with one or more critical findings divided by all 144 cases. Parse failures are therefore not counted as residual critical violations. No metric is evidence of complete semantic correctness.
