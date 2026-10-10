#!/usr/bin/env python3
"""Three sensitivity analyses of the frozen benchmark results (no frozen file is modified).

(1) Development-set exclusion. The 12 cases whose qwen3:8b pilot outputs (experiments/20260905-qwen3-8b-C0-pilot12)
    were used on 09-05 to iterate the detectors, scorer and repairer stay in the 144-case test set. Their case ids are
    read from the pilot output FILE NAMES only, checked against benchmark/v4/cases, and removed from every formal run
    (official score_rows.jsonl); trap failure, C2->C4 / C0->C4 transitions, clearance and control retention are
    recomputed on the remaining 66 risk / 66 control cases. The 6 development risk cases are also reported alone.
(2) lift_string_items switched off. hrgene.bundle.lift_string_items (added 09-07, after the gpt-oss data were seen)
    is replaced, inside this process only, by a deep copy that lifts nothing. gpt-oss:20b C0/C1/C2/C5 are re-scored
    from the raw outputs/. C4 is rebuilt offline with the frozen pipeline (stage_c4_repair + stage_c4_finalize, the
    same calls c34_postprocess.py makes): first the unpatched rebuild is checked to reproduce the stored stage1/ and
    final/ records exactly, then it is rerun with the patch. The only regeneration reuses the stored regen output,
    and only after checking that the patched run would send a byte-identical regeneration request. The two qwen
    models are checked to contain no bare-string claim items (lifting is the identity on them).
(3) Unicode punctuation normalisation. scoring._contains (the scorer's signature substring match) is wrapped so that
    the output text and the gold signature are first mapped U+2010..U+2015 and U+2212 -> '-', U+2018/U+2019 -> "'",
    U+201C/U+201D -> '"', U+00A0 -> ' ' (one character to one character, so match offsets are unchanged). All
    three models x C0/C1/C2/C5/C4 are re-scored (C3 reuses the C2 outputs).

Paired differences (C4 minus A failure rate) carry the Newcombe (1998) method-10 interval computed by
tab4_contrasts.newcombe_paired, the same implementation as the main contrasts; the method-8 limits are stored as
pairedDiffAfterMinusBefore.ciM8 for traceability only (revised 2026-09-23; before that this script reported method 8).

Every re-scored row is produced by the frozen hrgene.scoring.score_bundle. Before any patch, the unpatched re-score is
asserted equal to each run's score_rows.jsonl on every gold-anchored field, and the full-set transitions and
retention bootstrap are asserted equal to tab4_stats.json. Run after collect.py and tab4_stats.py, from analysis/:
    python3 sensitivity.py            -> sensitivity.json, sensitivity.md
"""
import sys

sys.dont_write_bytecode = True  # never leave .pyc files in runtime/ or analysis/

import copy  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(HERE))
from hrgene import bundle as HB  # noqa: E402
from hrgene import pipeline, prompts, scoring  # noqa: E402
from hrgene import textmatch as tm  # noqa: E402
from hrgene.validator import Validator  # noqa: E402
import c34_postprocess as C34  # noqa: E402  (frozen; imported for load_outputs only)
import tab4_stats as T4  # noqa: E402  (wilson / mcnemar_exact / bootstrap_mean_ci / SEED / B)
import tab4_contrasts as TC  # noqa: E402  (newcombe_paired only; no import-time side effects)

EXP = ROOT / "experiments"
CASES_DIR = ROOT / "benchmark" / "v4" / "cases"
GOLD_DIR = ROOT / "benchmark" / "v4" / "gold"
PILOT_RUN = "20260905-qwen3-8b-C0-pilot12"
MODEL_ORDER = ("gpt-oss:20b", "qwen3:8b", "qwen3:30b-a3b")
LIFT_MODEL = "gpt-oss:20b"
GEN = ("C0", "C1", "C2", "C5")
SCORED = ("C0", "C1", "C2", "C5", "C4")
RISK, CONTROL = T4.RISK, T4.CONTROL
GOLD_FIELDS = ("parsed", "trapFellStrict", "trapFellAny", "trapRequirementOverclaimed", "trapRouted", "validClaimPreserved",
               "validClaimSuppressed", "requirementStatusExact", "requirementNoOverclaim", "subjectiveRouted", "supportedCount")
PUNCT_MAP = {**{chr(c): "-" for c in range(0x2010, 0x2016)}, "−": "-", "‘": "'", "’": "'",
             "“": '"', "”": '"', " ": " "}
TRANS = str.maketrans(PUNCT_MAP)
CV_SECTIONS = HB.CV_SECTIONS
TC_METHOD = "Newcombe 1998 method 10 (tab4_contrasts.newcombe_paired)"


# ----------------------------------------------------------------------------------------------- loading
def load_json_dir(d):
    out = {}
    for f in sorted(glob.glob(str(d / "*.json"))):
        o = json.loads(Path(f).read_text(encoding="utf-8"))
        out[o["caseId"]] = o
    return out


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


def formal_runs():
    """{model: {condition: run dir name}} from collect.py's results.json (C3 excluded: it reuses C2)."""
    runs = {}
    for r in json.loads((HERE / "results.json").read_text()):
        if r["condition"] in SCORED:
            runs.setdefault(r["model"], {})[r["condition"]] = r["run"]
    if tuple(m for m in MODEL_ORDER if m in runs) != MODEL_ORDER or len(runs) != len(MODEL_ORDER):
        raise SystemExit(f"unexpected models in results.json: {sorted(runs)}")
    for m in MODEL_ORDER:
        if set(runs[m]) != set(SCORED):
            raise SystemExit(f"{m}: missing formal conditions {set(SCORED) - set(runs[m])}")
    return runs


def load_score_rows(run):
    path = EXP / run / "score_rows.jsonl"
    return {r["caseId"]: r for r in (json.loads(s) for s in path.read_text().splitlines() if s.strip())}


def load_items(run, cond):
    """[(caseId, bundle, validation)] exactly as benchmark/v4/score.py reads a run (outputs/*.r0.json or final/*.json)."""
    items = []
    if cond == "C4":
        for f in sorted(glob.glob(str(EXP / run / "final" / "*.json"))):
            rec = json.loads(Path(f).read_text(encoding="utf-8"))
            items.append((rec["case_id"], rec.get("bundle"), rec.get("validation")))
    else:
        for f in sorted(glob.glob(str(EXP / run / "outputs" / "*.r0.json"))):
            rec = json.loads(Path(f).read_text(encoding="utf-8"))
            cid = rec.get("case_id") or rec["request_id"].split(".")[0]
            items.append((cid, pipeline.parse_output(rec.get("content", "")), None))
    return items


# ----------------------------------------------------------------------------------------------- statistics
def pct(v, nd=1):
    return "–" if v is None else f"{100 * v:.{nd}f}"


def prop(k, n):
    lo, hi = T4.wilson(k, n)
    return {"k": k, "n": n, "p": (k / n) if n else None, "lo": lo, "hi": hi}


def newcombe_paired(a, b, c, d):
    """Paired difference after - before with the Newcombe (1998) method-10 interval of tab4_contrasts.newcombe_paired
    (imported, not copied); the method-8 (plain phi) limits are kept as ciM8 for traceability only.
    a = failed both, b = failed before only (repaired), c = failed after only (new), d = failed neither."""
    n = a + b + c + d
    if not n:
        return {"diff": None, "lo": None, "hi": None, "method": TC_METHOD, "ciM8": {"lo": None, "hi": None}}
    # tab4_contrasts notation, first proportion = after: e = both fail, f = new, g = repaired, h = both pass.
    lo, hi = TC.newcombe_paired(a, c, b, d, corrected_phi=True)
    lo8, hi8 = TC.newcombe_paired(a, c, b, d, corrected_phi=False)
    return {"diff": (c - b) / n, "lo": lo, "hi": hi, "method": TC_METHOD, "ciM8": {"lo": lo8, "hi": hi8}}


def trap(rows, ids):
    vals = [rows[i]["trapFellAny"] for i in ids if i in rows and rows[i]["controlStatus"] == RISK and rows[i].get("trapFellAny") is not None]
    return prop(sum(bool(v) for v in vals), len(vals))


def retention(rows, ids):
    vals = [rows[i]["validClaimPreserved"] for i in ids if i in rows and rows[i]["controlStatus"] == CONTROL and rows[i].get("validClaimPreserved") is not None]
    return {"mean": (sum(vals) / len(vals)) if vals else None, "n": len(vals)}


def transitions(before, after, ids):
    """Risk cases scorable in both arms; trapFellAny before -> after."""
    ids = sorted(i for i in ids if i in before and i in after and before[i]["controlStatus"] == RISK
                 and before[i].get("trapFellAny") is not None and after[i].get("trapFellAny") is not None)
    b = sum(1 for i in ids if before[i]["trapFellAny"] and not after[i]["trapFellAny"])
    c = sum(1 for i in ids if not before[i]["trapFellAny"] and after[i]["trapFellAny"])
    a = sum(1 for i in ids if before[i]["trapFellAny"] and after[i]["trapFellAny"])
    d = len(ids) - a - b - c
    return {"pairedN": len(ids), "repaired": b, "new": c, "unchangedFail": a, "unchangedPass": d,
            "exactP": T4.mcnemar_exact(b, c), "clearance": prop(b, a + b),
            "pairedDiffAfterMinusBefore": newcombe_paired(a, b, c, d),
            "newCaseIds": sorted(i for i in ids if not before[i]["trapFellAny"] and after[i]["trapFellAny"])}


def retention_diff(c2, c4, ids, seed_label):
    """Common scorable controls: mean per-case (C4 - C2) validClaimPreserved; case bootstrap as tab4_stats."""
    ids = sorted(i for i in ids if i in c2 and i in c4 and c2[i]["controlStatus"] == CONTROL
                 and c2[i].get("validClaimPreserved") is not None and c4[i].get("validClaimPreserved") is not None)
    diffs = [c4[i]["validClaimPreserved"] - c2[i]["validClaimPreserved"] for i in ids]
    lo, hi = T4.bootstrap_mean_ci(diffs, random.Random(seed_label))
    return {"pairedN": len(ids), "c2": sum(c2[i]["validClaimPreserved"] for i in ids) / len(ids),
            "c4": sum(c4[i]["validClaimPreserved"] for i in ids) / len(ids), "diff": sum(diffs) / len(diffs),
            "lo": lo, "hi": hi, "casesChanged": sum(1 for x in diffs if x != 0),
            "bootstrap": {"B": T4.B, "seed": seed_label, "unit": "case"}}


def mean_supported(rows):
    vals = [r["supportedCount"] for r in rows.values()]
    return sum(vals) / len(vals) if vals else None


# ----------------------------------------------------------------------------------------------- scoring
class Ctx:
    def __init__(self):
        self.cases = load_json_dir(CASES_DIR)
        self.gold = load_json_dir(GOLD_DIR)
        self.validator = Validator()
        self.lex = self.validator.rs.lex
        self.runs = formal_runs()
        self.official = {m: {c: load_score_rows(self.runs[m][c]) for c in SCORED} for m in MODEL_ORDER}
        self.items = {m: {c: load_items(self.runs[m][c], c) for c in SCORED} for m in MODEL_ORDER}

    def score(self, items):
        rows = {}
        for cid, bundle, val in items:
            rows[cid] = scoring.score_bundle(self.cases[cid], self.gold[cid], bundle, val, self.lex)
        return rows


def assert_reproduces(ctx):
    """Unpatched re-score == official score_rows.jsonl on every gold-anchored field, for all 15 formal runs."""
    checked = 0
    for m in MODEL_ORDER:
        for c in SCORED:
            mine, off = ctx.score(ctx.items[m][c]), ctx.official[m][c]
            if set(mine) != set(off) or len(mine) != 144:
                raise SystemExit(f"{m} {c}: case set differs from score_rows.jsonl")
            for cid, row in mine.items():
                for k in GOLD_FIELDS:
                    if row.get(k) != off[cid].get(k):
                        raise SystemExit(f"{m} {c} {cid} {k}: re-score {row.get(k)} != score_rows {off[cid].get(k)}")
                    checked += 1
    return checked


def assert_tab4(ctx):
    """Full-set transitions and retention bootstrap recomputed here must equal tab4_stats.json."""
    t4 = json.loads((HERE / "tab4_stats.json").read_text())
    for m in MODEL_ORDER:
        rows = ctx.official[m]
        ids = sorted(rows["C2"])
        for a in ("C0", "C2"):
            mine, ref = transitions(rows[a], rows["C4"], ids), t4["models"][m]["mcnemar"][f"{a}->C4"]
            for k in ("pairedN", "repaired", "new", "unchangedFail", "unchangedPass", "exactP"):
                if mine[k] != ref[k]:
                    raise SystemExit(f"{m} {a}->C4 {k}: {mine[k]} != tab4_stats {ref[k]}")
        mine = retention_diff(rows["C2"], rows["C4"], ids, f"{T4.SEED}|{m}|retention")
        ref = t4["models"][m]["controlRetentionC2toC4"]
        for k in ("pairedN", "c2", "c4", "diff", "lo", "hi"):
            if abs(mine[k] - ref[k]) > 1e-12:
                raise SystemExit(f"{m} retention {k}: {mine[k]} != tab4_stats {ref[k]}")


# ----------------------------------------------------------------------------------------------- (1) dev-set exclusion
def dev_ids(ctx):
    names = sorted(Path(p).name for p in glob.glob(str(EXP / PILOT_RUN / "outputs" / "*")))
    ids = sorted({n.split(".")[0] for n in names})
    missing = [i for i in ids if not (CASES_DIR / f"{i}.json").exists()]
    if len(ids) != 12 or missing:
        raise SystemExit(f"development set: {len(ids)} ids, missing from benchmark: {missing}")
    return ids, names


def summarise_subset(rows, ids, model, seed_suffix):
    out = {"trapFellAny": {c: trap(rows[c], ids) for c in SCORED},
           "controlRetention": {c: retention(rows[c], ids) for c in SCORED},
           "C2->C4": transitions(rows["C2"], rows["C4"], ids),
           "C0->C4": transitions(rows["C0"], rows["C4"], ids),
           "controlRetentionC2toC4": retention_diff(rows["C2"], rows["C4"], ids, f"{T4.SEED}|{model}|retention{seed_suffix}")}
    return out


def dev_exclusion(ctx):
    ids, names = dev_ids(ctx)
    dev = set(ids)
    fam = [{"caseId": i, "family": ctx.gold[i]["family"], "controlStatus": ctx.gold[i]["controlStatus"]} for i in ids]
    c2_pilot = sorted({Path(p).name.split(".")[0] for p in glob.glob(str(EXP / "20260905-qwen3-8b-C2-pilot12" / "outputs" / "*"))})
    res = {"source": f"experiments/{PILOT_RUN}/outputs (file names only)", "fileNames": names, "caseIds": ids,
           "allInBenchmark": True, "sameIdsAsC2Pilot": c2_pilot == ids, "cases": fam,
           "nRisk": sum(1 for x in fam if x["controlStatus"] == RISK), "nControl": sum(1 for x in fam if x["controlStatus"] == CONTROL),
           "models": {}}
    for m in MODEL_ORDER:
        rows = ctx.official[m]
        all_ids = sorted(rows["C2"])
        keep = [i for i in all_ids if i not in dev]
        dev_risk = [i for i in ids if ctx.gold[i]["controlStatus"] == RISK]
        res["models"][m] = {
            "full": summarise_subset(rows, all_ids, m, ""),
            "excludingDev": summarise_subset(rows, keep, m, "|devExcluded"),
            "devRiskCases": {c: {**trap(rows[c], dev_risk), "failedIds": sorted(i for i in dev_risk if rows[c].get(i, {}).get("trapFellAny"))} for c in SCORED},
            "devControlRetention": {c: retention(rows[c], [i for i in ids if ctx.gold[i]["controlStatus"] == CONTROL]) for c in SCORED},
        }
    return res


# ----------------------------------------------------------------------------------------------- (2) lift off
def no_lift(bundle):
    """Replacement for hrgene.bundle.lift_string_items: same deep copy, nothing lifted."""
    return copy.deepcopy(bundle)


class LiftOff:
    def __enter__(self):
        self.orig = HB.lift_string_items
        HB.lift_string_items = no_lift  # validator, repair and scoring all call it as bundle.lift_string_items
        return self

    def __exit__(self, *exc):
        HB.lift_string_items = self.orig
        return False


def string_items(bundle):
    """Number of bare-string items in the lists lift_string_items would lift."""
    if not isinstance(bundle, dict):
        return 0
    n = 0
    cv = bundle.get("optimizedCv")
    if isinstance(cv, dict):
        for sec in CV_SECTIONS:
            if isinstance(cv.get(sec), list):
                n += sum(1 for x in cv[sec] if isinstance(x, str))
    h = bundle.get("hiringEvidencePacket")
    if isinstance(h, dict) and isinstance(h.get("supportedClaims"), list):
        n += sum(1 for x in h["supportedClaims"] if isinstance(x, str))
    return n


def string_census(ctx):
    out = {}
    for m in MODEL_ORDER:
        out[m] = {}
        for c in SCORED:
            bundles = [b for _, b, _ in ctx.items[m][c] if isinstance(b, dict)]
            identity = sum(1 for b in bundles if canon(HB.lift_string_items(b)) == canon(b))
            out[m][c] = {"parsedBundles": len(bundles), "bundlesWithStringItems": sum(1 for b in bundles if string_items(b)),
                         "stringItems": sum(string_items(b) for b in bundles), "liftIsIdentity": identity}
    return out


def rebuild_c4(ctx, model, regen_policy):
    """Rebuild C4 from the C2 raw outputs with the frozen pipeline, as c34_postprocess.py repair + finalize do.
    Returns ({caseId: record}, diagnostics). regen_policy(rid, case, raw, first) -> regen raw text or None."""
    c2_run, c4_run = EXP / ctx.runs[model]["C2"], EXP / ctx.runs[model]["C4"]
    outputs = C34.load_outputs(str(c2_run))
    recs, needs = {}, []
    for rid, (raw, rec) in sorted(outputs.items()):
        case = ctx.cases[rec.get("case_id") or rid.split(".")[0]]
        first = json.loads(json.dumps(pipeline.stage_c4_repair(ctx.validator, case, raw), ensure_ascii=False))  # stored round trip
        regen_raw = None
        if first["needsRegeneration"]:  # c34_postprocess writes a regeneration request only for these
            needs.append(rid)
            regen_raw = regen_policy(rid, case, raw, first)
        final = pipeline.stage_c4_finalize(ctx.validator, case, first, regen_raw)
        ne = pipeline.repair_escalation(first["before"], final["validation"])
        recs[case["caseId"]] = {"stage1": {"request_id": rid, "case_id": case["caseId"], **first},
                                "final": json.loads(json.dumps({"request_id": rid, "case_id": case["caseId"], **final, "repairNonEscalating": ne}, ensure_ascii=False))}
    return recs, {"needsRegeneration": needs, "c4Run": c4_run}


def action_counts(recs):
    out = {}
    for r in recs.values():
        for e in r["final"]["repairLog"]:
            key = f"{e['action']}|{e['rule'].split('.')[-1]}|{e['code']}"
            out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def lift_off(ctx):
    m = LIFT_MODEL
    c4_run = EXP / ctx.runs[m]["C4"]
    stored_regen = C34.load_outputs(str(c4_run / "regen")) if (c4_run / "regen").is_dir() else {}
    stored_req = {}
    rq_path = c4_run / "regen_requests.jsonl"
    for line in rq_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            o = json.loads(line)
            stored_req[o["request_id"]] = o

    # (a) unpatched offline rebuild must reproduce the stored stage1/ and final/ records exactly
    recs_on, diag_on = rebuild_c4(ctx, m, lambda rid, case, raw, first: stored_regen[rid][0] if rid in stored_regen else None)
    s1_mis = f_mis = 0
    for cid, r in recs_on.items():
        rid = r["stage1"]["request_id"]
        s1 = json.loads((c4_run / "stage1" / f"{rid}.json").read_text(encoding="utf-8"))
        fi = json.loads((c4_run / "final" / f"{rid}.json").read_text(encoding="utf-8"))
        s1_mis += canon(s1) != canon(r["stage1"])
        f_mis += canon(fi) != canon(r["final"])
    if s1_mis or f_mis or sorted(diag_on["needsRegeneration"]) != sorted(stored_req):
        raise SystemExit(f"offline C4 rebuild does not reproduce the stored run: stage1 {s1_mis}, final {f_mis}")

    # (b) patched: score C0/C1/C2/C5 from raw outputs and rebuild C4 with the lift switched off
    regen_check = {}

    def regen_policy(rid, case, raw, first):
        findings = (first["after"] or first["before"])["findings"]
        msgs = prompts.build_regeneration_messages(case, "C4", ctx.validator.rs, raw, findings)
        same = rid in stored_req and canon(msgs) == canon(stored_req[rid]["messages"])
        regen_check[rid] = {"requestIdenticalToStored": same, "storedOutputAvailable": rid in stored_regen}
        return stored_regen[rid][0] if same and rid in stored_regen else None

    with LiftOff():
        off_rows = {c: ctx.score(ctx.items[m][c]) for c in GEN}
        recs_off, diag_off = rebuild_c4(ctx, m, regen_policy)
        c4_items = [(cid, r["final"]["bundle"], r["final"]["validation"]) for cid, r in sorted(recs_off.items())]
        off_rows["C4"] = ctx.score(c4_items)
    c4_scored_with_lift = ctx.score(c4_items)  # same rebuilt bundles, official (lifting) scorer
    lifted_scorer_same = all(canon({k: c4_scored_with_lift[i].get(k) for k in GOLD_FIELDS}) == canon({k: off_rows["C4"][i].get(k) for k in GOLD_FIELDS})
                             for i in off_rows["C4"])
    strings_left = sum(string_items(r["final"]["bundle"]) for r in recs_off.values())
    official_c4 = {cid: b for cid, b, _ in ctx.items[m]["C4"]}
    bundles_differ = sum(1 for cid, r in recs_off.items() if canon(r["final"]["bundle"]) != canon(official_c4[cid]))
    field_diffs = {k: sum(1 for cid in off_rows["C4"] if off_rows["C4"][cid].get(k) != ctx.official[m]["C4"][cid].get(k)) for k in GOLD_FIELDS}

    off = ctx.official[m]
    ids = sorted(off["C2"])
    res = {"model": m, "conditions": {}}
    for c in SCORED:
        o_t, n_t = trap(off[c], ids), trap(off_rows[c], ids)
        o_r, n_r = retention(off[c], ids), retention(off_rows[c], ids)
        res["conditions"][c] = {
            "trapFellAny": {"official": o_t, "liftOff": n_t, "deltaK": n_t["k"] - o_t["k"]},
            "controlRetention": {"official": o_r, "liftOff": n_r, "deltaPp": 100 * (n_r["mean"] - o_r["mean"])},
            "casesChanged": {"trapFellAny": sum(1 for i in ids if off[c][i].get("trapFellAny") != off_rows[c][i].get("trapFellAny")),
                             "validClaimPreserved": sum(1 for i in ids if off[c][i].get("validClaimPreserved") != off_rows[c][i].get("validClaimPreserved"))},
            "meanSupportedCount": {"official": mean_supported(off[c]), "liftOff": mean_supported(off_rows[c])},
            "trapFellIdsLost": sorted(i for i in ids if off[c][i].get("trapFellAny") and not off_rows[c][i].get("trapFellAny")),
            "trapFellIdsGained": sorted(i for i in ids if off_rows[c][i].get("trapFellAny") and not off[c][i].get("trapFellAny")),
        }
    named = sorted({i for x in res["conditions"].values() for i in x["trapFellIdsLost"] + x["trapFellIdsGained"]})
    res["caseFamilies"] = {i: ctx.gold[i]["family"] for i in named}
    res["C2->C4"] = {"official": transitions(off["C2"], off["C4"], ids), "liftOff": transitions(off_rows["C2"], off_rows["C4"], ids)}
    res["C0->C4"] = {"official": transitions(off["C0"], off["C4"], ids), "liftOff": transitions(off_rows["C0"], off_rows["C4"], ids)}
    res["controlRetentionC2toC4"] = {"official": retention_diff(off["C2"], off["C4"], ids, f"{T4.SEED}|{m}|retention"),
                                     "liftOff": retention_diff(off_rows["C2"], off_rows["C4"], ids, f"{T4.SEED}|{m}|retention|liftOff")}
    res["c4Rebuild"] = {
        "unpatchedReproducesStored": {"stage1Mismatches": s1_mis, "finalMismatches": f_mis, "records": len(recs_on)},
        "liftOffNeedsRegeneration": sorted(diag_off["needsRegeneration"]),
        "officialRegenerations": sorted(stored_req),
        "regenerationReuse": dict(sorted(regen_check.items())),
        "liftOffNotRepairable": sum(1 for r in recs_off.values() if r["final"]["notRepairable"]),
        "liftOffAggregate": dict(sorted({a: sum(1 for r in recs_off.values() if r["final"]["aggregate"] == a) for a in ("ACCEPT", "HUMAN_REVIEW", "BLOCK")}.items())),
        "officialAggregate": dict(sorted({a: sum(1 for r in recs_on.values() if r["final"]["aggregate"] == a) for a in ("ACCEPT", "HUMAN_REVIEW", "BLOCK")}.items())),
        "stringItemsInC2RawOutputs": sum(string_items(b) for _, b, _ in ctx.items[m]["C2"]),
        "stringItemsLeftInLiftOffC4": strings_left,
        "liftOffC4ScoredWithLiftingScorerIdentical": lifted_scorer_same,
        "liftOffC4BundlesDifferingFromOfficial": bundles_differ,
        "liftOffC4GoldFieldChangesVsOfficial": dict(sorted(field_diffs.items())),
        "repairActions": {"official": action_counts(recs_on), "liftOff": action_counts(recs_off)},
    }
    return res


# ----------------------------------------------------------------------------------------------- (3) Unicode normalisation
_ORIG_CONTAINS = scoring._contains


def contains_normalised(text, sig, lex):
    """The frozen _contains applied to mapped text and signature (negation is therefore checked on the mapped text)."""
    return _ORIG_CONTAINS(text.translate(TRANS), sig.translate(TRANS), lex)


def contains_normalised_rawneg(text, sig, lex):
    """Diagnostic variant: mapped substring search, negation checked on the unmapped text at the same offset."""
    t, s = text.translate(TRANS).lower(), sig.translate(TRANS).lower()
    idx = t.find(s)
    while idx != -1:
        if not tm.is_negated(text, idx, lex):
            return True
        idx = t.find(s, idx + 1)
    return False


class Patched:
    def __init__(self, fn):
        self.fn = fn

    def __enter__(self):
        scoring._contains = self.fn
        return self

    def __exit__(self, *exc):
        scoring._contains = _ORIG_CONTAINS
        return False


def has_mapped(text):
    return isinstance(text, str) and any(ch in PUNCT_MAP for ch in text)


def unicode_norm(ctx):
    sigs = [s for g in ctx.gold.values() for s in ((g.get("trap") or {}).get("signatures", []) + (g.get("trap") or {}).get("anywhereSignatures", [])
                                                    + (g.get("validClaimSignatures") or []))]
    res = {"mapping": {f"U+{ord(k):04X}": v for k, v in sorted(PUNCT_MAP.items())},
           "goldSignatures": {"total": len(sigs), "withAsciiHyphenOrApostrophe": sum(1 for s in sigs if "-" in s or "'" in s),
                              "withMappedCharacter": sum(1 for s in sigs if has_mapped(s))},
           "models": {}}
    for m in MODEL_ORDER:
        off = ctx.official[m]
        ids = sorted(off["C2"])
        with Patched(contains_normalised):
            nrm = {c: ctx.score(ctx.items[m][c]) for c in SCORED}
        with Patched(contains_normalised_rawneg):
            raw_neg = {c: ctx.score(ctx.items[m][c]) for c in SCORED}
        entry = {"conditions": {}}
        for c in SCORED:
            o_t, n_t = trap(off[c], ids), trap(nrm[c], ids)
            o_r, n_r = retention(off[c], ids), retention(nrm[c], ids)
            sup_mapped = 0
            for _, b, _ in ctx.items[m][c]:
                if isinstance(b, dict):
                    lb = HB.lift_string_items(b)
                    sup_mapped += any(has_mapped(t) for _, t, _, _, _ in HB.supported_side(lb))
            entry["conditions"][c] = {
                "trapFellAny": {"official": o_t, "normalised": n_t, "deltaK": n_t["k"] - o_t["k"]},
                "controlRetention": {"official": o_r, "normalised": n_r, "deltaPp": 100 * (n_r["mean"] - o_r["mean"])},
                "casesChanged": {"trapFellAny": sum(1 for i in ids if off[c][i].get("trapFellAny") != nrm[c][i].get("trapFellAny")),
                                 "validClaimPreserved": sum(1 for i in ids if off[c][i].get("validClaimPreserved") != nrm[c][i].get("validClaimPreserved"))},
                "trapFellIdsGained": sorted(i for i in ids if nrm[c][i].get("trapFellAny") and not off[c][i].get("trapFellAny")),
                "trapFellIdsLost": sorted(i for i in ids if off[c][i].get("trapFellAny") and not nrm[c][i].get("trapFellAny")),
                "bundlesWithMappedCharOnSupportedSide": sup_mapped,
                "rawNegationVariantDiffers": sum(1 for i in ids for k in ("trapFellAny", "validClaimPreserved") if raw_neg[c][i].get(k) != nrm[c][i].get(k)),
            }
        named = sorted({i for x in entry["conditions"].values() for i in x["trapFellIdsLost"] + x["trapFellIdsGained"]})
        entry["caseFamilies"] = {i: ctx.gold[i]["family"] for i in named}
        entry["C2->C4"] = {"official": transitions(off["C2"], off["C4"], ids), "normalised": transitions(nrm["C2"], nrm["C4"], ids)}
        entry["C0->C4"] = {"official": transitions(off["C0"], off["C4"], ids), "normalised": transitions(nrm["C0"], nrm["C4"], ids)}
        entry["controlRetentionC2toC4"] = {"official": retention_diff(off["C2"], off["C4"], ids, f"{T4.SEED}|{m}|retention"),
                                           "normalised": retention_diff(nrm["C2"], nrm["C4"], ids, f"{T4.SEED}|{m}|retention|unicode")}
        res["models"][m] = entry
    return res


# ----------------------------------------------------------------------------------------------- report
DEFS = (
    "Definitions and denominators. Supported side = the four optimizedCv claim lists, hiringEvidencePacket.supportedClaims, and the "
    "evidence texts and notes of requirement entries marked supported or partial_evidence. Trap failure = gold `trapFellAny` (frozen "
    "scorer: a trap signature in a supported-side text, a requirement status above gold, and the family-specific extra checks: decision "
    "wording, anywhereSignatures and boundary flags for the decision family, subjective sources cited as support or used to downgrade "
    "for the subjective family), counted as k/n over the risk cases whose output parses (`positive_risk`, trapFellAny not null); 95% "
    "Wilson interval. Control retention = mean over scorable matched clean controls (`matched_clean_control`, validClaimPreserved not "
    "null) of the per-case fraction of gold valid-claim signatures found on the supported side (a lenient metric: one occurrence "
    "anywhere on the supported side counts). Mean supported items = supportedCount averaged over all 144 cases (unparsed = 0). "
    "A->C4 transitions use the risk cases "
    "scorable in both arms: repaired = failed in A and not in C4, new = the reverse; clearance = repaired / (cases failed in A), Wilson "
    "interval; exact McNemar two-sided p = 2 x binomial tail on repaired+new (with new = 0 this is 2 x 0.5^repaired); paired difference "
    "= C4 minus A failure rate with a Newcombe (1998) method 10 score interval (tab4_contrasts.newcombe_paired, the same implementation "
    "as the main contrasts; the JSON also keeps the method 8 limits as `ciM8`, for traceability only). With no discordant pairs the "
    "difference is 0 and the method 10 interval is not a meaningful estimate. The C2->C4 retention difference is the mean per-case "
    "(C4 - C2) retention over controls scorable in both arms, with a percentile case bootstrap (B = 10000, seed string shown, as "
    "tab4_stats.py). C3 reuses the C2 outputs and is not repeated. Development set = the 12 case ids in the file names of "
    f"experiments/{PILOT_RUN}/outputs (6 risk, 6 control, one of each per family); `excluding dev` removes them from every arm, leaving "
    "66 risk and 66 control cases (fewer when an output does not parse). Lift off = hrgene.bundle.lift_string_items replaced in-process by "
    "a copy that lifts nothing, wherever it is called (validator, repairer, scorer); gpt-oss:20b C0/C1/C2/C5 are re-scored from outputs/, "
    "C4 is rebuilt offline from the C2 outputs with the frozen repair pipeline and then scored. Unicode normalisation = the scorer's signature match "
    "(scoring._contains, used for trap signatures, anywhereSignatures and valid-claim signatures) applied after mapping U+2010-U+2015 and "
    "U+2212 to '-', U+2018/U+2019 to \"'\", U+201C/U+201D to '\"' and U+00A0 to a space in both the output text and the signature; the "
    "decision lexicon, trapRouted and validClaimSuppressed are unchanged. All values in % unless marked k/n; POST HOC sensitivity checks."
)


def fmt_prop(p):
    return f"{p['k']}/{p['n']} ({pct(p['p'])} [{pct(p['lo'])}, {pct(p['hi'])}])"


def fmt_tr(t):
    d = t["pairedDiffAfterMinusBefore"]
    ci = (f"[{100 * d['lo']:+.1f}, {100 * d['hi']:+.1f}] pp" if t["repaired"] + t["new"]
          else "pp (no discordant pairs; no interval reported)")
    return (f"{t['repaired']} / {t['new']} / {t['unchangedFail']} / {t['unchangedPass']}; clearance {t['clearance']['k']}/{t['clearance']['n']} "
            f"({pct(t['clearance']['p'])} [{pct(t['clearance']['lo'])}, {pct(t['clearance']['hi'])}]); diff {100 * d['diff']:+.1f} "
            f"{ci}; p = {t['exactP']:.2e}")


def fmt_rd(r):
    return f"{pct(r['c2'], 2)} → {pct(r['c4'], 2)}, {100 * r['diff']:+.2f} pp [{100 * r['lo']:+.2f}, {100 * r['hi']:+.2f}] (n = {r['pairedN']})"


def render_md(rep):
    md = ["# Sensitivity analyses (generated by sensitivity.py)", "", DEFS, "",
          f"Integrity checks: the unpatched re-score reproduces every run's score_rows.jsonl on {rep['checks']['goldFieldsChecked']} gold-anchored "
          "field values (15 formal runs x 144 cases x 11 fields); full-set C0->C4 / C2->C4 transitions and the C2->C4 retention bootstrap equal "
          "tab4_stats.json.", ""]
    d = rep["devExclusion"]
    md += ["## 1. Development-set exclusion", "",
           f"Development cases ({len(d['caseIds'])}, all present in benchmark/v4/cases; same ids as the C2 pilot: {d['sameIdsAsC2Pilot']}): "
           + ", ".join(f"{x['caseId'][:8]} ({x['family']}, {'risk' if x['controlStatus'] == RISK else 'control'})" for x in d["cases"]) + ".", "",
           "| Model | Set | C0 trap | C2 trap | C4 trap | C4 control retention |", "|---|---|---|---|---|---|"]
    for m in MODEL_ORDER:
        for key, label in (("full", "all 144"), ("excludingDev", "excluding dev")):
            s = d["models"][m][key]
            rt = s["controlRetention"]["C4"]
            md.append(f"| {m} | {label} | {fmt_prop(s['trapFellAny']['C0'])} | {fmt_prop(s['trapFellAny']['C2'])} | {fmt_prop(s['trapFellAny']['C4'])} | "
                      f"{pct(rt['mean'], 2)} (n = {rt['n']}) |")
    md += ["", "Transitions (repaired / new / unchanged fail / unchanged pass; clearance; C4 − A paired difference; exact McNemar p):", "",
           "| Model | Set | C2 → C4 | C0 → C4 | C2 → C4 control retention |", "|---|---|---|---|---|"]
    for m in MODEL_ORDER:
        for key, label in (("full", "all 144"), ("excludingDev", "excluding dev")):
            s = d["models"][m][key]
            md.append(f"| {m} | {label} | {fmt_tr(s['C2->C4'])} | {fmt_tr(s['C0->C4'])} | {fmt_rd(s['controlRetentionC2toC4'])} |")
    md += ["", "The 6 development risk cases alone (trap failures k/6):", "", "| Model | C0 | C1 | C2 | C5 | C4 |", "|---|---|---|---|---|---|"]
    for m in MODEL_ORDER:
        r = d["models"][m]["devRiskCases"]
        md.append(f"| {m} | " + " | ".join(f"{r[c]['k']}/{r[c]['n']}" for c in ("C0", "C1", "C2", "C5", "C4")) + " |")
    md += ["", "Other conditions after exclusion (trap failure): " + "; ".join(
        f"{m} C1 {fmt_prop(d['models'][m]['excludingDev']['trapFellAny']['C1'])}, C5 {fmt_prop(d['models'][m]['excludingDev']['trapFellAny']['C5'])}"
        for m in MODEL_ORDER) + ".", ""]

    lo = rep["liftOff"]
    cr = lo["c4Rebuild"]
    md += ["## 2. lift_string_items switched off (gpt-oss:20b)", "",
           "Bare-string claim items per condition (parsed bundles with any / total string items): " + "; ".join(
               f"{m} " + ", ".join(f"{c} {rep['stringCensus'][m][c]['bundlesWithStringItems']}/{rep['stringCensus'][m][c]['stringItems']}" for c in SCORED)
               for m in MODEL_ORDER) + ". Lifting is the identity on every parsed qwen bundle: " + str(rep["qwenLiftIdentity"]) + ".", "",
           "| Condition | Trap official | Trap lift off | Δk | Retention official | Retention lift off | Δ pp | Mean supported items (official → off) |",
           "|---|---|---|---|---|---|---|---|"]
    for c in SCORED:
        x = lo["conditions"][c]
        md.append(f"| {c} | {fmt_prop(x['trapFellAny']['official'])} | {fmt_prop(x['trapFellAny']['liftOff'])} | {x['trapFellAny']['deltaK']:+d} | "
                  f"{pct(x['controlRetention']['official']['mean'], 2)} | {pct(x['controlRetention']['liftOff']['mean'], 2)} | {x['controlRetention']['deltaPp']:+.2f} | "
                  f"{x['meanSupportedCount']['official']:.2f} → {x['meanSupportedCount']['liftOff']:.2f} |")
    lost = lo["conditions"]["C2"]["trapFellIdsLost"]
    md += ["", f"C2 trap failures that disappear without the lift ({len(lost)}): "
           + ", ".join(f"{i[:8]} ({lo['caseFamilies'][i]})" for i in lost)
           + "; in these outputs the trap signature occurs only in bare-string claim items, which the unlifted scorer does not read.", "",
           f"C2 → C4: official {fmt_tr(lo['C2->C4']['official'])}; lift off {fmt_tr(lo['C2->C4']['liftOff'])}.", "",
           f"C0 → C4: official {fmt_tr(lo['C0->C4']['official'])}; lift off {fmt_tr(lo['C0->C4']['liftOff'])}.", "",
           f"C2 → C4 control retention: official {fmt_rd(lo['controlRetentionC2toC4']['official'])}; lift off {fmt_rd(lo['controlRetentionC2toC4']['liftOff'])}.", "",
           "C4 under lift off is rebuilt offline, not re-generated: the frozen stage_c4_repair / stage_c4_finalize were first run unpatched and "
           f"reproduced all {cr['unpatchedReproducesStored']['records']} stored stage1/ and final/ records exactly "
           f"({cr['unpatchedReproducesStored']['stage1Mismatches']} and {cr['unpatchedReproducesStored']['finalMismatches']} mismatches). With the lift off, "
           f"{len(cr['liftOffNeedsRegeneration'])} output(s) need regeneration ({', '.join(x[:8] for x in cr['liftOffNeedsRegeneration']) or 'none'}; "
           f"official: {', '.join(x[:8] for x in cr['officialRegenerations']) or 'none'}); "
           + "; ".join(f"{k[:8]}: regeneration request built under the patch byte-identical to the stored request = {v['requestIdenticalToStored']}, "
                       f"stored regeneration output reused = {v['requestIdenticalToStored'] and v['storedOutputAvailable']}" for k, v in cr["regenerationReuse"].items())
           + f". Final aggregates lift off {cr['liftOffAggregate']} (official {cr['officialAggregate']}), not repairable {cr['liftOffNotRepairable']}. "
           f"Without the lift the {cr['stringItemsInC2RawOutputs']} bare-string items of the C2 outputs are invisible to the detectors, and the schema "
           "conformance step of the repair (triggered by the raw schema failure) keeps only object items, so they are deleted instead of routed to "
           f"unsupportedClaims; {cr['stringItemsLeftInLiftOffC4']} string items remain. {cr['liftOffC4BundlesDifferingFromOfficial']} of 144 rebuilt C4 bundles differ "
           f"from the official ones, but the gold-anchored fields change in {sum(cr['liftOffC4GoldFieldChangesVsOfficial'].values())} case-field values "
           f"({ {k: v for k, v in cr['liftOffC4GoldFieldChangesVsOfficial'].items() if v} or 'none'}), and scoring the rebuilt C4 with the lifting scorer "
           f"gives identical gold fields: {cr['liftOffC4ScoredWithLiftingScorerIdentical']}. Repair actions (action|rule|code: count) official "
           f"{cr['repairActions']['official']}; lift off {cr['repairActions']['liftOff']}.", ""]

    u = rep["unicode"]
    md += ["## 3. Unicode punctuation normalisation", "",
           f"Gold signatures: {u['goldSignatures']['total']} (trap, anywhere and valid-claim), {u['goldSignatures']['withAsciiHyphenOrApostrophe']} contain an ASCII hyphen or "
           f"apostrophe, {u['goldSignatures']['withMappedCharacter']} contain a mapped character.", "",
           "| Model | Condition | Trap official | Trap normalised | Retention official | Retention normalised | Δ pp | Bundles with mapped char on supported side |",
           "|---|---|---|---|---|---|---|---|"]
    for m in MODEL_ORDER:
        for c in SCORED:
            x = u["models"][m]["conditions"][c]
            md.append(f"| {m} | {c} | {fmt_prop(x['trapFellAny']['official'])} | {fmt_prop(x['trapFellAny']['normalised'])} | "
                      f"{pct(x['controlRetention']['official']['mean'], 2)} | {pct(x['controlRetention']['normalised']['mean'], 2)} | {x['controlRetention']['deltaPp']:+.2f} | "
                      f"{x['bundlesWithMappedCharOnSupportedSide']} |")
    for m in MODEL_ORDER:
        e = u["models"][m]
        moves = [f"{c} +{', '.join(i[:8] for i in e['conditions'][c]['trapFellIdsGained'])}" for c in SCORED if e["conditions"][c]["trapFellIdsGained"]]
        moves += [f"{c} −{', '.join(i[:8] for i in e['conditions'][c]['trapFellIdsLost'])}" for c in SCORED if e["conditions"][c]["trapFellIdsLost"]]
        if moves:
            md += ["", f"{m}: trap failures added (+) or removed (−) by the normalisation: " + "; ".join(moves) + " (families: "
                   + ", ".join(f"{i[:8]} {f}" for i, f in e["caseFamilies"].items()) + ")."]
    md += ["", "| Model | C2 → C4 official | C2 → C4 normalised | Retention C2 → C4 official | Retention C2 → C4 normalised |", "|---|---|---|---|---|"]
    for m in MODEL_ORDER:
        e = u["models"][m]
        md.append(f"| {m} | {fmt_tr(e['C2->C4']['official'])} | {fmt_tr(e['C2->C4']['normalised'])} | {fmt_rd(e['controlRetentionC2toC4']['official'])} | "
                  f"{fmt_rd(e['controlRetentionC2toC4']['normalised'])} |")
    diffs = sum(u["models"][m]["conditions"][c]["rawNegationVariantDiffers"] for m in MODEL_ORDER for c in SCORED)
    md += ["", f"Negation in the normalised match is checked on the mapped text; checking it on the unmapped text instead changes {diffs} per-case "
           "trapFellAny / validClaimPreserved values across all models and conditions.", ""]
    return "\n".join(md) + "\n"


def main():
    ctx = Ctx()
    checked = assert_reproduces(ctx)
    assert_tab4(ctx)
    census = string_census(ctx)
    qwen_identity = all(census[m][c]["liftIsIdentity"] == census[m][c]["parsedBundles"] and census[m][c]["stringItems"] == 0
                        for m in MODEL_ORDER if m != LIFT_MODEL for c in SCORED)
    rep = {"script": "analysis/sensitivity.py", "posthoc": True, "models": list(MODEL_ORDER),
           "runs": {m: ctx.runs[m] for m in MODEL_ORDER},
           "checks": {"goldFieldsChecked": checked, "scoreRowsReproduced": True, "tab4StatsReproduced": True},
           "stringCensus": census, "qwenLiftIdentity": qwen_identity,
           "devExclusion": dev_exclusion(ctx), "liftOff": lift_off(ctx), "unicode": unicode_norm(ctx)}
    (HERE / "sensitivity.json").write_text(json.dumps(rep, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md = render_md(rep)
    (HERE / "sensitivity.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
