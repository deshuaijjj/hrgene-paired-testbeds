"""Traversal helpers for PairedReviewBundle v2 model outputs."""
CV_SECTIONS = ("professionalSummary", "experienceHighlights", "projectsAndWorkSamples", "skills")


def get(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def lift_string_items(bundle):
    """Deep copy in which bare strings inside the claim lists (optimizedCv sections, hiringEvidencePacket.supportedClaims)
    are lifted into claim objects with no sources. Some models (gpt-oss:20b under JSON mode) write CV bullets as plain
    strings; lifting lets every rule read them (a bullet without a source is a provenance failure, an over-claim inside it
    counts as a fallen trap) instead of silently ignoring them. Schema validity is judged on the raw output, not the lift."""
    import copy
    b = copy.deepcopy(bundle)
    if not isinstance(b, dict):
        return b
    cv = b.get("optimizedCv")
    if isinstance(cv, dict):
        for sec in CV_SECTIONS:
            items = cv.get(sec)
            if isinstance(items, list):
                cv[sec] = [{"claimId": "", "text": c, "sourceIds": [], "requirementIds": [], "supportBoundary": "supported", "witness": ""} if isinstance(c, str) else c for c in items]
    h = b.get("hiringEvidencePacket")
    if isinstance(h, dict) and isinstance(h.get("supportedClaims"), list):
        h["supportedClaims"] = [{"claim": c, "supportingRequirementIds": [], "sourceIds": [], "witness": ""} if isinstance(c, str) else c for c in h["supportedClaims"]]
    return b


def cv_claims(bundle):
    """Yield (path, claim_dict) for every optimizedCv claim."""
    cv = get(bundle, "optimizedCv", default={}) or {}
    for sec in CV_SECTIONS:
        items = cv.get(sec) or []
        if isinstance(items, list):
            for i, c in enumerate(items):
                if isinstance(c, dict):
                    yield f"$.optimizedCv.{sec}[{i}]", c


def hep(bundle):
    return get(bundle, "hiringEvidencePacket", default={}) or {}


def supported_claims(bundle):
    for i, c in enumerate(hep(bundle).get("supportedClaims") or []):
        if isinstance(c, dict):
            yield f"$.hiringEvidencePacket.supportedClaims[{i}]", c


def requirement_entries(bundle):
    for i, e in enumerate(hep(bundle).get("requirementEvidenceMap") or []):
        if isinstance(e, dict):
            yield f"$.hiringEvidencePacket.requirementEvidenceMap[{i}]", e


def requirement_evidence(bundle):
    """Yield (path, entry, evidence_item) for every evidence item inside requirementEvidenceMap."""
    for p, e in requirement_entries(bundle):
        for j, ev in enumerate(e.get("evidence") or []):
            if isinstance(ev, dict):
                yield f"{p}.evidence[{j}]", e, ev


def supported_side(bundle):
    """Every place where the model asserts something as supported.
    Yields (path, text, sourceIds, requirementIds, kind)."""
    for p, c in cv_claims(bundle):
        yield p, c.get("text", "") or "", list(c.get("sourceIds") or []), list(c.get("requirementIds") or []), "cv"
    for p, c in supported_claims(bundle):
        yield p, c.get("claim", "") or "", list(c.get("sourceIds") or []), list(c.get("supportingRequirementIds") or []), "supported"
    for p, e, ev in requirement_evidence(bundle):
        if e.get("status") in ("supported", "partial_evidence"):
            sids = [ev.get("sourceId")] if ev.get("sourceId") else []
            rids = [e.get("requirementId")] if e.get("requirementId") else []
            yield p, ev.get("text", "") or "", sids, rids, "req_evidence"
            if isinstance(ev.get("notes"), str) and ev["notes"].strip():
                yield p + ".notes", ev["notes"], sids, rids, "req_notes"


def all_text_fields(bundle):
    """Yield (path, text) for every free-text field a reader would see (excluding identifiers)."""
    cv = get(bundle, "optimizedCv", default={}) or {}
    if isinstance(cv.get("targetRoleTitle"), str):
        yield "$.optimizedCv.targetRoleTitle", cv["targetRoleTitle"]
    if isinstance(cv.get("evidenceBoundary"), str):
        yield "$.optimizedCv.evidenceBoundary", cv["evidenceBoundary"]
    for p, c in cv_claims(bundle):
        yield p + ".text", c.get("text", "") or ""
    h = hep(bundle)
    db = h.get("decisionBoundary") or {}
    if isinstance(db.get("statement"), str):
        yield "$.hiringEvidencePacket.decisionBoundary.statement", db["statement"]
    for p, e in requirement_entries(bundle):
        for j, ev in enumerate(e.get("evidence") or []):
            if isinstance(ev, dict):
                yield f"{p}.evidence[{j}].text", ev.get("text", "") or ""
                yield f"{p}.evidence[{j}].notes", ev.get("notes", "") or ""
        for j, m in enumerate(e.get("missingEvidence") or []):
            if isinstance(m, str):
                yield f"{p}.missingEvidence[{j}]", m
    for p, c in supported_claims(bundle):
        yield p + ".claim", c.get("claim", "") or ""
    for i, c in enumerate(h.get("unsupportedClaims") or []):
        if isinstance(c, dict):
            for k in ("claim", "reason", "requiredFollowUp"):
                if isinstance(c.get(k), str):
                    yield f"$.hiringEvidencePacket.unsupportedClaims[{i}].{k}", c[k]
    for i, g in enumerate(h.get("missingEvidenceGaps") or []):
        if isinstance(g, dict) and isinstance(g.get("gap"), str):
            yield f"$.hiringEvidencePacket.missingEvidenceGaps[{i}].gap", g["gap"]
    for i, r in enumerate(h.get("interviewSignalRisks") or []):
        if isinstance(r, dict):
            for k in ("text", "signalType", "jobRelatedBoundary", "recommendedHandling"):
                if isinstance(r.get(k), str):
                    yield f"$.hiringEvidencePacket.interviewSignalRisks[{i}].{k}", r[k]
    for i, q in enumerate(h.get("followUpQuestions") or []):
        if isinstance(q, dict):
            for k in ("question", "evidenceTarget"):
                if isinstance(q.get(k), str):
                    yield f"$.hiringEvidencePacket.followUpQuestions[{i}].{k}", q[k]
    for i, s in enumerate(h.get("humanReviewChecklist") or []):
        if isinstance(s, str):
            yield f"$.hiringEvidencePacket.humanReviewChecklist[{i}]", s
    if isinstance(h.get("auditSummary"), str):
        yield "$.hiringEvidencePacket.auditSummary", h["auditSummary"]
    for i, s in enumerate(h.get("limitations") or []):
        if isinstance(s, str):
            yield f"$.hiringEvidencePacket.limitations[{i}]", s


def resolve_path(bundle, path):
    """Return (container, key) for a '$.a.b[3].c' path so callers can mutate."""
    import re
    tokens = re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", path)
    cur = bundle
    parent, key = None, None
    for name, idx in tokens:
        parent, key = cur, (name if name else int(idx))
        cur = cur[key]
    return parent, key


_NON_ASSERTIVE = ("$.hiringEvidencePacket.unsupportedClaims", "$.hiringEvidencePacket.missingEvidenceGaps",
                  "$.hiringEvidencePacket.followUpQuestions", "$.hiringEvidencePacket.interviewSignalRisks")


def is_non_assertive_path(path):
    """Fields that record what is NOT established (unsupported claims, gaps, questions, risks)."""
    return path.startswith(_NON_ASSERTIVE)
