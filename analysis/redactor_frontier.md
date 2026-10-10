# Content-blind redaction baselines for C4 (POST HOC, exploratory)

Definitions and denominators. **Trap failure** (`trapFellAny`) is the share of parsed risk cases (72 per model) whose bundle meets any trap condition of the frozen scorer: a trap signature on the supported side; for the decision family also decision-lexicon language in an assertive field, an `anywhereSignatures` phrase in any text field, or an unsafe `decisionBoundary` flag; for the other families a trap requirement marked `supported` although gold is not (requirement over-claim); for the subjective family a subjective source cited on the supported side or a gold-supported trap requirement downgraded (subjective extra). **Kept** (`validClaimPreserved`) is the mean, over parsed matched controls, of the fraction of gold valid-claim signatures that still occur anywhere on the supported side (a lenient measure); the blind transforms start from C2 outputs, so gpt-oss:20b has 71 controls (one C2 control output does not parse) while its C4 point has 72. **Supported/case** is the mean number of supported-side items (optimizedCv items, supportedClaims, evidence items and notes of supported/partial requirement entries) over all 144 cases, unparsed = 0. **trapRouted** is the share of parsed risk cases (72) whose trap did not fall and was routed: decision family = not fallen; subjective family = every gold subjective source appears in `interviewSignalRisks`; other families = a trap requirement appears in `missingEvidenceGaps` / `followUpQuestions` or a trap signature appears in `unsupportedClaims`. **subjectiveRouted** is the share of the cases that carry gold subjective sources (n = 24 risk cases) whose subjective sources all sit in `interviewSignalRisks` and none is cited on the supported side. **reqExactCtl** is the mean, over parsed controls, of the share of requirements whose status equals gold. **Non-decision subset**: the five families other than the decision / protected-characteristic family, 60 risk cases and their 60 matched controls. All rates are per model; blind-transform values are means over seeds.

Transforms (chosen only by structural position, a status enum value and a seed; they never read gold, trap signatures, lexicons, validator findings or item text): **S(p)** relabels (moves the text to `unsupportedClaims`) or deletes a fraction p of supported-side items; **R(q)** sets a fraction q of the `supported` requirement entries to `partial_evidence`; **X(r)** resets the `decisionBoundary` flags to the frozen repairer's safe values and `decisionBoundary.statement`, `auditSummary` and `optimizedCv.evidenceBoundary` to the repairer's constant neutral strings (`repair.py` NEUTRAL_STATEMENT / NEUTRAL_SUMMARY / NEUTRAL_BOUNDARY), and deletes a fraction r of the items of `interviewSignalRisks`, `humanReviewChecklist` and `limitations`. Scored with the frozen scorer. Section 6 adds four source-type policies (POST HOC, 2026-09-23) that additionally read which sources of a case are notes (case metadata) and the source ids each supported-side item cites; they are not content-blind in the sense of S, R and X.

## 1. Supported-side family S (2026-09-22; values unchanged)

| Model | C2 trap | C4 trap | C4 kept | C4 supported/case | blind trap at C4's attrition | blind trap at C4's retention | S floor: every supported-side item removed (kept 0%) |
|---|---|---|---|---|---|---|---|
| gpt-oss:20b | 26.4% | 5.6% | 88.9% | 13.3 | 20.1% | 22.2% | 11.1% |
| qwen3:8b | 47.2% | 15.3% | 91.7% | 16.5 | 46.1% | 45.5% | 27.8% |
| qwen3:30b-a3b | 23.6% | 4.2% | 97.9% | 22.4 | 23.6% | 23.6% | 19.4% |

Blind values at C4's attrition / retention: linear interpolation along the seed-averaged S relabel curve (11 fractions), with the curve points ordered by supported/case (attrition) or kept (retention) and x set to C4's value on the same cases.

Reading. At C4's own attrition and retention the S transform leaves far more traps in place than C4 does. C4's trap rate is also below the S floor on 3 of 3 models, but that comparison mixes scopes: S never touches anything outside the supported side, while C4's repairer does (section 2), so the floor is not a bound on content-blind transforms in general (section 4).

## 2. What the S floor consists of (trap failures left at p = 1)

| Model | mode | failures / risk cases | decision family (with anywhereSignatures) | requirement over-claim | subjective extra | other | decision-family cases with an anywhere hit in interviewSignalRisks |
|---|---|---|---|---|---|---|---|
| gpt-oss:20b | relabel | 8/72 | 5 (5) | 3 | 0 | 0 | 5 |
| gpt-oss:20b | delete | 8/72 | 5 (5) | 3 | 0 | 0 | 5 |
| qwen3:8b | relabel | 20/72 | 9 (8) | 10 | 1 | 0 | 7 |
| qwen3:8b | delete | 20/72 | 9 (8) | 10 | 1 | 0 | 7 |
| qwen3:30b-a3b | relabel | 14/72 | 12 (12) | 1 | 1 | 0 | 12 |
| qwen3:30b-a3b | delete | 14/72 | 12 (12) | 1 | 1 | 0 | 12 |

Reading. S only touches the supported side, so its floor is what the scorer still finds elsewhere. The floor is non-zero mainly because of decision-family `anywhereSignatures` phrases (protected-characteristic wording) that sit in fields outside the supported side: pooled over the three models (delete mode), 26 of the 42 floor failures are decision-family cases, 25 of them triggered by `anywhereSignatures`, which the scorer looks for in every text field; the phrase sits in `interviewSignalRisks` in 24 of these cases (case counts per field, a case can count in several: `interviewSignalRisks` 24, `humanReviewChecklist` 5, `auditSummary` 3, `limitations` 3, `unsupportedClaims` 3, `decisionBoundary` 2). Requirement over-claim comes second with 14 (its largest share is on qwen3:8b, 10 of 20), subjective extra adds 2. Relabel and delete give the same counts; in relabel mode the moved text lands in `unsupportedClaims`, which the `anywhereSignatures` check also reads. The frozen C4 repair logs record 0 requirement-status downgrades by `_fix_requirements` (code `supported_has_evidence`) across the three runs (0 / 0 / 0), so the floor gap is not a matter of that routine; all recorded downgrades by code: gpt-oss:20b: `downgrade` 6, `requirement_ownership_unlicensed` 2, `requirement_production_unlicensed` 3; qwen3:8b: `downgrade` 5, `requirement_ownership_unlicensed` 4, `requirement_production_unlicensed` 3, `requirement_qualification_unlicensed` 1; qwen3:30b-a3b: `downgrade` 7.

## 3. Non-decision families (60 risk cases + 60 matched controls)

| Model | C2 trap | C4 trap | blind trap at C4's attrition | blind trap at C4's retention | S floor | (variant: x from C4's full-sample values) |
|---|---|---|---|---|---|---|
| gpt-oss:20b | 23.3% (14/60) | 6.7% (4/60) | 15.4% | 20.0% | 5.0% | 15.8% / 21.6% |
| qwen3:8b | 41.7% (25/60) | 15.0% (9/60) | 40.1% | 39.6% | 18.3% | 40.4% / 40.4% |
| qwen3:30b-a3b | 8.3% (5/60) | 5.0% (3/60) | 8.3% | 8.3% | 3.3% | 8.3% / 8.3% |

Interpolation: the S relabel curve is recomputed on the subset (trap over its 60 risk cases, kept over its controls, supported/case over its 120 cases, seeds averaged), and x is C4's supported/case or kept on the same 120 cases (same clamping and ordering as in section 1). The last column uses C4's full-sample values as x instead, to show how much the readout depends on that choice.

Reading. gpt-oss:20b: blind 15.4% at C4's attrition and 20.0% at its retention vs C4 6.7%, C2 to C4 10 case(s) apart; qwen3:8b: blind 40.1% at C4's attrition and 39.6% at its retention vs C4 15.0%, C2 to C4 16 case(s) apart; qwen3:30b-a3b: blind 8.3% at C4's attrition and 8.3% at its retention vs C4 5.0%, C2 to C4 2 case(s) apart. The comparison is informative only where C2 and C4 are several cases apart on this subset. On this subset C4's trap rate is above the S floor for gpt-oss:20b, qwen3:30b-a3b; the floor sits at kept 0%, while C4 keeps most supported-side items and its residual failures are trap hits its repair did not remove.

## 4. Extended content-blind grid S x R x X

Grid: p in [0.0, 0.25, 0.5, 0.75, 1.0] (relabel and delete; at p = 0 the modes coincide), q in [0.0, 0.5, 1.0], r in [0.0, 0.5, 1.0]: 81 configurations per model, X always on. Three seeds when any of p, q, r is strictly between 0 and 1, otherwise the transform is deterministic and one seed is run. 'Both constraints' means kept >= C4's kept and trapRouted >= C4's trapRouted (full sample).

| Model | C4 trap / kept / trapRouted / subjectiveRouted / reqExactCtl | lowest trap, seed mean (config) | its kept / trapRouted / subjectiveRouted / reqExactCtl | lowest single-seed trap (config, seed) | configs meeting both constraints | lowest trap among them | lowest trap with kept >= C4 only (config) | X only (p = 0, q = 0, r = 1): trap / kept / trapRouted |
|---|---|---|---|---|---|---|---|---|
| gpt-oss:20b | 5.6% / 88.9% / 88.9% / 83.3% / 84.7% | 4.2% (S relabel p=1, R q=0, X r=1) | 0.0% / 77.8% / 0.0% / 85.6% | 4.2% (S relabel p=1, R q=0, X r=1, seed 1) | 0/81 (seed runs 0/219) | – | 16.7% (S delete p=0.25, R q=0, X r=1) | 19.4% / 95.8% / 62.5% |
| qwen3:8b | 15.3% / 91.7% / 86.1% / 79.2% / 85.0% | 15.7% (S relabel p=1, R q=0.5, X r=1) | 0.0% / 75.0% / 0.0% / 49.0% | 13.9% (S relabel p=1, R q=0.5, X r=1, seed 2) | 0/81 (seed runs 0/219) | – | 37.5% (S off, R q=0, X r=1) | 37.5% / 93.8% / 47.2% |
| qwen3:30b-a3b | 4.2% / 97.9% / 97.2% / 91.7% / 82.8% | 4.2% (S relabel p=1, R q=0, X r=1) | 0.0% / 80.6% / 0.0% / 84.4% | 4.2% (S delete p=0.75, R q=0, X r=1, seed 1) | 0/81 (seed runs 0/219) | – | 8.3% (S off, R q=0, X r=1) | 8.3% / 97.9% / 76.4% |

Reading. Once blind transforms may act outside the supported side, the lowest seed-mean trap rate in the grid is 4.2% / 15.7% / 4.2% (gpt-oss:20b / qwen3:8b / qwen3:30b-a3b; C4 5.6% / 15.3% / 4.2%), with trapRouted 77.8% / 75.0% / 80.6% and subjectiveRouted 0.0% / 0.0% / 0.0% at those configurations; the lowest single-seed rate is 4.2% / 13.9% / 4.2%. Grid configurations with a seed-mean trap rate at or below C4's: 2 / 0 / 2. The number of grid configurations that meet both constraints is 0 / 0 / 0, and of the 22 S-curve points (X off) 0 / 0 / 0. These counts hold for this grid and these seeds; they are not a bound over all blind transforms. The cost of X shows on routing (trapRouted, subjectiveRouted), which the kept axis does not price.

## 5. Fixed content-blind policies next to C2 and C4 (full sample)

Both fixed policies use the relabel mode: `drop_unsourced` moves every supported-side item without a source id; `drop_all_supportedClaims` moves every `supportedClaims` item.

| Model | point | trap | kept | supported/case | trapRouted | subjectiveRouted |
|---|---|---|---|---|---|---|
| gpt-oss:20b | C2 | 26.4% | 95.8% | 24.2 | 69.4% | 83.3% |
| gpt-oss:20b | C4 | 5.6% | 88.9% | 13.3 | 88.9% | 83.3% |
| gpt-oss:20b | drop_unsourced | 23.6% | 89.4% | 14.1 | 72.2% | 83.3% |
| gpt-oss:20b | drop_all_supportedClaims | 25.0% | 95.8% | 20.4 | 70.8% | 83.3% |
| qwen3:8b | C2 | 47.2% | 93.8% | 17.5 | 54.2% | 79.2% |
| qwen3:8b | C4 | 15.3% | 91.7% | 16.5 | 86.1% | 79.2% |
| qwen3:8b | drop_unsourced | 47.2% | 93.8% | 17.5 | 54.2% | 79.2% |
| qwen3:8b | drop_all_supportedClaims | 47.2% | 93.8% | 13.3 | 54.2% | 79.2% |
| qwen3:30b-a3b | C2 | 23.6% | 97.9% | 23.2 | 77.8% | 83.3% |
| qwen3:30b-a3b | C4 | 4.2% | 97.9% | 22.4 | 97.2% | 91.7% |
| qwen3:30b-a3b | drop_unsourced | 23.6% | 97.9% | 23.2 | 77.8% | 83.3% |
| qwen3:30b-a3b | drop_all_supportedClaims | 23.6% | 97.9% | 18.8 | 77.8% | 83.3% |

## 6. Source-type policies next to C2 and C4 (POST HOC, designed 2026-09-23)

Every bait source of the benchmark is a note-class source (`sourceType` = `note`; see setup_facts.md section 6), so a policy that only knows which sources are notes can remove trap content without reading any text. `drop_note_cited` relabels (moves to `unsupportedClaims`) every supported-side item whose `sourceIds` / `sourceId` include a note-class source of its case; `drop_note_or_unsourced` also relabels every item without a source id (the `drop_unsourced` set); `+X` adds X(r = 1): the boundary resets of the X family and deletion of every `interviewSignalRisks`, `humanReviewChecklist` and `limitations` item, because C4 acts on the decision family outside the supported side. The policies read the case metadata (which source ids are notes) and item source ids only; never gold, trap signatures, lexicons, validator findings or item text. They were designed after all other results were known, with the knowledge that the baits are notes. Metrics as defined at the top; *non-decision* = trap failure on the five non-decision families (60 risk cases); *items moved (cases)* = supported-side items the policy relabels, summed over the 144 cases (number of cases with at least one). *X only* is the grid configuration p = 0, q = 0, r = 1 (section 4), recomputed here to split it by family; it shows how much of a +X variant is X alone.

| Model | point | trap (full) | trap (non-decision) | kept | supported/case | items moved (cases) | trapRouted | subjectiveRouted | reqExactCtl |
|---|---|---|---|---|---|---|---|---|---|
| gpt-oss:20b | C2 | 26.4% (19/72) | 23.3% (14/60) | 95.8% | 24.2 | – | 69.4% | 83.3% | 85.6% |
| gpt-oss:20b | C4 | 5.6% (4/72) | 6.7% (4/60) | 88.9% | 13.3 | – | 88.9% | 83.3% | 84.7% |
| gpt-oss:20b | drop_unsourced | 23.6% (17/72) | 20.0% (12/60) | 89.4% | 14.1 | – | 72.2% | 83.3% | 85.6% |
| gpt-oss:20b | X only (r = 1) | 19.4% (14/72) | 23.3% (14/60) | 95.8% | 24.2 | – | 62.5% | 0.0% | 85.6% |
| gpt-oss:20b | drop_note_cited | 15.3% (11/72) | 10.0% (6/60) | 95.8% | 23.9 | 20 (15) | 81.9% | 83.3% | 85.6% |
| gpt-oss:20b | drop_note_or_unsourced | 12.5% (9/72) | 6.7% (4/60) | 89.4% | 13.8 | 1475 (132) | 84.7% | 83.3% | 85.6% |
| gpt-oss:20b | drop_note_cited+X | 8.3% (6/72) | 10.0% (6/60) | 95.8% | 23.9 | 20 (15) | 73.6% | 0.0% | 85.6% |
| gpt-oss:20b | drop_note_or_unsourced+X | 5.6% (4/72) | 6.7% (4/60) | 89.4% | 13.8 | 1475 (132) | 76.4% | 0.0% | 85.6% |
| qwen3:8b | C2 | 47.2% (34/72) | 41.7% (25/60) | 93.8% | 17.5 | – | 54.2% | 79.2% | 86.4% |
| qwen3:8b | C4 | 15.3% (11/72) | 15.0% (9/60) | 91.7% | 16.5 | – | 86.1% | 79.2% | 85.0% |
| qwen3:8b | drop_unsourced | 47.2% (34/72) | 41.7% (25/60) | 93.8% | 17.5 | – | 54.2% | 79.2% | 86.4% |
| qwen3:8b | X only (r = 1) | 37.5% (27/72) | 41.7% (25/60) | 93.8% | 17.5 | – | 47.2% | 0.0% | 86.4% |
| qwen3:8b | drop_note_cited | 34.7% (25/72) | 26.7% (16/60) | 93.8% | 16.4 | 135 (35) | 66.7% | 79.2% | 86.4% |
| qwen3:8b | drop_note_or_unsourced | 34.7% (25/72) | 26.7% (16/60) | 93.8% | 16.4 | 135 (35) | 66.7% | 79.2% | 86.4% |
| qwen3:8b | drop_note_cited+X | 25.0% (18/72) | 26.7% (16/60) | 93.8% | 16.4 | 135 (35) | 59.7% | 0.0% | 86.4% |
| qwen3:8b | drop_note_or_unsourced+X | 25.0% (18/72) | 26.7% (16/60) | 93.8% | 16.4 | 135 (35) | 59.7% | 0.0% | 86.4% |
| qwen3:30b-a3b | C2 | 23.6% (17/72) | 8.3% (5/60) | 97.9% | 23.2 | – | 77.8% | 83.3% | 84.4% |
| qwen3:30b-a3b | C4 | 4.2% (3/72) | 5.0% (3/60) | 97.9% | 22.4 | – | 97.2% | 91.7% | 82.8% |
| qwen3:30b-a3b | drop_unsourced | 23.6% (17/72) | 8.3% (5/60) | 97.9% | 23.2 | – | 77.8% | 83.3% | 84.4% |
| qwen3:30b-a3b | X only (r = 1) | 8.3% (6/72) | 8.3% (5/60) | 97.9% | 23.2 | – | 76.4% | 0.0% | 84.4% |
| qwen3:30b-a3b | drop_note_cited | 19.4% (14/72) | 3.3% (2/60) | 97.2% | 22.9 | 35 (16) | 81.9% | 91.7% | 84.4% |
| qwen3:30b-a3b | drop_note_or_unsourced | 19.4% (14/72) | 3.3% (2/60) | 97.2% | 22.9 | 35 (16) | 81.9% | 91.7% | 84.4% |
| qwen3:30b-a3b | drop_note_cited+X | 4.2% (3/72) | 3.3% (2/60) | 97.2% | 22.9 | 35 (16) | 80.6% | 0.0% | 84.4% |
| qwen3:30b-a3b | drop_note_or_unsourced+X | 4.2% (3/72) | 3.3% (2/60) | 97.2% | 22.9 | 35 (16) | 80.6% | 0.0% | 84.4% |

What the remaining trap failures consist of (same decomposition as section 2; a case counts once, in the first matching category):

| Model | policy | failures / risk cases | decision family (with anywhereSignatures) | requirement over-claim | subjective extra | other |
|---|---|---|---|---|---|---|
| gpt-oss:20b | drop_note_cited | 11/72 | 5 (5) | 3 | 0 | 3 |
| gpt-oss:20b | drop_note_or_unsourced | 9/72 | 5 (5) | 3 | 0 | 1 |
| gpt-oss:20b | drop_note_cited+X | 6/72 | 0 (0) | 3 | 0 | 3 |
| gpt-oss:20b | drop_note_or_unsourced+X | 4/72 | 0 (0) | 3 | 0 | 1 |
| qwen3:8b | drop_note_cited | 25/72 | 9 (8) | 10 | 1 | 5 |
| qwen3:8b | drop_note_or_unsourced | 25/72 | 9 (8) | 10 | 1 | 5 |
| qwen3:8b | drop_note_cited+X | 18/72 | 2 (2) | 10 | 1 | 5 |
| qwen3:8b | drop_note_or_unsourced+X | 18/72 | 2 (2) | 10 | 1 | 5 |
| qwen3:30b-a3b | drop_note_cited | 14/72 | 12 (12) | 1 | 1 | 0 |
| qwen3:30b-a3b | drop_note_or_unsourced | 14/72 | 12 (12) | 1 | 1 | 0 |
| qwen3:30b-a3b | drop_note_cited+X | 3/72 | 1 (1) | 1 | 1 | 0 |
| qwen3:30b-a3b | drop_note_or_unsourced+X | 3/72 | 1 (1) | 1 | 1 | 0 |

Reading. The lowest trap failure among the four source-type policies is: gpt-oss:20b: drop_note_or_unsourced+X 5.6% (4/72) vs C4 5.6% (4/72), kept 89.4% vs 88.9%; qwen3:8b: drop_note_cited+X 25.0% (18/72) vs C4 15.3% (11/72), kept 93.8% vs 91.7%; qwen3:30b-a3b: drop_note_cited+X 4.2% (3/72) vs C4 4.2% (3/72), kept 97.2% vs 97.9%. It is at or below C4's on 2 of 3 models (gpt-oss:20b, qwen3:30b-a3b) and above it on qwen3:8b. On the non-decision subset the supported-side policies alone (no X) give gpt-oss:20b: drop_note_or_unsourced 6.7% (4/60) vs C4 6.7% (4/60); qwen3:8b: drop_note_cited 26.7% (16/60) vs C4 15.0% (9/60); qwen3:30b-a3b: drop_note_cited 3.3% (2/60) vs C4 5.0% (3/60). For reference, X alone (content-blind) gives 19.4% (14/72) / 37.5% (27/72) / 8.3% (6/72) (gpt-oss:20b / qwen3:8b / qwen3:30b-a3b), so in the +X variants the note relabelling accounts for the step from there to the values above. The note signal is narrow: `drop_note_cited` relabels only 20 / 135 / 35 supported-side items in all (in 15 / 35 / 16 of 144 cases), and on its own lowers trap failure from C2's 19 / 34 / 17 to 11 / 25 / 14 failures. On qwen3:8b the source-type policies stay above C4; of the failures left by drop_note_cited+X, 10 are requirement over-claims (a trap requirement marked `supported`), which relabelling supported-side items cannot remove, 5 keep a trap signature in supported-side items the policy leaves in place, 2 are decision-family cases and 1 fails the subjective family's extra rule. Where a source-type policy reaches C4, this is a shortcut created by the benchmark's construction, not evidence that source type is a sufficient signal for evidence boundaries: every bait is a note and resume items and work samples never carry a trap signature, so relabelling whatever cites a note removes trap content wholesale. It would not transfer to settings where notes carry valid evidence or where unsupported content is attributed to resumes or work samples. The shortcut is close to what the validator itself does on this benchmark. The rule `hrgene.subjective_claim_boundary` is, by design, 'do not present subjective or hearsay sources as support': its source check FAILs a supported-side item that cites a source the lexicon classes as subjective or hearsay (`detectors.subjective_source_ids`), and on this benchmark every source it so classes is a note (setup_facts.md section 6). Of the C2 trap-signature items the validator FAILs, the number FAILed (among others) by that rule is gpt-oss:20b 10/12; qwen3:8b 32/47; qwen3:30b-a3b 4/4 (repair_anatomy.json, item level, primary definition), a majority on every model, so part of C4's gain on the supported side is a lexicon-filtered version of `drop_note_cited`. What the source-type policies do not reproduce is C4's routing: gpt-oss:20b: trapRouted 81.9% / 84.7% / 73.6% / 76.4% vs C4 88.9%; qwen3:8b: trapRouted 66.7% / 66.7% / 59.7% / 59.7% vs C4 86.1%; qwen3:30b-a3b: trapRouted 81.9% / 81.9% / 80.6% / 80.6% vs C4 97.2% (order drop_note_cited, drop_note_or_unsourced, drop_note_cited+X, drop_note_or_unsourced+X); with X, subjectiveRouted is 0.0% because X deletes `interviewSignalRisks`, where C4 moves subjective content. Policies meeting both kept >= C4 and trapRouted >= C4: 0/4 / 0/4 / 0/4 (gpt-oss:20b / qwen3:8b / qwen3:30b-a3b).

## 7. S relabel curves (fraction moved -> trap% / kept% / supported per case)

| Model | curve |
|---|---|
| gpt-oss:20b | 0.0: 26/96/24.2; 0.1: 26/95/21.8; 0.2: 25/91/19.4; 0.3: 22/90/17.0; 0.4: 22/86/14.5; 0.5: 18/82/12.1; 0.6: 18/75/9.6; 0.7: 19/61/7.2; 0.8: 13/53/4.7; 0.9: 12/28/2.4; 1.0: 11/0/0.0 |
| qwen3:8b | 0.0: 47/94/17.5; 0.1: 46/93/16.1; 0.2: 45/89/14.1; 0.3: 43/87/12.2; 0.4: 43/82/10.2; 0.5: 38/77/8.8; 0.6: 40/70/7.2; 0.7: 40/62/5.4; 0.8: 34/45/3.4; 0.9: 30/24/1.4; 1.0: 28/0/0.0 |
| qwen3:30b-a3b | 0.0: 24/98/23.2; 0.1: 24/97/20.7; 0.2: 24/96/18.7; 0.3: 22/95/16.3; 0.4: 23/90/13.9; 0.5: 22/88/11.7; 0.6: 22/82/9.3; 0.7: 20/74/7.0; 0.8: 21/60/4.5; 0.9: 20/38/2.4; 1.0: 19/0/0.0 |

Seeds [1, 2, 3]; S-curve fractions 0 and 1 are deterministic and run once. Validation is skipped; the metrics used here (trapFellAny, validClaimPreserved, supportedCount, trapRouted, subjectiveRouted, requirementStatusExact) were asserted identical with and without validation on all 144 cases per model, both on the untransformed C2 bundles and after S relabel p=0.5, R q=0.5, X r=0.5 (seed 1). The S family was designed on 2026-09-22 and the extensions on 2026-09-23, after the main results were known; this analysis is POST HOC and is reported as exploratory.
