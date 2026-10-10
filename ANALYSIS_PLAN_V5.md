# Pre-registered analysis plan: HRgene v5 de-confounded testbed

Registered on OSF (project https://osf.io/uhpvy) before any v5 model output was generated. Materials are identified by
the SHA-256 manifest `PREREG_MANIFEST_V5.txt` registered together with this plan.

## 1. Question

In the earlier testbed (v4: 72 synthetic risk cases, 72 matched clean controls, hiring-review artifacts), deterministic
validation with bounded repair (condition C4, applied to the frozen outputs of the contract prompt, C2) cleared most
trap failures. A post hoc analysis then found that every bait source was a `note`, every note in a risk case was bait,
and valid content rarely occurred only in notes; policies that read only source types and reset fields matched C4's
observed trap-failure rate on two of three models. v5 asks: **once source type no longer identifies bait, does
validation-driven repair keep its advantage over source-type policies, and which part of its clearance depends on
content checks rather than on the note cue?**

## 2. Design (v5 testbed; nothing else changes)

- 144 synthetic English cases: 6 stress families x {risk, matched clean control} x 4 role families x 3 industries;
  each case has 5 resume entries, 1 work sample and 2 notes (as in v4); fresh identifiers.
- Each risk case has exactly one bait source. Bait location per family: 4 note / 4 resume / 4 work sample (decision
  family: 6 note / 6 resume) -> 26 note, 26 resume, 20 work-sample bait cases.
- In risk cases every non-bait note carries legitimate evidence (verification records, logistics). In 36 of 72
  controls at least one gold valid-claim signature occurs only in a note.
- Each bait is unlicensed by the text of the frozen task rules independently of its source type.
- Cases and gold were drafted by Claude agents (not among the evaluated models) from an authoring brief
  (`benchmark/v5/AUTHORING_BRIEF.md`); authors were instructed not to read or consult the validator, detectors or
  lexicons. Programmatic checks (`benchmark/v5/build/verify.py`) enforce identifiers, schemas, leak phrases, signature
  isolation, bait placement, note-only valid content, length and diversity. Whether the gold-derived ideal bundle
  passes the frozen validator is recorded as a property, not used as an authoring gate. No case-level human review.
- Unchanged from v4 (byte-identical, hashed): rule contract and lexicons, prompt renderer and C2 template, validator,
  repairer (including at most one regeneration), scorer, Ollama 0.33.0, models gpt-oss:20b (think=low), qwen3:8b and
  qwen3:30b-a3b (think=false) with the v4 digests, temperature 0, seed 1, num_ctx 16384, num_predict 6000, one
  generation per case. Only C2 is generated; C3 and C4 are derived by the frozen pipeline (`runtime/run_v5_chain.sh`).

## 3. Outcomes and analyses (script `analysis/v5_preregistered.py`, frozen)

Trap failure (`trapFellAny`), trap routing, subjective-source routing and valid-signature retention are computed by
the frozen v4 scorer. Unparseable outputs are excluded from semantic denominators, as in v4. Bait location = source
type of the gold bait source. All intervals 95%, per model, not adjusted for multiplicity. Source-type policies,
content-blind S transform, X reset and their seeds are exactly those of v4 (`analysis/redactor_frontier.py`).

| ID | Comparison (per model) | Statistic | Prediction |
|---|---|---|---|
| **P1 (primary)** | Trap-failure rate of the best of the 4 source-type policies (lowest rate; ties broken by fixed order) minus C4, over risk cases scored under both | Paired difference, Newcombe (1998) method 10 | Positive with interval above 0 for all three models; larger within non-note bait cases |
| P2 | C2->C4 clearance (share of C2 trap failures that C4 clears) by bait location | Wilson per location; note minus non-note, Newcombe hybrid score interval | Clearance lower for non-note than note bait; the drop concentrated in the quantification and qualification families, with ownership, subjective and decision families largely retained (family x location cells are descriptive) |
| P3 | Valid-signature retention on controls, each source-type policy minus C4 | Case bootstrap of the mean paired difference (B = 10000, seed 20261009) | Negative for note-filtering policies, most clearly within note-only-valid controls |
| P4 | Trap-failure rate of the content-blind S relabel curve interpolated at C4's supported-side items per case, versus C4 | Seed means (seeds 1-3), no interval | Higher than C4, overall and in non-decision families |

A prediction is reported as supported for a model when the interval lies on the predicted side of 0 (P1, P2, P3) or
the point estimate does (P4); otherwise as not supported. All four are reported for every model whatever the result.

Descriptive (not tested): C2->C4 paired difference overall; repair-log rules on cleared cases by bait location;
oracle-validator report; comparison with v4 (different authoring conventions, so not an estimate of a location effect).

## 4. Deviations

Any change after registration (failed runs, reruns, code fixes, additional analyses) is listed in a deviations section
of the report with its reason and timing; analyses added after seeing v5 outputs are labelled exploratory. Runner
retries follow the frozen runner (`--max-attempts 2`); outputs are never regenerated selectively.
