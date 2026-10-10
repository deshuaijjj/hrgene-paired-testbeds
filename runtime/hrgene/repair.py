"""Bounded deterministic repair (rho).

Only removes, moves, relabels or resets content; never adds a factual statement. Every change is logged.
Apply to a validation result; then re-validate. Regeneration (<=1) is handled by pipeline.py."""
import copy
import re

from . import bundle as B

NEUTRAL_STATEMENT = ("This packet supports qualified human review. It makes no employment decision, ranking or "
                     "recommendation and infers no protected characteristics.")
NEUTRAL_SUMMARY = ("This packet lists the evidence, gaps and follow-up questions found in the provided materials. "
                   "It makes no employment decision, ranking or recommendation; qualified human review is required "
                   "before any decision.")
NEUTRAL_BOUNDARY = ("Only statements traceable to the cited sources are presented as supported; everything else is "
                    "recorded as unsupported, a gap or a follow-up question.")

REASONS = {
    "hrgene.claim_provenance": ("No provided source supports this statement.", "Ask the candidate for a document that states this."),
    "hrgene.unsupported_quantification": ("The cited sources do not state this figure or outcome.", "Ask for the metric definition, baseline, observation window and any concurrent changes."),
    "hrgene.ownership_scope": ("The cited sources do not establish this level of ownership or authority.", "Ask which decisions, resources and approvals the candidate personally controlled."),
    "hrgene.deployment_boundary": ("The cited sources describe a non-production environment or do not state production deployment.", "Ask about the operating environment, release permissions, go-live confirmation and run-time responsibilities."),
    "hrgene.qualification_boundary": ("The cited sources do not establish this qualification, seniority or duration.", "Ask for the specific credential, its issuer and dates, and the scope of the experience."),
    "hrgene.human_review_boundary": ("Fit judgements and protected characteristics are outside the evidence boundary.", "None; removed from the packet."),
}

_ITEM_PATH = re.compile(r"^(\$\.(?:optimizedCv\.(?:professionalSummary|experienceHighlights|projectsAndWorkSamples|skills)|hiringEvidencePacket\.(?:supportedClaims|unsupportedClaims|missingEvidenceGaps|interviewSignalRisks|followUpQuestions|humanReviewChecklist|limitations))\[\d+\])")
_EVID_PATH = re.compile(r"^(\$\.hiringEvidencePacket\.requirementEvidenceMap\[\d+\])\.evidence\[(\d+)\]")
_REQ_PATH = re.compile(r"^(\$\.hiringEvidencePacket\.requirementEvidenceMap\[\d+\])")


def _resolve(bundle, path):
    try:
        parent, key = B.resolve_path(bundle, path)
        return parent[key]
    except Exception:  # noqa: BLE001
        return None


class Repairer:
    def __init__(self, ruleset, case):
        self.rs = ruleset
        self.case = case
        self.log = []

    def _log(self, rule, code, action, path, detail=""):
        self.log.append({"rule": rule, "code": code, "action": action, "path": path, "detail": detail})

    def repair(self, bundle, findings):
        b = B.lift_string_items(bundle)   # deep copy; bare-string claims lifted so finding paths resolve to objects
        if not isinstance(b, dict):
            return b, self.log
        ci_sources = {e["sourceId"] for e in (self.case.get("candidate", {}).get("evidence") or []) if isinstance(e, dict) and e.get("sourceId")}
        req_ids = [r["requirementId"] for r in (self.case.get("roleContext", {}).get("requirements") or []) if isinstance(r, dict)]
        route, delete, to_risk, drop_evidence, drop_src = {}, {}, {}, {}, {}
        scalar_reset, flag_reset, struct_fix, conform = set(), False, False, False

        for f in findings:
            if f["status"] != "FAIL":
                if f["code"] == "gap_and_followup_for_unmet":
                    struct_fix = True
                continue
            rule, code, path = f["rule"], f["code"], f["path"]
            m_ev = _EVID_PATH.match(path)
            m_item = _ITEM_PATH.match(path)
            if code in ("requirement_ownership_unlicensed", "requirement_production_unlicensed", "requirement_qualification_unlicensed", "requirement_years_unlicensed"):
                m_req = _REQ_PATH.match(path)
                entry = _resolve(b, m_req.group(1)) if m_req else None
                if isinstance(entry, dict) and entry.get("status") == "supported":
                    entry["status"] = "partial_evidence"
                    entry.setdefault("missingEvidence", [])
                    if isinstance(entry["missingEvidence"], list):
                        entry["missingEvidence"].append("The cited sources do not establish the requirement's " + f.get("witness", {}).get("family", "").lower().replace("_", " ") + " element; verify before treating it as met.")
                    self._log(rule, code, "downgrade_requirement_status", m_req.group(1), f"{entry.get('requirementId')}: supported -> partial_evidence")
                continue
            if rule == "hrgene.paired_review_bundle_completeness":
                conform = True
                continue
            if rule == "hrgene.evidence_gap_router":
                struct_fix = True
                continue
            if rule == "hrgene.human_review_boundary":
                if code == "boundary_flags":
                    flag_reset = True
                elif m_ev:
                    ev = _resolve(b, m_ev.group(0))
                    if ev is not None:
                        drop_evidence[id(ev)] = (m_ev.group(1), ev, rule, code)
                elif m_item:
                    obj = _resolve(b, m_item.group(1))
                    if obj is not None:
                        delete[id(obj)] = (m_item.group(1), rule, code)
                else:
                    scalar_reset.add(path)
                continue
            # rules 1-5, 7: claim-level
            if m_ev:
                ev = _resolve(b, m_ev.group(0))
                if ev is None:
                    continue
                if code == "source_ids_allowed" or code == "witness_in_source":
                    drop_evidence[id(ev)] = (m_ev.group(1), ev, rule, code)
                elif rule == "hrgene.subjective_claim_boundary":
                    drop_evidence[id(ev)] = (m_ev.group(1), ev, rule, code)
                    to_risk[id(ev)] = (ev, ev.get("sourceId"), ev.get("text", ""))
                else:
                    drop_evidence[id(ev)] = (m_ev.group(1), ev, rule, code)
                continue
            if m_item:
                obj = _resolve(b, m_item.group(1))
                if obj is None:
                    continue
                if code == "witness_in_source":
                    obj["witness"] = ""
                    self._log(rule, code, "clear_witness", m_item.group(1))
                    continue
                if code in ("requirement_ownership_unlicensed", "requirement_production_unlicensed", "requirement_qualification_unlicensed", "requirement_years_unlicensed"):
                    continue
                if code == "source_ids_allowed":
                    drop_src.setdefault(id(obj), (obj, set()))[1].add(f["witness"].get("sourceId"))
                    if m_item.group(1).startswith("$.hiringEvidencePacket.interviewSignalRisks"):
                        delete[id(obj)] = (m_item.group(1), rule, code)
                elif code == "requirement_ids_allowed":
                    bad = f["witness"].get("requirementId")
                    for k in ("requirementIds", "supportingRequirementIds"):
                        if isinstance(obj.get(k), list) and bad in obj[k]:
                            obj[k] = [x for x in obj[k] if x != bad]
                            self._log(rule, code, "drop_invalid_requirement_ids", m_item.group(1), bad)
                elif rule == "hrgene.subjective_claim_boundary":
                    sid = (f["witness"].get("sourceIds") or obj.get("sourceIds") or [""])[0]
                    to_risk[id(obj)] = (obj, sid, obj.get("text") or obj.get("claim") or "")
                    delete[id(obj)] = (m_item.group(1), rule, code)
                else:
                    reason, fup = REASONS.get(rule, REASONS["hrgene.claim_provenance"])
                    route[id(obj)] = (obj, m_item.group(1), rule, code, reason, fup)
                continue
            # non-item paths
            if code == "identity_copied":
                self._copy_identity(b)
            elif code == "requirement_ids_allowed" and path.endswith("role.requirementIds"):
                role = B.hep(b).get("role") or {}
                role["requirementIds"] = [r for r in (role.get("requirementIds") or []) if r in req_ids]
                self._log(rule, code, "drop_invalid_requirement_ids", path)
            elif code == "source_ids_allowed" and path.endswith("candidate.sources"):
                cand = B.hep(b).get("candidate") or {}
                cand["sources"] = [s for s in (cand.get("sources") or []) if s in ci_sources]
                self._log(rule, code, "drop_invalid_source_ids", path)

        # ---- apply drop_src (claims whose invalid ids are removed; route if nothing left)
        for _, (obj, bad) in drop_src.items():
            if isinstance(obj.get("sourceIds"), list):
                obj["sourceIds"] = [s for s in obj["sourceIds"] if s not in bad and s in ci_sources]
                self._log("hrgene.claim_provenance", "source_ids_allowed", "drop_invalid_source_ids", "", ",".join(sorted(x for x in bad if x)))
                if not obj["sourceIds"] and id(obj) not in delete and id(obj) not in route:
                    reason, fup = REASONS["hrgene.claim_provenance"]
                    route[id(obj)] = (obj, "", "hrgene.claim_provenance", "claim_has_source", reason, fup)

        hep = B.hep(b)
        hep.setdefault("unsupportedClaims", [])
        hep.setdefault("interviewSignalRisks", [])
        existing_unsupported = {c.get("claim") for c in hep["unsupportedClaims"] if isinstance(c, dict)}

        def filter_list(lst, section_path):
            kept = []
            for obj in lst:
                oid = id(obj)
                if oid in route:
                    _, p, rule, code, reason, fup = route[oid]
                    text = obj.get("text") or obj.get("claim") or ""
                    if text and text not in existing_unsupported:
                        hep["unsupportedClaims"].append({"claim": text, "reason": reason, "requiredFollowUp": fup})
                        existing_unsupported.add(text)
                    self._log(rule, code, "route_claim_to_unsupported", p or section_path, text[:120])
                    continue
                if oid in to_risk:
                    _, sid, text = to_risk[oid]
                    hep["interviewSignalRisks"].append({"sourceId": sid or "", "text": text, "signalType": "subjective_feedback",
                                                        "jobRelatedBoundary": "Not tied to an observable, job-related event in the materials.",
                                                        "severity": "medium", "recommendedHandling": "Verify in a structured interview with a concrete example before any use."})
                    self._log("hrgene.subjective_claim_boundary", "subjective", "move_claim_to_interview_signal_risk", section_path, text[:120])
                    continue
                if oid in delete:
                    p, rule, code = delete[oid]
                    self._log(rule, code, "remove_item", p, (obj.get("text") or obj.get("claim") or str(obj))[:120] if isinstance(obj, dict) else str(obj)[:120])
                    continue
                kept.append(obj)
            return kept

        cv = b.get("optimizedCv") or {}
        for sec in B.CV_SECTIONS:
            if isinstance(cv.get(sec), list):
                cv[sec] = filter_list(cv[sec], f"$.optimizedCv.{sec}")
        for sec in ("supportedClaims", "unsupportedClaims", "missingEvidenceGaps", "interviewSignalRisks", "followUpQuestions", "humanReviewChecklist", "limitations"):
            if isinstance(hep.get(sec), list):
                hep[sec] = filter_list(hep[sec], f"$.hiringEvidencePacket.{sec}")

        # ---- requirement evidence items
        for entry in hep.get("requirementEvidenceMap") or []:
            if not isinstance(entry, dict) or not isinstance(entry.get("evidence"), list):
                continue
            kept = []
            for ev in entry["evidence"]:
                if id(ev) in drop_evidence:
                    p, _, rule, code = drop_evidence[id(ev)]
                    self._log(rule, code, "remove_evidence_item", p, (ev.get("text") or "")[:120])
                    if id(ev) in to_risk:
                        _, sid, text = to_risk[id(ev)]
                        hep["interviewSignalRisks"].append({"sourceId": sid or "", "text": text, "signalType": "subjective_feedback",
                                                            "jobRelatedBoundary": "Not tied to an observable, job-related event in the materials.",
                                                            "severity": "medium", "recommendedHandling": "Verify in a structured interview with a concrete example before any use."})
                    continue
                kept.append(ev)
            if len(kept) < len(entry["evidence"]):
                entry["evidence"] = kept
                valid = [ev for ev in kept if isinstance(ev, dict) and ev.get("sourceId") in ci_sources]
                if entry.get("status") == "supported" and not valid:
                    entry["status"] = "partial_evidence"
                    entry.setdefault("missingEvidence", [])
                    if isinstance(entry["missingEvidence"], list):
                        entry["missingEvidence"].append("Cited evidence was removed by the validator; the requirement is not established by the remaining sources.")
                    self._log("hrgene.qualification_boundary", "downgrade", "downgrade_requirement_status", "", entry.get("requirementId", ""))

        # ---- scalar resets for decision / protected wording
        for path in sorted(scalar_reset):
            if path.endswith("auditSummary"):
                hep["auditSummary"] = NEUTRAL_SUMMARY
            elif path.endswith("evidenceBoundary"):
                cv["evidenceBoundary"] = NEUTRAL_BOUNDARY
            elif path.endswith("decisionBoundary.statement"):
                hep.setdefault("decisionBoundary", {})["statement"] = NEUTRAL_STATEMENT
            elif path.endswith("targetRoleTitle"):
                cv["targetRoleTitle"] = (self.case.get("roleContext") or {}).get("roleTitle", "")
            elif path.endswith(".notes"):
                obj = _resolve(b, path[: -len(".notes")])
                if isinstance(obj, dict):
                    obj["notes"] = ""
            elif ".missingEvidence[" in path:
                m = re.match(r"^(.*)\.missingEvidence\[(\d+)\]$", path)
                if m:
                    entry = _resolve(b, m.group(1))
                    if isinstance(entry, dict) and isinstance(entry.get("missingEvidence"), list):
                        idx = int(m.group(2))
                        if idx < len(entry["missingEvidence"]):
                            entry["missingEvidence"].pop(idx)
            self._log("hrgene.human_review_boundary", "text", "replace_text_field", path)

        if flag_reset:
            db = hep.setdefault("decisionBoundary", {})
            db.update({"employmentDecisionMade": False, "candidateRanked": False, "protectedCharacteristicsInferred": False, "humanReviewRequired": True})
            if not (isinstance(db.get("statement"), str) and db["statement"].strip()):
                db["statement"] = NEUTRAL_STATEMENT
            self._log("hrgene.human_review_boundary", "boundary_flags", "reset_boundary_flags", "$.hiringEvidencePacket.decisionBoundary")

        if struct_fix:
            self._fix_requirements(b, req_ids, ci_sources)
        if conform:
            self._conform(b)
        return b, self.log

    # ------------------------------------------------------------------
    def _copy_identity(self, b):
        cv = b.setdefault("optimizedCv", {})
        hep = b.setdefault("hiringEvidencePacket", {})
        cid = (self.case.get("candidate") or {}).get("candidateId")
        jd = self.case.get("jobDescriptionSourceId")
        if cid:
            cv["candidateId"] = cid
            hep.setdefault("candidate", {})["candidateId"] = cid
        if jd:
            hep.setdefault("role", {})["jobDescriptionSource"] = jd
        self._log("hrgene.claim_provenance", "identity_copied", "copy_identity_from_case", "$")

    def _fix_requirements(self, b, req_ids, ci_sources):
        hep = B.hep(b)
        rem = hep.get("requirementEvidenceMap")
        if not isinstance(rem, list):
            rem = hep["requirementEvidenceMap"] = []
        seen, kept = set(), []
        for e in rem:
            if not isinstance(e, dict):
                continue
            rid = e.get("requirementId")
            if rid not in req_ids or rid in seen:
                self._log("hrgene.evidence_gap_router", "requirement_coverage", "remove_item", "$.hiringEvidencePacket.requirementEvidenceMap", str(rid))
                continue
            seen.add(rid)
            if e.get("status") not in ("supported", "partial_evidence", "insufficient_evidence"):
                self._log("hrgene.evidence_gap_router", "status_enum", "normalise_unknown_status", "$.hiringEvidencePacket.requirementEvidenceMap", f"{rid}: {e.get('status')!r} -> insufficient_evidence")
                e["status"] = "insufficient_evidence"
            if e.get("status") == "supported":
                valid = [ev for ev in (e.get("evidence") or []) if isinstance(ev, dict) and ev.get("sourceId") in ci_sources]
                if not valid:
                    e["status"] = "insufficient_evidence"
                    self._log("hrgene.evidence_gap_router", "supported_has_evidence", "downgrade_requirement_status", "$.hiringEvidencePacket.requirementEvidenceMap", f"{rid}: supported -> insufficient_evidence")
            if not isinstance(e.get("evidence"), list):
                e["evidence"] = []
            if not isinstance(e.get("missingEvidence"), list):
                e["missingEvidence"] = []
            kept.append(e)
        for rid in req_ids:
            if rid not in seen:
                kept.append({"requirementId": rid, "status": "insufficient_evidence", "evidence": [], "missingEvidence": ["No cited evidence was located for this requirement."]})
                self._log("hrgene.evidence_gap_router", "requirement_coverage", "add_missing_requirement_entries", "$.hiringEvidencePacket.requirementEvidenceMap", rid)
        kept.sort(key=lambda e: req_ids.index(e["requirementId"]))
        hep["requirementEvidenceMap"] = kept
        gaps = hep.setdefault("missingEvidenceGaps", [])
        fups = hep.setdefault("followUpQuestions", [])
        gaps[:] = [g for g in gaps if isinstance(g, dict) and g.get("requirementId") in req_ids]
        fups[:] = [q for q in fups if isinstance(q, dict) and q.get("requirementId") in req_ids]
        for e in kept:
            rid = e["requirementId"]
            if e["status"] == "supported":
                continue
            has = any(g.get("requirementId") == rid for g in gaps) or any(q.get("requirementId") == rid for q in fups) or any(isinstance(m, str) and m.strip() for m in e["missingEvidence"])
            if not has:
                fups.append({"questionId": f"fq_{rid[4:]}_validator", "requirementId": rid, "question": "Which documents, dates and observable outcomes can you provide for this requirement?", "evidenceTarget": "A source that establishes the requirement."})
                self._log("hrgene.evidence_gap_router", "gap_and_followup_for_unmet", "add_gap_and_followup_for_unmet", "$.hiringEvidencePacket.followUpQuestions", rid)

    def _conform(self, b):
        """Fill required keys with typed defaults and drop unknown keys, following the v2 schema shape."""
        lang = self.case.get("language") or "en"
        cid = (self.case.get("candidate") or {}).get("candidateId", "")
        jd = self.case.get("jobDescriptionSourceId", "")
        b["schemaVersion"] = "jam.hrgene_paired_review_bundle.model_output.v2"
        cv = b.get("optimizedCv") if isinstance(b.get("optimizedCv"), dict) else {}
        b["optimizedCv"] = cv
        cv_keys = {"language": lang, "candidateId": cid, "targetRoleTitle": (self.case.get("roleContext") or {}).get("roleTitle", ""), "evidenceBoundary": NEUTRAL_BOUNDARY}
        for k, v in cv_keys.items():
            if not isinstance(cv.get(k), str):
                cv[k] = v
        if cv["language"] not in ("en", "zh-CN"):
            cv["language"] = lang
        for sec in B.CV_SECTIONS:
            items = cv.get(sec) if isinstance(cv.get(sec), list) else []
            cv[sec] = [self._conform_claim(c) for c in items if isinstance(c, dict)]
        for k in list(cv.keys()):
            if k not in cv_keys and k not in B.CV_SECTIONS:
                cv.pop(k)
        hep = b.get("hiringEvidencePacket") if isinstance(b.get("hiringEvidencePacket"), dict) else {}
        b["hiringEvidencePacket"] = hep
        db = hep.get("decisionBoundary") if isinstance(hep.get("decisionBoundary"), dict) else {}
        hep["decisionBoundary"] = {"employmentDecisionMade": False, "candidateRanked": False, "protectedCharacteristicsInferred": False, "humanReviewRequired": True,
                                   "statement": db.get("statement") if isinstance(db.get("statement"), str) and db.get("statement").strip() else NEUTRAL_STATEMENT}
        role = hep.get("role") if isinstance(hep.get("role"), dict) else {}
        hep["role"] = {"roleTitle": role.get("roleTitle") if isinstance(role.get("roleTitle"), str) else cv_keys["targetRoleTitle"],
                       "jobDescriptionSource": jd or (role.get("jobDescriptionSource") if isinstance(role.get("jobDescriptionSource"), str) else ""),
                       "requirementIds": [r for r in (role.get("requirementIds") or []) if isinstance(r, str)]}
        cand = hep.get("candidate") if isinstance(hep.get("candidate"), dict) else {}
        hep["candidate"] = {"candidateId": cid or (cand.get("candidateId") if isinstance(cand.get("candidateId"), str) else ""),
                            "sources": [s for s in (cand.get("sources") or []) if isinstance(s, str)]}
        strength = ("low", "medium", "high")
        rem = []
        for e in (hep.get("requirementEvidenceMap") or []):
            if not isinstance(e, dict):
                continue
            evs = []
            for ev in (e.get("evidence") or []):
                if isinstance(ev, dict):
                    evs.append({"sourceId": str(ev.get("sourceId", "")), "text": str(ev.get("text", "")), "evidenceStrength": ev.get("evidenceStrength") if ev.get("evidenceStrength") in strength else "low", "notes": str(ev.get("notes", ""))})
            rem.append({"requirementId": str(e.get("requirementId", "")), "status": e.get("status") if e.get("status") in ("supported", "partial_evidence", "insufficient_evidence") else "insufficient_evidence",
                        "evidence": evs, "missingEvidence": [m for m in (e.get("missingEvidence") or []) if isinstance(m, str)]})
        hep["requirementEvidenceMap"] = rem
        hep["supportedClaims"] = [{"claim": str(c.get("claim", "")), "supportingRequirementIds": [r for r in (c.get("supportingRequirementIds") or []) if isinstance(r, str)],
                                   "sourceIds": [s for s in (c.get("sourceIds") or []) if isinstance(s, str)], "evidenceStrength": c.get("evidenceStrength") if c.get("evidenceStrength") in strength else "low",
                                   "witness": str(c.get("witness", ""))} for c in (hep.get("supportedClaims") or []) if isinstance(c, dict)]
        hep["unsupportedClaims"] = [{"claim": str(c.get("claim", "")), "reason": str(c.get("reason", "")), "requiredFollowUp": str(c.get("requiredFollowUp", ""))} for c in (hep.get("unsupportedClaims") or []) if isinstance(c, dict)]
        hep["missingEvidenceGaps"] = [{"gapId": str(g.get("gapId", f"gap_{i}")), "requirementId": str(g.get("requirementId", "")), "severity": g.get("severity") if g.get("severity") in strength else "medium", "gap": str(g.get("gap", ""))} for i, g in enumerate(hep.get("missingEvidenceGaps") or []) if isinstance(g, dict)]
        hep["interviewSignalRisks"] = [{"sourceId": str(r.get("sourceId", "")), "text": str(r.get("text", "")), "signalType": str(r.get("signalType", "")), "jobRelatedBoundary": str(r.get("jobRelatedBoundary", "")), "severity": r.get("severity") if r.get("severity") in strength else "medium", "recommendedHandling": str(r.get("recommendedHandling", ""))} for r in (hep.get("interviewSignalRisks") or []) if isinstance(r, dict)]
        hep["followUpQuestions"] = [{"questionId": str(q.get("questionId", f"fq_{i}")), "requirementId": str(q.get("requirementId", "")), "question": str(q.get("question", "")), "evidenceTarget": str(q.get("evidenceTarget", ""))} for i, q in enumerate(hep.get("followUpQuestions") or []) if isinstance(q, dict)]
        hep["humanReviewChecklist"] = [s for s in (hep.get("humanReviewChecklist") or []) if isinstance(s, str)]
        hep["auditSummary"] = hep.get("auditSummary") if isinstance(hep.get("auditSummary"), str) else ""
        hep["limitations"] = [s for s in (hep.get("limitations") or []) if isinstance(s, str)]
        for k in list(hep.keys()):
            if k not in ("decisionBoundary", "role", "candidate", "requirementEvidenceMap", "supportedClaims", "unsupportedClaims", "missingEvidenceGaps", "interviewSignalRisks", "followUpQuestions", "humanReviewChecklist", "auditSummary", "limitations"):
                hep.pop(k)
        for k in list(b.keys()):
            if k not in ("schemaVersion", "optimizedCv", "hiringEvidencePacket"):
                b.pop(k)
        self._log("hrgene.paired_review_bundle_completeness", "schema_valid", "conform_to_schema", "$")

    def _conform_claim(self, c):
        return {"claimId": str(c.get("claimId", "")), "text": str(c.get("text", "")), "sourceIds": [s for s in (c.get("sourceIds") or []) if isinstance(s, str)],
                "requirementIds": [r for r in (c.get("requirementIds") or []) if isinstance(r, str)],
                "supportBoundary": c.get("supportBoundary") if c.get("supportBoundary") in ("supported", "partial_evidence") else "partial_evidence",
                "witness": str(c.get("witness", ""))}
