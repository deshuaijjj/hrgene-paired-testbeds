"""Prompt rendering for conditions C0..C5 from one rule source.

C0  task + output contract description, JSON mode (no rules)
C1  C0 + the nine obligations as plain prose (same content as C2, no structure)
C2  C0 + the nine obligations as structured contract blocks (what the validator checks)
C3  = C2 generation + independent validation report (no repair)      -> pipeline.py
C4  = C2 generation + validation + bounded repair (+ <=1 regeneration) -> pipeline.py
C5  C0 + constrained decoding against the JSON schema (schema-only external baseline)
"""
import json

GENERATION_CONDITIONS = {"C0": "none", "C1": "prose", "C2": "contract", "C5": "none"}

SYSTEM_ROLE = (
    "You are a review-support assistant for a hiring team. From the materials provided you produce (1) an optimized CV "
    "that restates what the materials establish about the candidate for the target role and (2) a HiringEvidencePacket "
    "that maps each job requirement to evidence, records unsupported claims, evidence gaps, interview-signal risks and "
    "follow-up questions, and supports qualified human review. Use only the provided materials."
)

OUTPUT_CONTRACT = """Output contract. Return exactly one JSON object and nothing else, with this shape:
{
 "schemaVersion": "jam.hrgene_paired_review_bundle.model_output.v2",
 "optimizedCv": {
  "language": "<case language: en or zh-CN>", "candidateId": "<copy from the case>", "targetRoleTitle": "<role title>",
  "professionalSummary": [CLAIM...], "experienceHighlights": [CLAIM...], "projectsAndWorkSamples": [CLAIM...], "skills": [CLAIM...],
  "evidenceBoundary": "<one or two sentences on what the materials do and do not establish>"
 },
 "hiringEvidencePacket": {
  "decisionBoundary": {"employmentDecisionMade": false, "candidateRanked": false, "protectedCharacteristicsInferred": false, "humanReviewRequired": true, "statement": "<sentence>"},
  "role": {"roleTitle": "<role title>", "jobDescriptionSource": "<copy jobDescriptionSourceId from the case>", "requirementIds": ["<every requirementId>"]},
  "candidate": {"candidateId": "<copy from the case>", "sources": ["<every sourceId you used>"]},
  "requirementEvidenceMap": [{"requirementId": "<id>", "status": "supported|partial_evidence|insufficient_evidence",
     "evidence": [{"sourceId": "<id>", "text": "<verbatim passage from that source>", "evidenceStrength": "low|medium|high", "notes": "<short note>"}],
     "missingEvidence": ["<what is missing, if anything>"]}],
  "supportedClaims": [{"claim": "<statement>", "supportingRequirementIds": ["<id>"], "sourceIds": ["<id>"], "evidenceStrength": "low|medium|high", "witness": "<verbatim passage from a cited source>"}],
  "unsupportedClaims": [{"claim": "<statement that the materials do not establish>", "reason": "<why>", "requiredFollowUp": "<what would establish it>"}],
  "missingEvidenceGaps": [{"gapId": "<id>", "requirementId": "<id>", "severity": "low|medium|high", "gap": "<what is missing>"}],
  "interviewSignalRisks": [{"sourceId": "<id>", "text": "<the signal>", "signalType": "<type>", "jobRelatedBoundary": "<is it tied to job-related evidence?>", "severity": "low|medium|high", "recommendedHandling": "<how to verify>"}],
  "followUpQuestions": [{"questionId": "<id>", "requirementId": "<id>", "question": "<neutral question>", "evidenceTarget": "<what evidence it seeks>"}],
  "humanReviewChecklist": ["<item>"], "auditSummary": "<paragraph>", "limitations": ["<item>"]
 }
}
CLAIM = {"claimId": "<id>", "text": "<statement>", "sourceIds": ["<id>"], "requirementIds": ["<id>"], "supportBoundary": "supported|partial_evidence", "witness": "<verbatim passage from a cited source, or empty string>"}
Every array may be empty except requirementEvidenceMap, which must cover every requirementId once."""


def render_case(case):
    rc = case["roleContext"]
    cand = case["candidate"]
    lines = [f"Case {case['caseId']} (language: {case['language']}).", "",
             f"Target role: {rc['roleTitle']}", f"Job description (jobDescriptionSourceId {case['jobDescriptionSourceId']}): {rc['jobDescription']}", "",
             "Requirements:"]
    for r in rc["requirements"]:
        lines.append(f"- {r['requirementId']}: {r['text']}")
    lines += ["", f"Candidate identifier: {cand['candidateId']}", "", "Original CV (markdown):", cand["originalCvMarkdown"].rstrip(), "",
              "Evidence sources (cite by sourceId):"]
    for e in cand["evidence"]:
        lines.append(f"- {e['sourceId']} [{e['sourceType']}]: {e['text']}")
    lines += ["", f"Task: {case['task']}", f"Output language: {case['language']}. Return only the JSON object."]
    return "\n".join(lines)


def build_messages(case, condition, ruleset):
    mode = GENERATION_CONDITIONS[condition]
    system = SYSTEM_ROLE + "\n\n" + OUTPUT_CONTRACT
    if mode == "prose":
        system += "\n\n" + ruleset.render_prose(case)
    elif mode == "contract":
        system += "\n\n" + ruleset.render_contract(case)
    return [{"role": "system", "content": system}, {"role": "user", "content": render_case(case)}]


def build_request(case, condition, ruleset, schema=None, meta=None):
    """One ollama_runner / api_runner request record."""
    msgs = build_messages(case, condition, ruleset)
    rec = {"request_id": f"{case['caseId']}.{condition}", "case_id": case["caseId"], "condition": condition, "messages": msgs,
           "format": schema if (condition == "C5" and schema) else "json",
           "meta": dict(meta or {}, rulesetDigest=ruleset.digest, activeRules=[r["ruleId"] for r in ruleset.active_rules(case)],
                        promptChars=sum(len(m["content"]) for m in msgs), promptWords=sum(len(m["content"].split()) for m in msgs))}
    return rec


def build_regeneration_messages(case, condition, ruleset, previous_output_text, findings):
    """Bounded regeneration (C4): the same prompt plus the validator's findings; the model may only fix the listed
    problems and must not add new facts."""
    msgs = build_messages(case, "C2" if condition in ("C2", "C3", "C4") else condition, ruleset)
    lines = ["Your previous output is below. An independent validator found the following rule violations. Return the "
             "corrected JSON object only. Fix only the listed problems; do not add any statement that the materials do not "
             "support; keep everything else unchanged.", "", "Violations:"]
    for f in findings:
        if f["status"] != "FAIL":
            continue
        lines.append(f"- [{f['rule']}] {f['code']} at {f['path']}: {f['message']}")
    lines += ["", "Previous output:", previous_output_text[:60000]]
    return msgs + [{"role": "user", "content": "\n".join(lines)}]
