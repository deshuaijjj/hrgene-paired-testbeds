# HRgene paired testbeds: a cue-confounded and a de-confounded testbed for LLM output repair

This repository accompanies the paper *Rethinking Synthetic Testbeds for LLM Output Repair: A Construction Cue and a Pre-registered De-confounded Test* (Yuxin Zhang, Xv Zhang, Jinxi Yang, Junjie Zhang, Man Yuan).

It contains two synthetic hiring-review testbeds for one task, the validation-and-repair pipeline analysed in the paper (HRgene), the recorded outputs of three open-weight models, and all analysis code. In the **original testbed** (`benchmark/v4`) every planted unsupported claim (the bait) sits in a note-type source. In the **de-confounded testbed** (`benchmark/v5`) the bait sits in a note, a resume entry or the work sample, notes also carry valid evidence, and the cases were written without access to the validator. The second study was pre-registered (https://osf.io/8vejq) before any of its outputs were generated.

All cases are fictional. They were drafted by LLM agents and verified by scripts; there was no case-level human review. The testbeds are not a measure of hiring quality and must not be used to rank or select real candidates. See `DATASHEET.md`.

## Contents

- `benchmark/v4/` (original testbed) and `benchmark/v5/` (de-confounded testbed): `authoring/` records, model-visible `cases/`, `gold/`, rendered `requests/`, and `build/` (identifier skeleton, compiler, oracle builder, verification script). `benchmark/v5/AUTHORING_BRIEF.md` is the brief given to the case-writing agents.
- `rules/`, `schema/`, `runtime/`: the nine-rule contract, lexicons, schemas, prompt renderer, generation runner, deterministic validator, repairer and scorer, with rule fixtures. The same bytes were used in both studies.
- `experiments/*-C[0-5]-full/`: Study 1, six conditions x three models on the original testbed. `experiments/*-C[2-4]-v5/`: Study 2 on the de-confounded testbed (C2 generated; C3 validation reports and C4 repair derived from it). `experiments/run-v5.log` is the run log of Study 2.
- `analysis/`: analysis scripts and their recorded outputs. `v5_preregistered.py` is the registered analysis of Study 2 (`v5_preregistered.json` is its output); `paper_numbers_v5.py` formats it for the paper.
- `ANALYSIS_PLAN_V5.md`, `PREREG_MANIFEST_V5.txt`: the registered plan and the SHA-256 manifest of the 478 files that define Study 2 (`DECONFOUND_PLAN.md` is the planning note listed in the manifest, in Chinese). `shasum -a 256 -c PREREG_MANIFEST_V5.txt` verifies them in this layout.
- `machine/`: hardware and inference-engine snapshots, with personal filesystem locations removed.
- `SHA256SUMS`: hashes of every file in this release.

## Licences

Data (cases, gold, authoring records, requests, model outputs, score records, analysis outputs, documentation) are released under CC BY 4.0 (`LICENSE-DATA.md`). Code (`runtime/`, `benchmark/*/build/`, `benchmark/v4/score.py`, `analysis/*.py`, shell scripts) is released under the MIT licence (`LICENSE`).

## Environment

Use Python 3.10 or newer. The benchmark verifier, rule tests, repair replay, scorer, statistics, and table generation use the Python standard library. Plotting additionally requires `matplotlib`; the architecture figure uses locally available fonts, so font substitution can change its rendered appearance across systems. Model inference used the model tags, quantization, digests, inference-engine version, and decoding settings recorded in each formal run's `config.json` and in `analysis/setup_facts.json`.

Before changing files, verify the packaged hashes with `shasum -a 256 -c SHA256SUMS` (macOS) or `sha256sum -c SHA256SUMS` (Linux). Run the commands below from the top-level directory of this repository, preferably in a disposable extracted copy. Analysis commands regenerate files under `analysis/`; the archived benchmark and experimental outputs should remain unchanged. No Ollama server or network access is needed for these commands.

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 benchmark/v4/build/verify.py
python3 runtime/tests/run_rule_tests.py --no-write
```

Expected benchmark verification: 144 cases and no problems, with the documented low-level text-overlap warning. Expected rule-fixture result: 90 passed, 0 failed. These are implementation consistency checks, not evidence of detector accuracy on naturally occurring outputs.

## Study 2: verify and re-run the registered analysis

```sh
export PYTHONDONTWRITEBYTECODE=1
shasum -a 256 -c PREREG_MANIFEST_V5.txt        # the registered files
python3 benchmark/v5/build/verify.py --oracle   # 144 cases, 0 problems; oracle report 107/144
python3 analysis/v5_preregistered.py            # P1-P4 from the recorded outputs -> analysis/v5_preregistered.json
python3 analysis/paper_numbers_v5.py            # numbers and tables used in the paper
```

No model inference is needed: the commands read the recorded outputs in `experiments/*-v5/`. To generate fresh outputs on your own machine, see `runtime/run_v5_chain.sh`; fresh generations are not expected to match the recorded ones byte for byte.

## Study 1: reproduce measurements and tables offline

Run in this order:

```sh
python3 analysis/tab2_benchmark.py
python3 analysis/collect.py
python3 analysis/tab4_conditions.py
python3 analysis/tab3_detector.py
python3 analysis/tab4_families.py
python3 analysis/tab4_stats.py
python3 analysis/tab4_contrasts.py
python3 analysis/repair_anatomy.py
python3 analysis/sensitivity.py
python3 analysis/setup_facts.py
python3 analysis/tab1_contract.py
python3 analysis/example_case.py
python3 analysis/redactor_frontier.py
python3 analysis/paper_numbers.py
python3 analysis/paper_tables.py
```

`collect.py` checks run coverage and C2/C3 correspondence and emits 18 rows, each with 144 cases. `repair_anatomy.py` replays the deterministic C2-to-C4 pipeline and checks the stored validation reports, repair logs, final artifacts, and score records. `sensitivity.py` first checks the unmodified re-score against the archived gold-anchored quantities before applying its explicitly post hoc sensitivity transformations. The redaction/source-type policies are also post hoc analyses. The stored results and all numeric fields are the manuscript's quantitative sources; mutation-injection results are stored in `benchmark/v4/detector_pr.json`.

The single recorded C4 regeneration is under `experiments/20260906-gpt-oss-20b-C4-full/regen/`. Offline replay **reuses that recorded output**, after checking the regenerated request; it does not call a language model. Fresh model generation on another hardware/software environment is a different exercise and is not claimed to reproduce outputs byte for byte. Do not run `ollama_runner.py` or the generation/post-processing CLI to validate the archived measurements.

To rebuild the paper figures after the numeric analysis (optional):

```sh
python3 analysis/fig2_main.py
python3 analysis/fig3_frontier.py
python3 paper/figures/fig1_architecture.py
```

The original `benchmark/v4/README.md` records the authoring conventions and limitations. References there to older design materials or unused review templates are historical context; those materials are not needed for the supplied verification and replay. Internal project-management and manuscript-source files are intentionally absent.

## Provenance

The scientific inputs and outputs are preserved byte for byte: cases, gold, authoring records, request payloads, model outputs, receipts, rule/lexicon/schema files, and runtime code. The fixed machine-readable protocol identifiers embedded in these records are retained for exact replay and digest verification. Schema `$id` values are identifiers, not artifact-download links.

For the original testbed's runs, only 29 metadata files differ from the working originals: absolute personal paths in formal-run `config.json` and `score.json` files were replaced by repository-relative paths, and personal home-directory paths in one machine snapshot were replaced by `[user-home]/`. No field that represents a measurement, model setting, case, claim, score, or request was changed. Recorded request, runner, model, and ruleset digests remain the historical values. SHA256SUMS describes the packaged bytes and is not a preregistration or a timestamped freeze record.

The archive excludes author names, email addresses, personal absolute paths, hidden files, version-control history, manuscript author blocks, unused human-review materials, and unrelated legacy artifacts. No public artifact hosting is implied by this local archive; it must be uploaded with the submission.

For Study 2's runs, absolute paths of the run machine in run configurations, score files and the run log were replaced by repository-relative paths; no measurement, setting, output or score was changed.

## Citation and contact

See `CITATION.cff`. Corrections are issued as versioned releases; please open an issue in the repository.
