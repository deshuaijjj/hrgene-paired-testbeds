#!/usr/bin/env python3
"""Content-blind redaction baselines for C4 (POST HOC, exploratory).

Question: how far could a CONTENT-BLIND transform of the frozen C2 bundles push gold trap failure down, and at what
cost, compared with C4? C4 is a deterministic post-processing pass over frozen C2 output (validate, one bounded repair,
at most one regeneration). Its repair actions fall into three groups: supported-side claims are relabelled into
unsupportedClaims; requirement-evidence items and protected-characteristic / decision-language items are deleted or
replaced (decision-boundary fields reset); subjective content is moved into interviewSignalRisks. A reviewer can object
that part of the improvement is what any blind redactor would achieve. This script measures blind baselines.

Transform families. Every transform picks WHAT to change only by structural position, a status enum value and a seed.
None reads the gold file, trap signatures, lexicons, validator findings or the text of any item.
  S(p, mode)  move ("relabel": append the text to unsupportedClaims) or delete a fraction p of the supported-side items
              (optimizedCv sections, supportedClaims, evidence items of supported / partial_evidence requirement entries).
  R(q)        set a fraction q of the requirementEvidenceMap entries whose status is "supported" to R_TARGET.
  X(r)        reset the decisionBoundary flags to the values the frozen repairer's flag reset writes, and
              decisionBoundary.statement / auditSummary / optimizedCv.evidenceBoundary to the repairer's constant neutral
              strings (read from runtime/hrgene/repair.py, never copied here); delete a fraction r of the items of
              interviewSignalRisks, humanReviewChecklist and limitations (r = 0 applies only the resets).

Source-type policies (POST HOC, designed on 2026-09-23 in response to a reviewer question: can a heuristic that only
looks at source types approach C4?). Every bait source of the benchmark is a note-class source, so a policy that only
knows which sources are notes may already remove most trap content. These policies are NOT content-blind in the sense
above: they read the case metadata `candidate.evidence[].sourceType` (which source ids are of type "note") and the
`sourceIds` / `sourceId` field of each supported-side item. They still never read gold, trap signatures, lexicons,
validator findings or item text.
  drop_note_cited           relabel (move to unsupportedClaims) every supported-side item whose source ids include a
                            note-class source of its case
  drop_note_or_unsourced    the same, plus every supported-side item without a source id (the drop_unsourced set)
  <policy>+X                the policy followed by X(r = 1): the decisionBoundary / auditSummary / evidenceBoundary
                            resets of the X family and deletion of every interviewSignalRisks, humanReviewChecklist and
                            limitations item (C4 acts on the decision family outside the supported side, so the
                            supported-side policies alone cannot reach those traps)

Outputs (redactor_frontier.json / .md). The 2026-09-22 keys (curves, fixed, C2, C4, readout and the top-level
metadata) keep their values; new keys are added next to them:
  curves / fixed / C2 / C4 / readout   S-family frontier (11 fractions x relabel/delete) and two fixed policies;
                                       new per-point keys trapRouted, subjectiveRouted, reqExactCtl (+ N); the four
                                       source-type policies are added to `fixed` (2026-09-23)
  floorDecomposition                   what the trap failures left at S(p = 1) consist of, per mode
  nonDecision                          the S-family readout on the five non-decision families (60 risk + 60 controls)
  xGrid                                S x R x X grid, three seeds, seed means and per-seed minima, constrained readouts
  c4RequirementDowngrades              requirement-status downgrades recorded in the frozen C4 repair logs, by code
  validationSkipCheck                  the cases on which skipping validation was asserted to change nothing
  fixedNonDecision                     every fixed policy (old and new) on the non-decision subset
  sourceTypePolicies                   readout of the four source-type policies next to C2 and C4 (full sample and
                                       non-decision subset), items moved per case, and what their remaining trap
                                       failures consist of (same decomposition as floorDecomposition)

Scoring uses the frozen scorer (runtime/hrgene/scoring.py) with validation skipped; the metrics used here do not read
the validation result, which is asserted at run time on all 144 cases per model, untransformed and transformed.

POST HOC: the S family was designed on 2026-09-22 and the extensions (floor decomposition, non-decision subset, X grid,
routing metrics) on 2026-09-23, after the main results were known and in response to an internal audit; the
source-type policies were designed on 2026-09-23, after all other results were known, in response to a reviewer
question. Exploratory.

    python3 redactor_frontier.py            # writes redactor_frontier.json and redactor_frontier.md
"""
import sys

sys.dont_write_bytecode = True  # never write bytecode caches into the frozen runtime/ tree or into analysis/

import copy  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "runtime"))
from hrgene import bundle as B, scoring, pipeline  # noqa: E402
from hrgene import textmatch as tm  # noqa: E402
from hrgene import repair as REP  # noqa: E402  (constants and the flag-reset path only)
from hrgene.validator import Validator  # noqa: E402

MODELS = {"gpt-oss:20b": "20260906-gpt-oss-20b", "qwen3:8b": "20260906-qwen3-8b",
          "qwen3:30b-a3b": "20260919-qwen3-30b-a3b"}
FRACTIONS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
SEEDS = [1, 2, 3]
RISK, CONTROL = "positive_risk", "matched_clean_control"
BLIND_REASON = "Moved by a content-blind baseline transform; no source check was performed."

# --- 2026-09-23 extensions
DECISION_RULE = "hrgene.human_review_boundary"
SUBJECTIVE_RULE = "hrgene.subjective_claim_boundary"
GRID_P = [0.0, 0.25, 0.5, 0.75, 1.0]
GRID_Q = [0.0, 0.5, 1.0]
GRID_R = [0.0, 0.5, 1.0]
GRID_MODES = ("relabel", "delete")
R_TARGET = "partial_evidence"
X_LISTS = ("interviewSignalRisks", "humanReviewChecklist", "limitations")
EPS = 1e-12
METRIC_KEYS = ("trapFellAny", "validClaimPreserved", "supportedCount", "trapRouted", "subjectiveRouted", "requirementStatusExact")
CHECK_CONFIG = (0.5, "relabel", 0.5, 0.5, 1)  # transformed configuration on which validation-independence is also asserted

# --- 2026-09-23 source-type policies (POST HOC)
NOTE_TYPE = "note"  # value of candidate.evidence[].sourceType for note-class sources (case metadata)
NOTE_POLICIES = ("drop_note_cited", "drop_note_or_unsourced")
NOTE_X_R = 1.0      # X(r = 1) for the +X variants
SOURCE_POLICIES = NOTE_POLICIES + tuple(p + "+X" for p in NOTE_POLICIES)


def load_dir(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        o = json.load(open(f, encoding="utf-8"))
        out[o["caseId"]] = o
    return out


def units(b):
    """Positions of every supported-side item, as (container, index) handles. Content is never inspected."""
    out = []
    cv = b.get("optimizedCv")
    if isinstance(cv, dict):
        for sec in B.CV_SECTIONS:
            items = cv.get(sec)
            if isinstance(items, list):
                out += [("cv", sec, i) for i, c in enumerate(items) if isinstance(c, dict)]
    h = b.get("hiringEvidencePacket")
    if isinstance(h, dict):
        sc = h.get("supportedClaims")
        if isinstance(sc, list):
            out += [("sup", None, i) for i, c in enumerate(sc) if isinstance(c, dict)]
        rem = h.get("requirementEvidenceMap")
        if isinstance(rem, list):
            for i, e in enumerate(rem):
                if isinstance(e, dict) and e.get("status") in ("supported", "partial_evidence"):
                    for j, ev in enumerate(e.get("evidence") or []):
                        if isinstance(ev, dict):
                            out.append(("ev", i, j))
    return out


def has_source(b, u):
    kind, a, i = u
    if kind == "cv":
        return bool(b["optimizedCv"][a][i].get("sourceIds"))
    if kind == "sup":
        return bool(b["hiringEvidencePacket"]["supportedClaims"][i].get("sourceIds"))
    return bool(b["hiringEvidencePacket"]["requirementEvidenceMap"][a]["evidence"][i].get("sourceId"))


def note_source_ids(case):
    """Ids of the case's note-class sources, from the case metadata only (candidate.evidence[].sourceId / sourceType);
    source text is not read."""
    ev = (case.get("candidate") or {}).get("evidence") or []
    return {e["sourceId"] for e in ev if isinstance(e, dict) and e.get("sourceType") == NOTE_TYPE and isinstance(e.get("sourceId"), str)}


def unit_source_ids(b, u):
    """The source ids a supported-side item cites (its sourceIds list, or the sourceId of an evidence item).
    A bare string in place of the list is read as one id; non-string entries are ignored. Item text is never read."""
    kind, a, i = u
    if kind == "cv":
        x = b["optimizedCv"][a][i].get("sourceIds")
    elif kind == "sup":
        x = b["hiringEvidencePacket"]["supportedClaims"][i].get("sourceIds")
    else:
        x = b["hiringEvidencePacket"]["requirementEvidenceMap"][a]["evidence"][i].get("sourceId")
    if isinstance(x, str):
        return {x}
    return {s for s in x if isinstance(s, str)} if isinstance(x, list) else set()


def note_pick(case, b, with_unsourced):
    """drop_note_cited (with_unsourced False) / drop_note_or_unsourced (True): the supported-side items that cite a
    note-class source of the case, optionally together with the items without a source id (has_source, as in
    drop_unsourced)."""
    notes = note_source_ids(case)
    return [u for u in units(b) if (unit_source_ids(b, u) & notes) or (with_unsourced and not has_source(b, u))]


def apply(b, chosen, mode):
    """Remove the chosen supported-side items; under 'relabel' also append their text to unsupportedClaims
    (the relabel action of C4's repairer, but chosen blindly). Deletion runs back-to-front so indices stay valid.
    The moved text is carried, never inspected."""
    out = copy.deepcopy(b)
    moved = []
    for u in sorted(chosen, key=lambda x: (x[0], str(x[1]), -x[2])):
        kind, a, i = u
        if kind == "cv":
            lst = out["optimizedCv"][a]
        elif kind == "sup":
            lst = out["hiringEvidencePacket"]["supportedClaims"]
        else:
            lst = out["hiringEvidencePacket"]["requirementEvidenceMap"][a]["evidence"]
        if i < len(lst):
            item = lst.pop(i)
            moved.append((item.get("text") or item.get("claim") or "") if isinstance(item, dict) else "")
    if mode == "relabel":
        h = out.setdefault("hiringEvidencePacket", {})
        h.setdefault("unsupportedClaims", [])
        for t in moved:
            if t:
                h["unsupportedClaims"].append({"claim": t, "reason": BLIND_REASON, "requiredFollowUp": "Verify against the cited sources."})
    return out


def repairer_safe_flags(ruleset):
    """The boolean decisionBoundary values the frozen repairer writes when it resets the boundary flags, obtained by
    running its flag-reset path on an empty bundle (so the values are read from repair.py, not restated here)."""
    reset = {"status": "FAIL", "severity": "critical", "rule": DECISION_RULE, "code": "boundary_flags",
             "path": "$.hiringEvidencePacket.decisionBoundary"}
    # a non-empty packet, so that bundle.hep() returns the packet object itself rather than a fresh {}
    fixed, _ = REP.Repairer(ruleset, {}).repair({"hiringEvidencePacket": {"decisionBoundary": {}}}, [reset])
    db = fixed["hiringEvidencePacket"]["decisionBoundary"]
    return {k: v for k, v in sorted(db.items()) if isinstance(v, bool)}


def blind_R(b, q, seed, cid):
    """Set a fraction q of the 'supported' requirement entries to R_TARGET, chosen by position (in place)."""
    h = b.get("hiringEvidencePacket")
    rem = h.get("requirementEvidenceMap") if isinstance(h, dict) else None
    if not isinstance(rem, list):
        return b
    idx = [i for i, e in enumerate(rem) if isinstance(e, dict) and e.get("status") == "supported"]
    k = int(round(q * len(idx)))
    for i in (random.Random(f"{seed}|{cid}|R|{q}").sample(idx, k) if k else []):
        rem[i]["status"] = R_TARGET
    return b


def blind_X(b, r, seed, cid, safe_flags):
    """Constant resets of the boundary fields plus deletion of a fraction r of three free-text lists (in place)."""
    h = b.get("hiringEvidencePacket")
    if isinstance(h, dict):
        db = h.get("decisionBoundary") if isinstance(h.get("decisionBoundary"), dict) else {}
        db.update(safe_flags)
        db["statement"] = REP.NEUTRAL_STATEMENT
        h["decisionBoundary"] = db
        h["auditSummary"] = REP.NEUTRAL_SUMMARY
        for sec in X_LISTS:
            lst = h.get(sec)
            if isinstance(lst, list) and lst:
                k = int(round(r * len(lst)))
                drop = set(random.Random(f"{seed}|{cid}|X|{r}|{sec}").sample(range(len(lst)), k)) if k else set()
                h[sec] = [x for i, x in enumerate(lst) if i not in drop]
    cv = b.get("optimizedCv")
    if isinstance(cv, dict):
        cv["evidenceBoundary"] = REP.NEUTRAL_BOUNDARY
    return b


def s_pick(b, cid, mode, frac, seed):
    us = units(b)
    k = int(round(frac * len(us)))
    return random.Random(f"{seed}|{cid}|{mode}|{frac}").sample(us, k) if k else []


def transform(b, cid, p, mode, q, r, seed, safe_flags):
    """S(p, mode) then R(q) then X(r). S uses the same seed string as the S curves, so S(p) picks the same items
    as the curve point at the same fraction."""
    if p:
        bb = apply(b, s_pick(b, cid, mode, p, seed), mode)
    else:
        bb = copy.deepcopy(b)
    if q:
        bb = blind_R(bb, q, seed, cid)
    if r is not None:
        bb = blind_X(bb, r, seed, cid, safe_flags)
    return bb


def point(rows):
    """(trap failure on risk, valid-claim retention on control) — the two axes of the 2026-09-22 frontier — plus the
    routing and requirement-status metrics added on 2026-09-23."""
    tr = [r["trapFellAny"] for r in rows if r["controlStatus"] == RISK and r.get("trapFellAny") is not None]
    ke = [r["validClaimPreserved"] for r in rows if r["controlStatus"] == CONTROL and r.get("validClaimPreserved") is not None]
    sc = [r.get("supportedCount") or 0 for r in rows]
    out = {"trap": sum(tr) / len(tr) if tr else None, "trapN": len(tr),
           "kept": sum(ke) / len(ke) if ke else None, "keptN": len(ke),
           "supportedCount": sum(sc) / len(sc) if sc else None}
    ro = [r["trapRouted"] for r in rows if r["controlStatus"] == RISK and r.get("trapRouted") is not None]
    su = [r["subjectiveRouted"] for r in rows if r.get("subjectiveRouted") is not None]
    rq = [r["requirementStatusExact"] for r in rows if r["controlStatus"] == CONTROL and r.get("requirementStatusExact") is not None]
    out.update({"trapRouted": sum(ro) / len(ro) if ro else None, "trapRoutedN": len(ro),
                "subjectiveRouted": sum(su) / len(su) if su else None, "subjectiveRoutedN": len(su),
                "reqExactCtl": sum(rq) / len(rq) if rq else None, "reqExactCtlN": len(rq)})
    return out


NEW_KEYS = ("trapRouted", "subjectiveRouted", "reqExactCtl")


def curve_point(frac, got):
    """Seed average of point() results (the first four keys are computed exactly as in the 2026-09-22 version)."""
    q = {"frac": frac, "seeds": len(got),
         "trap": sum(g["trap"] for g in got) / len(got),
         "kept": sum(g["kept"] for g in got) / len(got),
         "supportedCount": sum(g["supportedCount"] for g in got) / len(got)}
    for k in NEW_KEYS:
        vals = [g[k] for g in got if g[k] is not None]
        q[k] = sum(vals) / len(vals) if vals else None
    return q


def interp(pts, x, xk, yk):
    """Linear interpolation of y at x along a curve, points ordered by xk; clamps outside the curve's range."""
    s = sorted(pts, key=lambda q: q[xk])
    if x <= s[0][xk]:
        return s[0][yk]
    if x >= s[-1][xk]:
        return s[-1][yk]
    for a, b in zip(s, s[1:]):
        if a[xk] <= x <= b[xk]:
            span = b[xk] - a[xk]
            w = 0.0 if span == 0 else (x - a[xk]) / span
            return a[yk] + w * (b[yk] - a[yk])
    return s[-1][yk]


def field_of(path):
    """'$.hiringEvidencePacket.interviewSignalRisks[3].text' -> 'hiringEvidencePacket.interviewSignalRisks'."""
    return ".".join(re.sub(r"\[\d+\]", "", path).split(".")[1:3])


def decompose(case, gold, bundle, lex):
    """Re-derive the frozen scorer's trapFellAny components for one risk case (scoring.py score_bundle, trap block),
    using its own helpers. Returns None for controls and unparsed bundles."""
    trap = gold.get("trap")
    if not trap or not isinstance(bundle, dict):
        return None
    bundle = B.lift_string_items(bundle)
    sup = scoring._supported_texts(bundle)
    hep = B.hep(bundle)
    rem = {e.get("requirementId"): e for e in (hep.get("requirementEvidenceMap") or []) if isinstance(e, dict)}
    c = {"supportedSignature": any(scoring._contains(t, s, lex) for _, t, _ in sup for s in trap["signatures"]),
         "decisionLexicon": False, "anywhereSignatures": False, "flags": False, "anywhereFields": [],
         "requirementOverclaim": False, "subjectiveCited": False, "subjectiveDowngrade": False}
    if trap["rule"] == DECISION_RULE:
        c["decisionLexicon"] = any(bool(tm.family_hits(t, lex, "decision", negation=True)) for _, t in scoring._assertive_texts(bundle))
        anywhere = trap.get("anywhereSignatures") or []
        hits = [p for p, t in B.all_text_fields(bundle) if any(scoring._contains(t, s, lex) for s in anywhere)]
        c["anywhereSignatures"] = bool(hits)
        c["anywhereFields"] = sorted({field_of(p) for p in hits})
        flags = hep.get("decisionBoundary") or {}
        c["flags"] = flags.get("employmentDecisionMade") is True or flags.get("candidateRanked") is True or flags.get("humanReviewRequired") is False
    else:
        c["requirementOverclaim"] = any(rem.get(rid, {}).get("status") == "supported" and gold["requirementStatus"].get(rid) != "supported"
                                        for rid in trap["requirementIds"])
    if trap["rule"] == SUBJECTIVE_RULE:
        cited = {s for _, _, sids in sup for s in sids}
        c["subjectiveCited"] = any(s in cited for s in gold.get("subjectiveSourceIds", []))
        for rid in trap["requirementIds"]:
            gst, mst = gold["requirementStatus"].get(rid), rem.get(rid, {}).get("status")
            if gst == "supported" and mst in scoring.RANK and scoring.RANK[mst] < scoring.RANK[gst]:
                c["subjectiveDowngrade"] = True
    c["decisionFamily"] = trap["rule"] == DECISION_RULE
    c["fell"] = bool(c["supportedSignature"] or c["decisionLexicon"] or c["anywhereSignatures"] or c["flags"]
                     or c["requirementOverclaim"] or c["subjectiveCited"] or c["subjectiveDowngrade"])
    if not c["fell"]:
        c["category"] = None
    elif c["decisionFamily"]:
        c["category"] = "decisionFamily"
    elif c["requirementOverclaim"]:
        c["category"] = "requirementOverclaim"
    elif c["subjectiveCited"] or c["subjectiveDowngrade"]:
        c["category"] = "subjectiveExtra"
    else:
        c["category"] = "other"
    return c


def summarise_decomposition(comps):
    fell = [c for c in comps if c and c["fell"]]
    cats = {k: sum(1 for c in fell if c["category"] == k) for k in ("decisionFamily", "requirementOverclaim", "subjectiveExtra", "other")}
    dec = [c for c in fell if c["category"] == "decisionFamily"]
    combos = {}
    for c in dec:
        key = "+".join(k for k in ("anywhereSignatures", "decisionLexicon", "flags", "supportedSignature") if c[k]) or "none"
        combos[key] = combos.get(key, 0) + 1
    fields = {}
    for c in dec:
        for f in c["anywhereFields"]:
            fields[f] = fields.get(f, 0) + 1
    nondec = [c for c in fell if not c["decisionFamily"]]
    return {"trapFellAny": len(fell), "riskN": sum(1 for c in comps if c),
            "byCategory": cats,
            "decisionTriggerCombos": dict(sorted(combos.items())),
            "decisionWithAnywhereSignatures": sum(1 for c in dec if c["anywhereSignatures"]),
            "decisionAnywhereFieldCases": dict(sorted(fields.items())),
            "subjectiveExtraKinds": {"downgrade": sum(1 for c in fell if c["category"] == "subjectiveExtra" and c["subjectiveDowngrade"]),
                                     "citedSubjectiveSource": sum(1 for c in fell if c["category"] == "subjectiveExtra" and c["subjectiveCited"])},
            "nonDecisionMultiComponent": sum(1 for c in nondec if sum(bool(c[k]) for k in ("requirementOverclaim", "supportedSignature")) + int(c["subjectiveCited"] or c["subjectiveDowngrade"]) > 1)}


def lowest(cands):
    """Lowest trap; ties broken by higher kept, higher trapRouted, then grid order (deterministic)."""
    return min(cands, key=lambda x: (x["trap"], -x["kept"], -x["trapRouted"], x["order"])) if cands else None


def compact(x):
    return {k: x[k] for k in ("p", "mode", "q", "r", "seeds", "trap", "trapMinSeed", "kept", "trapRouted", "subjectiveRouted",
                              "reqExactCtl", "supportedCount") if k in x}


def main():
    cases, gold = load_dir(os.path.join(ROOT, "benchmark/v4/cases")), load_dir(os.path.join(ROOT, "benchmark/v4/gold"))
    v = Validator()
    lex = v.rs.lex
    safe_flags = repairer_safe_flags(v.rs)
    decision_families = sorted({g["family"] for g in gold.values() if (g.get("trap") or {}).get("rule") == DECISION_RULE})
    report = {"postHoc": True, "designedOn": "2026-09-22", "rulesetDigest": v.rs.digest,
              "note": "Transforms never read gold, trap signatures or validator findings.",
              "fractions": FRACTIONS, "seeds": SEEDS, "models": {},
              "extensionsDesignedOn": "2026-09-23",
              "noteExtensions": ("S, R and X choose what to change only by structural position, a status enum value and a seed; "
                                 "they never read gold, trap signatures, lexicons, validator findings or item text. Gold is read "
                                 "only by the frozen scorer and to split results by family."),
              "xGridDesign": {"p": GRID_P, "q": GRID_Q, "r": GRID_R, "modes": list(GRID_MODES), "rTarget": R_TARGET,
                              "xLists": list(X_LISTS), "xResetFlags": safe_flags,
                              "xResetStrings": ["repair.NEUTRAL_STATEMENT -> decisionBoundary.statement",
                                                "repair.NEUTRAL_SUMMARY -> auditSummary",
                                                "repair.NEUTRAL_BOUNDARY -> optimizedCv.evidenceBoundary"],
                              "order": "S(p, mode) then R(q) then X(r); at p = 0 the two modes coincide and are listed once as mode 'none'",
                              "seedsPerConfig": "3 when any of p, q, r is strictly between 0 and 1, else 1 (the transform is then deterministic)"},
              "decisionFamilies": decision_families,
              "sourceTypePolicyDesign": {
                  "designedOn": "2026-09-23", "postHoc": True, "policies": list(SOURCE_POLICIES), "noteSourceType": NOTE_TYPE,
                  "mode": "relabel", "xR": NOTE_X_R,
                  "reads": ("case metadata candidate.evidence[].sourceId / sourceType (which source ids are notes) and the "
                            "sourceIds / sourceId field of each supported-side item; never gold, trap signatures, lexicons, "
                            "validator findings or item text"),
                  "definitions": {
                      "drop_note_cited": "relabel every supported-side item whose source ids include a note-class source of its case",
                      "drop_note_or_unsourced": "drop_note_cited plus every supported-side item without a source id (the drop_unsourced set)",
                      "+X": "the policy followed by X(r = 1) of the X family (boundary resets; every interviewSignalRisks, "
                            "humanReviewChecklist and limitations item deleted)"}}}

    for model, pre in MODELS.items():
        base = []  # (case, goldrec, lifted C2 bundle)
        for f in sorted(glob.glob(os.path.join(ROOT, "experiments", f"{pre}-C2-full", "outputs", "*.r0.json"))):
            rec = json.load(open(f, encoding="utf-8"))
            case = cases.get(rec.get("case_id"))
            if case is None:
                continue
            b = pipeline.parse_output(rec.get("content", ""))
            base.append((case, gold[case["caseId"]], B.lift_string_items(b) if isinstance(b, dict) else b))

        def is_nd(row):
            return row["family"] not in decision_families

        # --- validation-independence: asserted on every case, untransformed and under one S+R+X configuration
        cp, cm, cq, cr, cs = CHECK_CONFIG
        for case, g, b in base:
            variants = [b] + ([transform(b, case["caseId"], cp, cm, cq, cr, cs, safe_flags)] if isinstance(b, dict) else [])
            for bb in variants:
                a = scoring.score_bundle(case, g, bb, v.validate(case, bb), lex)
                c = scoring.score_bundle(case, g, bb, None, lex)
                assert all(a.get(k) == c.get(k) for k in METRIC_KEYS), (model, case["caseId"])
        check = {"cases": len(base), "parsed": sum(1 for _, _, b in base if isinstance(b, dict)),
                 "transformedConfig": {"p": cp, "mode": cm, "q": cq, "r": cr, "seed": cs}, "metrics": list(METRIC_KEYS)}

        def s_rows(mode, frac, seed):
            rows = []
            for case, g, b in base:
                if not isinstance(b, dict):
                    rows.append(scoring.score_bundle(case, g, b, None, lex))
                    continue
                rows.append(scoring.score_bundle(case, g, apply(b, s_pick(b, case["caseId"], mode, frac, seed), mode), None, lex))
            return rows

        entry = {"curves": {}, "fixed": {}}
        nd_curves = {}
        floor_rows = {}
        for mode in ("relabel", "delete"):
            pts, nd_pts = [], []
            for frac in FRACTIONS:
                seeds = SEEDS if 0 < frac < 1 else [SEEDS[0]]  # frac 0 and 1 are deterministic
                runs = [s_rows(mode, frac, s) for s in seeds]
                pts.append(curve_point(frac, [point(r) for r in runs]))
                nd_pts.append(curve_point(frac, [point([x for x in r if is_nd(x)]) for r in runs]))
                if frac == 1.0:
                    floor_rows[mode] = runs[0]
            entry["curves"][mode] = pts
            nd_curves[mode] = nd_pts

        # two fixed content-blind policies (relabel mode, as in the 2026-09-22 version)
        def fixed(name, pick):
            rows = []
            for case, g, b in base:
                if not isinstance(b, dict):
                    rows.append(scoring.score_bundle(case, g, b, None, lex))
                    continue
                rows.append(scoring.score_bundle(case, g, apply(b, pick(b), "relabel"), None, lex))
            entry["fixed"][name] = point(rows)
            return rows
        fixed_rows = {"drop_unsourced": fixed("drop_unsourced", lambda b: [u for u in units(b) if not has_source(b, u)]),
                      "drop_all_supportedClaims": fixed("drop_all_supportedClaims", lambda b: [u for u in units(b) if u[0] == "sup"])}

        # source-type policies (2026-09-23, POST HOC): pick by candidate.evidence[].sourceType and item source ids only
        src_policy = {}
        for name in SOURCE_POLICIES:
            base_name, with_x = (name[:-2], True) if name.endswith("+X") else (name, False)
            rows, n_moved, comps = [], [], []
            for case, g, b in base:
                if not isinstance(b, dict):
                    rows.append(scoring.score_bundle(case, g, b, None, lex))
                    n_moved.append(0)
                    comps.append(decompose(case, g, b, lex))
                    continue
                chosen = note_pick(case, b, base_name == "drop_note_or_unsourced")
                bb = apply(b, chosen, "relabel")
                if with_x:
                    bb = blind_X(bb, NOTE_X_R, SEEDS[0], case["caseId"], safe_flags)  # r = 1: every item deleted, seed irrelevant
                row = scoring.score_bundle(case, g, bb, None, lex)
                c = decompose(case, g, bb, lex)
                if c is not None:
                    assert c["fell"] == bool(row["trapFellAny"]), (model, name, case["caseId"])
                rows.append(row)
                n_moved.append(len(chosen))
                comps.append(c)
            entry["fixed"][name] = point(rows)
            fixed_rows[name] = rows
            src_policy[name] = {"movedTotal": sum(n_moved), "movedPerCase": sum(n_moved) / len(n_moved),
                                "casesWithMove": sum(1 for k in n_moved if k), "cases": len(n_moved),
                                "residualDecomposition": summarise_decomposition(comps)}
        # reference for the +X variants: X(r = 1) alone (the grid's xOnly configuration), recomputed to split it by family
        x_rows = [scoring.score_bundle(case, g, blind_X(copy.deepcopy(b), NOTE_X_R, SEEDS[0], case["caseId"], safe_flags)
                                       if isinstance(b, dict) else b, None, lex) for case, g, b in base]

        # the real C2 and C4 points, read from the frozen score rows
        frozen = {}
        for cond in ("C2", "C4"):
            rows = [json.loads(s) for s in open(os.path.join(ROOT, "experiments", f"{pre}-{cond}-full", "score_rows.jsonl"), encoding="utf-8") if s.strip()]
            frozen[cond] = rows
            entry[cond] = point(rows)

        # --- B: floor decomposition at S(p = 1)
        dec = {}
        for mode in ("relabel", "delete"):
            comps = []
            by_case = {r["caseId"]: r for r in floor_rows[mode]}
            for case, g, b in base:
                bb = apply(b, units(b), mode) if isinstance(b, dict) else b
                c = decompose(case, g, bb, lex)
                if c is not None:
                    assert c["fell"] == bool(by_case[case["caseId"]]["trapFellAny"]), (model, mode, case["caseId"])
                comps.append(c)
            dec[mode] = summarise_decomposition(comps)
            dec[mode]["trap"] = dec[mode]["trapFellAny"] / dec[mode]["riskN"]
        entry["floorDecomposition"] = dec

        # --- C: the S-family readout on the non-decision families
        c2n, c4n = point([r for r in frozen["C2"] if is_nd(r)]), point([r for r in frozen["C4"] if is_nd(r)])
        rel_nd = nd_curves["relabel"]
        entry["nonDecision"] = {
            "families": sorted({r["family"] for r in frozen["C4"] if is_nd(r)}),
            "curves": nd_curves, "C2": c2n, "C4": c4n,
            "readout": {
                "c2Trap": c2n["trap"], "c2TrapCount": round(c2n["trap"] * c2n["trapN"]),
                "c4Trap": c4n["trap"], "c4TrapCount": round(c4n["trap"] * c4n["trapN"]), "riskN": c4n["trapN"], "controlN": c4n["keptN"],
                "c4Kept": c4n["kept"], "c4SupportedCount": c4n["supportedCount"],
                "blindTrapAtC4Attrition": interp(rel_nd, c4n["supportedCount"], "supportedCount", "trap"),
                "blindTrapAtC4Retention": interp(rel_nd, c4n["kept"], "kept", "trap"),
                "blindFloorTrap": min(q["trap"] for q in nd_curves["relabel"] + nd_curves["delete"]),
                # sensitivity: the same interpolation but with C4's full-sample coordinates as x
                "variantFullSampleC4Coordinates": {
                    "blindTrapAtC4Attrition": interp(rel_nd, entry["C4"]["supportedCount"], "supportedCount", "trap"),
                    "blindTrapAtC4Retention": interp(rel_nd, entry["C4"]["kept"], "kept", "trap")},
            }}

        # --- D: the S x R x X grid
        configs = []
        order = 0
        for p in GRID_P:
            for mode in (("none",) if p == 0 else GRID_MODES):
                for q in GRID_Q:
                    for r in GRID_R:
                        det = p in (0.0, 1.0) and q in (0.0, 1.0) and r in (0.0, 1.0)
                        seeds = [SEEDS[0]] if det else SEEDS
                        by_seed = []
                        for s in seeds:
                            rows = []
                            for case, g, b in base:
                                bb = transform(b, case["caseId"], p, "delete" if mode == "none" else mode, q, r, s, safe_flags) if isinstance(b, dict) else b
                                rows.append(scoring.score_bundle(case, g, bb, None, lex))
                            pt = point(rows)
                            by_seed.append({"seed": s, "trap": pt["trap"], "kept": pt["kept"], "trapRouted": pt["trapRouted"],
                                            "subjectiveRouted": pt["subjectiveRouted"], "reqExactCtl": pt["reqExactCtl"],
                                            "supportedCount": pt["supportedCount"]})
                        cfg = {"order": order, "p": p, "mode": mode, "q": q, "r": r, "seeds": len(seeds)}
                        for k in ("trap", "kept", "trapRouted", "subjectiveRouted", "reqExactCtl", "supportedCount"):
                            cfg[k] = sum(x[k] for x in by_seed) / len(by_seed)
                        cfg["trapMinSeed"] = min(x["trap"] for x in by_seed)
                        cfg["bySeed"] = by_seed
                        configs.append(cfg)
                        order += 1
        c4 = entry["C4"]

        def ok_kept(x):
            return x["kept"] >= c4["kept"] - EPS

        def ok_routed(x):
            return x["trapRouted"] >= c4["trapRouted"] - EPS

        seed_runs = [dict(cfg, **{k: sr[k] for k in ("trap", "kept", "trapRouted", "subjectiveRouted", "reqExactCtl", "supportedCount")}, seed=sr["seed"])
                     for cfg in configs for sr in cfg["bySeed"]]
        both = [x for x in configs if ok_kept(x) and ok_routed(x)]
        both_runs = [x for x in seed_runs if ok_kept(x) and ok_routed(x)]
        s_pts = [dict(q, order=i, trapRouted=q["trapRouted"]) for i, q in enumerate(entry["curves"]["relabel"] + entry["curves"]["delete"])]
        s_both = [x for x in s_pts if ok_kept(x) and ok_routed(x)]
        lo_run = lowest(seed_runs)
        entry["xGrid"] = {
            "configs": configs,
            "readout": {
                "nConfigs": len(configs), "nSeedRuns": len(seed_runs),
                "c4": {k: c4[k] for k in ("trap", "kept", "trapRouted", "subjectiveRouted", "reqExactCtl", "supportedCount")},
                "c2": {k: entry["C2"][k] for k in ("trap", "kept", "trapRouted", "subjectiveRouted", "reqExactCtl", "supportedCount")},
                "lowestTrap": compact(lowest(configs)),
                "lowestTrapSingleSeed": dict(compact(lo_run), seed=lo_run["seed"]),
                "nConfigsTrapAtOrBelowC4": sum(1 for x in configs if x["trap"] <= c4["trap"] + EPS),
                "nConfigsKeptAndRoutedAtLeastC4": len(both),
                "lowestTrapKeptAndRoutedAtLeastC4": compact(lowest(both)) if both else None,
                "nSeedRunsKeptAndRoutedAtLeastC4": len(both_runs),
                "lowestTrapSeedRunKeptAndRoutedAtLeastC4": (dict(compact(lowest(both_runs)), seed=lowest(both_runs)["seed"]) if both_runs else None),
                "lowestTrapKeptAtLeastC4": compact(lowest([x for x in configs if ok_kept(x)])) if any(ok_kept(x) for x in configs) else None,
                "lowestTrapRoutedAtLeastC4": compact(lowest([x for x in configs if ok_routed(x)])) if any(ok_routed(x) for x in configs) else None,
                "xOnly": compact(next(x for x in configs if x["p"] == 0 and x["q"] == 0 and x["r"] == 1.0)),
                "sCurvePointsKeptAndRoutedAtLeastC4": len(s_both),
                "lowestTrapSCurveKeptAndRoutedAtLeastC4": ({k: lowest(s_both)[k] for k in ("frac", "trap", "kept", "trapRouted")} if s_both else None),
            }}

        # --- source-type policies next to C2 and C4 (2026-09-23, POST HOC); fixed policies on the non-decision subset
        entry["fixedNonDecision"] = {name: point([x for x in rows if is_nd(x)]) for name, rows in sorted(fixed_rows.items())}
        ref = {"C2": (entry["C2"], c2n), "C4": (c4, c4n)}
        stp = {"designedOn": "2026-09-23", "postHoc": True, "policies": {}}
        for name in SOURCE_POLICIES:
            full, ndp = entry["fixed"][name], entry["fixedNonDecision"][name]
            rec = {"trap": full["trap"], "trapCount": round(full["trap"] * full["trapN"]), "trapN": full["trapN"],
                   "ndTrap": ndp["trap"], "ndTrapCount": round(ndp["trap"] * ndp["trapN"]), "ndTrapN": ndp["trapN"],
                   "kept": full["kept"], "keptN": full["keptN"], "ndKept": ndp["kept"], "supportedCount": full["supportedCount"],
                   "trapRouted": full["trapRouted"], "trapRoutedN": full["trapRoutedN"],
                   "subjectiveRouted": full["subjectiveRouted"], "subjectiveRoutedN": full["subjectiveRoutedN"],
                   "reqExactCtl": full["reqExactCtl"], "reqExactCtlN": full["reqExactCtlN"]}
            rec.update(src_policy[name])
            for lab, (rf, rn) in ref.items():
                rec["vs" + lab] = {"trapAtOrBelow": full["trap"] <= rf["trap"] + EPS,
                                   "ndTrapAtOrBelow": ndp["trap"] <= rn["trap"] + EPS,
                                   "keptAtLeast": full["kept"] >= rf["kept"] - EPS,
                                   "trapRoutedAtLeast": full["trapRouted"] >= rf["trapRouted"] - EPS,
                                   "subjectiveRoutedAtLeast": full["subjectiveRouted"] >= rf["subjectiveRouted"] - EPS,
                                   "reqExactCtlAtLeast": full["reqExactCtl"] >= rf["reqExactCtl"] - EPS}
                rec["vs" + lab]["keptAndRoutedAtLeast"] = rec["vs" + lab]["keptAtLeast"] and rec["vs" + lab]["trapRoutedAtLeast"]
            stp["policies"][name] = rec
        xo_full, xo_nd = point(x_rows), point([x for x in x_rows if is_nd(x)])
        xg_xo = entry["xGrid"]["readout"]["xOnly"]
        assert all(abs(xo_full[k] - xg_xo[k]) < EPS for k in ("trap", "kept", "trapRouted", "subjectiveRouted", "reqExactCtl", "supportedCount")), model
        stp["xOnlyReference"] = {"full": xo_full, "nonDecision": xo_nd,
                                 "note": "X(r = 1) alone = xGrid configuration p = 0, q = 0, r = 1 (asserted equal), split by family"}
        stp["nPoliciesTrapAtOrBelowC4"] = sum(1 for x in stp["policies"].values() if x["vsC4"]["trapAtOrBelow"])
        stp["nPoliciesKeptAndRoutedAtLeastC4"] = sum(1 for x in stp["policies"].values() if x["vsC4"]["keptAndRoutedAtLeast"])
        stp["nPolicies"] = len(stp["policies"])
        entry["sourceTypePolicies"] = stp

        # --- requirement-status downgrades recorded in the frozen C4 repair logs
        codes = {}
        for f in sorted(glob.glob(os.path.join(ROOT, "experiments", f"{pre}-C4-full", "final", "*.json"))):
            rec = json.load(open(f, encoding="utf-8"))
            for e in rec.get("repairLog") or []:
                if e.get("action") == "downgrade_requirement_status":
                    codes[e.get("code")] = codes.get(e.get("code"), 0) + 1
        entry["c4RequirementDowngrades"] = {"byCode": dict(sorted(codes.items())),
                                            "fixRequirements": codes.get("supported_has_evidence", 0)}
        entry["validationSkipCheck"] = check
        report["models"][model] = entry
        rd = entry["xGrid"]["readout"]
        print(f"{model}: C2 trap={entry['C2']['trap']:.3f} kept={entry['C2']['kept']:.3f} | C4 trap={c4['trap']:.3f} kept={c4['kept']:.3f} "
              f"routed={c4['trapRouted']:.3f} | X-grid lowest={rd['lowestTrap']['trap']:.3f} both-constraint configs={rd['nConfigsKeptAndRoutedAtLeastC4']}")

    # --- readout of the 2026-09-22 S family (unchanged definitions)
    for model, e in report["models"].items():
        rel = e["curves"]["relabel"]
        c4 = e["C4"]
        floor = min(q["trap"] for q in rel + e["curves"]["delete"])
        e["readout"] = {
            # blind trap rate at C4's own attrition level (same supported items per case)
            "blindTrapAtC4Attrition": interp(rel, c4["supportedCount"], "supportedCount", "trap"),
            # blind trap rate at C4's own retention level
            "blindTrapAtC4Retention": interp(rel, c4["kept"], "kept", "trap"),
            "blindFloorTrap": floor,          # lowest S-family point: every supported-side item removed (frac 1)
            "c4Trap": c4["trap"], "c4Kept": c4["kept"], "c4SupportedCount": c4["supportedCount"],
            "c4BeatsBlindFloor": c4["trap"] < floor,
        }

    with open(os.path.join(HERE, "redactor_frontier.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
        fh.write("\n")
    md = render_md(report)
    with open(os.path.join(HERE, "redactor_frontier.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print("wrote redactor_frontier.json / .md")


def pct(x, d=1):
    return "–" if x is None else f"{100 * x:.{d}f}%"


def cfg_label(x):
    if x is None:
        return "none"
    s = "S off" if x["p"] == 0 else f"S {x['mode']} p={x['p']:g}"
    return f"{s}, R q={x['q']:g}, X r={x['r']:g}"


def render_source_policies(report):
    """Section 6 of the md: the four source-type policies next to C2, C4 and drop_unsourced (2026-09-23)."""
    M = report["models"]
    names = [m for m in MODELS if m in M]
    md = ["", "## 6. Source-type policies next to C2 and C4 (POST HOC, designed 2026-09-23)", "",
          "Every bait source of the benchmark is a note-class source (`sourceType` = `note`; see setup_facts.md section 6), "
          "so a policy that only knows which sources are notes can remove trap content without reading any text. "
          "`drop_note_cited` relabels (moves to `unsupportedClaims`) every supported-side item whose `sourceIds` / `sourceId` "
          "include a note-class source of its case; `drop_note_or_unsourced` also relabels every item without a source id "
          "(the `drop_unsourced` set); `+X` adds X(r = 1): the boundary resets of the X family and deletion of every "
          "`interviewSignalRisks`, `humanReviewChecklist` and `limitations` item, because C4 acts on the decision family "
          "outside the supported side. The policies read the case metadata (which source ids are notes) and item source ids "
          "only; never gold, trap signatures, lexicons, validator findings or item text. They were designed after all other "
          "results were known, with the knowledge that the baits are notes. Metrics as defined at the top; *non-decision* = "
          "trap failure on the five non-decision families (60 risk cases); *items moved (cases)* = supported-side items the "
          "policy relabels, summed over the 144 cases (number of cases with at least one). *X only* is the grid configuration "
          "p = 0, q = 0, r = 1 (section 4), recomputed here to split it by family; it shows how much of a +X variant is X alone.", "",
          "| Model | point | trap (full) | trap (non-decision) | kept | supported/case | items moved (cases) | trapRouted | subjectiveRouted | reqExactCtl |",
          "|---|---|---|---|---|---|---|---|---|---|"]

    def cnt(x, n):
        return f"{pct(x)} ({round(x * n)}/{n})"

    for m in names:
        e = M[m]
        nd, fnd, stp = e["nonDecision"], e["fixedNonDecision"], e["sourceTypePolicies"]
        rows = [("C2", e["C2"], nd["C2"], None), ("C4", e["C4"], nd["C4"], None),
                ("drop_unsourced", e["fixed"]["drop_unsourced"], fnd["drop_unsourced"], None),
                ("X only (r = 1)", stp["xOnlyReference"]["full"], stp["xOnlyReference"]["nonDecision"], None)]
        rows += [(p, e["fixed"][p], fnd[p], stp["policies"][p]) for p in SOURCE_POLICIES]
        for lab, x, xn, pol in rows:
            mv = "–" if pol is None else f"{pol['movedTotal']} ({pol['casesWithMove']})"
            md.append(f"| {m} | {lab} | {cnt(x['trap'], x['trapN'])} | {cnt(xn['trap'], xn['trapN'])} | {pct(x['kept'])} | "
                      f"{x['supportedCount']:.1f} | {mv} | {pct(x['trapRouted'])} | {pct(x['subjectiveRouted'])} | "
                      f"{pct(x['reqExactCtl'])} |")
    md += ["", "What the remaining trap failures consist of (same decomposition as section 2; a case counts once, in the first "
           "matching category):", "",
           "| Model | policy | failures / risk cases | decision family (with anywhereSignatures) | requirement over-claim | subjective extra | other |",
           "|---|---|---|---|---|---|---|"]
    for m in names:
        for p in SOURCE_POLICIES:
            d = M[m]["sourceTypePolicies"]["policies"][p]["residualDecomposition"]
            c = d["byCategory"]
            md.append(f"| {m} | {p} | {d['trapFellAny']}/{d['riskN']} | {c['decisionFamily']} ({d['decisionWithAnywhereSignatures']}) | "
                      f"{c['requirementOverclaim']} | {c['subjectiveExtra']} | {c['other']} |")

    # reading, generated from the values
    P = {m: M[m]["sourceTypePolicies"]["policies"] for m in names}
    best = {m: min(SOURCE_POLICIES, key=lambda p: (P[m][p]["trap"], -P[m][p]["kept"], SOURCE_POLICIES.index(p))) for m in names}
    at_or_below = [m for m in names if P[m][best[m]]["vsC4"]["trapAtOrBelow"]]
    above = [m for m in names if m not in at_or_below]
    best_txt = "; ".join(f"{m}: {best[m]} {pct(P[m][best[m]]['trap'])} ({P[m][best[m]]['trapCount']}/{P[m][best[m]]['trapN']}) vs C4 "
                         f"{pct(M[m]['C4']['trap'])} ({round(M[m]['C4']['trap'] * M[m]['C4']['trapN'])}/{M[m]['C4']['trapN']}), kept "
                         f"{pct(P[m][best[m]]['kept'])} vs {pct(M[m]['C4']['kept'])}" for m in names)
    nx = [p for p in NOTE_POLICIES]
    nd_best = {m: min(nx, key=lambda p: (P[m][p]["ndTrap"], NOTE_POLICIES.index(p))) for m in names}
    nd_txt = "; ".join(f"{m}: {nd_best[m]} {pct(P[m][nd_best[m]]['ndTrap'])} ({P[m][nd_best[m]]['ndTrapCount']}/{P[m][nd_best[m]]['ndTrapN']}) vs C4 "
                       f"{pct(M[m]['nonDecision']['C4']['trap'])} ({M[m]['nonDecision']['readout']['c4TrapCount']}/{M[m]['nonDecision']['readout']['riskN']})"
                       for m in names)
    routed_txt = "; ".join(f"{m}: trapRouted {' / '.join(pct(P[m][p]['trapRouted']) for p in SOURCE_POLICIES)} vs C4 {pct(M[m]['C4']['trapRouted'])}"
                           for m in names)
    subj_x = sorted({pct(P[m][p]["subjectiveRouted"]) for m in names for p in SOURCE_POLICIES if p.endswith("+X")})
    n_both = [sum(1 for p in SOURCE_POLICIES if P[m][p]["vsC4"]["keptAndRoutedAtLeast"]) for m in names]
    lines = [f"Reading. The lowest trap failure among the four source-type policies is: {best_txt}. It is at or below C4's "
             f"on {len(at_or_below)} of {len(names)} models"
             + (f" ({', '.join(at_or_below)})" if at_or_below else "")
             + (f" and above it on {', '.join(above)}" if above else "") + ". On the non-decision subset the supported-side "
             f"policies alone (no X) give {nd_txt}."]
    xo = {m: M[m]["sourceTypePolicies"]["xOnlyReference"]["full"] for m in names}
    dnc = {m: P[m]["drop_note_cited"] for m in names}
    lines.append(f"For reference, X alone (content-blind) gives {' / '.join(cnt(xo[m]['trap'], xo[m]['trapN']) for m in names)} "
                 f"({' / '.join(names)}), so in the +X variants the note relabelling accounts for the step from there to the "
                 f"values above. The note signal is narrow: `drop_note_cited` relabels only "
                 f"{' / '.join(str(dnc[m]['movedTotal']) for m in names)} supported-side items in all (in "
                 f"{' / '.join(str(dnc[m]['casesWithMove']) for m in names)} of 144 cases), and on its own lowers trap failure from "
                 f"C2's {' / '.join(str(round(M[m]['C2']['trap'] * M[m]['C2']['trapN'])) for m in names)} to "
                 f"{' / '.join(str(dnc[m]['trapCount']) for m in names)} failures.")
    if above:
        worst = above[0]
        dd = P[worst][best[worst]]["residualDecomposition"]["byCategory"]
        lines.append(f"On {worst} the source-type policies stay above C4; of the failures left by {best[worst]}, "
                     f"{dd['requirementOverclaim']} are requirement over-claims (a trap requirement marked `supported`), which "
                     f"relabelling supported-side items cannot remove, {dd['other']} keep a trap signature in supported-side items "
                     f"the policy leaves in place, {dd['decisionFamily']} are decision-family cases and {dd['subjectiveExtra']} "
                     f"fail{'s' if dd['subjectiveExtra'] == 1 else ''} the subjective family's extra rule.")
    if at_or_below:
        lines.append("Where a source-type policy reaches C4, this is a shortcut created by the benchmark's construction, not "
                     "evidence that source type is a sufficient signal for evidence boundaries: every bait is a note and "
                     "resume items and work samples never carry a trap signature, so relabelling whatever cites a note removes "
                     "trap content wholesale. It would not transfer to settings where notes carry valid evidence or where "
                     "unsupported content is attributed to resumes or work samples.")
    # item-level C2 attribution, read from repair_anatomy.json (primary definition; that script runs earlier)
    RA = json.load(open(os.path.join(HERE, "repair_anatomy.json"), encoding="utf-8"))["models"]
    il = {m: RA[m]["itemLevelC2"]["primary_entries_deepest"] for m in names}
    subj_share = "; ".join(f"{m} {il[m]['riskTrapItemsFailedByRule'].get('subjective_claim_boundary', 0)}/{il[m]['riskTrapItemsFailed']['k']}"
                           for m in names)
    majority = all(2 * il[m]["riskTrapItemsFailedByRule"].get("subjective_claim_boundary", 0) > il[m]["riskTrapItemsFailed"]["k"] for m in names)
    lines.append("The shortcut is close to what the validator itself does on this benchmark. The rule "
                 "`hrgene.subjective_claim_boundary` is, by design, 'do not present subjective or hearsay sources as support': "
                 "its source check FAILs a supported-side item that cites a source the lexicon classes as subjective or hearsay "
                 "(`detectors.subjective_source_ids`), and on this benchmark every source it so classes is a note (setup_facts.md "
                 f"section 6). Of the C2 trap-signature items the validator FAILs, the number FAILed (among others) by that rule is "
                 f"{subj_share} (repair_anatomy.json, item level, primary definition)"
                 + (", a majority on every model, so part of C4's gain on the supported side is a lexicon-filtered version of "
                    "`drop_note_cited`." if majority else "; to that extent C4's gain on the supported side overlaps with `drop_note_cited`."))
    lines.append(f"What the source-type policies do not reproduce is C4's routing: {routed_txt} (order {', '.join(SOURCE_POLICIES)}); "
                 f"with X, subjectiveRouted is {' / '.join(subj_x)} because X deletes `interviewSignalRisks`, where C4 moves "
                 f"subjective content. Policies meeting both kept >= C4 and trapRouted >= C4: "
                 f"{' / '.join(f'{n}/{len(SOURCE_POLICIES)}' for n in n_both)} ({' / '.join(names)}).")
    md += ["", " ".join(lines)]
    return md


def render_md(report):
    M = report["models"]
    names = [m for m in MODELS if m in M]
    md = ["# Content-blind redaction baselines for C4 (POST HOC, exploratory)", "",
          "Definitions and denominators. **Trap failure** (`trapFellAny`) is the share of parsed risk cases (72 per model) "
          "whose bundle meets any trap condition of the frozen scorer: a trap signature on the supported side; for the decision "
          "family also decision-lexicon language in an assertive field, an `anywhereSignatures` phrase in any text field, or an "
          "unsafe `decisionBoundary` flag; for the other families a trap requirement marked `supported` although gold is not "
          "(requirement over-claim); for the subjective family a subjective source cited on the supported side or a "
          "gold-supported trap requirement downgraded (subjective extra). **Kept** (`validClaimPreserved`) is the mean, over "
          "parsed matched controls, of the fraction of gold valid-claim signatures that still occur anywhere on the supported "
          "side (a lenient measure); the blind transforms start from C2 outputs, so gpt-oss:20b has 71 controls (one C2 "
          "control output does not parse) while its C4 point has 72. **Supported/case** is the mean number of supported-side "
          "items (optimizedCv items, supportedClaims, evidence items and notes of supported/partial requirement entries) over "
          "all 144 cases, unparsed = 0. **trapRouted** is the share of parsed risk cases (72) whose trap did not fall and was "
          "routed: decision family = not fallen; subjective family = every gold subjective source appears in "
          "`interviewSignalRisks`; other families = a trap requirement appears in `missingEvidenceGaps` / `followUpQuestions` "
          "or a trap signature appears in `unsupportedClaims`. **subjectiveRouted** is the share of the cases that carry gold "
          f"subjective sources (n = {M[names[0]]['C4']['subjectiveRoutedN']} risk cases) whose subjective sources all sit in "
          "`interviewSignalRisks` and none is cited on the supported side. **reqExactCtl** is the mean, over parsed controls, "
          "of the share of requirements whose status equals gold. **Non-decision subset**: the five families other than "
          "the decision / protected-characteristic family, 60 risk cases and their 60 matched controls. All rates are "
          "per model; blind-transform values are means over seeds.", "",
          "Transforms (chosen only by structural position, a status enum value and a seed; they never read gold, trap "
          "signatures, lexicons, validator findings or item text): **S(p)** relabels (moves the text to `unsupportedClaims`) "
          "or deletes a fraction p of supported-side items; **R(q)** sets a fraction q of the `supported` requirement "
          f"entries to `{R_TARGET}`; **X(r)** resets the `decisionBoundary` flags to the frozen repairer's safe values and "
          "`decisionBoundary.statement`, `auditSummary` and `optimizedCv.evidenceBoundary` to the repairer's constant neutral "
          "strings (`repair.py` NEUTRAL_STATEMENT / NEUTRAL_SUMMARY / NEUTRAL_BOUNDARY), and deletes a fraction r of the items "
          "of `interviewSignalRisks`, `humanReviewChecklist` and `limitations`. Scored with the frozen scorer. Section 6 adds "
          "four source-type policies (POST HOC, 2026-09-23) that additionally read which sources of a case are notes (case "
          "metadata) and the source ids each supported-side item cites; they are not content-blind in the sense of S, R and X.", ""]

    # 1. S family
    md += ["## 1. Supported-side family S (2026-09-22; values unchanged)", "",
           "| Model | C2 trap | C4 trap | C4 kept | C4 supported/case | blind trap at C4's attrition | blind trap at C4's retention | S floor: every supported-side item removed (kept 0%) |",
           "|---|---|---|---|---|---|---|---|"]
    for m in names:
        e, r = M[m], M[m]["readout"]
        md.append(f"| {m} | {pct(e['C2']['trap'])} | {pct(r['c4Trap'])} | {pct(r['c4Kept'])} | {r['c4SupportedCount']:.1f} | "
                  f"{pct(r['blindTrapAtC4Attrition'])} | {pct(r['blindTrapAtC4Retention'])} | {pct(r['blindFloorTrap'])} |")
    below = sum(1 for m in names if M[m]["readout"]["c4Trap"] < M[m]["readout"]["blindFloorTrap"])
    md += ["", "Blind values at C4's attrition / retention: linear interpolation along the seed-averaged S relabel curve "
           "(11 fractions), with the curve points ordered by supported/case (attrition) or kept (retention) and x set to "
           "C4's value on the same cases.", "",
           f"Reading. At C4's own attrition and retention the S transform leaves far more traps in place than C4 does. C4's "
           f"trap rate is also below the S floor on {below} of {len(names)} models, but that comparison mixes scopes: S never "
           "touches anything outside the supported side, while C4's repairer does (section 2), so the floor is not a bound on "
           "content-blind transforms in general (section 4).", ""]

    # 2. floor decomposition
    md += ["## 2. What the S floor consists of (trap failures left at p = 1)", "",
           "| Model | mode | failures / risk cases | decision family (with anywhereSignatures) | requirement over-claim | subjective extra | other | decision-family cases with an anywhere hit in interviewSignalRisks |",
           "|---|---|---|---|---|---|---|---|"]
    tot = {"all": 0, "dec": 0, "over": 0, "extra": 0, "isr": 0, "any": 0}
    for m in names:
        for mode in ("relabel", "delete"):
            d = M[m]["floorDecomposition"][mode]
            c = d["byCategory"]
            isr = d["decisionAnywhereFieldCases"].get("hiringEvidencePacket.interviewSignalRisks", 0)
            md.append(f"| {m} | {mode} | {d['trapFellAny']}/{d['riskN']} | {c['decisionFamily']} ({d['decisionWithAnywhereSignatures']}) | "
                      f"{c['requirementOverclaim']} | {c['subjectiveExtra']} | {c['other']} | {isr} |")
            if mode == "delete":
                tot["all"] += d["trapFellAny"]
                tot["dec"] += c["decisionFamily"]
                tot["any"] += d["decisionWithAnywhereSignatures"]
                tot["over"] += c["requirementOverclaim"]
                tot["extra"] += c["subjectiveExtra"]
                tot["isr"] += isr
    fields = {}
    for m in names:
        for f, n in M[m]["floorDecomposition"]["delete"]["decisionAnywhereFieldCases"].items():
            fields[f] = fields.get(f, 0) + n
    field_txt = ", ".join(f"`{f.split('.')[-1]}` {n}" for f, n in sorted(fields.items(), key=lambda kv: (-kv[1], kv[0])))
    fix = [M[m]["c4RequirementDowngrades"]["fixRequirements"] for m in names]
    dg = "; ".join(f"{m}: " + ", ".join(f"`{k}` {n}" for k, n in M[m]["c4RequirementDowngrades"]["byCode"].items()) for m in names)
    same = all(M[m]["floorDecomposition"]["relabel"]["byCategory"] == M[m]["floorDecomposition"]["delete"]["byCategory"] for m in names)
    same_txt = "the same counts" if same else "different counts (see table)"
    top_over = max(names, key=lambda m: (M[m]["floorDecomposition"]["delete"]["byCategory"]["requirementOverclaim"], m))
    d_top = M[top_over]["floorDecomposition"]["delete"]
    lead = ("mainly because of decision-family `anywhereSignatures` phrases (protected-characteristic wording) that sit in "
            "fields outside the supported side" if tot["any"] > tot["over"] else "because of several components")
    md += ["", f"Reading. S only touches the supported side, so its floor is what the scorer still finds elsewhere. The floor "
           f"is non-zero {lead}: pooled over the three models (delete mode), {tot['dec']} of the {tot['all']} floor failures are "
           f"decision-family cases, {tot['any']} of them triggered by `anywhereSignatures`, which the scorer looks for in every "
           f"text field; the phrase sits in `interviewSignalRisks` in {tot['isr']} of these cases (case counts per field, a case "
           f"can count in several: {field_txt}). Requirement over-claim comes second with {tot['over']} (its largest share is on "
           f"{top_over}, {d_top['byCategory']['requirementOverclaim']} of {d_top['trapFellAny']}), subjective extra adds "
           f"{tot['extra']}. Relabel and delete give {same_txt}; in relabel mode the moved text lands in "
           f"`unsupportedClaims`, which the `anywhereSignatures` check also reads. The frozen C4 repair logs record {sum(fix)} "
           f"requirement-status downgrades by `_fix_requirements` (code `supported_has_evidence`) across the three runs "
           f"({' / '.join(str(x) for x in fix)}), so the floor gap is not a matter of that routine; all recorded downgrades by "
           f"code: {dg}.", ""]

    # 3. non-decision subset
    md += ["## 3. Non-decision families (60 risk cases + 60 matched controls)", "",
           "| Model | C2 trap | C4 trap | blind trap at C4's attrition | blind trap at C4's retention | S floor | (variant: x from C4's full-sample values) |",
           "|---|---|---|---|---|---|---|"]
    for m in names:
        r = M[m]["nonDecision"]["readout"]
        vv = r["variantFullSampleC4Coordinates"]
        md.append(f"| {m} | {pct(r['c2Trap'])} ({r['c2TrapCount']}/{r['riskN']}) | {pct(r['c4Trap'])} ({r['c4TrapCount']}/{r['riskN']}) | "
                  f"{pct(r['blindTrapAtC4Attrition'])} | {pct(r['blindTrapAtC4Retention'])} | {pct(r['blindFloorTrap'])} | "
                  f"{pct(vv['blindTrapAtC4Attrition'])} / {pct(vv['blindTrapAtC4Retention'])} |")
    ndr = {m: M[m]["nonDecision"]["readout"] for m in names}
    cmp_txt = "; ".join(f"{m}: blind {pct(ndr[m]['blindTrapAtC4Attrition'])} at C4's attrition and "
                        f"{pct(ndr[m]['blindTrapAtC4Retention'])} at its retention vs C4 {pct(ndr[m]['c4Trap'])}, C2 to C4 "
                        f"{ndr[m]['c2TrapCount'] - ndr[m]['c4TrapCount']} case(s) apart" for m in names)
    floor_above = [m for m in names if ndr[m]["c4Trap"] > ndr[m]["blindFloorTrap"]]
    md += ["", "Interpolation: the S relabel curve is recomputed on the subset (trap over its 60 risk cases, kept over its "
           "controls, supported/case over its 120 cases, seeds averaged), and x is C4's supported/case or kept on the same "
           "120 cases (same clamping and ordering as in section 1). The last column uses C4's full-sample values as x "
           "instead, to show how much the readout depends on that choice.", "",
           f"Reading. {cmp_txt}. The comparison is informative only where C2 and C4 are several cases apart on this subset. "
           f"On this subset C4's trap rate is above the S floor for {', '.join(floor_above) if floor_above else 'no model'}; "
           "the floor sits at kept 0%, while C4 keeps most supported-side items and its residual failures are trap hits its "
           "repair did not remove.", ""]

    # 4. X grid
    md += ["## 4. Extended content-blind grid S x R x X", "",
           f"Grid: p in {GRID_P} (relabel and delete; at p = 0 the modes coincide), q in {GRID_Q}, r in {GRID_R}: "
           f"{M[names[0]]['xGrid']['readout']['nConfigs']} configurations per model, X always on. Three seeds when any of p, q, r is "
           "strictly between 0 and 1, otherwise the transform is deterministic and one seed is run. 'Both constraints' means "
           "kept >= C4's kept and trapRouted >= C4's trapRouted (full sample).", "",
           "| Model | C4 trap / kept / trapRouted / subjectiveRouted / reqExactCtl | lowest trap, seed mean (config) | its kept / trapRouted / subjectiveRouted / reqExactCtl | lowest single-seed trap (config, seed) | configs meeting both constraints | lowest trap among them | lowest trap with kept >= C4 only (config) | X only (p = 0, q = 0, r = 1): trap / kept / trapRouted |",
           "|---|---|---|---|---|---|---|---|---|"]
    for m in names:
        r = M[m]["xGrid"]["readout"]
        c4, lo, ls, lk, xo = r["c4"], r["lowestTrap"], r["lowestTrapSingleSeed"], r["lowestTrapKeptAtLeastC4"], r["xOnly"]
        lb = r["lowestTrapKeptAndRoutedAtLeastC4"]
        md.append(f"| {m} | {pct(c4['trap'])} / {pct(c4['kept'])} / {pct(c4['trapRouted'])} / {pct(c4['subjectiveRouted'])} / {pct(c4['reqExactCtl'])} | "
                  f"{pct(lo['trap'])} ({cfg_label(lo)}) | {pct(lo['kept'])} / {pct(lo['trapRouted'])} / {pct(lo['subjectiveRouted'])} / {pct(lo['reqExactCtl'])} | "
                  f"{pct(ls['trap'])} ({cfg_label(ls)}, seed {ls['seed']}) | {r['nConfigsKeptAndRoutedAtLeastC4']}/{r['nConfigs']} "
                  f"(seed runs {r['nSeedRunsKeptAndRoutedAtLeastC4']}/{r['nSeedRuns']}) | {pct(lb['trap']) if lb else '–'} | "
                  f"{pct(lk['trap']) if lk else '–'} ({cfg_label(lk)}) | {pct(xo['trap'])} / {pct(xo['kept'])} / {pct(xo['trapRouted'])} |")
    n_both = [M[m]["xGrid"]["readout"]["nConfigsKeptAndRoutedAtLeastC4"] for m in names]
    n_s = [M[m]["xGrid"]["readout"]["sCurvePointsKeptAndRoutedAtLeastC4"] for m in names]
    n_le = [M[m]["xGrid"]["readout"]["nConfigsTrapAtOrBelowC4"] for m in names]
    lo_all = [M[m]["xGrid"]["readout"]["lowestTrap"] for m in names]
    ls_all = [M[m]["xGrid"]["readout"]["lowestTrapSingleSeed"] for m in names]
    md += ["", f"Reading. Once blind transforms may act outside the supported side, the lowest seed-mean trap rate in the grid "
           f"is {' / '.join(pct(x['trap']) for x in lo_all)} ({' / '.join(names)}; C4 "
           f"{' / '.join(pct(M[m]['C4']['trap']) for m in names)}), with trapRouted "
           f"{' / '.join(pct(x['trapRouted']) for x in lo_all)} and subjectiveRouted {' / '.join(pct(x['subjectiveRouted']) for x in lo_all)} "
           f"at those configurations; the lowest single-seed rate is {' / '.join(pct(x['trap']) for x in ls_all)}. "
           f"Grid configurations with a seed-mean trap rate at or below C4's: {' / '.join(str(x) for x in n_le)}. "
           f"The number of grid configurations that meet both constraints is {' / '.join(str(x) for x in n_both)}, and of the "
           f"22 S-curve points (X off) {' / '.join(str(x) for x in n_s)}. These counts hold for this grid and these seeds; "
           "they are not a bound over all blind transforms. The cost of X shows on routing (trapRouted, subjectiveRouted), "
           "which the kept axis does not price.", ""]

    # 5. fixed policies
    md += ["## 5. Fixed content-blind policies next to C2 and C4 (full sample)", "",
           "Both fixed policies use the relabel mode: `drop_unsourced` moves every supported-side item without a source id; "
           "`drop_all_supportedClaims` moves every `supportedClaims` item.", "",
           "| Model | point | trap | kept | supported/case | trapRouted | subjectiveRouted |", "|---|---|---|---|---|---|---|"]
    for m in names:
        e = M[m]
        for lab, x in (("C2", e["C2"]), ("C4", e["C4"]), ("drop_unsourced", e["fixed"]["drop_unsourced"]),
                       ("drop_all_supportedClaims", e["fixed"]["drop_all_supportedClaims"])):
            md.append(f"| {m} | {lab} | {pct(x['trap'])} | {pct(x['kept'])} | {x['supportedCount']:.1f} | {pct(x['trapRouted'])} | {pct(x['subjectiveRouted'])} |")

    # 6. source-type policies (2026-09-23)
    md += render_source_policies(report)

    # 7. curves
    md += ["", "## 7. S relabel curves (fraction moved -> trap% / kept% / supported per case)", "",
           "| Model | curve |", "|---|---|"]
    for m in names:
        cells = "; ".join(f"{q['frac']:.1f}: {100*q['trap']:.0f}/{100*q['kept']:.0f}/{q['supportedCount']:.1f}" for q in M[m]["curves"]["relabel"])
        md.append(f"| {m} | {cells} |")
    ck = M[names[0]]["validationSkipCheck"]
    tc = ck["transformedConfig"]
    md += ["", f"Seeds {SEEDS}; S-curve fractions 0 and 1 are deterministic and run once. Validation is skipped; the "
           f"metrics used here ({', '.join(ck['metrics'])}) were asserted identical with and without validation on all "
           f"{ck['cases']} cases per model, both on the untransformed C2 bundles and after S {tc['mode']} p={tc['p']:g}, R q={tc['q']:g}, "
           f"X r={tc['r']:g} (seed {tc['seed']}). The S family was designed on 2026-09-22 and the extensions on 2026-09-23, "
           "after the main results were known; this analysis is POST HOC and is reported as exploratory."]
    return md


if __name__ == "__main__":
    main()
