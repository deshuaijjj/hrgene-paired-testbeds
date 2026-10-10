#!/usr/bin/env python3
"""Setup facts for the method section: model identities, condition facts, contract coverage, benchmark freeze,
the two deliberately lexicon-blind qualification cases, and (2026-09-23) source-type facts.

Everything is read from frozen files (experiments/*/config.json, outputs, validations, benchmark/v4, rules/, runtime/,
machine/). Nothing in those directories is written. The C2->C4 counterfactual replays the frozen repairer on the frozen
C2 outputs with a filtered finding list, in memory only; no model is called.

Source-type facts (section 6, added 2026-09-23 in response to a reviewer question): counts of the three source types
(resume items, work samples, notes); which sources are baits, i.e. carry a gold trap signature (case-insensitive
substring occurrence of any gold trap.signatures / anywhereSignatures phrase in the source text; the gold
trap.baitSourceIds list is reported next to it); how many baits and control notes the validator's lexicon classes as
subjective or hearsay (runtime/hrgene/detectors.py subjective_source_ids); where the controls' valid-claim signatures
occur; and, per model, which rule FAILs the C2 supported-side items that carry a trap signature (the item-level
definition of repair_anatomy.py, re-derived here and asserted equal to repair_anatomy.json).

    python3 setup_facts.py        # writes setup_facts.json and setup_facts.md next to this script
"""
import ast
import glob
import hashlib
import json
import os
import re
import statistics
import sys

sys.dont_write_bytecode = True   # no __pycache__ next to the analysis scripts
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
from hrgene import pipeline, scoring  # noqa: E402
from hrgene import bundle as B, detectors as D, textmatch as tm  # noqa: E402  (source-type facts, section 6)
from hrgene.repair import Repairer  # noqa: E402
from hrgene.validator import Validator  # noqa: E402

EXP = os.path.join(ROOT, "experiments")
BENCH = os.path.join(ROOT, "benchmark", "v4")
RULES_PATH = os.path.join(ROOT, "rules", "canonical-rules.v2.json")
LEX_PATH = os.path.join(ROOT, "rules", "lexicons.v2.json")
SCHEMA_PATH = os.path.join(ROOT, "schema", "paired-review-bundle.v2.schema.json")
DETECTORS_PY = os.path.join(ROOT, "runtime", "hrgene", "detectors.py")
VALIDATOR_PY = os.path.join(ROOT, "runtime", "hrgene", "validator.py")
MACHINE_HW = os.path.join(ROOT, "machine", "macstudio_ollama_20260829.txt")
MACHINE_OLLAMA = os.path.join(ROOT, "machine", "macstudio_ollama_20260829_b.txt")
MACHINE_BENCH = os.path.join(ROOT, "machine", "macstudio_qwen3_bench_20260829.txt")

MODELS = [("gpt-oss:20b", "20260906-gpt-oss-20b"), ("qwen3:8b", "20260906-qwen3-8b"), ("qwen3:30b-a3b", "20260919-qwen3-30b-a3b")]
GEN_CONDS = ["C0", "C1", "C2", "C5"]
ALL_CONDS = ["C0", "C1", "C2", "C3", "C4", "C5"]
RISK, CONTROL = "positive_risk", "matched_clean_control"
DECISION_FAMILY = "decision_ranking_protected_human_review_boundary"
BLIND_PREFIXES = ["c6f939db", "d6c36309"]           # benchmark/v4/README.md, authoring conventions
RECORDED_FREEZE_DIGEST16 = "f11ee4c8b69aa664"        # RECORDS.md 2026-09-06 "基准冻结" entry (the value this script re-derives)
C2_HEADER_PHRASES = ["an independent validator will check", "sends the output back for repair"]

# Hand-assigned semantic counterparts: an implemented code whose behaviour is the one described by a declared check of
# the same rule but under a different name. Assigned by reading detectors.py; used ONLY for the secondary ("lenient")
# counterfactual. The primary coverage numbers use exact name matching.
COUNTERPART = {
    "production_not_stated_by_sources": "production_term_licensed",        # detect_deployment_boundary, no NONPRODUCTION in sources
    "nonproduction_rewritten_as_production": "production_term_licensed",   # same check; description names this case
    "subjective_term_on_supported_side": "no_subjective_terms_on_supported_side",
    "subjective_source_cited_as_support": "subjective_sources_not_cited_as_support",
    "participation_upgraded_to_ownership": "ownership_family_licensed",    # relabel of an ownership_family_licensed finding
    "years_exceed_sources": "qualification_family_licensed",               # the YEARS clause of that check's description
}


def rel(p):
    return os.path.relpath(p, ROOT)


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_by_case(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        o = load_json(f)
        out[o["caseId"]] = o
    return out


def run_dir(prefix, cond):
    return os.path.join(EXP, f"{prefix}-{cond}-full")


def outputs_by_case(prefix, cond):
    out = {}
    for f in sorted(glob.glob(os.path.join(run_dir(prefix, cond), "outputs", "*.r0.json"))):
        o = load_json(f)
        out[o["case_id"]] = o
    return out


def score_rows(prefix, cond):
    return {r["caseId"]: r for r in load_jsonl(os.path.join(run_dir(prefix, cond), "score_rows.jsonl"))}


def by_request_dir(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        o = load_json(f)
        out[o["case_id"]] = o
    return out


def pct(k, n):
    return round(100.0 * k / n, 1) if n else None


# ============================================================ 1. model identity
def model_identity():
    rows = []
    for model, prefix in MODELS:
        cfgs = [(c, run_dir(prefix, c)) for c in GEN_CONDS]
        regen = os.path.join(run_dir(prefix, "C4"), "regen")
        if os.path.exists(os.path.join(regen, "config.json")):
            cfgs.append(("C4-regeneration", regen))
        per_run = []
        for cond, d in cfgs:
            c = load_json(os.path.join(d, "config.json"))
            ident = c.get("identity") or {}
            det = ident.get("details") or {}
            n_out = len(glob.glob(os.path.join(d, "outputs", "*.r0.json")))
            outs = [load_json(f) for f in sorted(glob.glob(os.path.join(d, "outputs", "*.r0.json")))]
            per_run.append({
                "run": rel(d), "condition": cond,
                "tag": ident.get("model"), "quantization": det.get("quantization_level"), "parameterSize": det.get("parameter_size"),
                "family": det.get("family"), "format": det.get("format"), "contextLengthModel": det.get("context_length"),
                "sizeBytes": ident.get("size_bytes"), "digest": ident.get("digest"), "ollamaVersion": ident.get("ollama_version"),
                "modelfileParameters": " ".join((ident.get("parameters_from_modelfile") or "").split()),
                "think": str(c.get("think")).lower(), "temperature": (c.get("options") or {}).get("temperature"),
                "seed": c.get("seed_base"), "numCtx": (c.get("options") or {}).get("num_ctx"),
                "numPredict": (c.get("options") or {}).get("num_predict"), "repeat": c.get("repeat"), "keepAlive": c.get("keep_alive"),
                "runnerSha256": c.get("runner_sha256"), "requestsSha256": c.get("requests_sha256"), "nRequests": c.get("n_requests"),
                "nOutputs": n_out,
                "outputsDigestMismatch": sum(1 for o in outs if o.get("digest") != ident.get("digest")),
                "outputsModelMismatch": sum(1 for o in outs if o.get("model") != ident.get("model")),
                "outputsSeedMismatch": sum(1 for o in outs if str(o.get("seed")) != str(c.get("seed_base"))),
            })
        keys = ["tag", "quantization", "parameterSize", "family", "digest", "ollamaVersion", "think", "temperature", "seed", "numCtx",
                "numPredict", "repeat", "keepAlive", "runnerSha256", "contextLengthModel", "sizeBytes", "modelfileParameters"]
        inconsistent = sorted(k for k in keys if len({json.dumps(r[k]) for r in per_run}) > 1)
        first = per_run[0]
        rows.append({
            "model": model, "tag": first["tag"], "quantization": first["quantization"], "parameterSize": first["parameterSize"],
            "digest12": (first["digest"] or "")[:12], "digest": first["digest"], "think": first["think"],
            "ollamaVersion": first["ollamaVersion"], "temperature": first["temperature"], "seed": first["seed"],
            "numCtx": first["numCtx"], "numPredict": first["numPredict"], "repeat": first["repeat"], "keepAlive": first["keepAlive"],
            "contextLengthModel": first["contextLengthModel"], "sizeBytes": first["sizeBytes"],
            "modelfileParameters": first["modelfileParameters"], "runner12": (first["runnerSha256"] or "")[:12],
            "fieldsInconsistentAcrossRuns": inconsistent,
            "runs": [{k: r[k] for k in ("run", "condition", "nRequests", "nOutputs", "outputsDigestMismatch", "outputsModelMismatch",
                                         "outputsSeedMismatch")} | {"requests12": (r["requestsSha256"] or "")[:12]} for r in per_run],
        })
    return rows


def hardware():
    hw = {}
    with open(MACHINE_HW, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*(Model Name|Chip|Memory):\s*(.+?)\s*$", line)
            if m:
                hw[{"Model Name": "machine", "Chip": "chip", "Memory": "memory"}[m.group(1)]] = m.group(2)
    hw["hardwareSource"] = rel(MACHINE_HW)
    with open(MACHINE_OLLAMA, encoding="utf-8") as f:
        txt = f.read()
    m = re.search(r"ollama version is (\S+)", txt)
    hw["ollamaVersionMachineFile"] = m.group(1) if m else None
    m = re.search(r"found: (\S+ollama)", txt)
    hw["ollamaBinary"] = m.group(1) if m else None
    m = re.search(r"^(\{\"models\".*\})\s*$", txt, re.M)
    local = json.loads(m.group(1))["models"] if m else []
    hw["modelsListedInMachineFile"] = [{"tag": x["name"], "digest12": x["digest"][:12], "parameterSize": x["details"]["parameter_size"],
                                        "quantization": x["details"]["quantization_level"]} for x in local]
    hw["ollamaSource"] = rel(MACHINE_OLLAMA)
    with open(MACHINE_BENCH, encoding="utf-8") as f:
        m = re.search(r"gen_tok/s\s+([0-9.]+)", f.read())
    hw["qwen3_8bGenTokPerSecSmoke"] = float(m.group(1)) if m else None
    hw["benchSource"] = rel(MACHINE_BENCH)
    hw["machineFilesDate"] = "2026-08-29 (file names)"
    return hw


# ============================================================ 2. condition facts
def request_files():
    return {c: load_jsonl(os.path.join(BENCH, "requests", f"{c}.jsonl")) for c in GEN_CONDS}


def words(s):
    return len(s.split())


def extract_block(rendered, rule_id):
    """The exact text of one rule block inside render_contract output (brace matching, string-aware)."""
    key = f'"rule": "{rule_id}"'
    k = rendered.index(key)
    start = rendered.rfind("{", 0, k)
    depth, i, in_str, esc = 0, start, False, False
    while i < len(rendered):
        ch = rendered[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return rendered[start:i + 1]
        i += 1
    raise ValueError("unbalanced block")


def condition_facts(reqs, rs, cases, gold):
    out = {}
    # --- C0 vs C5 request lines
    c0 = {r["request_id"].split(".")[0]: r for r in reqs["C0"]}
    c5 = {r["request_id"].split(".")[0]: r for r in reqs["C5"]}
    assert sorted(c0) == sorted(c5)
    key_counts, meta_counts, lines_diff = {}, {}, 0
    for cid in sorted(c0):
        a, b = c0[cid], c5[cid]
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        if diff:
            lines_diff += 1
        for k in diff:
            key_counts[k] = key_counts.get(k, 0) + 1
        for k in sorted(set(a.get("meta", {})) | set(b.get("meta", {}))):
            if a["meta"].get(k) != b["meta"].get(k):
                meta_counts[k] = meta_counts.get(k, 0) + 1
    c0_formats = sorted({json.dumps(r["format"])[:40] for r in reqs["C0"]})
    c5_formats = sorted({hashlib.sha256(json.dumps(r["format"], sort_keys=True).encode()).hexdigest()[:12] for r in reqs["C5"]})
    schema_obj = load_json(SCHEMA_PATH)
    c5_is_schema = all(r["format"] == schema_obj for r in reqs["C5"])
    out["c0VsC5Requests"] = {"nLines": len(c0), "linesWithAnyDifference": lines_diff, "differingTopLevelKeys": key_counts,
                             "differingMetaKeys": meta_counts, "c0FormatValues": c0_formats, "c5FormatSha12": c5_formats,
                             "c5FormatEqualsBundleSchemaFile": c5_is_schema, "bundleSchemaFile": rel(SCHEMA_PATH)}
    # --- C0 vs C5 outputs, byte-identical content
    ident = {}
    for model, prefix in MODELS:
        o0, o5 = outputs_by_case(prefix, "C0"), outputs_by_case(prefix, "C5")
        s0, s5 = score_rows(prefix, "C0"), score_rows(prefix, "C5")
        same = {cid for cid in o0 if cid in o5 and o0[cid]["content"].encode("utf-8") == o5[cid]["content"].encode("utf-8")}
        risk = {cid for cid in o0 if gold[cid]["controlStatus"] == RISK}
        diff_risk = sorted(risk - same)
        discord = [cid for cid in diff_risk if s0[cid]["trapFellAny"] != s5[cid]["trapFellAny"]]
        ident[model] = {"identical": len(same), "n": len(o0), "identicalRisk": len(same & risk), "nRisk": len(risk),
                        "identicalControl": len(same - risk), "nControl": len(set(o0) - risk),
                        "nonIdenticalRisk": len(diff_risk), "nonIdenticalRiskTrapDiscordant": len(discord),
                        "nonIdenticalRiskTrapDiscordantCases": [c[:8] for c in discord]}
    out["c0VsC5OutputsByteIdentical"] = ident
    # --- prompt words (meta.promptWords = whitespace-split words over system + user messages)
    pw = {}
    for c in GEN_CONDS:
        vals = [r["meta"]["promptWords"] for r in reqs[c]]
        recomputed = [sum(words(m["content"]) for m in r["messages"]) for r in reqs[c]]
        chars = [r["meta"]["promptChars"] for r in reqs[c]]
        pw[c] = {"median": statistics.median(vals), "min": min(vals), "max": max(vals), "n": len(vals),
                 "metaEqualsRecomputed": vals == recomputed, "charsMedian": statistics.median(chars)}
    manifest = load_json(os.path.join(BENCH, "requests", "manifest.json"))
    for c in GEN_CONDS:
        pw[c]["manifestMedian"] = manifest["conditions"][c]["promptWords"]["median"]
    by_case = {c: {r["request_id"].split(".")[0]: r for r in reqs[c]} for c in GEN_CONDS}
    paired = [by_case["C2"][cid]["meta"]["promptWords"] - by_case["C1"][cid]["meta"]["promptWords"] for cid in sorted(by_case["C2"])]
    rule_words = {"C1": [], "C2": []}
    render_matches = {"C1": 0, "C2": 0}
    for cid in sorted(by_case["C0"]):
        sys0 = by_case["C0"][cid]["messages"][0]["content"]
        for c, fn in (("C1", rs.render_prose), ("C2", rs.render_contract)):
            sysc = by_case[c][cid]["messages"][0]["content"]
            rendered = fn(cases[cid])
            if sysc == sys0 + "\n\n" + rendered and by_case[c][cid]["messages"][1] == by_case["C0"][cid]["messages"][1]:
                render_matches[c] += 1
            rule_words[c].append(words(sysc) - words(sys0))
    pw["pairedC2minusC1"] = {"median": statistics.median(paired), "min": min(paired), "max": max(paired), "n": len(paired)}
    pw["rulesSectionWords"] = {c: {"median": statistics.median(v), "min": min(v), "max": max(v)} for c, v in rule_words.items()}
    pw["requestsEqualC0PlusRuntimeRendering"] = render_matches
    out["promptWords"] = pw
    # --- C2 header sentence
    hdr = {}
    for c in GEN_CONDS:
        hdr[c] = sum(1 for r in reqs[c] if all(p in r["messages"][0]["content"] for p in C2_HEADER_PHRASES))
    sample = reqs["C2"][0]["messages"][0]["content"]
    line = next(ln for ln in sample.split("\n") if C2_HEADER_PHRASES[0] in ln)
    out["c2ValidatorHeader"] = {"phrases": C2_HEADER_PHRASES, "requestsContainingBothPhrases": hdr, "headerLine": line}
    # --- per-rule obligation words, C1 prose vs C2 contract
    rendered_all = rs.render_contract(None, only_active=False)
    per_rule = []
    active_counts = {r["ruleId"]: 0 for r in rs.rules}
    for cid in sorted(cases):
        for r in rs.active_rules(cases[cid]):
            active_counts[r["ruleId"]] += 1
    for r in rs.rules:
        o = r["obligation"]
        must = sum(words(s) for s in o["mustDo"])
        mustnot = sum(words(s) for s in o["mustNot"])
        route = words(o["route"])
        block = extract_block(rendered_all, r["ruleId"])
        per_rule.append({"rule": r["ruleId"], "proseWords": words(o["prose"]), "mustDoWords": must, "mustNotWords": mustnot,
                         "routeWords": route, "contractObligationWords": must + mustnot + route, "contractBlockWords": words(block),
                         "activeInCases": active_counts[r["ruleId"]]})
    out["obligationWordsPerRule"] = per_rule
    out["obligationWordsTotal"] = {"prose": sum(x["proseWords"] for x in per_rule),
                                   "contractObligation": sum(x["contractObligationWords"] for x in per_rule),
                                   "contractBlock": sum(x["contractBlockWords"] for x in per_rule)}
    out["c2ExtraFieldsPerBlock"] = sorted(k for k in json.loads(rendered_all.split("\n", 1)[1])["rules"][0]
                                          if k not in ("rule", "must", "mustNot", "route"))
    out["c2TopLevelExtra"] = sorted(k for k in json.loads(rendered_all.split("\n", 1)[1]) if k != "rules")
    # --- requests sha256
    sha = {}
    for c in GEN_CONDS:
        local = sha256_file(os.path.join(BENCH, "requests", f"{c}.jsonl"))
        per_model = {}
        for model, prefix in MODELS:
            per_model[model] = load_json(os.path.join(run_dir(prefix, c), "config.json"))["requests_sha256"][:12]
        sha[c] = {"local12": local[:12], "byModel": per_model, "allModelsEqual": len(set(per_model.values())) == 1,
                  "equalsLocalFile": all(v == local[:12] for v in per_model.values())}
    out["requestsSha256"] = sha
    return out


# ============================================================ 3. contract coverage
def _const_strs(node):
    return sorted({n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)})


def static_codes():
    """Code literals the validator can emit, found by parsing detectors.py and validator.py (no execution)."""
    tree = ast.parse(open(DETECTORS_PY, encoding="utf-8").read())
    consts, registry = {}, {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            t, v = node.targets[0], node.value
            if isinstance(t, ast.Tuple) and isinstance(v, ast.Tuple):
                for a, b in zip(t.elts, v.elts):
                    if isinstance(a, ast.Name) and isinstance(b, ast.Constant):
                        consts[a.id] = b.value
            elif isinstance(t, ast.Name) and isinstance(v, ast.Constant):
                consts[t.id] = v.value
            elif isinstance(t, ast.Name) and t.id == "DETECTORS":
                for el in v.elts:
                    registry[el.elts[1].id] = el.elts[0].value
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    def params(fn):
        a = fn.args
        names = [x.arg for x in a.args]
        defaults = dict(zip(names[len(names) - len(a.defaults):], a.defaults))
        return names, defaults

    def sev_of(node, fn):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in consts:
                return consts[node.id]
            names, defaults = params(fn)
            if node.id in defaults and isinstance(defaults[node.id], ast.Name):
                return "param (default " + str(consts.get(defaults[node.id].id)) + ")"
        return "unresolved"

    helpers = {}
    for name, fn in funcs.items():
        if name in registry:
            continue
        names, defaults = params(fn)
        for call in ast.walk(fn):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "finding":
                ca = call.args[1]
                if isinstance(ca, ast.Name) and ca.id in names:
                    sev = sev_of(call.args[2], fn)
                    sev_param = call.args[2].id if isinstance(call.args[2], ast.Name) and call.args[2].id in names else None
                    helpers[name] = {"codeIndex": names.index(ca.id), "severity": sev, "severityParam": sev_param,
                                     "severityDefault": consts.get(defaults[sev_param].id) if sev_param else None}
    found = []
    for name, fn in funcs.items():
        if name not in registry:
            continue
        rule = registry[name]
        local_assign = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
                local_assign.setdefault(n.targets[0].id, []).append(n.value)
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id == "finding":
                    ca = n.args[1]
                    sev = sev_of(n.args[2], fn)
                    if isinstance(ca, ast.Constant):
                        found.append((ca.value, rule, name, sev, "finding() literal", n.lineno))
                    elif isinstance(ca, ast.Name) and ca.id in local_assign:
                        for v in local_assign[ca.id]:
                            for s in _const_strs(v):
                                found.append((s, rule, name, sev, "finding() via local variable", n.lineno))
                elif n.func.id in helpers:
                    h = helpers[n.func.id]
                    ca = n.args[h["codeIndex"]]
                    sev = h["severity"]
                    if h["severityParam"]:
                        kw = {k.arg: k.value for k in n.keywords}
                        sev = sev_of(kw[h["severityParam"]], fn) if h["severityParam"] in kw else h["severityDefault"]
                    if isinstance(ca, ast.Constant):
                        found.append((ca.value, rule, name, sev, f"code argument of {n.func.id}()", n.lineno))
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Subscript):
                sl = n.targets[0].slice
                if isinstance(sl, ast.Constant) and sl.value == "code" and isinstance(n.value, ast.Constant):
                    found.append((n.value.value, rule, name, "inherited from the relabelled finding", "relabel f['code'] = ...", n.lineno))
    vtree = ast.parse(open(VALIDATOR_PY, encoding="utf-8").read())
    for n in ast.walk(vtree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "finding":
            if all(isinstance(a, ast.Constant) for a in n.args[:3]):
                found.append((n.args[1].value, n.args[0].value, "Validator.validate", n.args[2].value, "finding() literal (validator.py)", n.lineno))
    codes = {}
    for code, rule, fn, sev, how, line in found:
        e = codes.setdefault(code, {"code": code, "rules": set(), "functions": set(), "severities": set(), "how": set(), "lines": set()})
        e["rules"].add(rule)
        e["functions"].add(fn)
        e["severities"].add(sev)
        e["how"].add(how)
        e["lines"].add(("validator.py:" if fn == "Validator.validate" else "detectors.py:") + str(line))
    for e in codes.values():
        for k in ("rules", "functions", "severities", "how", "lines"):
            e[k] = sorted(e[k])
    sev_decl = {"CRIT/NONCRIT": {k: v for k, v in consts.items() if k in ("CRIT", "NONCRIT")}}
    return codes, sev_decl, registry


CONTRACT_KEYS = ("severity", "handling", "onFail", "repair", "maxRegenerations", "activation", "obligation", "validationTarget",
                 "checks", "requiresGold", "provenance")


def severity_reads():
    """Where the code base reads a 'severity' / 'handling' / 'onFail' key (AST, runtime/hrgene/*.py)."""
    rows = []
    for p in sorted(glob.glob(os.path.join(ROOT, "runtime", "hrgene", "*.py"))):
        tree = ast.parse(open(p, encoding="utf-8").read())
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for n in ast.walk(fn):
                key = None
                if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value in CONTRACT_KEYS:
                    key = n.slice.value
                    obj = ast.unparse(n.value)
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" and n.args \
                        and isinstance(n.args[0], ast.Constant) and n.args[0].value in CONTRACT_KEYS:
                    key = n.args[0].value
                    obj = ast.unparse(n.func.value)
                if key:
                    kind = ("rule contract (rules/canonical-rules.v2.json)" if p.endswith("rules.py")
                            else "validator finding" if obj == "f" else "output bundle item")
                    rows.append({"file": rel(p), "function": fn.name, "key": key, "object": obj, "line": n.lineno, "reads": kind})
    uniq = {}
    for r in rows:
        uniq[(r["file"], r["function"], r["key"], r["object"])] = r
    return sorted(uniq.values(), key=lambda r: (r["file"], r["line"], r["key"]))


def detectors_gated_by_activation():
    """True if the loop over DETECTORS in validator.py refers to the activation result (it would then skip inactive rules)."""
    tree = ast.parse(open(VALIDATOR_PY, encoding="utf-8").read())
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For) and "DETECTORS" in ast.unparse(n.iter)]
    return {"loopsOverDETECTORS": len(loops),
            "loopBodyMentionsActivation": any("activation" in ast.unparse(b) for n in loops for b in n.body)}


def observed_codes():
    """(rule, code) -> {severity, status, count} over C3 validations and C4 stage1 before/after + final validations."""
    obs = {}
    for model, prefix in MODELS:
        srcs = []
        for f in sorted(glob.glob(os.path.join(run_dir(prefix, "C3"), "validations", "*.json"))):
            srcs.append(("C3", load_json(f)["validation"]))
        for f in sorted(glob.glob(os.path.join(run_dir(prefix, "C4"), "stage1", "*.json"))):
            s = load_json(f)
            srcs.append(("C4.before", s["before"]))
            if s.get("after"):
                srcs.append(("C4.after", s["after"]))
        for f in sorted(glob.glob(os.path.join(run_dir(prefix, "C4"), "final", "*.json"))):
            s = load_json(f)
            if s.get("validation"):
                srcs.append(("C4.final", s["validation"]))
        for where, val in srcs:
            for fd in val.get("findings", []):
                e = obs.setdefault(fd["code"], {"rules": set(), "severities": set(), "statuses": set(), "count": 0, "models": set(), "where": set()})
                e["rules"].add(fd["rule"])
                e["severities"].add(fd["severity"])
                e["statuses"].add(fd["status"])
                e["models"].add(model)
                e["where"].add(where)
                e["count"] += 1
    return {k: {kk: (sorted(vv) if isinstance(vv, set) else vv) for kk, vv in v.items()} for k, v in obs.items()}


def replay_counterfactual(v, cases, gold, keep_code):
    """For each model: C2 risk cases whose trap C4 cleared. Replay the frozen C4 repair on the frozen C2 output with
    findings restricted to `keep_code(code)`, score the repaired bundle with the frozen scorer."""
    res = {}
    for model, prefix in MODELS:
        s2, s4 = score_rows(prefix, "C2"), score_rows(prefix, "C4")
        o2 = outputs_by_case(prefix, "C2")
        stage1 = by_request_dir(os.path.join(run_dir(prefix, "C4"), "stage1"))
        final = by_request_dir(os.path.join(run_dir(prefix, "C4"), "final"))
        cleared = sorted(c for c, r in s2.items() if r["controlStatus"] == RISK and r["trapFellAny"] and s4[c]["trapFellAny"] is False)
        lost, regen_needed, rows = [], [], []
        for cid in cleared:
            case, g = cases[cid], gold[cid]
            bundle = pipeline.parse_output(o2[cid]["content"])
            val = v.validate(case, bundle)
            assert val["findings"] == stage1[cid]["before"]["findings"], f"{model} {cid}: replayed C2 validation differs from C4 stage1"
            assert not final[cid].get("regenerated"), f"{model} {cid}: regenerated case in the cleared set"
            full_rep, _ = Repairer(v.rs, case).repair(bundle, val["findings"])
            assert scoring.score_bundle(case, g, full_rep, None, v.rs.lex)["trapFellAny"] is False, f"{model} {cid}: full replay does not clear"
            kept = [f for f in val["findings"] if keep_code(f["code"])]
            rep, _ = Repairer(v.rs, case).repair(bundle, kept)
            fell = scoring.score_bundle(case, g, rep, None, v.rs.lex)["trapFellAny"]
            after = v.validate(case, rep)
            crit_kept = any(f["status"] == "FAIL" and f["severity"] == "critical" and keep_code(f["code"]) for f in after["findings"])
            dropped_codes = sorted({f["code"] for f in val["findings"] if f["status"] == "FAIL" and not keep_code(f["code"])})
            rows.append({"case": cid[:8], "family": g["family"], "clearedUnderFilter": not fell, "droppedFailCodes": dropped_codes,
                         "stillBlockUnderFilteredValidator": crit_kept})
            if fell:
                lost.append(cid[:8])
                if crit_kept:
                    regen_needed.append(cid[:8])
        res[model] = {"clearedActual": len(cleared), "clearedUnderFilter": len(cleared) - len(lost), "dependOnFilteredChecks": len(lost),
                      "dependCases": lost, "dependCasesFamilies": sorted({r["family"] for r in rows if not r["clearedUnderFilter"]}),
                      "ofWhichFilteredValidatorWouldStillBlock": len(regen_needed), "cases": rows}
    return res


def contract_coverage(rs, v, cases, gold):
    declared, gold_only = {}, []
    for r in rs.rules:
        for c in r["validationTarget"]["checks"]:
            if c.get("requiresGold"):
                gold_only.append({"rule": r["ruleId"], "id": c["id"]})
            else:
                declared.setdefault(c["id"], set()).add(r["ruleId"])
    static, sev_decl, registry = static_codes()
    obs = observed_codes()
    impl = sorted(set(static) | set(obs))
    decl_ids = set(declared)
    declared_not_impl = sorted(decl_ids - set(impl))
    impl_not_declared = sorted(set(impl) - decl_ids)
    rule_sev = {r["ruleId"]: r["severity"] for r in rs.rules}
    rule_onfail = {r["ruleId"]: r["handling"]["onFail"] for r in rs.rules}
    table = []
    for code in impl:
        st = static.get(code)
        ob = obs.get(code)
        rules = sorted(set((st or {}).get("rules", [])) | set((ob or {}).get("rules", [])))
        emitted = sorted(set(s for s in (ob or {}).get("severities", [])) | {s for s in (st or {}).get("severities", []) if s in ("critical", "noncritical")})
        table.append({"code": code, "rules": rules, "declared": code in decl_ids, "declaredUnderRules": sorted(declared.get(code, [])),
                      "counterpartOfDeclared": COUNTERPART.get(code), "inStaticParse": st is not None, "observedInRuns": ob is not None,
                      "observedCount": (ob or {}).get("count", 0), "observedStatuses": (ob or {}).get("statuses", []),
                      "staticSeverity": (st or {}).get("severities", []), "emittedSeverities": emitted,
                      "ruleJsonSeverity": sorted({rule_sev[r] for r in rules if r in rule_sev}),
                      "severityDiffersFromRuleJson": any(s != rule_sev.get(r) for r in rules for s in emitted if r in rule_sev),
                      "sourceLines": (st or {}).get("lines", []), "how": (st or {}).get("how", [])})
    for code in declared_not_impl:
        table.append({"code": code, "rules": sorted(declared[code]), "declared": True, "declaredUnderRules": sorted(declared[code]),
                      "counterpartOfDeclared": None, "inStaticParse": False, "observedInRuns": False, "observedCount": 0,
                      "observedStatuses": [], "staticSeverity": [], "emittedSeverities": [], "ruleJsonSeverity": [rule_sev[r] for r in sorted(declared[code])],
                      "severityDiffersFromRuleJson": False, "sourceLines": [], "how": [],
                      "implementedUnder": sorted(k for k, c in COUNTERPART.items() if c == code)})
    table.sort(key=lambda r: (r["rules"][0] if r["rules"] else "", r["code"]))
    counter_codes = {k for k in COUNTERPART if k in impl_not_declared}
    strict = replay_counterfactual(v, cases, gold, lambda code: code in decl_ids)
    lenient = replay_counterfactual(v, cases, gold, lambda code: code in decl_ids or code in COUNTERPART)
    # descriptive: cleared cases whose C2 validation carries at least one undeclared FAIL code
    desc = {}
    for model, prefix in MODELS:
        s2, s4 = score_rows(prefix, "C2"), score_rows(prefix, "C4")
        stage1 = by_request_dir(os.path.join(run_dir(prefix, "C4"), "stage1"))
        cleared = sorted(c for c, r in s2.items() if r["controlStatus"] == RISK and r["trapFellAny"] and s4[c]["trapFellAny"] is False)
        und_crit = set()
        with_und, all_crit_und = 0, []
        for cid in cleared:
            fs = [f for f in stage1[cid]["before"]["findings"] if f["status"] == "FAIL"]
            u = {f["code"] for f in fs if f["code"] not in decl_ids}
            crit = [f for f in fs if f["severity"] == "critical"]
            und_crit |= {f["code"] for f in crit if f["code"] not in decl_ids}
            with_und += bool(u)
            if crit and all(f["code"] not in decl_ids for f in crit):
                all_crit_und.append(cid[:8])
        desc[model] = {"cleared": len(cleared), "withAnyUndeclaredFail": with_und, "undeclaredCriticalCodesSeen": sorted(und_crit),
                       "allCriticalFailsUndeclared": len(all_crit_und), "allCriticalFailsUndeclaredCases": all_crit_und}
    all_und_crit = sorted(set().union(*[set(d["undeclaredCriticalCodesSeen"]) for d in desc.values()]))
    return {
        "declaredChecks": {k: sorted(v) for k, v in sorted(declared.items())}, "goldOnlyChecks": gold_only,
        "nDeclared": len(decl_ids), "nGoldOnly": len(gold_only), "nImplemented": len(impl),
        "implementedStaticOnly": sorted(set(static) - set(obs)), "implementedObservedOnly": sorted(set(obs) - set(static)),
        "declaredNotImplemented": declared_not_impl, "implementedNotDeclared": impl_not_declared,
        "implementedNotDeclaredWithDeclaredCounterpart": sorted(counter_codes),
        "implementedNotDeclaredNoCounterpart": sorted(set(impl_not_declared) - counter_codes),
        "counterpartMap": COUNTERPART, "codeTable": table,
        "severity": {"detectorsConstants": sev_decl["CRIT/NONCRIT"], "keyReads": severity_reads(),
                     "codesWhoseSeverityDiffersFromRuleJson": sorted(r["code"] for r in table if r["severityDiffersFromRuleJson"]),
                     "detectorsOrValidatorReadRuleSeverity": any(x["reads"].startswith("rule contract") and
                                                                 x["file"].endswith(("detectors.py", "validator.py")) for x in severity_reads()),
                     "ruleSeverityReadIn": sorted({f"{x['file']}:{x['function']}" for x in severity_reads() if x["reads"].startswith("rule contract")}),
                     "contractKeysNeverRead": sorted(set(CONTRACT_KEYS) - {x["key"] for x in severity_reads()}),
                     "detectorLoop": detectors_gated_by_activation(),
                     "ruleJsonSeverity": rule_sev, "ruleJsonOnFail": rule_onfail,
                     "aggregateRule": "validator.py: BLOCK iff any FAIL finding with severity 'critical'; HUMAN_REVIEW iff any other FAIL/UNRESOLVED"},
        "detectorRegistry": registry,
        "clearedCasesUndeclared": desc, "undeclaredCriticalCodesInClearedCases": all_und_crit,
        "counterfactualStrict": strict, "counterfactualLenient": lenient,
    }


# ============================================================ 4. freeze
def freeze_facts():
    parts = []
    for sub in ("cases", "gold"):
        for f in sorted(glob.glob(os.path.join(BENCH, sub, "*.json"))):
            with open(f, "rb") as fh:
                parts.append(fh.read())
    digest = hashlib.sha256(b"".join(parts)).hexdigest()
    rules_sha = sha256_file(RULES_PATH)
    run_digests = set()
    for model, prefix in MODELS:
        for c in ALL_CONDS:
            p = os.path.join(run_dir(prefix, c), "score.json" if c not in ("C3",) else "summary.json")
            if os.path.exists(p):
                run_digests.add(load_json(p)["rulesetDigest"])
    req_digests = set()
    for c in GEN_CONDS:
        for r in load_jsonl(os.path.join(BENCH, "requests", f"{c}.jsonl")):
            req_digests.add(r["meta"]["rulesetDigest"])
    return {"algorithm": "sha256(concatenated bytes of cases/*.json sorted by file name, then gold/*.json sorted by file name)",
            "nCases": len(glob.glob(os.path.join(BENCH, "cases", "*.json"))), "nGold": len(glob.glob(os.path.join(BENCH, "gold", "*.json"))),
            "casesGoldDigest16": digest[:16], "recordedFreezeDigest16": RECORDED_FREEZE_DIGEST16,
            "matchesRecordedFreeze": digest[:16] == RECORDED_FREEZE_DIGEST16,
            "rulesFileSha256_12": rules_sha[:12], "rulesFile": rel(RULES_PATH),
            "rulesetDigestInRequests": sorted(d[:19] for d in req_digests), "rulesetDigestInRunScores": sorted(d[:19] for d in run_digests),
            "rulesFileMatchesRunDigests": all(d == "sha256:" + rules_sha for d in run_digests | req_digests),
            "lexiconsSha256_12": sha256_file(LEX_PATH)[:12], "outputSchemaSha256_12": sha256_file(SCHEMA_PATH)[:12],
            "note": "rulesetDigest hashes rules/canonical-rules.v2.json only; the lexicon and schema files are reported separately"}


# ============================================================ 5. lexicon-blind qualification cases
def blind_cases(v, cases, gold):
    ids = []
    for p in BLIND_PREFIXES:
        m = [c for c in sorted(cases) if c.startswith(p)]
        assert len(m) == 1, p
        ids.append(m[0])
    out = {}
    for cid in ids:
        g = gold[cid]
        rec = {"case": cid[:8], "family": g["family"], "controlStatus": g["controlStatus"], "trapSignatures": g["trap"]["signatures"],
               "trapRequirementIds": g["trap"]["requirementIds"], "byModel": {}}
        for model, prefix in MODELS:
            row = {}
            for cond in ALL_CONDS:
                if cond == "C3":
                    base = score_rows(prefix, "C2")[cid]
                    val = by_request_dir(os.path.join(run_dir(prefix, "C3"), "validations"))[cid]["validation"]
                elif cond == "C4":
                    base = score_rows(prefix, "C4")[cid]
                    val = by_request_dir(os.path.join(run_dir(prefix, "C4"), "final"))[cid]["validation"]
                else:
                    base = score_rows(prefix, cond)[cid]
                    o = outputs_by_case(prefix, cond)[cid]
                    b = pipeline.parse_output(o["content"])
                    val = v.validate(cases[cid], b, raw_text=o["content"] if b is None else None)
                qf = [f for f in val["findings"] if f["rule"] == "hrgene.qualification_boundary" and f["status"] == "FAIL"]
                assert len(qf) == base["failsByRule"].get("qualification_boundary", 0), (model, cond, cid)
                row[cond] = {"trapFellAny": base["trapFellAny"], "trapFellStrict": base["trapFellStrict"],
                             "trapRequirementOverclaimed": base["trapRequirementOverclaimed"], "qualificationFail": len(qf),
                             "qualificationCodes": sorted({f["code"] for f in qf})}
            rec["byModel"][model] = row
        out[cid[:8]] = rec
    summary = {}
    for cond in ALL_CONDS:
        summary[cond] = {"trapFell": sum(1 for r in out.values() for m in r["byModel"].values() if m[cond]["trapFellAny"]),
                         "cells": sum(1 for r in out.values() for m in r["byModel"].values()),
                         "qualificationFailCells": sum(1 for r in out.values() for m in r["byModel"].values() if m[cond]["qualificationFail"])}
    return {"cases": out, "summaryByCondition": summary}


# ============================================================ 6. source types, baits and the subjective rule
SOURCE_TYPES = ("resume", "work_sample", "note")
SUBJECTIVE_RULE = "hrgene.subjective_claim_boundary"


def _occurs(text, phrase):
    """Plain case-insensitive substring occurrence (no negation filter: a source 'carries' a phrase if it contains it)."""
    return phrase.lower() in (text or "").lower()


def _on_or_under(finding_path, unit):
    """Same rule as repair_anatomy.on_or_under: the finding sits on the unit or inside it."""
    return finding_path == unit or finding_path.startswith(unit + ".") or finding_path.startswith(unit + "[")


def _kn(k, n):
    return {"k": k, "n": n, "pct": pct(k, n)}


def item_level_subjective(lex, cases, gold, note_ids, bait_sig, bait_gold, subj_ids):
    """Per model: C2 supported-side entries (scoring._supported_texts on the lifted C2 bundle, one entry per path) that
    contain a gold trap signature (scoring._contains, i.e. non-negated) in a risk case; each FAIL finding of the C3
    validation of that output is assigned to the deepest entry whose path equals or contains its path (the primary
    definition of repair_anatomy.py). Counts which rules FAIL those entries, and what the entries cite."""
    ra = load_json(os.path.join(HERE, "repair_anatomy.json"))["models"]
    out = {}
    for model, prefix in MODELS:
        o2 = outputs_by_case(prefix, "C2")
        v3 = by_request_dir(os.path.join(run_dir(prefix, "C3"), "validations"))
        n_items = n_failed = 0
        rules, subj_codes = {}, {}
        subj_any = subj_only = 0
        cites = {"note": 0, "baitSig": 0, "baitGold": 0, "lexiconSubjective": 0, "noSource": 0}
        failed_cites = {"note": 0, "lexiconSubjective": 0}
        for cid in sorted(o2):
            g = gold[cid]
            if g["controlStatus"] != RISK:
                continue
            raw = pipeline.parse_output(o2[cid]["content"])
            if not isinstance(raw, dict):
                continue
            b = B.lift_string_items(raw)
            units = {}
            for p, t, sids in scoring._supported_texts(b):
                e = units.setdefault(p, {"texts": [], "sids": set()})
                e["texts"].append(t or "")
                e["sids"] |= {s for s in sids if isinstance(s, str)}
            fails = [x for x in v3[cid]["validation"]["findings"] if x["status"] == "FAIL"]
            on = {}
            for x in fails:
                cand = [u for u in units if _on_or_under(x["path"], u)]
                if cand:
                    on.setdefault(max(cand, key=len), []).append(x)
            for u, e in sorted(units.items()):
                if not any(scoring._contains(t, s, lex) for t in e["texts"] for s in g["trap"]["signatures"]):
                    continue
                n_items += 1
                sids = e["sids"]
                c_note = bool(sids & note_ids[cid])
                c_subj = bool(sids & subj_ids[cid])
                cites["note"] += c_note
                cites["baitSig"] += bool(sids & bait_sig[cid])
                cites["baitGold"] += bool(sids & bait_gold[cid])
                cites["lexiconSubjective"] += c_subj
                cites["noSource"] += not sids
                fu = on.get(u) or []
                if not fu:
                    continue
                n_failed += 1
                failed_cites["note"] += c_note
                failed_cites["lexiconSubjective"] += c_subj
                rs_ = sorted({x["rule"] for x in fu})
                for r in rs_:
                    rules[r.split(".")[-1]] = rules.get(r.split(".")[-1], 0) + 1
                if SUBJECTIVE_RULE in rs_:
                    subj_any += 1
                    subj_only += rs_ == [SUBJECTIVE_RULE]
                    for c in sorted({x["code"] for x in fu if x["rule"] == SUBJECTIVE_RULE}):
                        subj_codes[c] = subj_codes.get(c, 0) + 1
        ref = ra[model]["itemLevelC2"]["primary_entries_deepest"]
        assert (n_failed, n_items) == (ref["riskTrapItemsFailed"]["k"], ref["riskTrapItemsFailed"]["n"]), model
        assert rules == ref["riskTrapItemsFailedByRule"], model
        out[model] = {"trapItems": n_items, "trapItemsFailed": _kn(n_failed, n_items),
                      "failedBySubjectiveRule": _kn(subj_any, n_failed), "failedBySubjectiveRuleOnly": _kn(subj_only, n_failed),
                      "failedBySubjectiveCode": dict(sorted(subj_codes.items())), "failedByRule": dict(sorted(rules.items())),
                      "trapItemsCiting": {k: _kn(v, n_items) for k, v in cites.items()},
                      "failedItemsCiting": {k: _kn(v, n_failed) for k, v in failed_cites.items()},
                      "matchesRepairAnatomy": True}
    return out


def source_type_facts(v, cases, gold):
    lex = v.rs.lex
    counts = {st: {"all": 0, "risk": 0, "control": 0} for st in SOURCE_TYPES}
    other_types = {}
    composition = {}
    note_ids, bait_sig, bait_gold, subj_ids = {}, {}, {}, {}
    baits = {"sig": {st: 0 for st in SOURCE_TYPES}, "gold": {st: 0 for st in SOURCE_TYPES}}
    risk_cases_with_sig_bait, sig_bait_per_case = 0, {}
    sig_subset_gold, gold_without_sig = 0, 0
    subj = {"baitSig": 0, "baitGold": 0, "controlNote": 0, "riskNoteNotGoldBait": 0, "resume": 0, "work_sample": 0}
    subj_kind = {"baitGold": {"subjectiveOnly": 0, "hearsayOnly": 0, "both": 0}, "controlNote": {"subjectiveOnly": 0, "hearsayOnly": 0, "both": 0}}
    subj_bait_by_family = {}
    bait_by_family = {}
    n_risk_notes = n_control_notes = risk_notes_sig_bait = risk_notes_gold_bait = 0
    sig_loc = {"total": 0, "noteOnly": 0, "nonNoteSource": 0, "noSource": 0, "inOriginalCvMarkdown": 0, "inJobDescriptionOrRequirements": 0}
    jd_cases_by_family = {}
    cv_md_hits = []
    anywhere_subset = True
    vsig = {"control": {"total": 0, "onlyNote": 0, "noteAndOther": 0, "nonNoteOnly": 0, "noSource": 0, "onlyNoteNotInCvMarkdown": 0},
            "risk": {"total": 0, "onlyNote": 0, "noteAndOther": 0, "nonNoteOnly": 0, "noSource": 0, "onlyNoteNotInCvMarkdown": 0}}
    only_note_cases = []
    for cid in sorted(cases):
        case, g = cases[cid], gold[cid]
        side = "risk" if g["controlStatus"] == RISK else "control"
        ev = [e for e in case["candidate"]["evidence"] if isinstance(e, dict)]
        comp = {}
        for e in ev:
            st = e.get("sourceType")
            if st in counts:
                counts[st]["all"] += 1
                counts[st][side] += 1
            else:
                other_types[st] = other_types.get(st, 0) + 1
            comp[st] = comp.get(st, 0) + 1
        ckey = ", ".join(f"{k} {n}" for k, n in sorted(comp.items()))
        composition.setdefault(side, {})
        composition[side][ckey] = composition[side].get(ckey, 0) + 1
        ci = D.CaseIndex(case)
        sids_subj = D.subjective_source_ids(ci, lex)
        # re-derive the same set from its two lexicon families, to report which family matched
        kind = {}
        for e in ev:
            t = e.get("text", "") or ""
            s_hit, h_hit = bool(tm.family_hits(t, lex, "subjective", negation=True)), bool(tm.family_hits(t, lex, "hearsay"))
            if s_hit or h_hit:
                kind[e["sourceId"]] = "both" if (s_hit and h_hit) else ("subjectiveOnly" if s_hit else "hearsayOnly")
        assert set(kind) == sids_subj, cid
        subj_ids[cid] = sids_subj
        notes = {e["sourceId"] for e in ev if e.get("sourceType") == "note"}
        note_ids[cid] = notes
        for e in ev:
            if e.get("sourceType") in ("resume", "work_sample") and e["sourceId"] in sids_subj:
                subj[e["sourceType"]] += 1
        cv_md = case["candidate"].get("originalCvMarkdown") or ""
        rc = case.get("roleContext") or {}
        jd = " ".join([rc.get("jobDescription") or ""] + [r.get("text") or "" for r in rc.get("requirements") or [] if isinstance(r, dict)])
        if side == "risk":
            trap = g["trap"]
            anywhere = trap.get("anywhereSignatures") or []
            anywhere_subset &= set(anywhere) <= set(trap["signatures"])
            phrases = list(dict.fromkeys(list(trap["signatures"]) + list(anywhere)))
            sb = {e["sourceId"] for e in ev if any(_occurs(e.get("text"), p) for p in phrases)}
            gb = set(trap.get("baitSourceIds") or [])
            bait_sig[cid], bait_gold[cid] = sb, gb
            risk_cases_with_sig_bait += bool(sb)
            sig_bait_per_case[len(sb)] = sig_bait_per_case.get(len(sb), 0) + 1
            sig_subset_gold += sb <= gb
            gold_without_sig += len(gb - sb)
            fam = g["family"]
            for e in ev:
                st = e.get("sourceType")
                if e["sourceId"] in sb:
                    baits["sig"][st] = baits["sig"].get(st, 0) + 1
                    subj["baitSig"] += e["sourceId"] in sids_subj
                if e["sourceId"] in gb:
                    baits["gold"][st] = baits["gold"].get(st, 0) + 1
                    subj["baitGold"] += e["sourceId"] in sids_subj
                    bait_by_family[fam] = bait_by_family.get(fam, 0) + 1
                    if e["sourceId"] in sids_subj:
                        subj_bait_by_family[fam] = subj_bait_by_family.get(fam, 0) + 1
                        subj_kind["baitGold"][kind[e["sourceId"]]] += 1
                if st == "note":
                    n_risk_notes += 1
                    risk_notes_sig_bait += e["sourceId"] in sb
                    risk_notes_gold_bait += e["sourceId"] in gb
                    if e["sourceId"] not in gb:
                        subj["riskNoteNotGoldBait"] += e["sourceId"] in sids_subj
            for p in trap["signatures"]:
                where = {e.get("sourceType") for e in ev if _occurs(e.get("text"), p)}
                sig_loc["total"] += 1
                sig_loc["noteOnly"] += where == {"note"}
                sig_loc["nonNoteSource"] += bool(where - {"note"})
                sig_loc["noSource"] += not where
                if _occurs(cv_md, p):
                    sig_loc["inOriginalCvMarkdown"] += 1
                    line = next((ln.strip() for ln in cv_md.splitlines() if _occurs(ln, p)), "")
                    cv_md_hits.append({"case": cid[:8], "signature": p, "line": line})
                sig_loc["inJobDescriptionOrRequirements"] += _occurs(jd, p)
            if any(_occurs(jd, p) for p in trap["signatures"]):
                jd_cases_by_family[fam] = jd_cases_by_family.get(fam, 0) + 1
        else:
            bait_sig[cid], bait_gold[cid] = set(), set()
            for e in ev:
                if e.get("sourceType") == "note":
                    n_control_notes += 1
                    if e["sourceId"] in sids_subj:
                        subj["controlNote"] += 1
                        subj_kind["controlNote"][kind[e["sourceId"]]] += 1
        for p in g.get("validClaimSignatures") or []:
            where = {e.get("sourceType") for e in ev if _occurs(e.get("text"), p)}
            x = vsig[side]
            x["total"] += 1
            x["onlyNote"] += where == {"note"}
            x["noteAndOther"] += ("note" in where) and len(where) > 1
            x["nonNoteOnly"] += bool(where) and "note" not in where
            x["noSource"] += not where
            if where == {"note"} and not _occurs(cv_md, p):
                x["onlyNoteNotInCvMarkdown"] += 1
            if where == {"note"} and side == "control":
                only_note_cases.append({"case": cid[:8], "signature": p, "inOriginalCvMarkdown": _occurs(cv_md, p)})
    n_sig = sum(baits["sig"].values())
    n_gold = sum(baits["gold"].values())
    assert other_types == {}, other_types
    lexicon_subjective_types = sorted({e.get("sourceType") for cid in cases for e in cases[cid]["candidate"]["evidence"]
                                       if isinstance(e, dict) and e.get("sourceId") in subj_ids[cid]})
    return {
        "definitions": {
            "bait": "risk-case source whose text contains any gold trap.signatures or trap.anywhereSignatures phrase "
                    "(case-insensitive substring, no negation filter)",
            "baitGold": "source listed in the gold trap.baitSourceIds of its risk case",
            "lexiconSubjective": "source id returned by runtime/hrgene/detectors.py subjective_source_ids (subjective lexicon "
                                 "family with negation, or hearsay family), the set the subjective_claim_boundary rule treats "
                                 "as subjective or hearsay",
            "validSignatureLocation": "source types whose text contains the gold validClaimSignature (case-insensitive substring)",
            "itemLevel": "repair_anatomy.py primary definition (C2 supported-side entries; FAIL assigned to the deepest entry)"},
        "counts": counts, "compositionPerCase": {k: dict(sorted(v_.items())) for k, v_ in sorted(composition.items())},
        "nSources": sum(c["all"] for c in counts.values()),
        "anywhereSignaturesSubsetOfSignatures": anywhere_subset,
        "baitsBySignature": {"n": n_sig, "byType": baits["sig"], "noteShare": _kn(baits["sig"].get("note", 0), n_sig),
                             "riskCasesWithBait": _kn(risk_cases_with_sig_bait, sum(1 for g in gold.values() if g["controlStatus"] == RISK)),
                             "perCase": {str(k): v_ for k, v_ in sorted(sig_bait_per_case.items())},
                             "casesWhereSubsetOfGoldBaitIds": sig_subset_gold},
        "baitsGold": {"n": n_gold, "byType": baits["gold"], "noteShare": _kn(baits["gold"].get("note", 0), n_gold),
                      "withoutSignature": gold_without_sig, "byFamily": dict(sorted(bait_by_family.items()))},
        "riskNotes": {"n": n_risk_notes, "baitBySignature": _kn(risk_notes_sig_bait, n_risk_notes), "baitGold": _kn(risk_notes_gold_bait, n_risk_notes)},
        "controlNotes": {"n": n_control_notes},
        "lexiconSubjective": {"baitsBySignature": _kn(subj["baitSig"], n_sig), "baitsGold": _kn(subj["baitGold"], n_gold),
                              "controlNotes": _kn(subj["controlNote"], n_control_notes),
                              "riskNotesNotGoldBait": subj["riskNoteNotGoldBait"],
                              "resumeItems": _kn(subj["resume"], counts["resume"]["all"]),
                              "workSamples": _kn(subj["work_sample"], counts["work_sample"]["all"]),
                              "sourceTypesClassed": lexicon_subjective_types,
                              "kindBaitsGold": subj_kind["baitGold"], "kindControlNotes": subj_kind["controlNote"],
                              "baitsGoldByFamily": dict(sorted(subj_bait_by_family.items()))},
        "trapSignatureLocations": dict(sig_loc, inOriginalCvMarkdownLines=cv_md_hits,
                                       riskCasesWithSignatureInJobDescriptionOrRequirements=sum(jd_cases_by_family.values()),
                                       riskCasesWithSignatureInJobDescriptionOrRequirementsByFamily=dict(sorted(jd_cases_by_family.items()))),
        "validSignatureLocations": vsig, "controlValidSignaturesOnlyInNotes": only_note_cases,
        "itemLevelC2": item_level_subjective(lex, cases, gold, note_ids, bait_sig, bait_gold, subj_ids),
    }


# ============================================================ markdown
def md(facts):
    L = []
    A = L.append
    A("# Setup facts (method section)")
    A("")
    A("Definitions and denominators. *Model identity*: fields copied from each formal run's `config.json` "
      "(`identity` = what Ollama reported at run time; `options`, `seed_base`, `repeat`, `think`); a model's fields must agree "
      "across its C0/C1/C2/C5 runs (and the gpt-oss C4 regeneration run); hardware from `machine/` files. "
      "*C0 vs C5 request difference*: the 144 request lines of `benchmark/v4/requests/C0.jsonl` and `C5.jsonl` compared key by key "
      "(denominator 144 lines). *Byte-identical outputs*: number of cases whose C0 and C5 `content` strings are byte-equal in UTF-8 "
      "(denominator 144 per model; risk 72, control 72); *trap-discordant* = among the non-identical risk cases, how many have a "
      "different `trapFellAny` in C0 and C5 score rows. *Prompt words*: `meta.promptWords` of each request = whitespace-split "
      "word count of system + user messages (median over the 144 requests of a condition; re-computed from the messages and "
      "checked equal); *rules-section words* = system-message words of C1/C2 minus those of C0 for the same case. "
      "*Obligation words per rule*: whitespace words of `obligation.prose` (C1) vs of `mustDo` + `mustNot` + `route` (C2 duty text) "
      "vs of the whole rendered C2 block (includes `severity`, `applies`, `checkedBy`, `onViolation`). "
      "*Contract coverage*: a declared check is a `validationTarget.checks[].id` without `requiresGold`; an implemented code is a code "
      "string found by parsing `detectors.py`/`validator.py` or observed in any finding of the three models' C3 validations and C4 "
      "stage1/final validations; matching is by exact name. *Cleared case*: a risk case with `trapFellAny` true in C2 and false in C4. "
      "*Counterfactual (strict)*: the frozen repairer is re-run on the frozen C2 output with only findings whose code is declared; "
      "a cleared case *depends on undeclared checks* when the repaired bundle then still fails `trapFellAny` (frozen scorer); "
      "the lenient variant also keeps the hand-assigned renamed counterparts listed below (denominator: the model's cleared cases; "
      "no regeneration is simulated). *All critical FAILs undeclared*: cleared cases whose C2 validation (C4 stage1 `before`) has at "
      "least one critical FAIL and every critical FAIL code is undeclared. *Blind cases*: `trapFellAny` from the frozen score rows and "
      "the count of `qualification_boundary` FAIL findings, per model × condition (one output each). *Freeze digest*: sha256 over the "
      "concatenated bytes of `cases/*.json` then `gold/*.json`, each sorted by file name.")
    A("")
    A("## 1. Model identity")
    A("")
    A("| Model | Tag | Quant. | Params | Digest (12) | think | Ollama | temp | seed | num_ctx | num_predict | repeat | inconsistent fields |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in facts["models"]:
        A(f"| {m['model']} | `{m['tag']}` | {m['quantization']} | {m['parameterSize']} | `{m['digest12']}` | {m['think']} | {m['ollamaVersion']} | "
          f"{m['temperature']} | {m['seed']} | {m['numCtx']} | {m['numPredict']} | {m['repeat']} | {', '.join(m['fieldsInconsistentAcrossRuns']) or 'none'} |")
    A("")
    for m in facts["models"]:
        runs = "; ".join(f"{r['condition']} {r['nOutputs']}/{r['nRequests']} outputs (digest/model/seed mismatches "
                         f"{r['outputsDigestMismatch']}/{r['outputsModelMismatch']}/{r['outputsSeedMismatch']})" for r in m["runs"])
        A(f"- {m['model']}: {runs}. Modelfile default parameters: `{m['modelfileParameters'] or 'none'}` (overridden by the request options).")
    hw = facts["hardware"]
    A("")
    A(f"Hardware: {hw.get('machine')}, {hw.get('chip')}, {hw.get('memory')} (source `{hw['hardwareSource']}`); Ollama binary "
      f"`{hw.get('ollamaBinary')}`, version {hw.get('ollamaVersionMachineFile')} (source `{hw['ollamaSource']}`). "
      f"Models listed in that file: " + ", ".join(f"{x['tag']} {x['quantization']} {x['parameterSize']} `{x['digest12']}`" for x in hw["modelsListedInMachineFile"]) + ".")
    cf = facts["conditions"]
    A("")
    A("## 2. Condition facts")
    A("")
    r = cf["c0VsC5Requests"]
    A(f"C0 vs C5 requests: {r['linesWithAnyDifference']}/{r['nLines']} lines differ; differing top-level keys "
      + ", ".join(f"`{k}` ({n})" for k, n in sorted(r["differingTopLevelKeys"].items()))
      + f"; differing `meta` keys: {', '.join(sorted(r['differingMetaKeys'])) or 'none'}. C0 `format` values: {', '.join(r['c0FormatValues'])}; "
      f"C5 `format` equals `{r['bundleSchemaFile']}`: {r['c5FormatEqualsBundleSchemaFile']}.")
    A("")
    A("| Model | C0 = C5 byte-identical (all) | risk | control | non-identical risk | of which trap-discordant |")
    A("|---|---|---|---|---|---|")
    for model, x in cf["c0VsC5OutputsByteIdentical"].items():
        A(f"| {model} | {x['identical']}/{x['n']} | {x['identicalRisk']}/{x['nRisk']} | {x['identicalControl']}/{x['nControl']} | "
          f"{x['nonIdenticalRisk']} | {x['nonIdenticalRiskTrapDiscordant']} |")
    pw = cf["promptWords"]
    A("")
    A("| Condition | prompt words median | min | max | chars median | manifest median | meta = recomputed |")
    A("|---|---|---|---|---|---|---|")
    for c in GEN_CONDS:
        x = pw[c]
        A(f"| {c} | {x['median']} | {x['min']} | {x['max']} | {x['charsMedian']} | {x['manifestMedian']} | {x['metaEqualsRecomputed']} |")
    A("")
    A(f"Paired per-case C2 − C1 prompt words: median {pw['pairedC2minusC1']['median']} (min {pw['pairedC2minusC1']['min']}, max {pw['pairedC2minusC1']['max']}). "
      f"Rules-section words: C1 median {pw['rulesSectionWords']['C1']['median']}, C2 median {pw['rulesSectionWords']['C2']['median']}. "
      f"Requests equal to C0 + runtime rendering (`render_prose`/`render_contract`): C1 {pw['requestsEqualC0PlusRuntimeRendering']['C1']}/144, "
      f"C2 {pw['requestsEqualC0PlusRuntimeRendering']['C2']}/144.")
    h = cf["c2ValidatorHeader"]
    A("")
    A("C2 contract header (measured in the requests): requests containing both phrases "
      + ", ".join(f"{c} {n}/144" for c, n in h["requestsContainingBothPhrases"].items()) + ". Header line as sent:")
    A("")
    A("> " + h["headerLine"])
    A("")
    A(f"Fields a C2 block adds beyond the duty text: {', '.join('`' + k + '`' for k in cf['c2ExtraFieldsPerBlock'])}; top level adds "
      f"{', '.join('`' + k + '`' for k in cf['c2TopLevelExtra'])}.")
    A("")
    A("| Rule | C1 prose words | C2 mustDo+mustNot+route words | C2 rendered block words | active in cases |")
    A("|---|---|---|---|---|")
    for x in cf["obligationWordsPerRule"]:
        A(f"| {x['rule'].split('.')[-1]} | {x['proseWords']} | {x['contractObligationWords']} | {x['contractBlockWords']} | {x['activeInCases']}/144 |")
    t = cf["obligationWordsTotal"]
    A(f"| **all nine** | {t['prose']} | {t['contractObligation']} | {t['contractBlock']} | |")
    A("")
    A("| Condition | requests sha256 (local file, 12) | " + " | ".join(m for m, _ in MODELS) + " | all models equal | equals local file |")
    A("|---|---|" + "---|" * len(MODELS) + "---|---|")
    for c, x in cf["requestsSha256"].items():
        A(f"| {c} | `{x['local12']}` | " + " | ".join(f"`{x['byModel'][m]}`" for m, _ in MODELS) + f" | {x['allModelsEqual']} | {x['equalsLocalFile']} |")
    cc = facts["contractCoverage"]
    A("")
    A("## 3. Contract coverage (declared checks vs implemented codes)")
    A("")
    A(f"Declared (non-gold) checks: {cc['nDeclared']}; gold-only (`requiresGold`, scoring only): {cc['nGoldOnly']}; implemented codes: {cc['nImplemented']} "
      f"(static-only {len(cc['implementedStaticOnly'])}, observed-only {len(cc['implementedObservedOnly'])}).")
    A("")
    A(f"- **Declared but no same-name implementation ({len(cc['declaredNotImplemented'])})**: " + ", ".join(f"`{c}`" for c in cc["declaredNotImplemented"]))
    A(f"- **Implemented but not declared ({len(cc['implementedNotDeclared'])})**: " + ", ".join(f"`{c}`" for c in cc["implementedNotDeclared"]))
    A(f"  - of which renamed counterparts of a declared check (hand-assigned, see `counterpartMap`) ({len(cc['implementedNotDeclaredWithDeclaredCounterpart'])}): "
      + ", ".join(f"`{c}`→`{cc['counterpartMap'][c]}`" for c in cc["implementedNotDeclaredWithDeclaredCounterpart"]))
    A(f"  - with no declared counterpart ({len(cc['implementedNotDeclaredNoCounterpart'])}): " + ", ".join(f"`{c}`" for c in cc["implementedNotDeclaredNoCounterpart"]))
    A("")
    A("| Rule | Code | declared | emitted severity | rule JSON severity | observed findings | source |")
    A("|---|---|---|---|---|---|---|")
    for x in cc["codeTable"]:
        A(f"| {', '.join(r.split('.')[-1] for r in x['rules'])} | `{x['code']}` | {'yes' if x['declared'] else 'no'} | {', '.join(x['emittedSeverities']) or '—'} | "
          f"{', '.join(x['ruleJsonSeverity'])} | {x['observedCount']} | {', '.join(x['sourceLines']) or '—'} |")
    s = cc["severity"]
    A("")
    A(f"Severity source: `detectors.py` defines {', '.join(f'{k} = \"{v}\"' for k, v in s['detectorsConstants'].items())} and passes them "
      f"literally to `finding()`. Reads of a contract-field key ({', '.join('`' + k + '`' for k in CONTRACT_KEYS)}) in `runtime/hrgene/*.py` "
      f"(subscript or `.get` with that constant key):")
    A("")
    for x in s["keyReads"]:
        A(f"- `{x['file']}:{x['line']}` {x['function']}(): `{x['object']}[{x['key']!r}]` — reads a {x['reads']}")
    A("")
    A(f"The rule file's contract fields are read only in: {', '.join('`' + x + '`' for x in s['ruleSeverityReadIn'])}; "
      f"detectors.py or validator.py read any of them: {s['detectorsOrValidatorReadRuleSeverity']}. Contract keys never read by "
      f"`runtime/hrgene/*.py`: {', '.join('`' + k + '`' for k in s['contractKeysNeverRead']) or 'none'}. validator.py loops over "
      f"`DETECTORS` {s['detectorLoop']['loopsOverDETECTORS']} time(s); the loop body refers to the activation result: "
      f"{s['detectorLoop']['loopBodyMentionsActivation']} (activation only fills `perRule.active` in the report).")
    A("")
    A(f"Codes whose emitted severity differs from their rule's JSON `severity`: {', '.join('`' + c + '`' for c in s['codesWhoseSeverityDiffersFromRuleJson']) or 'none'}. "
      f"{s['aggregateRule']}.")
    A("")
    A("C2→C4 cleared risk cases and undeclared checks:")
    A("")
    A("| Model | cleared | with ≥1 undeclared FAIL code in C2 validation | all critical FAILs undeclared | strict counterfactual: still cleared | depend on undeclared (strict) | cases | lenient: depend |")
    A("|---|---|---|---|---|---|---|---|")
    for model, _ in MODELS:
        d, st, le = cc["clearedCasesUndeclared"][model], cc["counterfactualStrict"][model], cc["counterfactualLenient"][model]
        A(f"| {model} | {d['cleared']} | {d['withAnyUndeclaredFail']} | {d['allCriticalFailsUndeclared']}"
          f"{' (' + ', '.join(d['allCriticalFailsUndeclaredCases']) + ')' if d['allCriticalFailsUndeclaredCases'] else ''} | "
          f"{st['clearedUnderFilter']} | {st['dependOnFilteredChecks']} | "
          f"{', '.join(st['dependCases']) or '—'} | {le['dependOnFilteredChecks']} ({', '.join(le['dependCases']) or '—'}) |")
    A("")
    dropped = {}
    for model, _ in MODELS:
        for r in cc["counterfactualStrict"][model]["cases"]:
            if not r["clearedUnderFilter"]:
                for c in r["droppedFailCodes"]:
                    dropped.setdefault(c, set()).add(f"{model}:{r['case']}")
    A("Undeclared FAIL codes present in the strict-dependent cases (model:case): "
      + "; ".join(f"`{c}` {len(v)}" for c, v in sorted(dropped.items())) + ". "
      "*All critical FAILs undeclared* is a descriptive count: every critical FAIL finding in the case's C2 validation carries an undeclared code.")
    A("")
    A(f"Undeclared critical codes seen among FAIL findings of cleared cases (C2 validation): {', '.join('`' + c + '`' for c in cc['undeclaredCriticalCodesInClearedCases'])}. "
      "In the counterfactual a case that is no longer cleared would, under a validator restricted to the same codes, still be BLOCK in "
      + ", ".join(f"{m}: {cc['counterfactualStrict'][m]['ofWhichFilteredValidatorWouldStillBlock']}" for m, _ in MODELS)
      + " case(s) (strict); those would have triggered one regeneration, which is not simulated.")
    fz = facts["freeze"]
    A("")
    A("## 4. Benchmark freeze")
    A("")
    A(f"{fz['nCases']} cases + {fz['nGold']} gold files; {fz['algorithm']} → `{fz['casesGoldDigest16']}` "
      f"(recorded at freeze: `{fz['recordedFreezeDigest16']}`, match: {fz['matchesRecordedFreeze']}). "
      f"`{fz['rulesFile']}` sha256 `{fz['rulesFileSha256_12']}`; rulesetDigest in requests {', '.join(fz['rulesetDigestInRequests'])}, in run scores "
      f"{', '.join(fz['rulesetDigestInRunScores'])} (equal to the file: {fz['rulesFileMatchesRunDigests']}). Lexicons sha256 `{fz['lexiconsSha256_12']}`, "
      f"output schema sha256 `{fz['outputSchemaSha256_12']}` ({fz['note']}).")
    bc = facts["qualificationBlindCases"]
    A("")
    A("## 5. The two lexicon-blind qualification cases")
    A("")
    A("Cell = trapFellAny / number of `qualification_boundary` FAIL findings (codes). C3 shares C2's output; C4 is the final repaired bundle.")
    A("")
    A("| Case | Model | " + " | ".join(ALL_CONDS) + " |")
    A("|---|---|" + "---|" * len(ALL_CONDS))
    for cid, rec in bc["cases"].items():
        for model, _ in MODELS:
            row = rec["byModel"][model]
            cells = []
            for c in ALL_CONDS:
                x = row[c]
                tf = {True: "fell", False: "clear", None: "n/a"}[x["trapFellAny"]]
                cells.append(f"{tf} / {x['qualificationFail']}" + (f" ({', '.join(x['qualificationCodes'])})" if x["qualificationCodes"] else ""))
            A(f"| {cid} | {model} | " + " | ".join(cells) + " |")
    A("")
    A("Totals over the 2 cases × 3 models (6 cells per condition): "
      + "; ".join(f"{c} fell {x['trapFell']}/{x['cells']}, qualification FAIL in {x['qualificationFailCells']}/{x['cells']}" for c, x in bc["summaryByCondition"].items()) + ".")
    A("")
    md_source_types(A, facts["sourceTypes"])
    return "\n".join(L) + "\n"


def md_source_types(A, st):
    def kn(x):
        return f"{x['k']}/{x['n']} ({x['pct']}%)"
    d = st["definitions"]
    A("## 6. Source types, baits and the subjective rule (added 2026-09-23)")
    A("")
    A(f"Definitions. *Source* = an item of `candidate.evidence` (the job description is not among them); its type is the "
      f"case-metadata field `sourceType`. *Bait* = {d['bait']}; *gold bait* = {d['baitGold']}. *Lexicon-subjective* = "
      f"{d['lexiconSubjective']}. *Valid-signature location* = {d['validSignatureLocation']}. *Item level* = {d['itemLevel']}; "
      "an item counts for a rule when at least one FAIL finding of that rule is assigned to it. `anywhereSignatures` is a subset "
      f"of `signatures` in every risk case: {st['anywhereSignaturesSubsetOfSignatures']}.")
    A("")
    c = st["counts"]
    A("| Source type | all | risk cases | controls | lexicon-subjective |")
    A("|---|---|---|---|---|")
    ls = st["lexiconSubjective"]
    subj_all = {"resume": ls["resumeItems"]["k"], "work_sample": ls["workSamples"]["k"],
                "note": ls["baitsGold"]["k"] + ls["controlNotes"]["k"] + ls["riskNotesNotGoldBait"]}
    for t in SOURCE_TYPES:
        A(f"| {t} | {c[t]['all']} | {c[t]['risk']} | {c[t]['control']} | {subj_all[t]} |")
    A(f"| **all** | {st['nSources']} | {sum(c[t]['risk'] for t in SOURCE_TYPES)} | {sum(c[t]['control'] for t in SOURCE_TYPES)} | {sum(subj_all.values())} |")
    A("")
    A("Composition per case: " + "; ".join(f"{side}: " + ", ".join(f"[{k}] × {n}" for k, n in comp.items()) for side, comp in st["compositionPerCase"].items())
      + f". Source types the lexicon classes as subjective or hearsay: {', '.join(ls['sourceTypesClassed'])}.")
    A("")
    bs, bg, rn = st["baitsBySignature"], st["baitsGold"], st["riskNotes"]
    A(f"- Baits (signature occurrence): {bs['n']} sources, by type " + ", ".join(f"{k} {v}" for k, v in bs["byType"].items())
      + f"; notes {kn(bs['noteShare'])}. Risk cases with at least one bait: {bs['riskCasesWithBait']['k']}/{bs['riskCasesWithBait']['n']}; "
      f"baits per case: " + ", ".join(f"{k}: {v} cases" for k, v in bs["perCase"].items())
      + f"; the bait set is a subset of the gold `baitSourceIds` in {bs['casesWhereSubsetOfGoldBaitIds']} cases.")
    A(f"- Gold baits (`baitSourceIds`): {bg['n']} sources, by type " + ", ".join(f"{k} {v}" for k, v in bg["byType"].items())
      + f"; notes {kn(bg['noteShare'])}; {bg['withoutSignature']} of them contain no trap signature phrase.")
    A(f"- Notes in risk cases: {rn['n']}; baits by signature {kn(rn['baitBySignature'])}, gold baits {kn(rn['baitGold'])}. "
      f"Notes in controls: {st['controlNotes']['n']}.")
    A(f"- Lexicon-subjective: baits (signature) {kn(ls['baitsBySignature'])}; gold baits {kn(ls['baitsGold'])} "
      f"(subjective family only / hearsay only / both: {ls['kindBaitsGold']['subjectiveOnly']} / {ls['kindBaitsGold']['hearsayOnly']} / {ls['kindBaitsGold']['both']}); "
      f"control notes {kn(ls['controlNotes'])} ({ls['kindControlNotes']['subjectiveOnly']} / {ls['kindControlNotes']['hearsayOnly']} / {ls['kindControlNotes']['both']}); "
      f"resume items {kn(ls['resumeItems'])}; work samples {kn(ls['workSamples'])}. Lexicon-subjective gold baits by family: "
      + ", ".join(f"{k} {v}/{bg['byFamily'][k]}" for k, v in ls["baitsGoldByFamily"].items()) + ".")
    sl = st["trapSignatureLocations"]
    A(f"- Trap signatures (one count per signature per risk case, {sl['total']} in all): occurring only in notes {sl['noteOnly']}, "
      f"in a resume item or work sample {sl['nonNoteSource']}, in no source {sl['noSource']}; also occurring in the job description "
      f"or requirement texts {sl['inJobDescriptionOrRequirements']} (in {sl['riskCasesWithSignatureInJobDescriptionOrRequirements']} of the 72 risk cases: "
      + ", ".join(f"{k} {v}" for k, v in sl["riskCasesWithSignatureInJobDescriptionOrRequirementsByFamily"].items())
      + f"); in the original CV markdown {sl['inOriginalCvMarkdown']} ("
      + "; ".join(f"{h['case']} `{h['signature']}` in line “{h['line']}”" for h in sl["inOriginalCvMarkdownLines"]) + ").")
    for side in ("control", "risk"):
        x = st["validSignatureLocations"][side]
        A(f"- Valid-claim signatures in {'controls' if side == 'control' else 'risk cases'} ({x['total']}): only in notes {x['onlyNote']} "
          f"(of which not in the original CV markdown {x['onlyNoteNotInCvMarkdown']}), in notes and another source type {x['noteAndOther']}, "
          f"only in resume items / work samples {x['nonNoteOnly']}, in no source {x['noSource']}.")
    A("  Control signatures only in notes: " + ("; ".join(f"{h['case']} `{h['signature']}`" for h in st["controlValidSignaturesOnlyInNotes"]) or "none") + ".")
    A("")
    A("Item level (C2): which rule FAILs the supported-side items that carry a trap signature.")
    A("")
    A("| Model | trap items FAILed | FAILed by subjective_claim_boundary (any) | subjective rule only | by code | trap items citing a note | citing a lexicon-subjective source | FAILed items citing a note |")
    A("|---|---|---|---|---|---|---|---|")
    for m, x in st["itemLevelC2"].items():
        A(f"| {m} | {kn(x['trapItemsFailed'])} | {kn(x['failedBySubjectiveRule'])} | {kn(x['failedBySubjectiveRuleOnly'])} | "
          + ", ".join(f"`{k}` {v}" for k, v in x["failedBySubjectiveCode"].items()) + f" | {kn(x['trapItemsCiting']['note'])} | "
          f"{kn(x['trapItemsCiting']['lexiconSubjective'])} | {kn(x['failedItemsCiting']['note'])} |")
    A("")
    A("The item-level counts are re-derived here and asserted equal to `repair_anatomy.json` (`itemLevelC2.primary_entries_deepest`: "
      "trap items, FAILed items and FAILs by rule). A trap item can be FAILed by several rules; *any* counts items with at least one "
      "subjective_claim_boundary FAIL, *only* those whose FAILs all come from that rule.")
    A("")


def main():
    v = Validator()
    rs = v.rs
    cases = load_by_case(os.path.join(BENCH, "cases"))
    gold = load_by_case(os.path.join(BENCH, "gold"))
    reqs = request_files()
    facts = {
        "schema": "hrgene.v4.setup_facts.v1",
        "models": model_identity(),
        "hardware": hardware(),
        "conditions": condition_facts(reqs, rs, cases, gold),
        "contractCoverage": contract_coverage(rs, v, cases, gold),
        "freeze": freeze_facts(),
        "qualificationBlindCases": blind_cases(v, cases, gold),
        "sourceTypes": source_type_facts(v, cases, gold),
    }
    with open(os.path.join(HERE, "setup_facts.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(facts, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    with open(os.path.join(HERE, "setup_facts.md"), "w", encoding="utf-8") as f:
        f.write(md(facts))
    cc = facts["contractCoverage"]
    print("declared-not-implemented:", cc["declaredNotImplemented"])
    print("implemented-not-declared:", len(cc["implementedNotDeclared"]))
    for m, _ in MODELS:
        print(m, "cleared", cc["counterfactualStrict"][m]["clearedActual"], "depend(strict)", cc["counterfactualStrict"][m]["dependOnFilteredChecks"],
              "depend(lenient)", cc["counterfactualLenient"][m]["dependOnFilteredChecks"])
    print("freeze", facts["freeze"]["casesGoldDigest16"], facts["freeze"]["matchesRecordedFreeze"])
    st = facts["sourceTypes"]
    print("baits (signature)", st["baitsBySignature"]["n"], "notes", st["baitsBySignature"]["noteShare"], "| gold baits", st["baitsGold"]["n"],
          "| lexicon-subjective gold baits", st["lexiconSubjective"]["baitsGold"], "control notes", st["lexiconSubjective"]["controlNotes"])
    for m, x in st["itemLevelC2"].items():
        print(m, "trap items FAILed", x["trapItemsFailed"], "by subjective rule", x["failedBySubjectiveRule"])


if __name__ == "__main__":
    main()
