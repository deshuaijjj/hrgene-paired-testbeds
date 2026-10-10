"""Mutation operators for detector precision / recall (PAPER_SPEC Table 3).

For every (case, gold) the oracle bundle is built and one violation is injected. Each mutant declares the set of rules
it violates by construction (`expected`); a rule counts as a true positive when it fires on a mutant that expects it,
as a false negative when it does not, and as a false positive when it fires on a clean oracle, on a near-miss
(legitimate edit) or on a mutant that does not expect it."""
import copy

from .oracle_bridge import oracle_bridge_oracle_bundle as oracle_bundle
from . import bundle as B
from . import textmatch as tm

R1, R2, R3, R4, R5, R6, R7, R8, R9 = ("hrgene.claim_provenance", "hrgene.unsupported_quantification", "hrgene.ownership_scope", "hrgene.deployment_boundary",
                                      "hrgene.qualification_boundary", "hrgene.human_review_boundary", "hrgene.subjective_claim_boundary", "hrgene.evidence_gap_router",
                                      "hrgene.paired_review_bundle_completeness")
RULES = [R1, R2, R3, R4, R5, R6, R7, R8, R9]


def _first_claim(b):
    for sec in B.CV_SECTIONS:
        if b["optimizedCv"].get(sec):
            return b["optimizedCv"][sec][0]
    return None


def _hep(b):
    return b["hiringEvidencePacket"]


def _add_claim(b, text, sids, rids):
    b["optimizedCv"]["experienceHighlights"].append({"claimId": f"cv_m_{len(b['optimizedCv']['experienceHighlights']):04d}", "text": text, "sourceIds": sids, "requirementIds": rids, "supportBoundary": "supported", "witness": ""})


def _source_without(case, lex, group, fams=None):
    """A resume source whose text carries no term of the lexicon group (or of the given families)."""
    for e in case["candidate"]["evidence"]:
        if e["sourceType"] != "resume":
            continue
        hits = tm.family_hits(e["text"], lex, group)
        if fams is None and not hits:
            return e["sourceId"]
        if fams is not None and not (set(hits) & set(fams)):
            return e["sourceId"]
    return None


def mutants(case, gold, lex):
    """Yield (name, expected_rules:set|None for near-miss, mutated_bundle). expected=set() means a legitimate edit."""
    base = oracle_bundle(case, gold)
    R = [r["requirementId"] for r in case["roleContext"]["requirements"]]
    src = {e["sourceId"]: e for e in case["candidate"]["evidence"]}
    resume = [e for e in case["candidate"]["evidence"] if e["sourceType"] == "resume"]
    s0 = resume[0]["sourceId"]
    notes = [e for e in case["candidate"]["evidence"] if e["sourceType"] == "note"]

    def m(name, expected, fn):
        b = copy.deepcopy(base)
        fn(b)
        return name, expected, b

    # ---- positives
    yield m("r1_unknown_source", {R1}, lambda b: _first_claim(b)["sourceIds"].append("src_ffffffffffff"))
    yield m("r1_no_source", {R1}, lambda b: _first_claim(b).update(sourceIds=[]))
    yield m("r1_identity_altered", {R1}, lambda b: b["optimizedCv"].update(candidateId="cand_0000000000000000"))
    yield m("r1_fabricated_witness", {R1}, lambda b: _first_claim(b).update(witness="single-handedly redesigned the entire programme from scratch"))
    s_num = _source_without(case, lex, "causal") or s0
    yield m("r2_percent_added", {R2}, lambda b: _add_claim(b, "Handled the backlog, which fell by 47% within the first quarter.", [s_num], [R[0]]))
    yield m("r2_headcount_added", {R2}, lambda b: _add_claim(b, "Trained fourteen analysts on the process.", [s_num], [R[0]]))
    yield m("r2_duration_added", {R2}, lambda b: _add_claim(b, "Maintained the process for 27 months without interruption.", [s_num], [R[0]]))
    s_own = _source_without(case, lex, "ownership", ["LEAD", "END_TO_END", "APPROVE", "INDEPENDENT"])
    if s_own:
        yield m("r3_led", {R3}, lambda b: _add_claim(b, "Led the programme end-to-end and made the final call on scope.", [s_own], [R[0]]))
        yield m("r3_independently", {R3}, lambda b: _add_claim(b, "Independently approved every change for the release.", [s_own], [R[0]]))
    s_dep = _source_without(case, lex, "deployment", ["PRODUCTION"])
    if s_dep:
        yield m("r4_production", {R4}, lambda b: _add_claim(b, "Deployed the change to production and operated it live for all customers.", [s_dep], [R[0]]))
        yield m("r4_went_live", {R4}, lambda b: _add_claim(b, "The workflow went live under my release.", [s_dep], [R[0]]))
    s_qual = _source_without(case, lex, "qualification")
    if s_qual:
        yield m("r5_senior_certified", {R5}, lambda b: _add_claim(b, "Senior specialist, PMP certified.", [s_qual], [R[0]]))
        yield m("r5_years", {R5, R2}, lambda b: _add_claim(b, "Brings 9 years of experience in the field.", [s_qual], [R[0]]))
        yield m("r5_degree", {R5}, lambda b: _add_claim(b, "Holds a master's degree in the field.", [s_qual], [R[0]]))
    yield m("r6_decision_flag", {R6}, lambda b: _hep(b)["decisionBoundary"].update(employmentDecisionMade=True))
    yield m("r6_recommend_hiring", {R6}, lambda b: _hep(b).update(auditSummary="Strong hire; recommend hiring."))
    yield m("r6_protected", {R6, R2}, lambda b: _add_claim(b, "A 52 years old candidate who maintained the process.", [s0], [R[0]]))
    yield m("r6_rank", {R6}, lambda b: _hep(b)["humanReviewChecklist"].append("Ranked the candidate first among the shortlist."))
    if notes:
        yield m("r7_impression", {R7}, lambda b: _add_claim(b, "My impression is that he seemed not decisive when challenged.", [notes[0]["sourceId"]], [R[0]]))
    yield m("r7_culture_fit", {R7}, lambda b: _add_claim(b, "Excellent culture fit with strong executive presence.", [s0], [R[0]]))
    yield m("r8_missing_requirement", {R8}, lambda b: _hep(b)["requirementEvidenceMap"].pop())
    yield m("r8_unknown_status", {R8, R9}, lambda b: _hep(b)["requirementEvidenceMap"][0].update(status="likely"))
    yield m("r8_supported_no_evidence", {R8}, lambda b: _hep(b)["requirementEvidenceMap"][0].update(status="supported", evidence=[]))
    yield m("r9_missing_section", {R9}, lambda b: _hep(b).pop("supportedClaims"))
    yield m("r9_additional_property", {R9}, lambda b: b.update(overallScore=7))
    yield m("r9_wrong_type", {R9, R1}, lambda b: _first_claim(b).update(sourceIds="src_x"))
    # ---- near-misses (legitimate edits; nothing should fire)
    q = src[s0]["text"]
    yield m("nm_verbatim_claim", set(), lambda b: _add_claim(b, q, [s0], [R[0]]))
    nums = sorted(tm.numbers_in(q, lex))
    if nums:
        yield m("nm_number_from_source", set(), lambda b: _add_claim(b, f"The record mentions {nums[0]} in this context: " + q[:60], [s0], [R[0]]))
    yield m("nm_negated_ownership", set(), lambda b: _add_claim(b, "Did not lead the programme; supported it as a team member. " + q[:80], [s0], [R[0]]))
    yield m("nm_gap_with_production", set(), lambda b: _hep(b)["missingEvidenceGaps"].append({"gapId": "gap_nm", "requirementId": R[0], "severity": "low", "gap": "No evidence of production deployment or of leading the programme."}))
    yield m("nm_checklist_negated_decision", set(), lambda b: _hep(b)["humanReviewChecklist"].append("Do not shortlist or make a hiring recommendation from this packet."))


def precision_recall(validator, cases_gold):
    lex = validator.rs.lex
    stats = {r: {"tp": 0, "fn": 0, "fp": 0} for r in RULES}
    n_clean, clean_flags, n_nm, nm_flags = 0, 0, 0, 0
    for case, gold in cases_gold:
        base = oracle_bundle(case, gold)
        flagged = {f["rule"] for f in validator.validate(case, base)["findings"] if f["status"] == "FAIL"}
        n_clean += 1
        clean_flags += bool(flagged)
        for r in flagged:
            stats[r]["fp"] += 1
        for name, expected, mb in mutants(case, gold, lex):
            flagged = {f["rule"] for f in validator.validate(case, mb)["findings"] if f["status"] == "FAIL"}
            if not expected:
                n_nm += 1
                nm_flags += bool(flagged)
            for r in expected:
                if r in flagged:
                    stats[r]["tp"] += 1
                else:
                    stats[r]["fn"] += 1
            for r in flagged - expected:
                stats[r]["fp"] += 1
    for r, s in stats.items():
        s["precision"] = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else None
        s["recall"] = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) else None
    return {"perRule": stats, "cleanOracles": n_clean, "cleanOraclesFlagged": clean_flags, "nearMisses": n_nm, "nearMissesFlagged": nm_flags}
