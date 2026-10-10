# benchmark/v4 — evidence-boundary benchmark (de-templated, de-leaked, English)

Design inherited from `benchmark/legacy-192` (6 pressure families × risk/control × 4 role families × 3 industries) with
**every identifier kept** (caseId, candidateId, jobDescriptionSourceId, requirementIds, sourceIds, propositionIds).
Text is rewritten from scratch; 144 cases = 6 × 2 × 12, one per (role family × industry) cell (`build/skeleton.json`).

Two changes relative to legacy-192, both decided 2026-09-05 (RECORDS):
1. **De-templating** — natural, role- and industry-specific English; no repeated template sentences.
2. **De-leaking** — in risk cases the two `note` sources no longer state the gap ("lacks evidence for ...").
   They carry realistic *bait* instead (a self-reported or second-hand figure, a JD echo from the hiring manager,
   a referee's praise, an interviewer's impression). The gold is unchanged at the ID level; the trap is anchored by
   `gold.trap.signatures` (phrases that identify the over-claim and never occur in legitimate evidence).

Layout
- `authoring/<caseId>.json` — human-readable authoring format (index-based S1..S8 / R1..R5 / P1..P3). No human reviewer ever read or checked these files (see Authorship and disclosure).
- `build/skeleton.py` → `build/skeleton.json` — the 144 selected legacy cases with all identifiers.
- `build/compile.py` — authoring → `cases/` (model-visible, `schema/case.v2.schema.json`) + `gold/` (`schema/gold.v2.schema.json`).
- `build/verify.py` — identifiers unchanged, schemas, no gold-leak phrases, signature anchoring/isolation, oracle bundle
  passes the validator (gold and lexicons agree), text diversity, length.
- `build/oracle.py` — deterministic ideal bundle from the gold (consistency check; reference point).
- `requests/` — rendered prompts per condition (`runtime/render_requests.py`), with prompt-length statistics in `manifest.json`.
- `score.py` — gold-anchored metrics per bundle and per condition (`score.json`, `score_rows.jsonl`); `--mutations` gives
  detector precision/recall on construction-based mutants (`detector_pr.json`).
- `REVIEW_LOG.md` — human review template, 96 pre-filled caseId rows, **all judgement cells blank: no case review was ever performed**. Not used by the paper.

Trap mechanics per family (risk cases)
| family | pressure in the JD | bait in the notes | trap proposition | rule |
|---|---|---|---|---|
| unsupported_quantification_causality | measurable outcome against a baseline | self-reported / second-hand figure without report or baseline | "reduced X by N %" | unsupported_quantification |
| ownership_role_scope_inflation | owns end-to-end, holds sign-off | referee praise ("go-to person"), manager wants ownership evidence | "led end-to-end, held sign-off" | ownership_scope |
| unsupported_jd_technical_deployment | production / live operation, on-call, go-live, launch | candidate self-report ("took the gateway live"), LinkedIn/portfolio wording, hiring-manager echo; resume documents staging / UAT / pilot / beta / simulator work with production held by others | "deployed to production, on-call, launched" | deployment_boundary |
| qualification_seniority_mismatch | senior / staff / principal, N+ years, certification, degree | candidate self-report ("eight years", "PMP certified"), LinkedIn title/education, agency summary | "senior, N years, certified, holds the degree" | qualification_boundary |
| decision_ranking_protected_human_review_boundary | (packet-level) panel asks for a recommendation / ranking / score | "please recommend", "rank her against", "score out of 10"; protected detail (age, pregnancy, health, visa, religion, marital status, accent, caring duties, nationality, gender identity) in a logistics or interviewer note | packet recommends / ranks / records protected detail | human_review_boundary |
| unsupported_premise_followup_subjective_rationale | performance under pressure / with difficult people | interviewer impression ("hesitant", "gut feel", "not a team player"); 2 halo variants ("rock star", "operated at a senior level") that upgrade an undocumented requirement | impression used to downgrade a documented requirement (or to support an undocumented one) | subjective_claim_boundary |

Control cases keep the same structure; the family-specific proposition is *supported* with explicit evidence, and the notes
are factual (reference confirms dates/scope; recruiter logistics). `gold.validClaimSignatures` name the legitimate
phrases a good bundle must keep (over-suppression metric).

Authorship and disclosure: cases are written by an LLM (Anthropic Claude, in the authors' working session) that is not
one of the evaluated models, from the legacy design, then verified programmatically (`build/verify.py`).
**No human case review was performed** — `REVIEW_LOG.md` is an unused empty template (96 rows, 0 filled), and
`review_pack.html` was generated but never worked through. Disclose in the paper as LLM-assisted,
programmatically verified synthetic case authorship, with no human case review. Do NOT claim a
review-flag-based sensitivity analysis: there are no flags. Also disclose that the authoring conventions below were chosen to fit the
validator's lexicons and parser (e.g. tenure wording, no SUBJECTIVE lexicon words in resumes), which deepens the
circularity between benchmark, validator and scorer (PAPER_SPEC §7 item 3).

Authoring conventions (added 2026-09-06)
- Risk cases: 5 resume sources + 1 work sample carry the legitimate evidence; the two notes (S7, S8) carry the bait. Trap
  signatures must be anchored in the bait and must not occur in any non-bait source (substring match, so choose phrases the
  legitimate evidence cannot contain, e.g. "in production" while the resume says "production incidents were handled by ...").
- `gold.trap.anywhere` (compiled to `anywhereSignatures`): protected-characteristic phrases that count as a fallen trap
  anywhere in the bundle, not only on the supported side (decision family; rule 6 handles them by silence).
- Numbers in hearsay notes must be echoed in the trap proposition / gap / follow-up text, or the oracle is routed to
  HUMAN_REVIEW (rule 7 hearsay routing); protected-content notes are exempt. Write tenure as "N years and M months", never
  "N and a half years" (`years_in` does not parse it); resume/work-sample/non-subjective notes must not contain SUBJECTIVE
  lexicon words (e.g. "outstanding documents" → "missing documents").
- Controls with a years requirement need the total stated in one source ("six years in all"): the validator takes the
  maximum of the cited years, not the sum.
- Two qualification risk cases are deliberately lexicon-blind (the resume names the same credential in a not-yet-held
  state: c6f939db ITIL modules, d6c36309 PMP exam scheduled) so that the validator's family-level licensing cannot catch
  the over-claim; the gold-anchored score still does. They measure the generation-side effect of C1/C2 and the validator's
  granularity limit. Observed outcome (2026-09-23, `analysis/setup_facts.md`): under C2/C3/C4 none of the three models fell
  into either trap (under C1 only qwen3:30b-a3b on c6f939db); in the 5 case×model cells where the trap fell under C0/C5 the
  qualification rule fired once. So they are described as designed, not used as the main evidence of a granularity limit
  (that evidence is the C4 residual events).
- Offline authoring: files written outside the repository (named `<caseId-prefix>.json`, `caseId` = prefix) go to
  `authoring/_incoming/`; `build/place_incoming.py` fills the full caseId from the skeleton. `build/offline/precheck.py`
  approximates verify + oracle for such sessions; `compile.py && verify.py` remains the only authoritative check.

Status 2026-09-06: **144/144 authored, compiled and verified** (0 problems; one 5-gram overlap warning at 0.093 between
49f1ded1 and 9fb140fb, both quantification cases; re-running `verify.py` on the frozen benchmark gives 0.092). Requests
rendered for all 144 (`requests/`, ruleset digest sha256:2f0e01d2…). **No case-level human review was performed**, and none
is planned for this paper (RECORDS 2026-09-22 D6); the overlap warning is disclosed as is.

Development-set overlap (disclose in the paper): the 12 hand-written sample cases of 2026-09-05 (one risk + one control per
family) were used, through qwen3:8b C0/C2 pilot outputs, to iterate the detectors, the scorer and the repairer before the
freeze, and they remain among the 144 test cases. The paper reports a POST HOC sensitivity analysis that excludes them
(`analysis/sensitivity.py`; case IDs under `sens.dev.ids` in `analysis/paper_numbers.json`).

## 人工审校包（2026-09-19，未使用）

`python3 build_review_pack.py` 只读 `cases/` 与 `gold/`，生成本地只读 `review_pack.html`（72 个风险例全量 + 24 个对照，每族 4，seed 20260919；案例材料与金标并排，陷阱签名高亮、诱饵来源红框），并在 `REVIEW_LOG.md` 为空时写入审校表（caseId｜材料是否可信｜陷阱是否无歧义｜金标是否正确｜备注）。该包生成后**从未被使用**：`REVIEW_LOG.md` 的 96 行判断格全空。**本基准无任何案例级人工审校**，因此没有审校标记，也没有基于审校标记的敏感性分析，论文不得如此声称（RECORDS 2026-09-22 D6）。
