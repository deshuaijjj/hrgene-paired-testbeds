#!/usr/bin/env python3
"""Write PREREG_MANIFEST_V5.txt at the repository root: SHA-256 of every file that defines the v5 pre-registered run
(testbed, task rules, pipeline, scorer, run script, analysis code and plans). Run after the cases and requests are final
and before any v5 generation; the manifest is registered on OSF with ANALYSIS_PLAN_V5.md."""
import glob
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
PATTERNS = [
    "ANALYSIS_PLAN_V5.md", "DECONFOUND_PLAN.md",
    "benchmark/v5/AUTHORING_BRIEF.md", "benchmark/v5/build/*.py", "benchmark/v5/build/skeleton.json",
    "benchmark/v5/authoring/*.json", "benchmark/v5/cases/*.json", "benchmark/v5/gold/*.json", "benchmark/v5/requests/*",
    "benchmark/v4/score.py", "rules/*.json", "schema/*.json",
    "runtime/hrgene/*.py", "runtime/ollama_runner.py", "runtime/render_requests.py", "runtime/c34_postprocess.py",
    "runtime/run_v5_chain.sh",
    "analysis/v5_preregistered.py", "analysis/redactor_frontier.py", "analysis/tab4_contrasts.py",
]


def main():
    files = []
    for pat in PATTERNS:
        hits = sorted(glob.glob(os.path.join(ROOT, pat)))
        assert hits, f"no files for {pat}"
        files += [h for h in hits if os.path.isfile(h)]
    lines = []
    for f in files:
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        lines.append(f"{h}  {os.path.relpath(f, ROOT)}")
    out = os.path.join(ROOT, "PREREG_MANIFEST_V5.txt")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{len(lines)} files -> {out}; manifest sha256 {hashlib.sha256(open(out, 'rb').read()).hexdigest()}")


if __name__ == "__main__":
    main()
