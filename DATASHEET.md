# Datasheet: HRgene paired testbeds

Following Gebru et al., "Datasheets for Datasets" (Communications of the ACM, 2021).

## Motivation

**Purpose.** The testbeds were created to evaluate systems that validate and repair structured outputs of large language models against task rules, and, as a pair, to test whether a measured repair gain depends on how a testbed is constructed. The original testbed (`benchmark/v4`) contains a construction cue: every planted unsupported claim (bait) is a note-type source. The de-confounded testbed (`benchmark/v5`) removes that cue.

**Creators and funding.** Created by the authors of the accompanying paper (Yuxin Zhang, Xv Zhang, Jinxi Yang, Junjie Zhang, Man Yuan), funded internally by JAM Studio. No external funding.

## Composition

**Instances.** Each testbed has 144 fictional English hiring-review cases: 72 risk cases and 72 matched clean controls, 12 + 12 per stress family (quantification, ownership, deployment, qualification, decision, subjective), one risk case and one control per combination of four role families and three industries.

**What an instance contains.** A case (`cases/<id>.json`) has a role title, a job description, five requirements, an original CV and eight typed evidence sources with identifiers (five resume entries, one work sample, two notes). Its gold record (`gold/<id>.json`) has three propositions with support status and supporting sources, the gold status of each requirement, the trap (risk cases: rule, trap requirement, bait source, trap signatures, and for the decision family protected-content signatures), subjective and non-production source lists, an expected gap, permitted follow-up targets, and valid-claim signatures. `authoring/<id>.json` is the human-readable source from which case and gold are compiled.

**Differences between the two testbeds.** Original: two notes per risk case, both bait; cases written to conventions that fit the validator's lexicons; an ideal artifact built from the gold had to pass the validator. De-confounded: exactly one bait source per risk case, in a note (26 cases), a resume entry (26) or the work sample (20); non-bait notes carry legitimate evidence; in 36 of 72 controls a gold valid-claim signature occurs only in a note; cases written from the task-rule texts without access to the validator; the validator accepts the gold-derived ideal artifact in 107 of 144 cases (recorded, not enforced).

**Labels.** Gold was drafted with the cases and encodes the intended reading of each synthetic case. It has not been compared with judgments of hiring practitioners.

**Missing information, errors, noise.** No instances are missing. Known limitations: no case-level human review in either testbed; scoring by substring signatures can miss paraphrases or count unintended matches; family-by-location cells in the de-confounded testbed hold at most four risk cases.

**Splits.** No train/test split; all cases are evaluation cases. Twelve cases of the original testbed were used while developing the validator, scorer and repairer and remain in it (listed in the paper's sensitivity appendix). No case of the de-confounded testbed was used in development.

**Confidential or sensitive content, people.** All persons, employers, events and identifiers are invented. Real names of credentials and certifying bodies appear with invented certificate numbers. Decision-family cases contain fictional statements of protected characteristics (for example age, health, family status, nationality, religion); they exist to test that systems do not repeat them. No data from or about real individuals is included.

**Associated outputs.** The release includes the recorded outputs of gpt-oss:20b, qwen3:8b and qwen3:30b-a3b (Ollama 0.33.0): 18 runs on the original testbed (conditions C0-C5) and 9 on the de-confounded testbed (C2 generated, C3 and C4 derived), with run configurations, receipts, validation reports, repair logs and score rows.

## Collection process

Cases and gold of both testbeds were drafted by LLM agents (Anthropic Claude; not among the evaluated models) under written authoring conventions and verified by scripts (`benchmark/*/build/verify.py`: identifiers, schemas, gold-leak phrases, isolation of trap signatures in the bait, length and diversity; for the de-confounded testbed also bait placement, note-only valid content and text overlap with the original testbed). The de-confounded testbed was authored on 9 October 2026 from `benchmark/v5/AUTHORING_BRIEF.md`, with bait placement fixed in `benchmark/v5/build/skeleton.json` before any text was written. No crowd workers or human annotators were involved, and no ethical review was required because no human subjects or personal data are involved.

## Preprocessing

`build/compile.py` converts authoring records into case and gold files and attaches identifiers. Nothing else is preprocessed. For recorded runs, absolute personal paths in metadata were replaced by repository-relative paths.

## Uses

**Intended.** Evaluating validation, repair and guardrail systems on a cue-confounded and a de-confounded version of one task; comparing post-processing systems on the released fixed generations; replaying the paper's results; methodological work on testbed construction and construction-cue audits.

**Not intended.** Assessing, ranking or selecting real candidates; claims about fairness, legal compliance or production readiness of any hiring tool; training data for systems that make employment decisions.

**Caveats for users.** Results on the original testbed overstate what a validator-based repair achieves when the bait is not confined to notes (see the paper). Source-type policies are informative controls on both testbeds and should be reported next to any repair system.

## Distribution

Public release on GitHub (https://github.com/deshuaijjj/hrgene-paired-testbeds) with an archived copy of each release on Zenodo (v1.0.0: https://doi.org/10.5281/zenodo.23287375). Data: CC BY 4.0. Code: MIT. No third-party restrictions apply.

## Maintenance

Maintained by the corresponding author (Yuxin Zhang). Errata and corrections are handled through the repository's issue tracker and published as versioned releases; each release is archived with its own DOI and earlier versions stay available. The versions used in the paper are fixed by `SHA256SUMS` and, for the second study, by the registered manifest `PREREG_MANIFEST_V5.txt` (https://osf.io/8vejq). Contributions of additional cases or systems are welcome through pull requests; they will be kept separate from the frozen versions.
