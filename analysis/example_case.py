#!/usr/bin/env python3
"""Worked example for the results section: one risk case traced from the C2 output, through the validator finding,
to the C4 repair.

Selection rule (revised 2026-09-23; the original rule required all three models and selected 859049ac, one of the 12
development cases used on 09-05 to iterate the detectors, scorer and repairer). Applied mechanically:
  1. risk cases (controlStatus positive_risk) outside the decision family
     (decision_ranking_protected_human_review_boundary, whose trap can sit outside the supported side);
  2. excluding the 12 development cases (case ids = file names of experiments/20260905-qwen3-8b-C0-pilot12/outputs/;
     checked against sensitivity.json devExclusion.caseIds when that file exists);
  3. per model, the case qualifies when trapFellAny is true in C2 and false in C4 (frozen score rows);
  4. keep the cases that qualify on the largest number of models, which must be at least 2;
  5. ties: sort by caseId and take the first.
A signature hit that exists only as a substring not on a word boundary (for example the signature "5 years" inside
"2.5 years") is reported as such in the output; the case is not changed because of it.

    python3 example_case.py       # writes example_case.md next to this script
"""
import glob
import json
import os
import re
import sys

sys.dont_write_bytecode = True   # no __pycache__ next to the analysis scripts
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
from hrgene import bundle as B, pipeline, scoring  # noqa: E402
from hrgene import textmatch as tm  # noqa: E402
from hrgene.rules import RuleSet  # noqa: E402

EXP = os.path.join(ROOT, "experiments")
BENCH = os.path.join(ROOT, "benchmark", "v4")
PILOT_RUN = "20260905-qwen3-8b-C0-pilot12"
MIN_MODELS = 2
REVISED = "2026-09-23"
MODELS = [("gpt-oss:20b", "20260906-gpt-oss-20b"), ("qwen3:8b", "20260906-qwen3-8b"), ("qwen3:30b-a3b", "20260919-qwen3-30b-a3b")]
DECISION_FAMILY = "decision_ranking_protected_human_review_boundary"
TRUNC = 300
EVID_PATH = re.compile(r"^(\$\.hiringEvidencePacket\.requirementEvidenceMap\[(\d+)\])\.evidence\[(\d+)\]")


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_dir(prefix, cond):
    return os.path.join(EXP, f"{prefix}-{cond}-full")


def rows(prefix, cond):
    return {r["caseId"]: r for r in load_jsonl(os.path.join(run_dir(prefix, cond), "score_rows.jsonl"))}


def cut(s, n=TRUNC):
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def cut_witness(w):
    return {k: (cut(v) if isinstance(v, str) else v) for k, v in sorted(w.items())}


def dev_ids():
    """The 12 development case ids, from the pilot output file names (cross-checked with sensitivity.json)."""
    ids = sorted({os.path.basename(p).split(".")[0] for p in glob.glob(os.path.join(EXP, PILOT_RUN, "outputs", "*"))})
    if len(ids) != 12 or any(not os.path.exists(os.path.join(BENCH, "cases", i + ".json")) for i in ids):
        raise SystemExit(f"development ids: expected 12 benchmark cases, got {ids}")
    sens = os.path.join(HERE, "sensitivity.json")
    if os.path.exists(sens) and load_json(sens)["devExclusion"]["caseIds"] != ids:
        raise SystemExit("development ids differ from sensitivity.json devExclusion.caseIds")
    return ids


def select(gold, dev):
    ok, status = {}, {}
    for model, prefix in MODELS:
        s2, s4 = rows(prefix, "C2"), rows(prefix, "C4")
        for cid, r in s2.items():
            status.setdefault(cid, {})[model] = (r["trapFellAny"], s4[cid]["trapFellAny"])
            g = gold[cid]
            if g["controlStatus"] != "positive_risk" or g["family"] == DECISION_FAMILY or cid in dev:
                continue
            if r["trapFellAny"] is True and s4[cid]["trapFellAny"] is False:
                ok.setdefault(cid, []).append(model)
    best = max((len(ms) for ms in ok.values()), default=0)
    if best < MIN_MODELS:
        raise SystemExit(f"no case satisfies the selection rule on {MIN_MODELS} or more models")
    tied = sorted(c for c, ms in ok.items() if len(ms) == best)
    hist = {k: sum(1 for ms in ok.values() if len(ms) == k) for k in range(1, len(MODELS) + 1)}
    return tied[0], ok[tied[0]], tied, hist, status[tied[0]]


def on_word_boundary(text, start, end):
    """False when the match continues a word or a number (letter/digit before or after, or a decimal point before)."""
    before = text[start - 1] if start > 0 else ""
    before2 = text[start - 2] if start > 1 else ""
    after = text[end] if end < len(text) else ""
    if before.isalnum() or after.isalnum():
        return False
    if before in ".," and before2.isdigit():
        return False
    return True


def substring_artifacts(text, sig, lex):
    """Signature occurrences the scorer counts (case-insensitive, not negated) that are all off a word boundary."""
    t, s = text.lower(), sig.lower()
    counted, idx = [], t.find(s)
    while idx != -1:
        if not tm.is_negated(text, idx, lex):
            counted.append(idx)
        idx = t.find(s, idx + 1)
    if counted and all(not on_word_boundary(text, i, i + len(s)) for i in counted):
        i = counted[0]
        return {"signature": sig, "context": text[max(0, i - 12):i + len(s) + 12]}
    return None


def findings_on(findings, path):
    out = []
    for f in findings:
        p = f["path"]
        if p == path or p.startswith(path + ".") or p.startswith(path + "["):
            out.append(f)
    return out


def trace_model(model, prefix, case, gold, lex):
    cid = case["caseId"]
    sigs = gold["trap"]["signatures"]
    raw = next(o for o in (load_json(f) for f in sorted(glob.glob(os.path.join(run_dir(prefix, "C2"), "outputs", "*.r0.json"))))
               if o["case_id"] == cid)
    c2 = B.lift_string_items(pipeline.parse_output(raw["content"]))
    stage1 = next(o for o in (load_json(f) for f in sorted(glob.glob(os.path.join(run_dir(prefix, "C4"), "stage1", "*.json"))))
                  if o["case_id"] == cid)
    final = next(o for o in (load_json(f) for f in sorted(glob.glob(os.path.join(run_dir(prefix, "C4"), "final", "*.json"))))
                 if o["case_id"] == cid)
    before = stage1["before"]["findings"]
    fb = final["bundle"]
    final_fields = list(B.all_text_fields(fb))
    final_supported = {p for p, _, _ in scoring._supported_texts(fb)}
    items, seen = [], set()
    for path, text, sids in scoring._supported_texts(c2):
        hit = [s for s in sigs if scoring._contains(text, s, lex)]
        if not hit or (path, text) in seen:
            continue   # the scorer lists requirement-evidence notes twice; keep one
        seen.add((path, text))
        fs = findings_on(before, path)
        m_ev = EVID_PATH.match(path)
        if m_ev:   # evidence items (and their notes) are removed as a whole; the log records the entry path + evidence text
            ev = c2["hiringEvidencePacket"]["requirementEvidenceMap"][int(m_ev.group(2))]["evidence"][int(m_ev.group(3))]
            log = [e for e in stage1["repairLog"] if e["action"] == "remove_evidence_item" and e["path"] == m_ev.group(1)
                   and e.get("detail") == (ev.get("text") or "")[:120]]
        else:
            log = [e for e in stage1["repairLog"] if e["path"] == path or (e.get("detail") == text[:120] and path.startswith(e["path"]))]
        where = sorted(p for p, t in final_fields if t == text)
        if not where:
            where = sorted(p for p, t in final_fields if text and text in t)
        arts = [a for a in (substring_artifacts(text, h, lex) for h in hit) if a]
        items.append({
            "path": path, "sourceIds": sids, "signatures": hit, "text": cut(text), "substringArtifacts": arts,
            "onlyArtifactHits": len(arts) == len(hit),
            "findings": [{"rule": f["rule"].split(".")[-1], "code": f["code"], "severity": f["severity"], "status": f["status"],
                          "path": f["path"], "witness": cut_witness(f.get("witness") or {})} for f in fs],
            "repairLog": [{"rule": e["rule"].split(".")[-1], "code": e["code"], "action": e["action"], "path": e["path"]} for e in log],
            "c4Locations": where, "c4StillSupportedSide": any(p in final_supported or any(p.startswith(q) for q in final_supported) for p in where),
        })
    c2_rem = {e.get("requirementId"): (p, e) for p, e in B.requirement_entries(c2)}
    c4_rem = {e.get("requirementId"): e for _, e in B.requirement_entries(fb)}
    reqs = []
    for rid in gold["trap"]["requirementIds"]:
        p, e = c2_rem.get(rid, (None, {}))
        rf = [f for f in before if p and (f["path"] == p or f["path"].startswith(p + ".status"))]
        rl = [e2 for e2 in stage1["repairLog"] if e2["action"] in ("downgrade_requirement_status", "add_missing_requirement_entries",
                                                                     "normalise_unknown_status") and rid in (e2.get("detail") or "")]
        reqs.append({"requirementId": rid, "goldStatus": gold["requirementStatus"].get(rid), "c2Status": e.get("status"),
                     "c4Status": (c4_rem.get(rid) or {}).get("status"),
                     "findings": [{"rule": f["rule"].split(".")[-1], "code": f["code"], "severity": f["severity"], "status": f["status"],
                                   "path": f["path"], "witness": cut_witness(f.get("witness") or {})} for f in rf],
                     "repairLog": [{"code": x["code"], "action": x["action"], "detail": x["detail"]} for x in rl]})
    s2, s4 = rows(prefix, "C2")[cid], rows(prefix, "C4")[cid]
    return {"model": model, "c2": {k: s2[k] for k in ("trapFellAny", "trapFellStrict", "trapRequirementOverclaimed", "aggregate")},
            "c4": {k: s4[k] for k in ("trapFellAny", "trapFellStrict", "trapRequirementOverclaimed", "trapRouted", "aggregate", "regenerated")},
            "c2Aggregate": stage1["before"]["aggregate"], "items": items, "requirements": reqs,
            "c2HasPacket": isinstance(c2.get("hiringEvidencePacket"), dict), "c2TopLevelKeys": sorted(c2)}


def main():
    rs = RuleSet(os.path.join(ROOT, "rules", "canonical-rules.v2.json"))
    gold = {g["caseId"]: g for g in (load_json(f) for f in sorted(glob.glob(os.path.join(BENCH, "gold", "*.json"))))}
    dev = dev_ids()
    cid, models, tied, hist, status = select(gold, dev)
    case = load_json(os.path.join(BENCH, "cases", cid + ".json"))
    g = gold[cid]
    src = {e["sourceId"]: e for e in case["candidate"]["evidence"]}
    traces = [trace_model(m, p, case, g, rs.lex) for m, p in MODELS if m in models]

    L = []
    A = L.append
    A("# Worked example: one trap from C2 output to C4 repair")
    A("")
    A(f"Selection rule (revised {REVISED}; the original rule, which required all three models, selected `859049ac`, one of the 12 "
      "development cases, and was replaced for that reason). Applied mechanically to the frozen score rows: risk cases "
      "(`positive_risk`) outside the decision family, excluding the 12 development cases (the file names of "
      f"`experiments/{PILOT_RUN}/outputs/`, identical to sensitivity.json `devExclusion.caseIds`); a case qualifies on a model when "
      "`trapFellAny` is true in C2 and false in C4; keep the cases that qualify on the largest number of models (at least "
      f"{MIN_MODELS}); ties are broken by taking the first caseId. A signature hit that exists only as a substring off a word boundary "
      "is flagged below and does not change the selection.")
    A("")
    A("Definitions. *Trap item*: a supported-side entry of the C2 output (optimizedCv claim, supportedClaims entry, or evidence text / "
      "note of a supported or partial requirement; bare-string CV bullets lifted as in the scorer) that contains a gold trap "
      "signature under the scorer's case-insensitive, negation-aware substring match. *Substring artifact*: every occurrence the "
      "scorer counts is preceded or followed by a letter or digit, or preceded by a decimal point after a digit (e.g. `5 years` "
      "inside `2.5 years`). *Finding*: every validator finding in the C4 "
      "input validation (`stage1.before`, i.e. the validator run on the frozen C2 output) whose path is the item's path or inside it. "
      "*Repair*: the C4 repair-log entries on that path; *C4 location*: the final C4 bundle's text fields whose text equals the item "
      "text (else contains it). Texts are truncated to 300 characters. Trap requirements are listed with their gold, C2 and C4 status.")
    A("")
    A(f"Selected case: `{cid}` ({', '.join(models)}; {len(tied)} case(s) qualify on {len(models)} models, first by caseId). "
      f"Family: `{g['family']}`; anchoring rule: `{g['trap']['rule']}`.")
    A("")
    A("Qualifying cases by number of models (non-decision risk cases outside the development set): "
      + ", ".join(f"{k} model(s): {v}" for k, v in sorted(hist.items())) + ". Tied candidates: "
      + ", ".join(f"`{c[:8]}`" for c in tied) + ".")
    A("")
    A("Per-model C2 → C4 trapFellAny on the selected case: "
      + "; ".join(f"{m} {status[m][0]} → {status[m][1]}" + ("" if m in models else " (not traced)") for m, _ in MODELS) + ".")
    A("")
    A("Trap signatures: " + ", ".join(f"`{s}`" for s in g["trap"]["signatures"]) + ".")
    if g["trap"].get("anywhereSignatures"):
        A("")
        A("Anywhere signatures: " + ", ".join(f"`{s}`" for s in g["trap"]["anywhereSignatures"]) + ".")
    A("")
    A("Trap requirements (case text): " + "; ".join(
        f"`{r['requirementId']}` — {r['text']}" for r in case["roleContext"]["requirements"] if r["requirementId"] in g["trap"]["requirementIds"]) + ".")
    A("")
    A("Bait sources:")
    A("")
    for sid in g["trap"].get("baitSourceIds") or []:
        e = src.get(sid, {})
        A(f"- `{sid}` [{e.get('sourceType')}]: {cut(e.get('text', ''))}")
    for t in traces:
        A("")
        A(f"## {t['model']}")
        A("")
        A(f"C2: trapFellAny {t['c2']['trapFellAny']} (signature on supported side {t['c2']['trapFellStrict']}, requirement over-claim "
          f"{t['c2']['trapRequirementOverclaimed']}); validator aggregate on the C2 output {t['c2Aggregate']}. "
          f"C4: trapFellAny {t['c4']['trapFellAny']}, trapRouted {t['c4']['trapRouted']}, aggregate {t['c4']['aggregate']}, regenerated {t['c4']['regenerated']}.")
        if not t["c2HasPacket"]:
            A("")
            A("The C2 output has no `hiringEvidencePacket` object (top-level keys: " + ", ".join(f"`{k}`" for k in t["c2TopLevelKeys"])
              + "); the requirement statuses below are therefore absent in C2 and were added by the repairer in C4.")
        A("")
        if not t["items"]:
            A("No supported-side C2 item contains a trap signature (the trap fell through the requirement status).")
        n_art = sum(1 for it in t["items"] if it["onlyArtifactHits"])
        if n_art:
            A(f"Substring artifacts: {n_art} of {len(t['items'])} trap item(s) contain trap signatures only as substring artifacts "
              "(flagged per item below); the scorer counts them as signature hits.")
            A("")
        for i, it in enumerate(t["items"], 1):
            A(f"**Item {i}** `{it['path']}` (sources {', '.join(it['sourceIds']) or 'none'}; signatures {', '.join('`' + s + '`' for s in it['signatures'])}):")
            A("")
            A(f"> {it['text']}")
            A("")
            for a in it["substringArtifacts"]:
                A(f"- substring artifact: signature `{a['signature']}` is counted only inside `…{a['context']}…` (not on a word boundary; "
                  "the scorer's verbatim substring match counts it)")
            if it["findings"]:
                for f in it["findings"]:
                    A(f"- finding: {f['rule']} / `{f['code']}` / {f['severity']} / {f['status']} at `{f['path']}`; witness "
                      f"`{json.dumps(f['witness'], ensure_ascii=False, sort_keys=True)}`")
            else:
                A("- finding: none on this path")
            if it["repairLog"]:
                for e in it["repairLog"]:
                    A(f"- repair: `{e['action']}` (triggered by {e['rule']} / `{e['code']}`)")
            else:
                A("- repair: no repair-log entry on this path")
            A(f"- C4 location: {', '.join('`' + p + '`' for p in it['c4Locations']) or 'not present (removed)'}; still on the supported side: {it['c4StillSupportedSide']}")
            A("")
        A("| Trap requirement | gold | C2 status | C4 status | findings on the entry | repair |")
        A("|---|---|---|---|---|---|")
        for r in t["requirements"]:
            fs = "; ".join(f"{f['rule']} / `{f['code']}` / {f['severity']}" for f in r["findings"]) or "—"
            rp = "; ".join(f"`{x['action']}` ({x['code']}): {x['detail']}" for x in r["repairLog"]) or "—"
            A(f"| `{r['requirementId']}` | {r['goldStatus']} | {r['c2Status'] or 'absent'} | {r['c4Status'] or 'absent'} | {fs} | {rp} |")
    A("")
    with open(os.path.join(HERE, "example_case.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("selected", cid, models, "tied", len(tied), "items", [len(t["items"]) for t in traces],
          "artifacts", [sum(len(it["substringArtifacts"]) for it in t["items"]) for t in traces])


if __name__ == "__main__":
    main()
