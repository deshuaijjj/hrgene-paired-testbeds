#!/usr/bin/env python3
"""Compile benchmark/v4/authoring/<caseId>.json (human-readable, index-based) into
benchmark/v4/cases/<caseId>.json (model-visible, case.v2) and benchmark/v4/gold/<caseId>.json (gold.v2),
re-attaching every identifier from build/skeleton.json.

Authoring format (indices are 1-based: S1..S8 sources, R1..R5 requirements, P1..P3 propositions):
{
  "caseId": "...", "roleTitle": "...", "jobDescription": "...",
  "requirements": ["...", x5],
  "evidence": [{"type": "resume|work_sample|note", "text": "..."}, x8 in skeleton order],
  "gold": {
    "propositions": [{"text": "...", "status": "supported|unsupported", "sources": [1,5], "requirements": [1],
                      "boundaryCategory": "...", "criticality": "critical|noncritical", "rationale": "..."}, x3],
    "requirementStatus": ["supported", "partial_evidence", "insufficient_evidence", ...x5],
    "trap": {"proposition": 3, "rule": "hrgene....", "requirements": [3], "signatures": ["23%"], "bait": [7],
             "anywhere": []},   # risk cases only; "anywhere" = protected-content phrases that count anywhere in the bundle
    "subjective": [8], "nonProduction": [6],
    "expectedGap": "...", "expectedBoundaryNote": "...", "followUpTargets": ["..."], "validClaimSignatures": ["..."]
  }
}"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V4 = os.path.normpath(os.path.join(HERE, ".."))
ROOT = os.path.normpath(os.path.join(V4, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
from hrgene import schema_lite  # noqa: E402

TASK = "Generate one evidence-bounded optimized CV and one complete HiringEvidencePacket for qualified human review."
CASE_SCHEMA = json.load(open(os.path.join(ROOT, "schema", "case.v2.schema.json"), encoding="utf-8"))
GOLD_SCHEMA = json.load(open(os.path.join(ROOT, "schema", "gold.v2.schema.json"), encoding="utf-8"))


def skeleton():
    s = json.load(open(os.path.join(HERE, "skeleton.json"), encoding="utf-8"))
    return {c["caseId"]: c for c in s["cases"]}


def cv_markdown(a):
    lines = ["# Curriculum vitae", "", f"Target role: {a['roleTitle']}", "", "## Experience", ""]
    for e in a["evidence"]:
        if e["type"] == "resume":
            lines.append(f"- {e['text']}")
    ws = [e for e in a["evidence"] if e["type"] == "work_sample"]
    if ws:
        lines += ["", "## Work samples", ""] + [f"- {e['text']}" for e in ws]
    return "\n".join(lines) + "\n"


def compile_one(a, sk):
    assert len(a["requirements"]) == len(sk["requirementIds"]), "requirement count differs from skeleton"
    assert len(a["evidence"]) == len(sk["sourceIds"]), "evidence count differs from skeleton"
    for e, t in zip(a["evidence"], sk["sourceTypes"]):
        assert e["type"] == t, f"evidence type order must follow the skeleton ({sk['sourceTypes']})"
    R, S, P = sk["requirementIds"], sk["sourceIds"], sk["propositionIds"]
    case = {
        "schemaVersion": "jam.hrgene_generation_case_view.v2",
        "caseId": sk["caseId"], "language": a.get("language", "en"), "task": TASK,
        "roleContext": {"roleTitle": a["roleTitle"], "jobDescription": a["jobDescription"],
                        "requirements": [{"requirementId": rid, "text": t} for rid, t in zip(R, a["requirements"])]},
        "jobDescriptionSourceId": sk["jobDescriptionSourceId"],
        "candidate": {"candidateId": sk["candidateId"], "originalCvMarkdown": a.get("originalCvMarkdown") or cv_markdown(a),
                      "evidence": [{"sourceId": sid, "sourceType": e["type"], "text": e["text"]} for sid, e in zip(S, a["evidence"])]},
        "outputSchemaVersion": "jam.hrgene_paired_review_bundle.model_output.v2",
    }
    g = a["gold"]
    assert len(g["propositions"]) == len(P), "proposition count differs from skeleton"
    props = []
    for pid, p in zip(P, g["propositions"]):
        props.append({"atomicPropositionId": pid, "canonicalProposition": p["text"], "supportStatus": p["status"],
                      "supportingSourceIds": [S[i - 1] for i in p.get("sources", [])],
                      "relevantRequirementIds": [R[i - 1] for i in p.get("requirements", [])],
                      "boundaryCategory": p["boundaryCategory"], "criticality": p["criticality"], "rationale": p["rationale"]})
    gold = {
        "schemaVersion": "jam.hrgene_gold.v2", "caseId": sk["caseId"], "family": sk["family"], "controlStatus": sk["controlStatus"],
        "propositions": props,
        "requirementStatus": {rid: st for rid, st in zip(R, g["requirementStatus"])},
        "subjectiveSourceIds": [S[i - 1] for i in g.get("subjective", [])],
        "nonProductionSourceIds": [S[i - 1] for i in g.get("nonProduction", [])],
        "expectedGap": g["expectedGap"], "expectedBoundaryNote": g["expectedBoundaryNote"],
        "permittedFollowUpTargets": g.get("followUpTargets", []),
        "validClaimSignatures": g.get("validClaimSignatures", []),
    }
    if "trap" in g:
        t = g["trap"]
        anywhere = [x for x in t.get("anywhere", [])]
        sigs = list(t["signatures"]) + [x for x in anywhere if x not in t["signatures"]]
        gold["trap"] = {"propositionId": P[t["proposition"] - 1], "rule": t["rule"], "requirementIds": [R[i - 1] for i in t.get("requirements", [])],
                        "signatures": sigs, "baitSourceIds": [S[i - 1] for i in t.get("bait", [])]}
        if anywhere:
            gold["trap"]["anywhereSignatures"] = anywhere   # protected content: counts as fallen anywhere in the bundle
    return case, gold


def main(paths=None):
    sk = skeleton()
    os.makedirs(os.path.join(V4, "cases"), exist_ok=True)
    os.makedirs(os.path.join(V4, "gold"), exist_ok=True)
    paths = paths or sorted(glob.glob(os.path.join(V4, "authoring", "*.json")))
    ok = 0
    for p in paths:
        a = json.load(open(p, encoding="utf-8"))
        if a["caseId"] not in sk:
            print(f"SKIP {p}: caseId not in skeleton")
            continue
        case, gold = compile_one(a, sk[a["caseId"]])
        errs = schema_lite.validate(case, CASE_SCHEMA) + schema_lite.validate(gold, GOLD_SCHEMA)
        if errs:
            print(f"ERROR {p}: " + "; ".join(errs[:5]))
            continue
        json.dump(case, open(os.path.join(V4, "cases", f"{a['caseId']}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(gold, open(os.path.join(V4, "gold", f"{a['caseId']}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        ok += 1
    print(f"compiled {ok} / {len(paths)} authoring files")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
