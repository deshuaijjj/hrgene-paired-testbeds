"""The nine detectors (phi). Each returns a list of findings for (case, bundle).

Finding = {"rule", "code", "severity", "status", "path", "message", "witness"}
  status: FAIL (a violation), UNRESOLVED (needs a human; not a proven violation), PASS is never emitted.
Detectors never read gold; gold-based checks live in scoring.py."""
from . import bundle as B
from . import textmatch as tm

CRIT, NONCRIT = "critical", "noncritical"


def finding(rule, code, severity, path, message, witness=None, status="FAIL"):
    return {"rule": rule, "code": code, "severity": severity, "status": status,
            "path": path, "message": message, "witness": witness or {}}


class CaseIndex:
    def __init__(self, case):
        self.case = case
        cand = case.get("candidate", {}) or {}
        self.candidate_id = cand.get("candidateId")
        self.jd_source_id = case.get("jobDescriptionSourceId")
        self.language = case.get("language")
        self.sources = {}
        for e in cand.get("evidence", []) or []:
            if isinstance(e, dict) and e.get("sourceId"):
                self.sources[e["sourceId"]] = e
        self.requirements = {}
        for r in (case.get("roleContext", {}) or {}).get("requirements", []) or []:
            if isinstance(r, dict) and r.get("requirementId"):
                self.requirements[r["requirementId"]] = r

    def source_texts(self, ids):
        return [self.sources[s].get("text", "") for s in ids if s in self.sources]


# ---------------------------------------------------------------- rule 1
def detect_claim_provenance(case, bundle, ctx):
    R = "hrgene.claim_provenance"
    ci, out = ctx["index"], []
    for path, text, sids, rids, kind in B.supported_side(bundle):
        if kind == "req_notes":
            continue
        if not sids:
            out.append(finding(R, "claim_has_source", CRIT, path, "supported-side statement cites no source", {"text": text[:160]}))
        for s in sids:
            if s not in ci.sources:
                out.append(finding(R, "source_ids_allowed", CRIT, path, f"cited sourceId {s!r} is not in the case", {"sourceId": s}))
        for r in rids:
            if r not in ci.requirements:
                out.append(finding(R, "requirement_ids_allowed", CRIT, path, f"cited requirementId {r!r} is not in the case", {"requirementId": r}))
    h = B.hep(bundle)
    for i, r in enumerate(h.get("interviewSignalRisks") or []):
        if isinstance(r, dict) and r.get("sourceId") and r["sourceId"] not in ci.sources:
            out.append(finding(R, "source_ids_allowed", CRIT, f"$.hiringEvidencePacket.interviewSignalRisks[{i}]", f"sourceId {r['sourceId']!r} is not in the case", {"sourceId": r["sourceId"]}))
    cv = bundle.get("optimizedCv") or {}
    if ci.candidate_id and cv.get("candidateId") != ci.candidate_id:
        out.append(finding(R, "identity_copied", CRIT, "$.optimizedCv.candidateId", "candidateId differs from the case", {"expected": ci.candidate_id, "actual": cv.get("candidateId")}))
    cand = h.get("candidate") or {}
    if ci.candidate_id and cand.get("candidateId") != ci.candidate_id:
        out.append(finding(R, "identity_copied", CRIT, "$.hiringEvidencePacket.candidate.candidateId", "candidateId differs from the case", {"expected": ci.candidate_id, "actual": cand.get("candidateId")}))
    for s in cand.get("sources") or []:
        if s not in ci.sources:
            out.append(finding(R, "source_ids_allowed", CRIT, "$.hiringEvidencePacket.candidate.sources", f"sourceId {s!r} is not in the case", {"sourceId": s}))
    role = h.get("role") or {}
    if ci.jd_source_id and role.get("jobDescriptionSource") != ci.jd_source_id:
        out.append(finding(R, "identity_copied", CRIT, "$.hiringEvidencePacket.role.jobDescriptionSource", "jobDescriptionSource differs from the case", {"expected": ci.jd_source_id, "actual": role.get("jobDescriptionSource")}))
    for r in role.get("requirementIds") or []:
        if r not in ci.requirements:
            out.append(finding(R, "requirement_ids_allowed", CRIT, "$.hiringEvidencePacket.role.requirementIds", f"requirementId {r!r} is not in the case", {"requirementId": r}))
    # witness quotes
    for path, c in list(B.cv_claims(bundle)) + list(B.supported_claims(bundle)):
        w = c.get("witness")
        if isinstance(w, str) and w.strip():
            cited = ci.source_texts(c.get("sourceIds") or [])
            pool = cited if cited else [e.get("text", "") for e in ci.sources.values()]
            if not tm.is_substring_of_any(w, pool):
                out.append(finding(R, "witness_in_source", NONCRIT, path + ".witness", "witness quote is not a verbatim passage of the cited sources", {"witness": w[:160], "sourceIds": c.get("sourceIds")}))
    for path, e, ev in B.requirement_evidence(bundle):
        t = ev.get("text")
        if isinstance(t, str) and t.strip() and ev.get("sourceId") in ci.sources:
            if not tm.is_substring_of_any(t, [ci.sources[ev["sourceId"]].get("text", "")]):
                out.append(finding(R, "evidence_text_not_verbatim", NONCRIT, path + ".text", "requirement evidence text is not a verbatim passage of its source", {"text": t[:160], "sourceId": ev.get("sourceId")}, status="UNRESOLVED"))
    return out


# ---------------------------------------------------------------- rule 2
def detect_unsupported_quantification(case, bundle, ctx):
    R = "hrgene.unsupported_quantification"
    ci, lex, out = ctx["index"], ctx["lex"], []
    for path, text, sids, rids, kind in B.supported_side(bundle):
        if not text or kind == "req_notes":
            continue
        src_texts = ci.source_texts(sids)
        if not src_texts:
            continue  # provenance rule already fails a claim without a valid source
        claim_nums = tm.numbers_in(text, lex)
        src_nums = set()
        for t in src_texts:
            src_nums |= tm.numbers_in(t, lex, ignore_years=False)
        missing = sorted(claim_nums - src_nums)
        if missing:
            out.append(finding(R, "numbers_in_cited_sources", CRIT, path, "number(s) not stated by the cited sources: " + ", ".join(missing), {"numbers": missing, "sourceIds": sids, "text": text[:200]}))
        causal = tm.family_hits(text, lex, "causal")
        if causal:
            src_causal = any(tm.family_hits(t, lex, "causal") for t in src_texts)
            if not src_causal:
                terms = sorted({h[0] for hs in causal.values() for h in hs})
                out.append(finding(R, "causal_term_licensed", NONCRIT, path, "causal/comparative wording not present in the cited sources: " + ", ".join(terms), {"terms": terms, "sourceIds": sids, "text": text[:200]}))
    return out


# ---------------------------------------------------------------- rules 3-5 share family licensing
def _family_licensing(rule, group, code, case, bundle, ctx, severity=CRIT, extra=None):
    ci, lex, out = ctx["index"], ctx["lex"], []
    for path, text, sids, rids, kind in B.supported_side(bundle):
        if not text:
            continue
        src_texts = ci.source_texts(sids)
        if not src_texts:
            continue  # provenance rule already fails a claim without a valid source
        claim_f = tm.family_hits(text, lex, group, negation=True, claim_side=True)
        if not claim_f:
            continue
        src_f = {}
        for t in src_texts:
            for fam, hits in tm.family_hits(t, lex, group).items():
                src_f.setdefault(fam, []).extend(hits)
        for fam, hits in claim_f.items():
            if extra and extra(fam, hits, src_texts, out, path, text, sids):
                continue
            if fam not in src_f:
                terms = sorted({h[0] for h in hits})
                out.append(finding(rule, code, severity, path, f"{group} term(s) [{fam}] not licensed by the cited sources: " + ", ".join(terms), {"family": fam, "terms": terms, "sourceIds": sids, "sourceFamilies": sorted(src_f), "text": text[:200]}))
    return out




def _requirement_level_licensing(rule, group, code, case, bundle, ctx, fams=None):
    """A requirement marked `supported` whose own text carries a family term must have that family licensed by the
    sources cited in its evidence entries; otherwise the status itself is an over-claim."""
    ci, lex, out = ctx["index"], ctx["lex"], []
    for path, e in B.requirement_entries(bundle):
        if e.get("status") != "supported":
            continue
        rid = e.get("requirementId")
        rtext = (ci.requirements.get(rid) or {}).get("text", "") or ""
        req_f = tm.family_hits(rtext, lex, group, negation=True, claim_side=True)
        if fams:
            req_f = {k: v for k, v in req_f.items() if k in fams}
        excl = getattr(lex, "requirement_level_exclude", set())
        req_f = {k: [h for h in v if h[0] not in excl] for k, v in req_f.items()}
        req_f = {k: v for k, v in req_f.items() if v}
        if not req_f:
            continue
        sids = [ev.get("sourceId") for ev in (e.get("evidence") or []) if isinstance(ev, dict)]
        src_texts = ci.source_texts(sids)
        if not src_texts:
            continue  # rule 8 (supported_has_evidence) covers the missing-evidence case
        src_f = set()
        for t in src_texts:
            src_f |= set(tm.family_hits(t, lex, group))
        for fam, hits in req_f.items():
            if fam not in src_f:
                terms = sorted({h[0] for h in hits})
                out.append(finding(rule, code, CRIT, path + ".status", f"requirement marked supported but its {group} term(s) [{fam}] ({', '.join(terms)}) are not licensed by the cited sources", {"requirementId": rid, "family": fam, "terms": terms, "sourceIds": sids}))
    return out


def detect_ownership_scope(case, bundle, ctx):
    R = "hrgene.ownership_scope"
    lex, ci = ctx["lex"], ctx["index"]
    out = _family_licensing(R, "ownership", "ownership_family_licensed", case, bundle, ctx)
    # annotate findings whose sources explicitly describe participation (the classic upgrade)
    for f in out:
        src_texts = ci.source_texts(f["witness"].get("sourceIds") or [])
        part = [h[0] for t in src_texts for h in tm.find_terms(t, lex.families["participation"]["PARTICIPATE"])]
        if part:
            f["code"] = "participation_upgraded_to_ownership"
            f["witness"]["participationTermsInSources"] = sorted(set(part))
    out.extend(_requirement_level_licensing(R, "ownership", "requirement_ownership_unlicensed", case, bundle, ctx, fams=["LEAD", "OWN", "MANAGE", "INDEPENDENT", "APPROVE", "END_TO_END"]))
    return out


def detect_deployment_boundary(case, bundle, ctx):
    R = "hrgene.deployment_boundary"
    ci, lex, out = ctx["index"], ctx["lex"], []
    for path, text, sids, rids, kind in B.supported_side(bundle):
        if not text:
            continue
        src_texts = ci.source_texts(sids)
        if not src_texts:
            continue  # provenance rule already fails a claim without a valid source
        claim_f = tm.family_hits(text, lex, "deployment", negation=True)
        if "PRODUCTION" not in claim_f:
            continue
        src_prod = any("PRODUCTION" in tm.family_hits(t, lex, "deployment") for t in src_texts)
        if src_prod:
            continue
        src_nonprod = sorted({h[0] for t in src_texts for h in tm.family_hits(t, lex, "deployment").get("NONPRODUCTION", [])})
        terms = sorted({h[0] for h in claim_f["PRODUCTION"]})
        code = "nonproduction_rewritten_as_production" if src_nonprod else "production_not_stated_by_sources"
        out.append(finding(R, code, CRIT, path, "production/live wording not licensed by the cited sources: " + ", ".join(terms), {"terms": terms, "sourceIds": sids, "nonProductionTermsInSources": src_nonprod, "text": text[:200]}))
    out.extend(_requirement_level_licensing(R, "deployment", "requirement_production_unlicensed", case, bundle, ctx, fams=["PRODUCTION"]))
    return out


def detect_qualification_boundary(case, bundle, ctx):
    R = "hrgene.qualification_boundary"
    ci, lex = ctx["index"], ctx["lex"]

    def years_check(fam, hits, src_texts, out, path, text, sids):
        if fam != "YEARS":
            return False
        cy = tm.years_in(text)
        sy = []
        for t in src_texts:
            sy.extend(tm.years_in(t))
        if cy and (not sy or max(cy) > max(sy)):
            out.append(finding(R, "years_exceed_sources", CRIT, path, f"years of experience {max(cy):g} not supported by the cited sources (sources: {sorted(set(sy))})", {"claimYears": cy, "sourceYears": sy, "sourceIds": sids, "text": text[:200]}))
        return True

    out = _family_licensing(R, "qualification", "qualification_family_licensed", case, bundle, ctx, extra=years_check)
    out.extend(_requirement_level_licensing(R, "qualification", "requirement_qualification_unlicensed", case, bundle, ctx, fams=["SENIORITY", "CERTIFICATION", "DEGREE"]))
    # years asked by the requirement vs years in the cited sources
    ci, lex = ctx["index"], ctx["lex"]
    for path, e in B.requirement_entries(bundle):
        if e.get("status") != "supported":
            continue
        rid = e.get("requirementId")
        ry = tm.years_in((ci.requirements.get(rid) or {}).get("text", "") or "")
        if not ry:
            continue
        sids = [ev.get("sourceId") for ev in (e.get("evidence") or []) if isinstance(ev, dict)]
        src_texts = ci.source_texts(sids)
        if not src_texts:
            continue  # a supported requirement without valid evidence is rule 8's finding (supported_has_evidence)
        sy = []
        for t in src_texts:
            sy.extend(tm.years_in(t))
        if not sy or max(sy) < max(ry):
            out.append(finding(R, "requirement_years_unlicensed", CRIT, path + ".status", f"requirement asks for {max(ry):g} years; cited sources state {sorted(set(sy))}", {"requirementId": rid, "requirementYears": ry, "sourceYears": sy, "sourceIds": sids}))
    return out


# ---------------------------------------------------------------- rule 6
def detect_human_review_boundary(case, bundle, ctx):
    R = "hrgene.human_review_boundary"
    lex, out = ctx["lex"], []
    db = B.hep(bundle).get("decisionBoundary")
    expected = {"employmentDecisionMade": False, "candidateRanked": False, "protectedCharacteristicsInferred": False, "humanReviewRequired": True}
    if not isinstance(db, dict):
        out.append(finding(R, "boundary_flags", CRIT, "$.hiringEvidencePacket.decisionBoundary", "decisionBoundary missing"))
    else:
        for k, v in expected.items():
            if db.get(k) is not v:
                out.append(finding(R, "boundary_flags", CRIT, f"$.hiringEvidencePacket.decisionBoundary.{k}", f"{k} must be {v}", {"actual": db.get(k)}))
        if not (isinstance(db.get("statement"), str) and db["statement"].strip()):
            out.append(finding(R, "boundary_flags", CRIT, "$.hiringEvidencePacket.decisionBoundary.statement", "statement missing"))
    for path, text in B.all_text_fields(bundle):
        if not text:
            continue
        if not B.is_non_assertive_path(path):
            dec = tm.family_hits(text, lex, "decision", negation=True)
            if dec:
                terms = sorted({h[0] for hs in dec.values() for h in hs})
                out.append(finding(R, "no_decision_language", CRIT, path, "employment-decision language: " + ", ".join(terms), {"terms": terms, "text": text[:200]}))
        prot = tm.family_hits(text, lex, "protected", negation=True)
        if prot:
            terms = sorted({h[0] for hs in prot.values() for h in hs})
            out.append(finding(R, "no_protected_characteristics", CRIT, path, "protected-characteristic wording: " + ", ".join(terms), {"terms": terms, "text": text[:200]}))
    return out


# ---------------------------------------------------------------- rule 7
def subjective_source_ids(case_index, lex):
    ids = set()
    for sid, e in case_index.sources.items():
        t = e.get("text", "") or ""
        if tm.family_hits(t, lex, "subjective", negation=True) or tm.family_hits(t, lex, "hearsay"):
            ids.add(sid)
    return ids


def detect_subjective_claim_boundary(case, bundle, ctx):
    R = "hrgene.subjective_claim_boundary"
    ci, lex, out = ctx["index"], ctx["lex"], []
    subj = ctx.get("subjectiveSourceIds")
    if subj is None:
        subj = subjective_source_ids(ci, lex)
    for path, text, sids, rids, kind in B.supported_side(bundle):
        hits = tm.family_hits(text, lex, "subjective", negation=True) if text else {}
        if hits:
            terms = sorted({h[0] for hs in hits.values() for h in hs})
            out.append(finding(R, "subjective_term_on_supported_side", NONCRIT, path, "subjective wording presented as supported: " + ", ".join(terms), {"terms": terms, "text": text[:200]}))
        cited_subj = [s for s in sids if s in subj]
        if cited_subj:
            out.append(finding(R, "subjective_source_cited_as_support", NONCRIT, path, "subjective/hearsay source cited as support: " + ", ".join(cited_subj), {"sourceIds": cited_subj, "text": text[:200]}))
    h = B.hep(bundle)
    routed = {r.get("sourceId") for r in (h.get("interviewSignalRisks") or []) if isinstance(r, dict)}
    other_text = " ".join([c.get("claim", "") + " " + c.get("reason", "") for c in (h.get("unsupportedClaims") or []) if isinstance(c, dict)]
                          + [q.get("question", "") for q in (h.get("followUpQuestions") or []) if isinstance(q, dict)]
                          + [g.get("gap", "") for g in (h.get("missingEvidenceGaps") or []) if isinstance(g, dict)])
    other_nums = tm.numbers_in(other_text, lex)
    for s in sorted(subj):
        if s in routed or s in other_text:
            continue
        stext = ci.sources[s].get("text", "") or ""
        if tm.family_hits(stext, lex, "protected"):
            continue  # protected-characteristic content must be excluded, not routed (rule 6 scans the bundle for it)
        is_subjective = bool(tm.family_hits(stext, lex, "subjective", negation=True))
        if not is_subjective:
            # hearsay-only source: routed when its figure(s) appear in the unsupported / gap / follow-up text
            nums = tm.numbers_in(stext, lex)
            if not nums or nums & other_nums:
                continue
        out.append(finding(R, "subjective_sources_routed", NONCRIT, "$.hiringEvidencePacket.interviewSignalRisks", f"subjective/hearsay source {s} is not routed to interviewSignalRisks / gaps / follow-up", {"sourceId": s}, status="UNRESOLVED"))
    return out


# ---------------------------------------------------------------- rule 8
STATUS_ENUM = ("supported", "partial_evidence", "insufficient_evidence")


def detect_evidence_gap_router(case, bundle, ctx):
    R = "hrgene.evidence_gap_router"
    ci, out = ctx["index"], []
    h = B.hep(bundle)
    seen = {}
    for path, e in B.requirement_entries(bundle):
        rid = e.get("requirementId")
        seen.setdefault(rid, []).append(path)
        if rid not in ci.requirements:
            out.append(finding(R, "requirement_coverage", NONCRIT, path, f"unknown requirementId {rid!r}", {"requirementId": rid}))
        st = e.get("status")
        if st not in STATUS_ENUM:
            out.append(finding(R, "status_enum", NONCRIT, path + ".status", f"status {st!r} is not one of {STATUS_ENUM}", {"status": st}))
        elif st == "supported":
            valid = [ev for ev in (e.get("evidence") or []) if isinstance(ev, dict) and ev.get("sourceId") in ci.sources]
            if not valid:
                out.append(finding(R, "supported_has_evidence", NONCRIT, path, "requirement marked supported without a valid cited evidence entry", {"requirementId": rid}))
        else:
            gaps = [g for g in (h.get("missingEvidenceGaps") or []) if isinstance(g, dict) and g.get("requirementId") == rid]
            fups = [q for q in (h.get("followUpQuestions") or []) if isinstance(q, dict) and q.get("requirementId") == rid]
            missing = [m for m in (e.get("missingEvidence") or []) if isinstance(m, str) and m.strip()]
            if not (gaps or fups or missing):
                out.append(finding(R, "gap_and_followup_for_unmet", NONCRIT, path, f"requirement {rid} is {st} but has no gap, missingEvidence or follow-up question", {"requirementId": rid}, status="UNRESOLVED"))
    for rid in ci.requirements:
        if rid not in seen:
            out.append(finding(R, "requirement_coverage", NONCRIT, "$.hiringEvidencePacket.requirementEvidenceMap", f"requirement {rid} is not covered", {"requirementId": rid}))
    for rid, paths in seen.items():
        if len(paths) > 1:
            out.append(finding(R, "requirement_coverage", NONCRIT, paths[1], f"requirement {rid} appears {len(paths)} times", {"requirementId": rid}))
    for i, g in enumerate(h.get("missingEvidenceGaps") or []):
        if isinstance(g, dict) and g.get("requirementId") not in ci.requirements:
            out.append(finding(R, "gap_requirement_id_valid", NONCRIT, f"$.hiringEvidencePacket.missingEvidenceGaps[{i}]", f"gap cites unknown requirementId {g.get('requirementId')!r}", {"requirementId": g.get("requirementId")}))
    for i, q in enumerate(h.get("followUpQuestions") or []):
        if isinstance(q, dict) and q.get("requirementId") not in ci.requirements:
            out.append(finding(R, "gap_requirement_id_valid", NONCRIT, f"$.hiringEvidencePacket.followUpQuestions[{i}]", f"follow-up cites unknown requirementId {q.get('requirementId')!r}", {"requirementId": q.get("requirementId")}))
    return out


# ---------------------------------------------------------------- rule 9
def detect_paired_review_bundle_completeness(case, bundle, ctx):
    R = "hrgene.paired_review_bundle_completeness"
    from . import schema_lite
    out = []
    errors = schema_lite.validate(bundle, ctx["schema"])
    if errors:
        out.append(finding(R, "schema_valid", CRIT, errors[0].split(":")[0], f"{len(errors)} schema error(s); first: {errors[0]}", {"errors": errors[:8]}))
    lang = (bundle.get("optimizedCv") or {}).get("language")
    if ctx["index"].language and lang != ctx["index"].language:
        out.append(finding(R, "language_matches_case", CRIT, "$.optimizedCv.language", f"language {lang!r} differs from the case language {ctx['index'].language!r}", {"actual": lang}))
    return out


DETECTORS = [
    ("hrgene.claim_provenance", detect_claim_provenance),
    ("hrgene.unsupported_quantification", detect_unsupported_quantification),
    ("hrgene.ownership_scope", detect_ownership_scope),
    ("hrgene.deployment_boundary", detect_deployment_boundary),
    ("hrgene.qualification_boundary", detect_qualification_boundary),
    ("hrgene.human_review_boundary", detect_human_review_boundary),
    ("hrgene.subjective_claim_boundary", detect_subjective_claim_boundary),
    ("hrgene.evidence_gap_router", detect_evidence_gap_router),
    ("hrgene.paired_review_bundle_completeness", detect_paired_review_bundle_completeness),
]
