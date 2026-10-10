#!/usr/bin/env python3
"""Flat registry of every number the manuscript quotes -> analysis/paper_numbers.json + paper_numbers.md.

The manuscript template (paper/src/manuscript_*.md) refers to numbers only as {{key}} placeholders;
paper/render.py fills them from paper_numbers.json. This script computes nothing new about the study except
(i) sums / differences of counts that the source products report separately (each such key says so in its
source string). The sensitivity transitions' Newcombe method-10 intervals are read from sensitivity.json, which
computes them with tab4_contrasts.newcombe_paired (the same implementation as the main contrasts).

Inputs (all read-only): analysis/{results.json, tab4_stats.json, tab4_contrasts.json, tab4_families.csv,
c4_transitions.json, tab2_benchmark.json, repair_anatomy.json, redactor_frontier.json, sensitivity.json,
setup_facts.json, example_case.md, tab1_contract.md}, benchmark/v4/detector_pr.json, and the C2 / C4
score_rows.jsonl of the formal runs (package-level validator flags split by risk / control).

Output: {key: {"text": string printed in the paper, "value": raw number or null, "source": "file:field path"}}.
A key whose text contains Chinese characters or Chinese punctuation also carries "text_en" (English wording with the
same numbers, from TEXT_EN below; the English manuscript prints text_en when present, else text). text and value are
the same with or without it.
Key = <group>.<model>.<condition or contrast>.<metric>[.<variant>]; model slugs gptoss / q8b / q30b, pooled for
the three models together; groups without a model dimension drop that segment. Standard library only;
deterministic (json.dumps(sort_keys=True); no resampling).
"""
import csv
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import tab4_contrasts as TC  # noqa: E402  (wilson / newcombe_paired only; the module has no import-time side effects)

MODELS = ("gpt-oss:20b", "qwen3:8b", "qwen3:30b-a3b")
SLUG = {"gpt-oss:20b": "gptoss", "qwen3:8b": "q8b", "qwen3:30b-a3b": "q30b"}
CONDS = ("C0", "C1", "C2", "C3", "C4", "C5")
RISK, CONTROL = "positive_risk", "matched_clean_control"
FAM = {
    "decision_ranking_protected_human_review_boundary": "decision",
    "ownership_role_scope_inflation": "ownership",
    "qualification_seniority_mismatch": "qualification",
    "unsupported_jd_technical_deployment": "deployment",
    "unsupported_premise_followup_subjective_rationale": "subjective",
    "unsupported_quantification_causality": "quantification",
}
FAM_ORDER = ("decision", "ownership", "qualification", "deployment", "subjective", "quantification")
MINUS = "−"
KEY_RE = re.compile(r"[A-Za-z0-9_.\-]+")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# English manuscript (2026-09-23): Chinese characters (CJK ideographs) and Chinese punctuation (CJK symbols, full-width
# forms, curly quotes, ellipsis, em dash, middle dot). Every key whose text matches needs a TEXT_EN entry; an entry for
# a key whose text does not match is an error, so the table cannot go stale.
CJK_RE = re.compile("[　-〿㐀-䶿一-鿿豈-﫿︰-﹏＀-￯"
                    "‘’“”…—·]")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
TEXT_EN = {}  # key -> English text. As of 2026-09-23 no registered text contains Chinese, so the table is empty.

GROUPS = (
    ("bench", "基准构成与冻结摘要"),
    ("detector", "检测器变异注入（实现自洽性检查，不是真实输出上的 P/R）"),
    ("run", "正式运行目录"),
    ("main", "每模型 × 条件的主表指标（表 4）"),
    ("contrast", "配对对比（风险案例 trapFellAny）"),
    ("clear", "清除率"),
    ("family", "按族描述（不检验）"),
    ("cost", "代价：对照保留、supported 条目、对照改动、显式压制、interviewSignalRisks"),
    ("repair", "修复动作分类与流水线检查"),
    ("validator", "校验器行为：条目级召回与对照代理、C4 残留事件"),
    ("frontier", "内容无关删减基线与来源类型策略（POST HOC，探索性）"),
    ("sens", "三项敏感性（POST HOC）：开发集剔除、关闭字符串提升、Unicode 标点归一化"),
    ("setup", "模型身份与解码参数、硬件；来源类型事实（setup.source.*）"),
    ("cond", "条件事实：C0/C5 请求差异、逐字节相同、prompt 词数、C2 头部句、requests 哈希"),
    ("contract", "契约声明与实现的覆盖漂移"),
    ("blind", "资历族两例词表盲区"),
    ("example", "示例案例"),
    ("stats", "统计方法常量"),
)


# ---------------------------------------------------------------- formatting

def fpct(p, nd=1):
    return f"{100 * p:.{nd}f}%"


def fsigned(x, nd):
    s = f"{abs(x):.{nd}f}"
    if s.strip("0.") == "":
        return s
    return ("+" if x > 0 else MINUS) + s


def fnum(x, nd):
    s = f"{abs(x):.{nd}f}"
    return s if (x >= 0 or s.strip("0.") == "") else MINUS + s


def fci(lo, hi, nd=1):
    return f"[{100 * lo:.{nd}f}, {100 * hi:.{nd}f}]"


def fci_pp(lo, hi, nd):
    return f"[{fsigned(lo, nd)}, {fsigned(hi, nd)}]"


def fp(p):
    return f"{p:.1e}" if p < 0.001 else f"{p:.3f}"


def fg(x):
    """Design constants such as 0.25 or 1.0 -> '0.25' / '1'."""
    return f"{x:g}"


def short(case_id):
    return case_id.split("-")[0].split("(")[0]


def slugify(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s.replace("|", "__").replace("@", "__").replace("+", "_and_"))


def src(file, *path):
    out = file + ":"
    for i, p in enumerate(path):
        if isinstance(p, int):
            out += f"[{p}]"
        elif IDENT.fullmatch(p):
            out += ("." if i else "") + p
        else:
            out += f'["{p}"]'
    return out


def at(obj, *path):
    for p in path:
        obj = obj[p]
    return obj


# ---------------------------------------------------------------- registry

class Registry:
    def __init__(self):
        self.d = {}
        self.notes = []

    def put(self, key, text, value, source):
        if not KEY_RE.fullmatch(key):
            raise SystemExit(f"invalid key {key!r}")
        if key in self.d:
            raise SystemExit(f"duplicate key {key!r}")
        if isinstance(value, bool):
            value = int(value)
        if value is not None and not (isinstance(value, (int, float)) and math.isfinite(value)):
            raise SystemExit(f"non-numeric value for {key!r}: {value!r}")
        self.d[key] = {"text": str(text), "value": value, "source": source}

    def count(self, key, value, source):
        self.put(key, str(int(value)), int(value), source)

    def text(self, key, text, source):
        self.put(key, text, None, source)

    def kn(self, key, k, n, source, with_pct=False):
        self.put(key + ".kn", f"{k}/{n}", None, source)
        if with_pct:
            self.put(key, fpct(k / n) if n else "–", (k / n) if n else None, source)

    def prop(self, key, k, n, p, lo, hi, source):
        """Proportion with its Wilson interval: base (pct), .k .n .kn, .ci .full."""
        self.put(key, fpct(p), p, source)
        if k is not None:
            self.count(key + ".k", k, source)
        self.count(key + ".n", n, source)
        if k is not None:
            self.put(key + ".kn", f"{k}/{n}", None, source)
        if lo is not None:
            self.put(key + ".ci", fci(lo, hi), None, source)
            self.put(key + ".full", f"{fpct(p)} {fci(lo, hi)}", None, source)

    def wilson(self, key, k, n, source):
        lo, hi = TC.wilson(k, n)
        self.prop(key, k, n, k / n, lo, hi, source + " (Wilson 95% CI via tab4_contrasts.wilson)")

    def ppdiff(self, key, diff_pp, lo_pp, hi_pp, nd, source, with_ci=True):
        self.put(key, fsigned(diff_pp, nd) + " pp", diff_pp, source)
        if with_ci:
            self.put(key + ".ci", fci_pp(lo_pp, hi_pp, nd), None, source)
            self.put(key + ".full", f"{fsigned(diff_pp, nd)} pp {fci_pp(lo_pp, hi_pp, nd)}", None, source)

    def pval(self, key, p, source):
        self.put(key, fp(p), p, source)

    def mean(self, key, x, nd, source):
        self.put(key, fnum(x, nd), x, source)


# ---------------------------------------------------------------- loading

def load_json(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def load_jsonl(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def md_field(path, pattern):
    m = re.search(pattern, (HERE / path).read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"{path}: pattern {pattern!r} not found")
    return m.group(1)


# ---------------------------------------------------------------- groups

def bench(R, tab2, setup, pr):
    f = "tab2_benchmark.json"
    R.count("bench.cases.n", tab2["n"], src(f, "n"))
    R.count("bench.risk.n", tab2["controlStatus"][RISK], src(f, "controlStatus", RISK))
    R.count("bench.control.n", tab2["controlStatus"][CONTROL], src(f, "controlStatus", CONTROL))
    R.count("bench.families.n", len(tab2["families"]), src(f, "families") + " (number of keys)")
    for fam, slug in FAM.items():
        R.count(f"bench.family.{slug}.n", tab2["families"][fam], src(f, "families", fam))
        R.count(f"bench.family.{slug}.risk.n", tab2["familyByControl"][f"{fam}|{RISK}"], src(f, "familyByControl", f"{fam}|{RISK}"))
        R.count(f"bench.family.{slug}.control.n", tab2["familyByControl"][f"{fam}|{CONTROL}"], src(f, "familyByControl", f"{fam}|{CONTROL}"))
        R.text(f"bench.family.{slug}.name", fam, src(f, "families") + " (key)")
    for rule, n in sorted(tab2["trapRule"].items()):
        R.count(f"bench.trapRule.{rule.split('.')[-1]}.n", n, src(f, "trapRule", rule))
    for what in ("requirements", "propositions", "evidence"):
        (per, cnt), = tab2["perCase"][what].items()
        if cnt != tab2["n"]:
            raise SystemExit(f"tab2 perCase {what} not constant")
        R.count(f"bench.perCase.{what}", int(per), src(f, "perCase", what) + " (constant over all cases)")
    R.count("bench.anywhereCases.n", tab2["casesWithAnywhereSignatures"], src(f, "casesWithAnywhereSignatures"))
    R.count("bench.rules.n", len(pr["perRule"]), src("../benchmark/v4/detector_pr.json", "perRule") + " (number of rules)")
    fz, g = setup["freeze"], "setup_facts.json"
    if not (fz["matchesRecordedFreeze"] and fz["rulesFileMatchesRunDigests"]):
        raise SystemExit("setup_facts freeze digests do not match the recorded freeze")
    R.text("bench.freeze.casesGold", fz["casesGoldDigest16"], src(g, "freeze", "casesGoldDigest16"))
    R.text("bench.freeze.casesGold.short", fz["casesGoldDigest16"][:8], src(g, "freeze", "casesGoldDigest16") + " (first 8 hex)")
    R.text("bench.freeze.rules", fz["rulesFileSha256_12"], src(g, "freeze", "rulesFileSha256_12"))
    R.text("bench.freeze.rules.short", fz["rulesFileSha256_12"][:8], src(g, "freeze", "rulesFileSha256_12") + " (first 8 hex)")
    R.text("bench.freeze.rulesFile", fz["rulesFile"], src(g, "freeze", "rulesFile"))
    R.text("bench.freeze.lexicons", fz["lexiconsSha256_12"], src(g, "freeze", "lexiconsSha256_12"))
    R.text("bench.freeze.outputSchema", fz["outputSchemaSha256_12"], src(g, "freeze", "outputSchemaSha256_12"))
    R.count("bench.freeze.nCases", fz["nCases"], src(g, "freeze", "nCases"))
    R.count("bench.freeze.nGold", fz["nGold"], src(g, "freeze", "nGold"))


def detector(R, pr):
    f = "../benchmark/v4/detector_pr.json"
    total = 0
    for rule, s in pr["perRule"].items():
        n = s["tp"] + s["fn"]
        total += n
        slug = rule.split(".")[-1]
        R.count(f"detector.{slug}.mutants", n, src(f, "perRule", rule, "tp") + " + fn")
        R.put(f"detector.{slug}.precision", f"{s['precision']:.2f}", s["precision"], src(f, "perRule", rule, "precision"))
        R.put(f"detector.{slug}.recall", f"{s['recall']:.2f}", s["recall"], src(f, "perRule", rule, "recall"))
    R.count("detector.rules.n", len(pr["perRule"]), src(f, "perRule") + " (number of rules)")
    R.count("detector.mutants.n", total, src(f, "perRule") + " (sum of tp + fn over rules)")
    pmin = min(s["precision"] for s in pr["perRule"].values())
    rmin = min(s["recall"] for s in pr["perRule"].values())
    R.put("detector.precision.min", f"{pmin:.2f}", pmin, src(f, "perRule") + " (minimum precision over rules)")
    R.put("detector.recall.min", f"{rmin:.2f}", rmin, src(f, "perRule") + " (minimum recall over rules)")
    R.kn("detector.cleanOracles", pr["cleanOraclesFlagged"], pr["cleanOracles"], src(f, "cleanOraclesFlagged") + " / cleanOracles")
    R.count("detector.cleanOracles.n", pr["cleanOracles"], src(f, "cleanOracles"))
    R.kn("detector.nearMisses", pr["nearMissesFlagged"], pr["nearMisses"], src(f, "nearMissesFlagged") + " / nearMisses")
    R.count("detector.nearMisses.n", pr["nearMisses"], src(f, "nearMisses"))
    R.text("detector.rulesetDigest", pr["rulesetDigest"].split(":")[-1][:12], src(f, "rulesetDigest") + " (first 12 hex)")


def main_table(R, results, stats, contrasts, families_rows):
    by = {(r["model"], r["condition"]): r for r in results}
    f = "tab4_stats.json"
    metrics = (("parsed", "parsed"), ("schemaValid", "schemaValid"), ("trapFellAny", "trap"),
               ("trapRequirementOverclaimed", "overclaim"), ("trapRouted", "trapRouted"),
               ("validClaimSuppressed", "suppressed"), ("validatorFlagged", "flagged"),
               ("residualCriticalViolationRate", "residual"))
    for m in MODELS:
        s = SLUG[m]
        for c in CONDS:
            row = by[(m, c)]
            R.text(f"run.{s}.{c}", row["run"], src("results.json", f"[model={m}, condition={c}]", "run"))
            base = f"main.{s}.{c}"
            props = stats["models"][m]["proportions"][c]
            for metric, name in metrics:
                v = props[metric]
                # tab4_stats reports "Controls suppressed" on scored controls only; results.json's plain
                # validClaimSuppressed pools risk and control cases, so compare with its control-only column.
                rkey = metric + "_matched_clean_control" if metric == "validClaimSuppressed" else metric
                if abs(v["p"] - row[rkey]) > 1e-12 or v["n"] != row[rkey + "_n"]:
                    raise SystemExit(f"tab4_stats / results.json disagree on {m} {c} {metric}")
                R.prop(f"{base}.{name}", v["k"], v["n"], v["p"], v["lo"], v["hi"], src(f, "models", m, "proportions", c, metric))
            v = props["validClaimPreserved_matched_clean_control"]
            sp = src(f, "models", m, "proportions", c, "validClaimPreserved_matched_clean_control")
            R.put(f"{base}.kept", fpct(v["p"]), v["p"], sp)
            R.count(f"{base}.kept.n", v["n"], sp)
            R.put(f"{base}.kept.ci", fci(v["lo"], v["hi"]), None, sp)
            R.put(f"{base}.kept.full", f"{fpct(v['p'])} {fci(v['lo'], v['hi'])}", None, sp)
            sr = src("results.json", f"[model={m}, condition={c}]")
            for metric, name in (("subjectiveRouted", "subjRouted"), ("trapFellStrict", "trapStrict")):
                n = row[metric + "_n"]
                k = round(row[metric] * n)
                if abs(k / n - row[metric]) > 1e-9:
                    raise SystemExit(f"{m} {c} {metric} is not a count ratio")
                R.wilson(f"{base}.{name}", k, n, sr + "." + metric + " × " + metric + "_n")
            R.mean(f"{base}.supportedPerCase", row["supportedCount"], 1, sr + ".supportedCount (mean over all 144, unparsed = 0)")
            R.put(f"{base}.reqExact", fpct(row["requirementStatusExact"]), row["requirementStatusExact"], sr + ".requirementStatusExact (mean over parsed cases)")
            R.count(f"{base}.reqExact.n", row["requirementStatusExact_n"], sr + ".requirementStatusExact_n")
            R.put(f"{base}.boundaryViolation", fpct(row["boundaryViolation"]), row["boundaryViolation"], sr + ".boundaryViolation")
        # package-level flags split by risk / control
        fr = contrasts["models"][m]["flagRates"]
        for c in ("C0", "C1", "C3", "C5"):
            for grp, name in (("risk", "flaggedRisk"), ("control", "flaggedControl")):
                v = fr[c][grp]
                R.prop(f"main.{s}.{c}.{name}", v["k"], v["n"], v["p"], v["lo"], v["hi"], src("tab4_contrasts.json", "models", m, "flagRates", c, grp))
        for c in ("C2", "C4"):
            run = by[(m, c)]["run"]
            rows = load_jsonl(ROOT / "experiments" / run / "score_rows.jsonl")
            for status, name, grp in ((RISK, "flaggedRisk", "risk"), (CONTROL, "flaggedControl", "control")):
                sel = [r for r in rows if r["controlStatus"] == status]
                k = sum(1 for r in sel if r["validatorFlagged"])
                if c == "C2" and (k, len(sel)) != (fr["C3"][grp]["k"], fr["C3"][grp]["n"]):
                    raise SystemExit(f"{m}: C2 validatorFlagged split differs from the C3 flag rate")
                R.wilson(f"main.{s}.{c}.{name}", k, len(sel), f"experiments/{run}/score_rows.jsonl: validatorFlagged over controlStatus={status}")
    # families by condition
    for m in MODELS:
        s = SLUG[m]
        for c in CONDS:
            rows = [r for r in families_rows if r["model"] == m and r["condition"] == c]
            if len(rows) != 6:
                raise SystemExit(f"tab4_families.csv: {m} {c} has {len(rows)} rows")
            sums = {"decision": [0, 0], "other5": [0, 0]}
            for r in rows:
                fam = FAM[r["family"]]
                sf = src("tab4_families.csv", f"[model={m}, condition={c}, family={r['family']}]")
                k, n = int(r["trapFailures"]), int(r["riskScored"])
                R.kn(f"family.{s}.{c}.{fam}.trap", k, n, sf + " trapFailures / riskScored", with_pct=True)
                if r["controlPreserved"] not in ("", "None"):
                    R.put(f"family.{s}.{c}.{fam}.kept", fpct(float(r["controlPreserved"])), float(r["controlPreserved"]), sf + " controlPreserved")
                R.count(f"family.{s}.{c}.{fam}.kept.n", int(r["controlScored"]), sf + " controlScored")
                R.count(f"family.{s}.{c}.{fam}.suppressed", int(r["controlsSuppressed"]), sf + " controlsSuppressed")
                grp = "decision" if fam == "decision" else "other5"
                sums[grp][0] += k
                sums[grp][1] += n
            k, n = sums["other5"]
            R.kn(f"family.{s}.{c}.other5.trap", k, n, src("tab4_families.csv", f"[model={m}, condition={c}]") + " sum of trapFailures / riskScored over the five non-decision families", with_pct=True)


def contrast_keys(R, key, t, source):
    R.count(f"{key}.n", t["pairedN"], source + ".pairedN")
    R.count(f"{key}.b", t["repaired"], source + ".repaired")
    R.count(f"{key}.c", t["new"], source + ".new")
    R.count(f"{key}.a", t["unchangedFail"], source + ".unchangedFail")
    R.count(f"{key}.d", t["unchangedPass"], source + ".unchangedPass")
    R.count(f"{key}.discordant", t["discordant"], source + ".discordant")
    R.kn(f"{key}.before", t["before"]["k"], t["pairedN"], source + ".before", with_pct=True)
    R.kn(f"{key}.after", t["after"]["k"], t["pairedN"], source + ".after", with_pct=True)
    degenerate = t["discordant"] == 0
    R.ppdiff(f"{key}.diff", t["diffPP"], t["ciPP"][0], t["ciPP"][1], 1, source + ".diffPP / ciPP (Newcombe method 10)")
    lo8, hi8 = t["ciPP_method8_uncorrectedPhi"]
    R.put(f"{key}.diff.ciM8", fci_pp(lo8, hi8, 1), None, source + ".ciPP_method8_uncorrectedPhi (traceability only)")
    R.pval(f"{key}.p", t["exactP"], source + ".exactP (exact two-sided McNemar)")
    if t.get("newCaseIds"):
        R.text(f"{key}.newIds", ", ".join(short(x) for x in t["newCaseIds"]), source + ".newCaseIds")
    return degenerate


def contrasts_group(R, C, stats, sens):
    f = "tab4_contrasts.json"
    if list(C["modelOrder"]) != list(MODELS):
        raise SystemExit(f"unexpected model order {C['modelOrder']}")
    if not (C["newcombeSelfTest"]["passed"] and all(v["allEqual"] for v in C["consistency"].values())):
        raise SystemExit("tab4_contrasts self-test / consistency failed")
    for m in MODELS:
        s = SLUG[m]
        for name, t in C["models"][m]["contrasts"].items():
            a, b = name.split("->")
            key = f"contrast.{s}.{a}to{b}"
            if contrast_keys(R, key, t, src(f, "models", m, "contrasts", name)):
                R.notes.append(f"`{key}.diff`：{m} {name} 没有不一致对（b = c = 0，见 `{key}.discordant`），差值为 0。"
                               f"`.ci` / `.full` 是 method 10 按设计给出的非退化区间 {R.d[key + '.diff.ci']['text']}（Newcombe 1998 表 III 的零差值行同样如此；"
                               f"method 8 给出 {R.d[key + '.diff.ciM8']['text']}）。正文宜直接写「0/{t['pairedN']} 个不一致对」；若报区间须注明是 method 10。")
            if name in stats["models"][m]["mcnemar"]:
                ref = stats["models"][m]["mcnemar"][name]
                if (ref["pairedN"], ref["repaired"], ref["new"]) != (t["pairedN"], t["repaired"], t["new"]):
                    raise SystemExit(f"tab4_contrasts / tab4_stats disagree on {m} {name}")
        cl = C["models"][m]["clearanceC2toC4"]
        sc = src(f, "models", m, "clearanceC2toC4")
        R.prop(f"clear.{s}.C2toC4", cl["cleared"], cl["c2Failures"], cl["p"], cl["lo"], cl["hi"], sc)
        R.count(f"clear.{s}.C2toC4.still", cl["stillFailing"], sc + ".stillFailing")
        full = sens["devExclusion"]["models"][m]["full"]
        if full["C2->C4"]["clearance"]["k"] != cl["cleared"] or full["C2->C4"]["clearance"]["n"] != cl["c2Failures"]:
            raise SystemExit(f"sensitivity / tab4_contrasts clearance differ for {m}")
        v = full["C0->C4"]["clearance"]
        R.prop(f"clear.{s}.C0toC4", v["k"], v["n"], v["p"], v["lo"], v["hi"], src("sensitivity.json", "devExclusion", "models", m, "full", "C0->C4", "clearance"))
        # families C2 -> C4
        fams = C["models"][m]["familiesC2toC4"]
        for grp, name in [("decisionFamily", "decision"), ("otherFiveFamilies", "other5")] + [(f"family:{k}", v) for k, v in FAM.items() if v != "decision"]:
            t = fams[grp]
            sf = src(f, "models", m, "familiesC2toC4", grp)
            R.count(f"family.{s}.C2toC4.{name}.c2fail", t["c2Failures"], sf + ".c2Failures")
            R.count(f"family.{s}.C2toC4.{name}.c4fail", t["c4Failures"], sf + ".c4Failures")
            R.count(f"family.{s}.C2toC4.{name}.repaired", t["repaired"], sf + ".repaired")
            R.count(f"family.{s}.C2toC4.{name}.new", t["new"], sf + ".new")
            R.count(f"family.{s}.C2toC4.{name}.n", t["pairedN"], sf + ".pairedN")
            R.text(f"family.{s}.C2toC4.{name}.arrow", f"{t['c2Failures']} → {t['c4Failures']}", sf + ".c2Failures → c4Failures")
        dec, dec1 = fams["decisionFamily"], fams["family:decision_ranking_protected_human_review_boundary"]
        if any(dec[k] != dec1[k] for k in ("c2Failures", "c4Failures", "repaired", "new", "pairedN")):
            raise SystemExit("decision family entry inconsistent")
    for name, t in C["pooled"]["contrasts"].items():
        a, b = name.split("->")
        contrast_keys(R, f"contrast.pooled.{a}to{b}", t, src(f, "pooled", "contrasts", name))
    cl = C["pooled"]["clearanceC2toC4"]
    sc = src(f, "pooled", "clearanceC2toC4")
    R.prop("clear.pooled.C2toC4", cl["cleared"], cl["c2Failures"], cl["p"], cl["lo"], cl["hi"], sc)
    R.count("clear.pooled.C2toC4.still", cl["stillFailing"], sc + ".stillFailing")
    ok = all(x["holds"] for x in C["signIdentityIntoC4"] if x["applies"])
    R.text("contrast.signIdentityIntoC4.holds", "true" if ok else "false", src(f, "signIdentityIntoC4") + " (every applicable entry holds: exact p = 2·0.5^b when c = 0)")
    if not ok:
        raise SystemExit("sign identity does not hold")


def cost_group(R, stats, transitions, RA):
    f = "repair_anatomy.json"
    for m in MODELS:
        s = SLUG[m]
        r = stats["models"][m]["controlRetentionC2toC4"]
        sr = src("tab4_stats.json", "models", m, "controlRetentionC2toC4")
        ctl = RA["models"][m]["controls"]
        changed = ctl["validClaimPreservedChanged"]
        R.ppdiff(f"cost.{s}.C2toC4.keptDiff", 100 * r["diff"], 100 * r["lo"], 100 * r["hi"], 2, sr + " (diff, bootstrap lo/hi)", with_ci=changed > 0)
        if changed == 0:
            R.notes.append(f"`cost.{s}.C2toC4.keptDiff`：{m} 的 {r['pairedN']} 个配对对照保留率差全部为 0（repair_anatomy validClaimPreservedChanged = 0），bootstrap 区间退化为 [0, 0]，未生成 .ci/.full 键；正文写「保留率无变化」。")
        R.count(f"cost.{s}.C2toC4.keptDiff.n", r["pairedN"], sr + ".pairedN")
        R.put(f"cost.{s}.C2toC4.keptC2", fpct(r["c2"]), r["c2"], sr + ".c2 (paired controls)")
        R.put(f"cost.{s}.C2toC4.keptC4", fpct(r["c4"]), r["c4"], sr + ".c4 (paired controls)")
        sc = src(f, "models", m, "controls")
        R.kn(f"cost.{s}.controls.keptChanged", changed, ctl["pairedPreservedN"], sc + ".validClaimPreservedChanged / pairedPreservedN")
        R.count(f"cost.{s}.controls.keptChanged", changed, sc + ".validClaimPreservedChanged")
        R.count(f"cost.{s}.controls.keptDecreased", ctl["preservedDecreased"], sc + ".preservedDecreased")
        R.kn(f"cost.{s}.controls.anyRepair", ctl["anyRepairAction"], ctl["n"], sc + ".anyRepairAction / n")
        R.count(f"cost.{s}.controls.anyRepair", ctl["anyRepairAction"], sc + ".anyRepairAction")
        R.kn(f"cost.{s}.controls.relabeledOrRemoved", ctl["supportedSideRelabeledOrRemoved"], ctl["n"], sc + ".supportedSideRelabeledOrRemoved / n (includes a regenerated control, measured on its regenerated output)")
        R.count(f"cost.{s}.controls.relabeledOrRemoved", ctl["supportedSideRelabeledOrRemoved"], sc + ".supportedSideRelabeledOrRemoved")
        vs_c2 = ctl["supportedSideRelabeledOrRemoved"] - ctl["supportedSideRelabeledOrRemovedOnRegeneratedOutput"]
        R.kn(f"cost.{s}.controls.relabeledOrRemovedVsC2", vs_c2, ctl["pairedSupportedN"], sc + ".supportedSideRelabeledOrRemoved − supportedSideRelabeledOrRemovedOnRegeneratedOutput, over pairedSupportedN")
        R.kn(f"cost.{s}.controls.supportedDecreased", ctl["supportedCountDecreased"], ctl["pairedSupportedN"], sc + ".supportedCountDecreased / pairedSupportedN")
        R.count(f"cost.{s}.controls.objectsRemoved", ctl["supportedSideObjectsRemoved"], sc + ".supportedSideObjectsRemoved")
        R.text(f"cost.{s}.controls.regeneratedIds", ", ".join(ctl["regeneratedControlIds"]) or "none", sc + ".regeneratedControlIds")
        # explicit suppression
        t = next(x for x in transitions if x["model"] == m)
        st = src("c4_transitions.json", f"[model={m}]")
        R.count(f"cost.{s}.suppressed.new", t["newSuppressed"], st + ".newSuppressed")
        R.count(f"cost.{s}.suppressed.recovered", t["recoveredSuppressed"], st + ".recoveredSuppressed")
        R.count(f"cost.{s}.suppressed.pairedN", t["pairedEvaluableN"], st + ".pairedEvaluableN")
        if abs(t["pairedDeltaPP"] - 100 * r["diff"]) > 1e-9:
            raise SystemExit(f"c4_transitions / tab4_stats retention diff differ for {m}")
        # supported-side entries
        sc_ = RA["models"][m]["supportedCount"]
        for part, name in (("paired", ""), ("pairedRisk", ".risk"), ("pairedControl", ".control")):
            v = sc_[part]
            sp = src(f, "models", m, "supportedCount", part)
            R.mean(f"cost.{s}.supported{name}.c2", v["meanC2"], 1, sp + ".meanC2")
            R.mean(f"cost.{s}.supported{name}.c4", v["meanC4"], 1, sp + ".meanC4")
            R.put(f"cost.{s}.supported{name}.delta", fsigned(v["meanDelta"], 2), v["meanDelta"], sp + ".meanDelta")
            R.count(f"cost.{s}.supported{name}.n", v["n"], sp + ".n")
            R.put(f"cost.{s}.supported{name}.retained", fpct(v["retainedShare"]), v["retainedShare"], sp + ".retainedShare")
            R.kn(f"cost.{s}.supported{name}.decreased", v["decreased"], v["n"], sp + ".decreased / n")
            R.count(f"cost.{s}.supported{name}.increased", v["increased"], sp + ".increased")
        sp = src(f, "models", m, "supportedCount")
        R.mean(f"cost.{s}.supported.all144.c2", sc_["all144MeanC2_unparsedAsZero"], 1, sp + ".all144MeanC2_unparsedAsZero")
        R.mean(f"cost.{s}.supported.all144.c4", sc_["all144MeanC4_unparsedAsZero"], 1, sp + ".all144MeanC4_unparsedAsZero")
        R.put(f"cost.{s}.supported.all144.delta", fsigned(sc_["all144Delta_unparsedAsZero"], 2), sc_["all144Delta_unparsedAsZero"], sp + ".all144Delta_unparsedAsZero")
        z = sc_["zeroedCaseIds"]
        R.count(f"cost.{s}.zeroed", len(z["risk"]) + len(z["control"]), sp + ".zeroedCaseIds (risk + control)")
        R.count(f"cost.{s}.zeroed.risk", len(z["risk"]), sp + ".zeroedCaseIds.risk")
        R.count(f"cost.{s}.zeroed.control", len(z["control"]), sp + ".zeroedCaseIds.control")
        R.text(f"cost.{s}.zeroed.ids", ", ".join(z["risk"] + z["control"]) or "none", sp + ".zeroedCaseIds")
        # interviewSignalRisks
        isr = RA["models"][m]["interviewSignalRisks"]
        for part in ("risk", "control", "all"):
            v = isr[part]
            si = src(f, "models", m, "interviewSignalRisks", part)
            R.put(f"cost.{s}.isr.{part}", fpct(v["c4Items"] / v["c2Items"]), v["c4Items"] / v["c2Items"], si + ".c4Items / c2Items")
            R.count(f"cost.{s}.isr.{part}.c2", v["c2Items"], si + ".c2Items")
            R.count(f"cost.{s}.isr.{part}.c4", v["c4Items"], si + ".c4Items")
            R.count(f"cost.{s}.isr.{part}.removed", v["removedByRepair"], si + ".removedByRepair")
            R.count(f"cost.{s}.isr.{part}.movedInItems", v["movedInItems"], si + ".movedInItems")
            R.count(f"cost.{s}.isr.{part}.movedInEvidence", v["movedInEvidence"], si + ".movedInEvidence")
            if abs(round(100 * v["c4Items"] / v["c2Items"], 1) - v["ratioC4overC2"]["pct"]) > 1e-9:
                raise SystemExit("interviewSignalRisks ratio mismatch")
        for fam in FAM_ORDER:
            v = isr["riskByFamily"][fam]
            si = src(f, "models", m, "interviewSignalRisks", "riskByFamily", fam)
            R.count(f"cost.{s}.isr.{fam}.c2", v["c2Items"], si + ".c2Items")
            R.count(f"cost.{s}.isr.{fam}.c4", v["c4Items"], si + ".c4Items")
            R.count(f"cost.{s}.isr.{fam}.removed", v["removedByRepair"], si + ".removedByRepair")
        # supported-side composition and bare strings
        comp = RA["models"][m]["supportedSideCompositionC2"]
        v = comp["optimizedCvShare"]
        R.kn(f"cost.{s}.cvShare", v["k"], v["n"], src(f, "models", m, "supportedSideCompositionC2", "optimizedCvShare"), with_pct=True)
        for kind, n in sorted(comp["byKind"].items()):
            R.count(f"cost.{s}.composition.{kind}", n, src(f, "models", m, "supportedSideCompositionC2", "byKind", kind))
        bs = RA["models"][m]["bareStringItems"]
        sb = src(f, "models", m, "bareStringItems")
        R.kn(f"cost.{s}.bare.bundles", bs["c2BundlesWithStringCvItems"], bs["c2ParsedBundles"], sb + ".c2BundlesWithStringCvItems / c2ParsedBundles")
        R.count(f"cost.{s}.bare.stringItems", bs["c2StringCvItems"], sb + ".c2StringCvItems")
        R.count(f"cost.{s}.bare.objectItems", bs["c2ObjectCvItems"], sb + ".c2ObjectCvItems")
        R.count(f"cost.{s}.bare.claimHasSource", bs["c4ClaimHasSourceRoutes"], sb + ".c4ClaimHasSourceRoutes")
        R.count(f"cost.{s}.bare.claimHasSourceOnRaw", bs["c4ClaimHasSourceRoutesOnRawStrings"], sb + ".c4ClaimHasSourceRoutesOnRawStrings")


def repair_group(R, RA, RF, C):
    f = "repair_anatomy.json"
    cat_slug = {"relabel_supported_to_unsupported": "relabel", "delete_or_replace": "deleteReplace",
                "move_to_interviewSignalRisks": "moveISR", "requirement_status_or_structure": "reqStatus",
                "other_structural": "otherStructural"}
    if list(RA["categories"]) != list(cat_slug):
        raise SystemExit(f"unexpected repair categories {RA['categories']}")
    labels = sorted({lab for m in MODELS for lab in RA["models"][m]["repairActions"]["byLabel"]})
    arcs = sorted({a for m in MODELS for a in RA["models"][m]["repairActions"]["byActionRuleCode"]})
    comps = list(RA["components"])
    cleared_actions = sorted({a for m in MODELS for a in RA["models"][m]["clearedC2toC4"]["clearedCasesWithAction"]})
    dec_actions = sorted({a for m in MODELS for a in RA["models"][m]["clearedC2toC4"]["decisionFamilyClearedCasesWithAction"]})
    dec_events = sorted({a for m in MODELS for a in RA["models"][m]["clearedC2toC4"]["decisionFamilyRepairEventsByActionSection"]})
    codes = sorted({c for m in MODELS for c in RF["models"][m]["c4RequirementDowngrades"]["byCode"]})
    for m in MODELS:
        s = SLUG[m]
        M = RA["models"][m]
        ra = M["repairActions"]
        sa = src(f, "models", m, "repairActions")
        R.count(f"repair.{s}.events.total", ra["totalEvents"], sa + ".totalEvents")
        for cat, slug in cat_slug.items():
            v = ra["byCategory"][cat]
            R.count(f"repair.{s}.cat.{slug}.events", v["events"]["total"], sa + f'.byCategory["{cat}"].events.total')
            R.count(f"repair.{s}.cat.{slug}.events.risk", v["events"]["risk"], sa + f'.byCategory["{cat}"].events.risk')
            R.count(f"repair.{s}.cat.{slug}.events.control", v["events"]["control"], sa + f'.byCategory["{cat}"].events.control')
            R.count(f"repair.{s}.cat.{slug}.cases", v["cases"]["total"], sa + f'.byCategory["{cat}"].cases.total')
            R.count(f"repair.{s}.cat.{slug}.cases.risk", v["cases"]["risk"], sa + f'.byCategory["{cat}"].cases.risk')
            R.count(f"repair.{s}.cat.{slug}.cases.control", v["cases"]["control"], sa + f'.byCategory["{cat}"].cases.control')
        for lab in labels:
            v = ra["byLabel"].get(lab)
            sl = sa + f'.byLabel["{lab}"]' + ("" if v else " (absent = 0)")
            R.count(f"repair.{s}.label.{slugify(lab)}.events", v["events"]["total"] if v else 0, sl)
            R.count(f"repair.{s}.label.{slugify(lab)}.cases", v["cases"]["total"] if v else 0, sl)
        for arc in arcs:
            v = ra["byActionRuleCode"].get(arc)
            R.count(f"repair.{s}.arc.{slugify(arc)}", v["total"] if v else 0, sa + f'.byActionRuleCode["{arc}"].total' + ("" if v else " (absent = 0)"))
        R.count(f"repair.{s}.claimHasSource", ra["claimHasSourceRoutes"], sa + ".claimHasSourceRoutes")
        R.count(f"repair.{s}.fixReq.downgrades", ra["fixRequirementsStatusDowngrades"], sa + ".fixRequirementsStatusDowngrades")
        R.count(f"repair.{s}.fixReq.duplicateCases", len(ra["fixRequirementsDuplicateRemovalCases"]), sa + ".fixRequirementsDuplicateRemovalCases (count)")
        R.text(f"repair.{s}.fixReq.duplicateCases.ids", ", ".join(ra["fixRequirementsDuplicateRemovalCases"]) or "none", sa + ".fixRequirementsDuplicateRemovalCases")
        dg = RF["models"][m]["c4RequirementDowngrades"]
        sd = src("redactor_frontier.json", "models", m, "c4RequirementDowngrades")
        if dg["fixRequirements"] != ra["fixRequirementsStatusDowngrades"]:
            raise SystemExit(f"_fix_requirements downgrade counts differ for {m}")
        for code in codes:
            R.count(f"repair.{s}.downgrade.{code}", dg["byCode"].get(code, 0), sd + f'.byCode["{code}"]' + ("" if code in dg["byCode"] else " (absent = 0)"))
        R.count(f"repair.{s}.downgrade.total", sum(dg["byCode"].values()), sd + ".byCode (sum)")
        # pipeline
        p = M["pipeline"]
        sp = src(f, "models", m, "pipeline")
        R.count(f"repair.{s}.regenerated", p["regenerated"], sp + ".regenerated")
        R.text(f"repair.{s}.regenerated.ids", ", ".join(p["regeneratedCases"]) or "none", sp + ".regeneratedCases")
        R.count(f"repair.{s}.notRepairable", p["notRepairable"], sp + ".notRepairable")
        R.kn(f"repair.{s}.nonEscalating", p["repairNonEscalatingTrue"], p["repairNonEscalatingTrue"] + p["repairNonEscalatingFalse"], sp + ".repairNonEscalatingTrue / (True + False)")
        R.count(f"repair.{s}.componentFalseToTrue", p["componentFalseToTrueTotal"], sp + ".componentFalseToTrueTotal")
        R.count(f"repair.{s}.trapFalseToTrue", p["trapFellAnyFalseToTrueRisk"], sp + ".trapFellAnyFalseToTrueRisk")
        R.count(f"repair.{s}.newSupportedText", p["casesWithNewSupportedSideTextInC4"], sp + ".casesWithNewSupportedSideTextInC4")
        R.kn(f"repair.{s}.newSupportedText", p["casesWithNewSupportedSideTextInC4"], p["casesComparedForNewText"], sp + ".casesWithNewSupportedSideTextInC4 / casesComparedForNewText")
        for agg in ("ACCEPT", "HUMAN_REVIEW", "BLOCK"):
            R.count(f"repair.{s}.c4agg.{agg}", p["c4AggregateSummary"].get(agg, 0), sp + f".c4AggregateSummary.{agg}" + ("" if agg in p["c4AggregateSummary"] else " (absent = 0)"))
        for name, v in sorted(M["checks"].items()):
            R.count(f"repair.{s}.check.{name}", v, src(f, "models", m, "checks", name))
        # cleared cases
        cl = M["clearedC2toC4"]
        scl = src(f, "models", m, "clearedC2toC4")
        cc = C["models"][m]["clearanceC2toC4"]
        if (cl["cleared"], cl["c2Fell"], cl["new"]) != (cc["cleared"], cc["c2Failures"], C["models"][m]["contrasts"]["C2->C4"]["new"]):
            raise SystemExit(f"repair_anatomy / tab4_contrasts clearance differ for {m}")
        v = cl["decisionFamilyShareOfCleared"]
        R.kn(f"repair.{s}.cleared.decisionShare", v["k"], v["n"], scl + ".decisionFamilyShareOfCleared", with_pct=True)
        R.kn(f"repair.{s}.cleared.nonDecision", cl["nonDecisionCleared"], cl["nonDecisionC2Fell"], scl + ".nonDecisionCleared / nonDecisionC2Fell")
        R.count(f"repair.{s}.cleared.unattributed", cl["unattributedHitLocations"], scl + ".unattributedHitLocations")
        for comp in comps:
            R.count(f"repair.{s}.cleared.component.{comp}", cl["clearedCasesWithComponent"].get(comp, 0), scl + f".clearedCasesWithComponent.{comp}" + ("" if comp in cl["clearedCasesWithComponent"] else " (absent = 0)"))
        for cat, slug in cat_slug.items():
            R.count(f"repair.{s}.cleared.category.{slug}", cl["clearedCasesWithCategory"].get(cat, 0), scl + f'.clearedCasesWithCategory["{cat}"]' + ("" if cat in cl["clearedCasesWithCategory"] else " (absent = 0)"))
        for a in cleared_actions:
            R.count(f"repair.{s}.cleared.action.{slugify(a)}", cl["clearedCasesWithAction"].get(a, 0), scl + f'.clearedCasesWithAction["{a}"]' + ("" if a in cl["clearedCasesWithAction"] else " (absent = 0)"))
        for a in dec_actions:
            R.count(f"repair.{s}.cleared.decisionAction.{slugify(a)}", cl["decisionFamilyClearedCasesWithAction"].get(a, 0), scl + f'.decisionFamilyClearedCasesWithAction["{a}"]' + ("" if a in cl["decisionFamilyClearedCasesWithAction"] else " (absent = 0)"))
        for a in dec_events:
            R.count(f"repair.{s}.cleared.decisionEvents.{slugify(a)}", cl["decisionFamilyRepairEventsByActionSection"].get(a, 0), scl + f'.decisionFamilyRepairEventsByActionSection["{a}"]' + ("" if a in cl["decisionFamilyRepairEventsByActionSection"] else " (absent = 0)"))
        R.count(f"repair.{s}.cleared.decisionEvents.total", sum(cl["decisionFamilyRepairEventsByActionSection"].values()), scl + ".decisionFamilyRepairEventsByActionSection (sum)")
        for fam in FAM_ORDER:
            v = cl["byFamily"][fam]
            fc = C["models"][m]["familiesC2toC4"]["decisionFamily" if fam == "decision" else "family:" + next(k for k, x in FAM.items() if x == fam)]
            if (v["c2Fell"], v["cleared"], v["residual"]) != (fc["c2Failures"], fc["repaired"], fc["c4Failures"]):
                raise SystemExit(f"repair_anatomy / tab4_contrasts family counts differ for {m} {fam}")
    R.count("repair.pooled.regenerated", sum(RA["models"][m]["pipeline"]["regenerated"] for m in MODELS), src(f, "models", "*", "pipeline", "regenerated") + " (sum over models)")
    R.count("repair.pooled.notRepairable", sum(RA["models"][m]["pipeline"]["notRepairable"] for m in MODELS), src(f, "models", "*", "pipeline", "notRepairable") + " (sum over models)")
    R.count("repair.pooled.fixReq.downgrades", sum(RA["models"][m]["repairActions"]["fixRequirementsStatusDowngrades"] for m in MODELS), src(f, "models", "*", "repairActions", "fixRequirementsStatusDowngrades") + " (sum over models)")


def validator_group(R, RA):
    f = "repair_anatomy.json"
    variants = (("primary_entries_deepest", ""), ("sensitivity_entries_under", ".under"),
                ("sensitivity_objectsTextOnly_under", ".textOnly"), ("sensitivity_objectsMerged_under", ".merged"))
    rules = sorted({r for m in MODELS for v, _ in variants for part in ("riskTrapItemsFailedByRule", "controlValidItemsFailedByRule")
                    for r in RA["models"][m]["itemLevelC2"][v][part]})
    comps = list(RA["components"])
    pooled = {"n": 0, "c3Flagged": 0, "c3FailOnTrapRuleAnywhere": 0, "accept": 0}
    for m in MODELS:
        s = SLUG[m]
        for var, suffix in variants:
            v = RA["models"][m]["itemLevelC2"][var]
            sv = src(f, "models", m, "itemLevelC2", var)
            for part, name in (("riskTrapItemsFailed", "trapFailed"), ("riskTrapItemsFailedOnTrapRule", "trapFailedOnTrapRule"),
                               ("controlValidItemsFailed", "controlFailed"), ("controlFailedItemsContainingValidSignature", "failedWithValidSignature")):
                x = v[part]
                R.kn(f"validator.{s}.item.{name}{suffix}", x["k"], x["n"], sv + "." + part, with_pct=True)
            R.count(f"validator.{s}.item.trapCases{suffix}", v["riskCasesWithTrapItems"], sv + ".riskCasesWithTrapItems")
            if not suffix:
                for rule in rules:
                    R.count(f"validator.{s}.item.trapFailedByRule.{rule}", v["riskTrapItemsFailedByRule"].get(rule, 0), sv + f".riskTrapItemsFailedByRule.{rule}" + ("" if rule in v["riskTrapItemsFailedByRule"] else " (absent = 0)"))
                    R.count(f"validator.{s}.item.controlFailedByRule.{rule}", v["controlValidItemsFailedByRule"].get(rule, 0), sv + f".controlValidItemsFailedByRule.{rule}" + ("" if rule in v["controlValidItemsFailedByRule"] else " (absent = 0)"))
                for fam in FAM_ORDER:
                    x = v["riskByFamily"].get(fam)
                    if x:
                        R.kn(f"validator.{s}.item.trapFailed.{fam}", x["k"], x["n"], sv + f".riskByFamily.{fam}", with_pct=True)
        rc = RA["models"][m]["residualC4"]
        sr = src(f, "models", m, "residualC4")
        n = rc["n"]
        R.count(f"validator.{s}.residual.n", n, sr + ".n")
        R.kn(f"validator.{s}.residual.c3Flagged", rc["c3Flagged"], n, sr + ".c3Flagged / n")
        R.kn(f"validator.{s}.residual.c3TrapRuleFail", rc["c3FailOnTrapRuleAnywhere"], n, sr + ".c3FailOnTrapRuleAnywhere / n")
        R.kn(f"validator.{s}.residual.c3TrapRuleOnHitItem", rc["c3TrapRuleFailOnHitItem"], n, sr + ".c3TrapRuleFailOnHitItem / n")
        R.kn(f"validator.{s}.residual.c3AnyFailOnHitItem", rc["c3AnyFailOnHitItem"], n, sr + ".c3AnyFailOnHitItem / n")
        acc = rc["c4AggregateCounts"].get("ACCEPT", 0)
        R.kn(f"validator.{s}.residual.c4Accept", acc, n, sr + ".c4AggregateCounts.ACCEPT / n")
        R.count(f"validator.{s}.residual.c4Findings", rc["c4FindingsTotal"], sr + ".c4FindingsTotal")
        for comp in comps:
            R.count(f"validator.{s}.residual.component.{comp}", rc["componentsC4"].get(comp, 0), sr + f".componentsC4.{comp}" + ("" if comp in rc["componentsC4"] else " (absent = 0)"))
        R.text(f"validator.{s}.residual.ids", ", ".join(c["caseId"] for c in rc["cases"]), sr + ".cases[].caseId")
        pooled["n"] += n
        pooled["c3Flagged"] += rc["c3Flagged"]
        pooled["c3FailOnTrapRuleAnywhere"] += rc["c3FailOnTrapRuleAnywhere"]
        pooled["accept"] += acc
    sp = src(f, "models", "*", "residualC4")
    R.count("validator.pooled.residual.n", pooled["n"], sp + ".n (sum over models)")
    R.kn("validator.pooled.residual.c3Flagged", pooled["c3Flagged"], pooled["n"], sp + ".c3Flagged (sums over models)")
    R.kn("validator.pooled.residual.c3TrapRuleFail", pooled["c3FailOnTrapRuleAnywhere"], pooled["n"], sp + ".c3FailOnTrapRuleAnywhere (sums over models)")
    R.kn("validator.pooled.residual.c4Accept", pooled["accept"], pooled["n"], sp + ".c4AggregateCounts.ACCEPT (sums over models)")


def cfg_text(c, seed=False):
    s = "S off" if (c["mode"] == "none" or c["p"] == 0) else f"S {c['mode']} p={fg(c['p'])}"
    t = f"{s}, R q={fg(c['q'])}, X r={fg(c['r'])}"
    return t + (f", seed {c['seed']}" if seed else "")


def frontier_group(R, RF, stats):
    f = "redactor_frontier.json"
    if not RF["postHoc"]:
        raise SystemExit("redactor_frontier.json is expected to be flagged POST HOC")
    R.text("frontier.design.fractions", ", ".join(fg(x) for x in RF["fractions"]), src(f, "fractions"))
    R.count("frontier.design.fractions.n", len(RF["fractions"]), src(f, "fractions") + " (count)")
    R.text("frontier.design.seeds", ", ".join(str(x) for x in RF["seeds"]), src(f, "seeds"))
    for axis in ("p", "q", "r"):
        R.text(f"frontier.design.{axis}", ", ".join(fg(x) for x in RF["xGridDesign"][axis]), src(f, "xGridDesign", axis))
    R.text("frontier.design.designedOn", RF["designedOn"], src(f, "designedOn"))
    R.text("frontier.design.extensionsDesignedOn", RF["extensionsDesignedOn"], src(f, "extensionsDesignedOn"))
    fields = sorted({k.split(".")[-1] for m in MODELS for k in RF["models"][m]["floorDecomposition"]["delete"]["decisionAnywhereFieldCases"]})
    combos = sorted({k for m in MODELS for k in RF["models"][m]["floorDecomposition"]["delete"]["decisionTriggerCombos"]})
    pooled = {"trapFellAny": 0, "riskN": 0, "decisionFamily": 0, "decisionWithAnywhereSignatures": 0, "requirementOverclaim": 0,
              "subjectiveExtra": 0, "other": 0, "nConfigs": 0, "nConfigsKeptAndRoutedAtLeastC4": 0, "nSeedRuns": 0,
              "nSeedRunsKeptAndRoutedAtLeastC4": 0, "fields": {k: 0 for k in fields}}
    for m in MODELS:
        s = SLUG[m]
        M = RF["models"][m]
        st = stats["models"][m]["proportions"]
        # points
        for pt in ("C2", "C4"):
            v = M[pt]
            sp = src(f, "models", m, pt)
            R.kn(f"frontier.{s}.{pt}.trap", round(v["trap"] * v["trapN"]), v["trapN"], sp + ".trap × trapN", with_pct=True)
            R.put(f"frontier.{s}.{pt}.kept", fpct(v["kept"]), v["kept"], sp + ".kept")
            R.count(f"frontier.{s}.{pt}.kept.n", v["keptN"], sp + ".keptN")
            R.mean(f"frontier.{s}.{pt}.supportedPerCase", v["supportedCount"], 1, sp + ".supportedCount")
            R.put(f"frontier.{s}.{pt}.trapRouted", fpct(v["trapRouted"]), v["trapRouted"], sp + ".trapRouted")
            R.put(f"frontier.{s}.{pt}.subjRouted", fpct(v["subjectiveRouted"]), v["subjectiveRouted"], sp + ".subjectiveRouted")
            R.count(f"frontier.{s}.{pt}.subjRouted.n", v["subjectiveRoutedN"], sp + ".subjectiveRoutedN")
            R.put(f"frontier.{s}.{pt}.reqExact", fpct(v["reqExactCtl"]), v["reqExactCtl"], sp + ".reqExactCtl")
        if abs(M["C4"]["trap"] - st["C4"]["trapFellAny"]["p"]) > 1e-12 or abs(M["C2"]["trap"] - st["C2"]["trapFellAny"]["p"]) > 1e-12:
            raise SystemExit(f"redactor_frontier / tab4_stats trap rates differ for {m}")
        # S family readout
        ro = M["readout"]
        sr = src(f, "models", m, "readout")
        R.put(f"frontier.{s}.S.attrition", fpct(ro["blindTrapAtC4Attrition"]), ro["blindTrapAtC4Attrition"], sr + ".blindTrapAtC4Attrition")
        R.put(f"frontier.{s}.S.retention", fpct(ro["blindTrapAtC4Retention"]), ro["blindTrapAtC4Retention"], sr + ".blindTrapAtC4Retention")
        R.put(f"frontier.{s}.S.floor", fpct(ro["blindFloorTrap"]), ro["blindFloorTrap"], sr + ".blindFloorTrap")
        # floor decomposition
        fd, fr = M["floorDecomposition"]["delete"], M["floorDecomposition"]["relabel"]
        if fd != fr:
            raise SystemExit(f"floor decomposition differs between delete and relabel for {m}")
        sf = src(f, "models", m, "floorDecomposition", "delete")
        R.kn(f"frontier.{s}.S.floor", fd["trapFellAny"], fd["riskN"], sf + ".trapFellAny / riskN")
        if abs(fd["trap"] - ro["blindFloorTrap"]) > 1e-12:
            raise SystemExit("floor readout mismatch")
        for cat in ("decisionFamily", "requirementOverclaim", "subjectiveExtra", "other"):
            R.count(f"frontier.{s}.floor.{cat}", fd["byCategory"][cat], sf + f".byCategory.{cat}")
            pooled[cat] += fd["byCategory"][cat]
        R.count(f"frontier.{s}.floor.decisionAnywhere", fd["decisionWithAnywhereSignatures"], sf + ".decisionWithAnywhereSignatures")
        for combo in combos:
            R.count(f"frontier.{s}.floor.combo.{slugify(combo)}", fd["decisionTriggerCombos"].get(combo, 0), sf + f'.decisionTriggerCombos["{combo}"]' + ("" if combo in fd["decisionTriggerCombos"] else " (absent = 0)"))
        for kind, n in sorted(fd["subjectiveExtraKinds"].items()):
            R.count(f"frontier.{s}.floor.subjExtra.{kind}", n, sf + f".subjectiveExtraKinds.{kind}")
        byfield = {k.split(".")[-1]: v for k, v in fd["decisionAnywhereFieldCases"].items()}
        for fld in fields:
            R.count(f"frontier.{s}.floor.field.{fld}", byfield.get(fld, 0), sf + f'.decisionAnywhereFieldCases["hiringEvidencePacket.{fld}"]' + ("" if fld in byfield else " (absent = 0)"))
            pooled["fields"][fld] += byfield.get(fld, 0)
        pooled["trapFellAny"] += fd["trapFellAny"]
        pooled["riskN"] += fd["riskN"]
        pooled["decisionWithAnywhereSignatures"] += fd["decisionWithAnywhereSignatures"]
        # non-decision subset
        nd = M["nonDecision"]
        rd = nd["readout"]
        sn = src(f, "models", m, "nonDecision", "readout")
        R.kn(f"frontier.{s}.nd.C2.trap", rd["c2TrapCount"], rd["riskN"], sn + ".c2TrapCount / riskN", with_pct=True)
        R.kn(f"frontier.{s}.nd.C4.trap", rd["c4TrapCount"], rd["riskN"], sn + ".c4TrapCount / riskN", with_pct=True)
        R.count(f"frontier.{s}.nd.gap", rd["c2TrapCount"] - rd["c4TrapCount"], sn + ".c2TrapCount − c4TrapCount")
        R.count(f"frontier.{s}.nd.controlN", rd["controlN"], sn + ".controlN")
        R.put(f"frontier.{s}.nd.C4.kept", fpct(rd["c4Kept"]), rd["c4Kept"], sn + ".c4Kept")
        R.mean(f"frontier.{s}.nd.C4.supportedPerCase", rd["c4SupportedCount"], 1, sn + ".c4SupportedCount")
        R.put(f"frontier.{s}.nd.S.attrition", fpct(rd["blindTrapAtC4Attrition"]), rd["blindTrapAtC4Attrition"], sn + ".blindTrapAtC4Attrition")
        R.put(f"frontier.{s}.nd.S.retention", fpct(rd["blindTrapAtC4Retention"]), rd["blindTrapAtC4Retention"], sn + ".blindTrapAtC4Retention")
        R.put(f"frontier.{s}.nd.S.floor", fpct(rd["blindFloorTrap"]), rd["blindFloorTrap"], sn + ".blindFloorTrap")
        vx = rd["variantFullSampleC4Coordinates"]
        R.put(f"frontier.{s}.nd.S.attrition.fullX", fpct(vx["blindTrapAtC4Attrition"]), vx["blindTrapAtC4Attrition"], sn + ".variantFullSampleC4Coordinates.blindTrapAtC4Attrition")
        R.put(f"frontier.{s}.nd.S.retention.fullX", fpct(vx["blindTrapAtC4Retention"]), vx["blindTrapAtC4Retention"], sn + ".variantFullSampleC4Coordinates.blindTrapAtC4Retention")
        # extended grid
        xg = M["xGrid"]["readout"]
        sx = src(f, "models", m, "xGrid", "readout")
        R.count(f"frontier.{s}.grid.nConfigs", xg["nConfigs"], sx + ".nConfigs")
        R.count(f"frontier.{s}.grid.nSeedRuns", xg["nSeedRuns"], sx + ".nSeedRuns")
        R.count(f"frontier.{s}.grid.atOrBelowC4", xg["nConfigsTrapAtOrBelowC4"], sx + ".nConfigsTrapAtOrBelowC4")
        R.kn(f"frontier.{s}.grid.atOrBelowC4", xg["nConfigsTrapAtOrBelowC4"], xg["nConfigs"], sx + ".nConfigsTrapAtOrBelowC4 / nConfigs")
        # the grid configurations whose seed-mean trap rate is at or below C4's (same 1e-12 tolerance as redactor_frontier.py)
        cfgs = M["xGrid"]["configs"]
        low = [x for x in cfgs if x["trap"] <= xg["c4"]["trap"] + 1e-12]
        if len(cfgs) != xg["nConfigs"] or len(low) != xg["nConfigsTrapAtOrBelowC4"]:
            raise SystemExit(f"{m}: xGrid.configs disagree with the readout counts")
        sl = src(f, "models", m, "xGrid", "configs") + " filtered to trap <= readout.c4.trap"
        R.text(f"frontier.{s}.grid.atOrBelowC4.configs", "; ".join(cfg_text(x) for x in sorted(low, key=lambda x: x["order"])) or "none", sl + " ({mode, p, q, r}, grid order)")
        for fld, name in (("kept", "maxKept"), ("trapRouted", "maxTrapRouted"), ("subjectiveRouted", "maxSubjRouted")):
            if low:
                v = max(x[fld] for x in low)
                R.put(f"frontier.{s}.grid.atOrBelowC4.{name}", fpct(v), v, sl + f" (maximum of {fld})")
            else:
                R.put(f"frontier.{s}.grid.atOrBelowC4.{name}", "–", None, sl + f" (no configuration; maximum of {fld} undefined)")
        R.put(f"frontier.{s}.grid.C4.trapRouted", fpct(xg["c4"]["trapRouted"]), xg["c4"]["trapRouted"], sx + ".c4.trapRouted")
        R.put(f"frontier.{s}.grid.C4.subjRouted", fpct(xg["c4"]["subjectiveRouted"]), xg["c4"]["subjectiveRouted"], sx + ".c4.subjectiveRouted")
        R.count(f"frontier.{s}.grid.both", xg["nConfigsKeptAndRoutedAtLeastC4"], sx + ".nConfigsKeptAndRoutedAtLeastC4")
        R.kn(f"frontier.{s}.grid.both", xg["nConfigsKeptAndRoutedAtLeastC4"], xg["nConfigs"], sx + ".nConfigsKeptAndRoutedAtLeastC4 / nConfigs")
        R.kn(f"frontier.{s}.grid.bothSeedRuns", xg["nSeedRunsKeptAndRoutedAtLeastC4"], xg["nSeedRuns"], sx + ".nSeedRunsKeptAndRoutedAtLeastC4 / nSeedRuns")
        n_s = len(RF["fractions"]) * len(M["curves"])
        R.kn(f"frontier.{s}.grid.sCurveBoth", xg["sCurvePointsKeptAndRoutedAtLeastC4"], n_s, sx + ".sCurvePointsKeptAndRoutedAtLeastC4 / (len(fractions) × number of S curves)")
        for name, part in (("lowest", "lowestTrap"), ("lowestSeed", "lowestTrapSingleSeed"), ("keptOnly", "lowestTrapKeptAtLeastC4"), ("xOnly", "xOnly")):
            v = xg[part]
            sv = sx + "." + part
            R.put(f"frontier.{s}.grid.{name}.trap", fpct(v["trap"]), v["trap"], sv + ".trap")
            R.put(f"frontier.{s}.grid.{name}.kept", fpct(v["kept"]), v["kept"], sv + ".kept")
            R.put(f"frontier.{s}.grid.{name}.trapRouted", fpct(v["trapRouted"]), v["trapRouted"], sv + ".trapRouted")
            R.put(f"frontier.{s}.grid.{name}.subjRouted", fpct(v["subjectiveRouted"]), v["subjectiveRouted"], sv + ".subjectiveRouted")
            R.put(f"frontier.{s}.grid.{name}.reqExact", fpct(v["reqExactCtl"]), v["reqExactCtl"], sv + ".reqExactCtl")
            R.mean(f"frontier.{s}.grid.{name}.supportedPerCase", v["supportedCount"], 1, sv + ".supportedCount")
            R.text(f"frontier.{s}.grid.{name}.config", cfg_text(v, seed=(name == "lowestSeed")), sv + ".{mode, p, q, r" + (", seed}" if name == "lowestSeed" else "}"))
        for part in ("lowestTrapKeptAndRoutedAtLeastC4", "lowestTrapRoutedAtLeastC4", "lowestTrapSCurveKeptAndRoutedAtLeastC4", "lowestTrapSeedRunKeptAndRoutedAtLeastC4"):
            R.text(f"frontier.{s}.grid.{part}", "none" if xg[part] is None else cfg_text(xg[part]), sx + "." + part + " (null = no configuration)")
        pooled["nConfigs"] += xg["nConfigs"]
        pooled["nConfigsKeptAndRoutedAtLeastC4"] += xg["nConfigsKeptAndRoutedAtLeastC4"]
        pooled["nSeedRuns"] += xg["nSeedRuns"]
        pooled["nSeedRunsKeptAndRoutedAtLeastC4"] += xg["nSeedRunsKeptAndRoutedAtLeastC4"]
        # fixed policies
        for pol, name in (("drop_unsourced", "dropUnsourced"), ("drop_all_supportedClaims", "dropAllSupportedClaims")):
            v = M["fixed"][pol]
            sv = src(f, "models", m, "fixed", pol)
            R.kn(f"frontier.{s}.{name}.trap", round(v["trap"] * v["trapN"]), v["trapN"], sv + ".trap × trapN", with_pct=True)
            R.put(f"frontier.{s}.{name}.kept", fpct(v["kept"]), v["kept"], sv + ".kept")
            R.mean(f"frontier.{s}.{name}.supportedPerCase", v["supportedCount"], 1, sv + ".supportedCount")
            R.put(f"frontier.{s}.{name}.trapRouted", fpct(v["trapRouted"]), v["trapRouted"], sv + ".trapRouted")
            R.put(f"frontier.{s}.{name}.subjRouted", fpct(v["subjectiveRouted"]), v["subjectiveRouted"], sv + ".subjectiveRouted")
        vs = M["validationSkipCheck"]
        R.count(f"frontier.{s}.skipCheck.cases", vs["cases"], src(f, "models", m, "validationSkipCheck", "cases"))
    sp = src(f, "models", "*", "floorDecomposition", "delete")
    R.kn("frontier.pooled.floor", pooled["trapFellAny"], pooled["riskN"], sp + ".trapFellAny / riskN (sums over models)")
    R.count("frontier.pooled.floor.total", pooled["trapFellAny"], sp + ".trapFellAny (sum over models)")
    for cat in ("decisionFamily", "requirementOverclaim", "subjectiveExtra", "other"):
        R.count(f"frontier.pooled.floor.{cat}", pooled[cat], sp + f".byCategory.{cat} (sum over models)")
    R.count("frontier.pooled.floor.decisionAnywhere", pooled["decisionWithAnywhereSignatures"], sp + ".decisionWithAnywhereSignatures (sum over models)")
    for fld in fields:
        R.count(f"frontier.pooled.floor.field.{fld}", pooled["fields"][fld], sp + f'.decisionAnywhereFieldCases["hiringEvidencePacket.{fld}"] (sum over models)')
    sx = src(f, "models", "*", "xGrid", "readout")
    R.count("frontier.pooled.grid.nConfigs", pooled["nConfigs"], sx + ".nConfigs (sum over models)")
    R.kn("frontier.pooled.grid.both", pooled["nConfigsKeptAndRoutedAtLeastC4"], pooled["nConfigs"], sx + ".nConfigsKeptAndRoutedAtLeastC4 / nConfigs (sums over models)")
    R.kn("frontier.pooled.grid.bothSeedRuns", pooled["nSeedRunsKeptAndRoutedAtLeastC4"], pooled["nSeedRuns"], sx + ".nSeedRunsKeptAndRoutedAtLeastC4 / nSeedRuns (sums over models)")


SRC_POLICIES = (("drop_note_cited", "dropNoteCited"), ("drop_note_or_unsourced", "dropNoteOrUnsourced"),
                ("drop_note_cited+X", "dropNoteCitedX"), ("drop_note_or_unsourced+X", "dropNoteOrUnsourcedX"))


def frontier_source_group(R, RF, stats):
    """Source-type policies of redactor_frontier.json (POST HOC, 2026-09-23): full sample, non-decision subset,
    routing, items moved, residual composition; plus the non-decision value of drop_unsourced and of X alone."""
    f = "redactor_frontier.json"
    d = RF["sourceTypePolicyDesign"]
    if not d["postHoc"] or [p for p, _ in SRC_POLICIES] != d["policies"]:
        raise SystemExit("redactor_frontier.json: unexpected source-type policy design")
    R.text("frontier.design.sourcePolicies.designedOn", d["designedOn"], src(f, "sourceTypePolicyDesign", "designedOn"))
    R.count("frontier.design.sourcePolicies.n", len(d["policies"]), src(f, "sourceTypePolicyDesign", "policies") + " (count)")
    pooled = {"n": 0, "both": 0, "atOrBelow": 0}
    for m in MODELS:
        s = SLUG[m]
        M = RF["models"][m]
        stp = M["sourceTypePolicies"]
        for pol, name in SRC_POLICIES:
            v, nd = M["fixed"][pol], M["fixedNonDecision"][pol]
            rec = stp["policies"][pol]
            sv, sn, sr = src(f, "models", m, "fixed", pol), src(f, "models", m, "fixedNonDecision", pol), src(f, "models", m, "sourceTypePolicies", "policies", pol)
            if rec["trapCount"] != round(v["trap"] * v["trapN"]) or abs(rec["ndTrap"] - nd["trap"]) > 1e-12:
                raise SystemExit(f"{m} {pol}: sourceTypePolicies readout disagrees with fixed / fixedNonDecision")
            R.kn(f"frontier.{s}.{name}.trap", rec["trapCount"], v["trapN"], sv + ".trap × trapN", with_pct=True)
            R.kn(f"frontier.{s}.{name}.nd.trap", rec["ndTrapCount"], nd["trapN"], sn + ".trap × trapN", with_pct=True)
            R.put(f"frontier.{s}.{name}.kept", fpct(v["kept"]), v["kept"], sv + ".kept")
            R.count(f"frontier.{s}.{name}.kept.n", v["keptN"], sv + ".keptN")
            R.mean(f"frontier.{s}.{name}.supportedPerCase", v["supportedCount"], 1, sv + ".supportedCount")
            R.put(f"frontier.{s}.{name}.trapRouted", fpct(v["trapRouted"]), v["trapRouted"], sv + ".trapRouted")
            R.put(f"frontier.{s}.{name}.subjRouted", fpct(v["subjectiveRouted"]), v["subjectiveRouted"], sv + ".subjectiveRouted")
            R.put(f"frontier.{s}.{name}.reqExact", fpct(v["reqExactCtl"]), v["reqExactCtl"], sv + ".reqExactCtl")
            R.count(f"frontier.{s}.{name}.moved", rec["movedTotal"], sr + ".movedTotal")
            R.kn(f"frontier.{s}.{name}.movedCases", rec["casesWithMove"], rec["cases"], sr + ".casesWithMove / cases")
            rd = rec["residualDecomposition"]
            for cat in ("decisionFamily", "requirementOverclaim", "subjectiveExtra", "other"):
                R.count(f"frontier.{s}.{name}.residual.{cat}", rd["byCategory"][cat], sr + f".residualDecomposition.byCategory.{cat}")
            for flag, key in (("trapAtOrBelow", "atOrBelowC4"), ("ndTrapAtOrBelow", "nd.atOrBelowC4"), ("keptAtLeast", "keptAtLeastC4"),
                              ("trapRoutedAtLeast", "trapRoutedAtLeastC4"), ("keptAndRoutedAtLeast", "bothC4")):
                R.text(f"frontier.{s}.{name}.{key}", "true" if rec["vsC4"][flag] else "false", sr + f".vsC4.{flag}")
        R.kn(f"frontier.{s}.srcPolicies.atOrBelowC4", stp["nPoliciesTrapAtOrBelowC4"], stp["nPolicies"], src(f, "models", m, "sourceTypePolicies", "nPoliciesTrapAtOrBelowC4") + " / nPolicies")
        R.kn(f"frontier.{s}.srcPolicies.both", stp["nPoliciesKeptAndRoutedAtLeastC4"], stp["nPolicies"], src(f, "models", m, "sourceTypePolicies", "nPoliciesKeptAndRoutedAtLeastC4") + " / nPolicies")
        pooled["n"] += stp["nPolicies"]
        pooled["both"] += stp["nPoliciesKeptAndRoutedAtLeastC4"]
        pooled["atOrBelow"] += stp["nPoliciesTrapAtOrBelowC4"]
        # drop_unsourced and X alone on the non-decision subset (reference rows)
        nd = M["fixedNonDecision"]["drop_unsourced"]
        R.kn(f"frontier.{s}.dropUnsourced.nd.trap", round(nd["trap"] * nd["trapN"]), nd["trapN"], src(f, "models", m, "fixedNonDecision", "drop_unsourced") + ".trap × trapN", with_pct=True)
        xo = stp["xOnlyReference"]
        sx = src(f, "models", m, "sourceTypePolicies", "xOnlyReference")
        if abs(xo["full"]["trap"] - M["xGrid"]["readout"]["xOnly"]["trap"]) > 1e-12:
            raise SystemExit(f"{m}: X-only reference differs from the grid's xOnly configuration")
        R.kn(f"frontier.{s}.xOnly.trap", round(xo["full"]["trap"] * xo["full"]["trapN"]), xo["full"]["trapN"], sx + ".full.trap × trapN", with_pct=True)
        R.kn(f"frontier.{s}.xOnly.nd.trap", round(xo["nonDecision"]["trap"] * xo["nonDecision"]["trapN"]), xo["nonDecision"]["trapN"], sx + ".nonDecision.trap × trapN", with_pct=True)
    sp = src(f, "models", "*", "sourceTypePolicies")
    R.kn("frontier.pooled.srcPolicies.atOrBelowC4", pooled["atOrBelow"], pooled["n"], sp + ".nPoliciesTrapAtOrBelowC4 / nPolicies (sums over models)")
    R.kn("frontier.pooled.srcPolicies.both", pooled["both"], pooled["n"], sp + ".nPoliciesKeptAndRoutedAtLeastC4 / nPolicies (sums over models)")
    R.notes.append("`frontier.*.dropNote*`：POST HOC（2026-09-23）来源类型策略，在已知「诱饵全部是 note」之后设计，读取案例元数据中的来源类型与条目 sourceIds，"
                   "不是内容无关变换；`*X` 变体另加 X(r = 1)（决策边界重置、清空 interviewSignalRisks / 检查清单 / 局限），其 subjRouted 按构造为 0。"
                   "`frontier.<m>.xOnly.*` 是 X 单独作用的参照（= 网格配置 p = 0、q = 0、r = 1）。")


def setup_source_group(R, setup):
    """Source-type facts of setup_facts.json (section 6, 2026-09-23)."""
    f = "setup_facts.json"
    st = setup["sourceTypes"]
    sp = src(f, "sourceTypes")
    R.count("setup.source.n", st["nSources"], sp + ".nSources")
    per_case = {}
    for side, comp in st["compositionPerCase"].items():
        if len(comp) != 1:
            raise SystemExit(f"source composition is not uniform across {side} cases")
        per_case[side] = {kv.split(" ")[0]: int(kv.split(" ")[1]) for kv in next(iter(comp)).split(", ")}
    if per_case["risk"] != per_case["control"]:
        raise SystemExit("risk and control cases have different source compositions")
    for t, name in (("resume", "resume"), ("work_sample", "workSample"), ("note", "note")):
        c = st["counts"][t]
        R.count(f"setup.source.{name}.n", c["all"], sp + f".counts.{t}.all")
        R.count(f"setup.source.{name}.risk.n", c["risk"], sp + f".counts.{t}.risk")
        R.count(f"setup.source.{name}.control.n", c["control"], sp + f".counts.{t}.control")
        R.count(f"setup.source.{name}.perCase", per_case["risk"][t], sp + ".compositionPerCase (uniform over all 144 cases)")
    b, bg = st["baitsBySignature"], st["baitsGold"]
    R.count("setup.source.bait.n", b["n"], sp + ".baitsBySignature.n")
    R.kn("setup.source.bait.note", b["noteShare"]["k"], b["noteShare"]["n"], sp + ".baitsBySignature.noteShare", with_pct=True)
    R.count("setup.source.bait.nonNote", b["n"] - b["byType"]["note"], sp + ".baitsBySignature.n − byType.note")
    R.kn("setup.source.bait.riskCases", b["riskCasesWithBait"]["k"], b["riskCasesWithBait"]["n"], sp + ".baitsBySignature.riskCasesWithBait")
    for k, n in b["perCase"].items():
        R.count(f"setup.source.bait.casesWith{k}", n, sp + f'.baitsBySignature.perCase["{k}"]')
    R.count("setup.source.bait.subsetOfGoldCases", b["casesWhereSubsetOfGoldBaitIds"], sp + ".baitsBySignature.casesWhereSubsetOfGoldBaitIds")
    R.count("setup.source.baitGold.n", bg["n"], sp + ".baitsGold.n")
    R.kn("setup.source.baitGold.note", bg["noteShare"]["k"], bg["noteShare"]["n"], sp + ".baitsGold.noteShare", with_pct=True)
    R.count("setup.source.baitGold.noSignature", bg["withoutSignature"], sp + ".baitsGold.withoutSignature")
    rn = st["riskNotes"]
    R.count("setup.source.riskNote.n", rn["n"], sp + ".riskNotes.n")
    R.kn("setup.source.riskNote.bait", rn["baitBySignature"]["k"], rn["baitBySignature"]["n"], sp + ".riskNotes.baitBySignature", with_pct=True)
    R.kn("setup.source.riskNote.baitGold", rn["baitGold"]["k"], rn["baitGold"]["n"], sp + ".riskNotes.baitGold", with_pct=True)
    R.count("setup.source.controlNote.n", st["controlNotes"]["n"], sp + ".controlNotes.n")
    ls = st["lexiconSubjective"]
    for part, name in (("baitsBySignature", "bait"), ("baitsGold", "baitGold"), ("controlNotes", "controlNote"),
                       ("resumeItems", "resume"), ("workSamples", "workSample")):
        R.kn(f"setup.source.subj.{name}", ls[part]["k"], ls[part]["n"], sp + f".lexiconSubjective.{part}", with_pct=True)
    for part, name in (("kindBaitsGold", "baitGold"), ("kindControlNotes", "controlNote")):
        for kind in ("subjectiveOnly", "hearsayOnly", "both"):
            R.count(f"setup.source.subj.{name}.{kind}", ls[part][kind], sp + f".lexiconSubjective.{part}.{kind}")
    R.count("setup.source.subj.total", ls["baitsGold"]["k"] + ls["controlNotes"]["k"] + ls["riskNotesNotGoldBait"] + ls["resumeItems"]["k"] + ls["workSamples"]["k"],
            sp + ".lexiconSubjective.{baitsGold, controlNotes, resumeItems, workSamples}.k + riskNotesNotGoldBait (sum)")
    R.text("setup.source.subj.types", ", ".join(ls["sourceTypesClassed"]), sp + ".lexiconSubjective.sourceTypesClassed")
    sl = st["trapSignatureLocations"]
    for k, name in (("total", "n"), ("noteOnly", "noteOnly"), ("nonNoteSource", "nonNote"), ("noSource", "noSource"),
                    ("inJobDescriptionOrRequirements", "inJD"), ("inOriginalCvMarkdown", "inCvMarkdown")):
        R.count(f"setup.source.trapSig.{name}", sl[k], sp + f".trapSignatureLocations.{k}")
    R.kn("setup.source.trapSig.inJD.cases", sl["riskCasesWithSignatureInJobDescriptionOrRequirements"], b["riskCasesWithBait"]["n"],
         sp + ".trapSignatureLocations.riskCasesWithSignatureInJobDescriptionOrRequirements / 72 risk cases")
    for side, name in (("control", "validCtl"), ("risk", "validRisk")):
        x = st["validSignatureLocations"][side]
        R.count(f"setup.source.{name}.n", x["total"], sp + f".validSignatureLocations.{side}.total")
        R.kn(f"setup.source.{name}.onlyNote", x["onlyNote"], x["total"], sp + f".validSignatureLocations.{side}.onlyNote / total", with_pct=True)
        for k in ("noteAndOther", "nonNoteOnly", "noSource"):
            R.count(f"setup.source.{name}.{k}", x[k], sp + f".validSignatureLocations.{side}.{k}")
    R.text("setup.source.validCtl.onlyNote.ids", ", ".join(h["case"] for h in st["controlValidSignaturesOnlyInNotes"]), sp + ".controlValidSignaturesOnlyInNotes[].case")
    for m in MODELS:
        s = SLUG[m]
        x = st["itemLevelC2"][m]
        sx = src(f, "sourceTypes", "itemLevelC2", m)
        if not x["matchesRepairAnatomy"]:
            raise SystemExit(f"{m}: item-level source facts do not match repair_anatomy.json")
        for part, name in (("failedBySubjectiveRule", "subj"), ("failedBySubjectiveRuleOnly", "subjOnly")):
            R.kn(f"setup.source.{s}.trapItemFail.{name}", x[part]["k"], x[part]["n"], sx + f".{part}", with_pct=True)
        R.count(f"setup.source.{s}.trapItemFail.subj.citedAsSupport", x["failedBySubjectiveCode"].get("subjective_source_cited_as_support", 0),
                sx + ".failedBySubjectiveCode.subjective_source_cited_as_support" + ("" if "subjective_source_cited_as_support" in x["failedBySubjectiveCode"] else " (absent = 0)"))
        for part, name in (("note", "citeNote"), ("lexiconSubjective", "citeSubj"), ("noSource", "noSource")):
            y = x["trapItemsCiting"][part]
            R.kn(f"setup.source.{s}.trapItem.{name}", y["k"], y["n"], sx + f".trapItemsCiting.{part}", with_pct=True)
        y = x["failedItemsCiting"]["note"]
        R.kn(f"setup.source.{s}.trapItemFail.citeNote", y["k"], y["n"], sx + ".failedItemsCiting.note", with_pct=True)


def sens_transition(R, key, t, source):
    """sensitivity.json transition block -> keys; the paired-difference interval is sensitivity.json's Newcombe method 10."""
    a, b, c, d = t["unchangedFail"], t["repaired"], t["new"], t["unchangedPass"]
    n = a + b + c + d
    if n != t["pairedN"]:
        raise SystemExit(f"{key}: cells do not sum to pairedN")
    R.count(f"{key}.n", n, source + ".pairedN")
    R.count(f"{key}.b", b, source + ".repaired")
    R.count(f"{key}.c", c, source + ".new")
    R.count(f"{key}.a", a, source + ".unchangedFail")
    R.count(f"{key}.d", d, source + ".unchangedPass")
    cl = t["clearance"]
    R.prop(f"{key}.clear", cl["k"], cl["n"], cl["p"], cl["lo"], cl["hi"], source + ".clearance")
    pd = t["pairedDiffAfterMinusBefore"]
    if "method 10" not in pd.get("method", "") or abs(pd["diff"] - (c - b) / n) > 1e-12:
        raise SystemExit(f"{key}: sensitivity.json paired difference is not the method-10 block of the 2x2 counts")
    ps = source + ".pairedDiffAfterMinusBefore"
    R.ppdiff(f"{key}.diff", 100 * pd["diff"], 100 * pd["lo"], 100 * pd["hi"], 1, ps + ".{diff, lo, hi} (Newcombe method 10)")
    if b + c == 0:
        R.notes.append(f"`{key}.diff`：没有不一致对（b = c = 0），差值为 0；`.ci` 是 method 10 的非退化区间，正文宜写「0/{n} 个不一致对」。")
    R.put(f"{key}.diff.ciM8", fci_pp(100 * pd["ciM8"]["lo"], 100 * pd["ciM8"]["hi"], 1), None, ps + ".ciM8 (method 8, traceability only)")
    R.pval(f"{key}.p", t["exactP"], source + ".exactP")


def sens_retention(R, key, r, source):
    changed = r["casesChanged"]
    R.ppdiff(key, 100 * r["diff"], 100 * r["lo"], 100 * r["hi"], 2, source + " (diff, bootstrap lo/hi)", with_ci=changed > 0)
    R.count(f"{key}.n", r["pairedN"], source + ".pairedN")
    R.count(f"{key}.changed", changed, source + ".casesChanged")
    R.put(f"{key}.c2", fpct(r["c2"]), r["c2"], source + ".c2")
    R.put(f"{key}.c4", fpct(r["c4"]), r["c4"], source + ".c4")


def sens_group(R, S):
    f = "sensitivity.json"
    dev = S["devExclusion"]
    sd = src(f, "devExclusion")
    R.count("sens.dev.n", len(dev["caseIds"]), sd + ".caseIds (count)")
    R.count("sens.dev.nRisk", dev["nRisk"], sd + ".nRisk")
    R.count("sens.dev.nControl", dev["nControl"], sd + ".nControl")
    R.text("sens.dev.ids", ", ".join(short(x) for x in dev["caseIds"]), sd + ".caseIds")
    R.text("sens.dev.source", dev["source"], sd + ".source")
    if not (dev["allInBenchmark"] and dev["sameIdsAsC2Pilot"]):
        raise SystemExit("development-set ids check failed")
    for m in MODELS:
        s = SLUG[m]
        dm = dev["models"][m]
        for part, setname in (("full", "all"), ("excludingDev", "excl")):
            blk = dm[part]
            sp = src(f, "devExclusion", "models", m, part)
            for c, v in blk["trapFellAny"].items():
                R.prop(f"sens.dev.{s}.{setname}.{c}.trap", v["k"], v["n"], v["p"], v["lo"], v["hi"], sp + f".trapFellAny.{c}")
            for c, v in blk["controlRetention"].items():
                R.put(f"sens.dev.{s}.{setname}.{c}.kept", fpct(v["mean"]), v["mean"], sp + f".controlRetention.{c}.mean")
                R.count(f"sens.dev.{s}.{setname}.{c}.kept.n", v["n"], sp + f".controlRetention.{c}.n")
            for tr in ("C2->C4", "C0->C4"):
                a, b = tr.split("->")
                sens_transition(R, f"sens.dev.{s}.{setname}.{a}to{b}", blk[tr], sp + f'["{tr}"]')
            sens_retention(R, f"sens.dev.{s}.{setname}.keptDiff", blk["controlRetentionC2toC4"], sp + ".controlRetentionC2toC4")
        for c, v in dm["devRiskCases"].items():
            R.kn(f"sens.dev.{s}.devRisk.{c}", v["k"], v["n"], src(f, "devExclusion", "models", m, "devRiskCases", c) + ".k / n")
    lo_ = S["liftOff"]
    sl = src(f, "liftOff")
    if lo_["model"] != "gpt-oss:20b":
        raise SystemExit("lift-off sensitivity is expected for gpt-oss:20b")
    for c, v in lo_["conditions"].items():
        sc = sl + f".conditions.{c}"
        for arm, name in (("official", "official"), ("liftOff", "off")):
            x = v["trapFellAny"][arm]
            R.prop(f"sens.lift.gptoss.{c}.trap.{name}", x["k"], x["n"], x["p"], x["lo"], x["hi"], sc + f".trapFellAny.{arm}")
            R.put(f"sens.lift.gptoss.{c}.kept.{name}", fpct(v["controlRetention"][arm]["mean"]), v["controlRetention"][arm]["mean"], sc + f".controlRetention.{arm}.mean")
            R.mean(f"sens.lift.gptoss.{c}.supportedPerCase.{name}", v["meanSupportedCount"][arm], 1, sc + f".meanSupportedCount.{arm}")
        R.put(f"sens.lift.gptoss.{c}.kept.delta", fsigned(v["controlRetention"]["deltaPp"], 2) + " pp", v["controlRetention"]["deltaPp"], sc + ".controlRetention.deltaPp")
        R.put(f"sens.lift.gptoss.{c}.trap.deltaK", fsigned(v["trapFellAny"]["deltaK"], 0), v["trapFellAny"]["deltaK"], sc + ".trapFellAny.deltaK")
        R.text(f"sens.lift.gptoss.{c}.lostIds", ", ".join(short(x) for x in v["trapFellIdsLost"]) or "none", sc + ".trapFellIdsLost")
    for tr in ("C2->C4", "C0->C4"):
        a, b = tr.split("->")
        for arm, name in (("official", "official"), ("liftOff", "off")):
            sens_transition(R, f"sens.lift.gptoss.{a}to{b}.{name}", lo_[tr][arm], sl + f'["{tr}"].{arm}')
    for arm, name in (("official", "official"), ("liftOff", "off")):
        sens_retention(R, f"sens.lift.gptoss.keptDiff.{name}", lo_["controlRetentionC2toC4"][arm], sl + f".controlRetentionC2toC4.{arm}")
    rb = lo_["c4Rebuild"]
    sr = sl + ".c4Rebuild"
    R.count("sens.lift.gptoss.stringItemsC2", rb["stringItemsInC2RawOutputs"], sr + ".stringItemsInC2RawOutputs")
    R.count("sens.lift.gptoss.stringItemsLeftC4", rb["stringItemsLeftInLiftOffC4"], sr + ".stringItemsLeftInLiftOffC4")
    R.count("sens.lift.gptoss.c4Differing", rb["liftOffC4BundlesDifferingFromOfficial"], sr + ".liftOffC4BundlesDifferingFromOfficial")
    R.count("sens.lift.gptoss.goldFieldChanges", sum(rb["liftOffC4GoldFieldChangesVsOfficial"].values()), sr + ".liftOffC4GoldFieldChangesVsOfficial (sum)")
    for k_, v in sorted(rb["liftOffC4GoldFieldChangesVsOfficial"].items()):
        R.count(f"sens.lift.gptoss.goldFieldChanges.{k_}", v, sr + f".liftOffC4GoldFieldChangesVsOfficial.{k_}")
    R.count("sens.lift.gptoss.notRepairable", rb["liftOffNotRepairable"], sr + ".liftOffNotRepairable")
    R.text("sens.lift.gptoss.rebuildReproduces", "true" if (rb["unpatchedReproducesStored"]["stage1Mismatches"] == 0 and rb["unpatchedReproducesStored"]["finalMismatches"] == 0) else "false",
           sr + ".unpatchedReproducesStored.{stage1Mismatches, finalMismatches} == 0")
    R.text("sens.lift.qwenIdentity", "true" if S["qwenLiftIdentity"] else "false", src(f, "qwenLiftIdentity"))
    for m in MODELS:
        for c, v in S["stringCensus"][m].items():
            R.kn(f"sens.lift.{SLUG[m]}.{c}.stringBundles", v["bundlesWithStringItems"], v["parsedBundles"], src(f, "stringCensus", m, c) + ".bundlesWithStringItems / parsedBundles")
            R.count(f"sens.lift.{SLUG[m]}.{c}.stringItems", v["stringItems"], src(f, "stringCensus", m, c, "stringItems"))
    U = S["unicode"]
    su = src(f, "unicode")
    R.count("sens.uni.signatures.total", U["goldSignatures"]["total"], su + ".goldSignatures.total")
    R.count("sens.uni.signatures.asciiHyphenApostrophe", U["goldSignatures"]["withAsciiHyphenOrApostrophe"], su + ".goldSignatures.withAsciiHyphenOrApostrophe")
    R.count("sens.uni.signatures.mapped", U["goldSignatures"]["withMappedCharacter"], su + ".goldSignatures.withMappedCharacter")
    R.count("sens.uni.mappedChars", len(U["mapping"]), su + ".mapping (number of mapped code points)")
    for m in MODELS:
        s = SLUG[m]
        um = U["models"][m]
        for c, v in um["conditions"].items():
            sc = su + f'.models["{m}"].conditions.{c}'
            for arm, name in (("official", "official"), ("normalised", "norm")):
                x = v["trapFellAny"][arm]
                R.prop(f"sens.uni.{s}.{c}.trap.{name}", x["k"], x["n"], x["p"], x["lo"], x["hi"], sc + f".trapFellAny.{arm}")
                R.put(f"sens.uni.{s}.{c}.kept.{name}", fpct(v["controlRetention"][arm]["mean"]), v["controlRetention"][arm]["mean"], sc + f".controlRetention.{arm}.mean")
            R.put(f"sens.uni.{s}.{c}.kept.delta", fsigned(v["controlRetention"]["deltaPp"], 2) + " pp", v["controlRetention"]["deltaPp"], sc + ".controlRetention.deltaPp")
            R.put(f"sens.uni.{s}.{c}.trap.deltaK", fsigned(v["trapFellAny"]["deltaK"], 0), v["trapFellAny"]["deltaK"], sc + ".trapFellAny.deltaK")
            R.count(f"sens.uni.{s}.{c}.mappedBundles", v["bundlesWithMappedCharOnSupportedSide"], sc + ".bundlesWithMappedCharOnSupportedSide")
            R.text(f"sens.uni.{s}.{c}.gainedIds", ", ".join(short(x) for x in v["trapFellIdsGained"]) or "none", sc + ".trapFellIdsGained")
        for tr in ("C2->C4", "C0->C4"):
            a, b = tr.split("->")
            for arm, name in (("official", "official"), ("normalised", "norm")):
                sens_transition(R, f"sens.uni.{s}.{a}to{b}.{name}", um[tr][arm], su + f'.models["{m}"]["{tr}"].{arm}')
        for arm, name in (("official", "official"), ("normalised", "norm")):
            sens_retention(R, f"sens.uni.{s}.keptDiff.{name}", um["controlRetentionC2toC4"][arm], su + f'.models["{m}"].controlRetentionC2toC4.{arm}')


def setup_group(R, setup):
    f = "setup_facts.json"
    for i, mm in enumerate(setup["models"]):
        m = mm["model"]
        s = SLUG[m]
        sp = src(f, "models", i)
        if mm["fieldsInconsistentAcrossRuns"]:
            raise SystemExit(f"{m}: identity fields inconsistent across runs")
        for fld, name in (("tag", "tag"), ("quantization", "quant"), ("parameterSize", "params"), ("digest12", "digest12"),
                          ("digest", "digest"), ("think", "think"), ("ollamaVersion", "ollama"), ("keepAlive", "keepAlive"),
                          ("modelfileParameters", "modelfileParameters"), ("runner12", "runner12")):
            R.text(f"setup.{s}.{name}", str(mm[fld]), sp + "." + fld)
        R.put(f"setup.{s}.temperature", fg(mm["temperature"]), mm["temperature"], sp + ".temperature")
        for fld, name in (("seed", "seed"), ("numCtx", "numCtx"), ("numPredict", "numPredict"), ("repeat", "repeat"), ("contextLengthModel", "ctxModel")):
            R.count(f"setup.{s}.{name}", mm[fld], sp + "." + fld)
        R.put(f"setup.{s}.sizeGB", f"{mm['sizeBytes'] / 1e9:.1f} GB", mm["sizeBytes"], sp + ".sizeBytes (/1e9)")
        for run in mm["runs"]:
            c = run["condition"].replace("-", "_")
            R.kn(f"setup.{s}.outputs.{c}", run["nOutputs"], run["nRequests"], sp + f".runs[condition={run['condition']}].nOutputs / nRequests")
            mism = run["outputsDigestMismatch"] + run["outputsModelMismatch"] + run["outputsSeedMismatch"]
            R.count(f"setup.{s}.outputs.{c}.mismatches", mism, sp + f".runs[condition={run['condition']}].outputs{{Digest,Model,Seed}}Mismatch (sum)")
    vals = {mm["ollamaVersion"] for mm in setup["models"]}
    if len(vals) != 1:
        raise SystemExit("Ollama version differs across models")
    R.text("setup.ollama", vals.pop(), src(f, "models", "*", "ollamaVersion") + " (identical for all models)")
    for fld, v in (("temperature", {mm["temperature"] for mm in setup["models"]}), ("seed", {mm["seed"] for mm in setup["models"]}),
                   ("numCtx", {mm["numCtx"] for mm in setup["models"]}), ("numPredict", {mm["numPredict"] for mm in setup["models"]}),
                   ("repeat", {mm["repeat"] for mm in setup["models"]})):
        if len(v) != 1:
            raise SystemExit(f"{fld} differs across models")
        x = v.pop()
        R.put(f"setup.all.{fld}", fg(x) if isinstance(x, float) else str(x), x, src(f, "models", "*", fld) + " (identical for all models)")
    hw = setup["hardware"]
    sh = src(f, "hardware")
    for fld in ("machine", "chip", "memory", "ollamaVersionMachineFile"):
        R.text(f"setup.hw.{fld}", hw[fld], sh + "." + fld)
    R.put("setup.hw.qwen3_8bTokPerSec", fg(hw["qwen3_8bGenTokPerSecSmoke"]), hw["qwen3_8bGenTokPerSecSmoke"], sh + ".qwen3_8bGenTokPerSecSmoke")


def cond_group(R, setup):
    f = "setup_facts.json"
    c = setup["conditions"]
    q = c["c0VsC5Requests"]
    sq = src(f, "conditions", "c0VsC5Requests")
    R.text("cond.C0C5.diffKeys", ", ".join(sorted(q["differingTopLevelKeys"])), sq + ".differingTopLevelKeys (keys)")
    R.count("cond.C0C5.diffKeys.n", len(q["differingTopLevelKeys"]), sq + ".differingTopLevelKeys (count)")
    R.count("cond.C0C5.diffMetaKeys.n", len(q["differingMetaKeys"]), sq + ".differingMetaKeys (count)")
    R.kn("cond.C0C5.linesDiffer", q["linesWithAnyDifference"], q["nLines"], sq + ".linesWithAnyDifference / nLines")
    R.text("cond.C0.format", ", ".join(json.loads(x) if x.startswith('"') else x for x in q["c0FormatValues"]), sq + ".c0FormatValues")
    R.text("cond.C5.formatIsBundleSchema", "true" if q["c5FormatEqualsBundleSchemaFile"] else "false", sq + ".c5FormatEqualsBundleSchemaFile")
    R.text("cond.C5.schemaFile", q["bundleSchemaFile"], sq + ".bundleSchemaFile")
    bi = c["c0VsC5OutputsByteIdentical"]
    for m in MODELS:
        s = SLUG[m]
        v = bi[m]
        sb = src(f, "conditions", "c0VsC5OutputsByteIdentical", m)
        R.kn(f"cond.{s}.C0C5.identical", v["identical"], v["n"], sb + ".identical / n", with_pct=True)
        R.kn(f"cond.{s}.C0C5.identicalRisk", v["identicalRisk"], v["nRisk"], sb + ".identicalRisk / nRisk")
        R.kn(f"cond.{s}.C0C5.identicalControl", v["identicalControl"], v["nControl"], sb + ".identicalControl / nControl")
        R.count(f"cond.{s}.C0C5.nonIdenticalRisk", v["nonIdenticalRisk"], sb + ".nonIdenticalRisk")
        R.count(f"cond.{s}.C0C5.trapDiscordant", v["nonIdenticalRiskTrapDiscordant"], sb + ".nonIdenticalRiskTrapDiscordant")
    pw = c["promptWords"]
    for cond in ("C0", "C1", "C2", "C5"):
        v = pw[cond]
        sp = src(f, "conditions", "promptWords", cond)
        if not v["metaEqualsRecomputed"]:
            raise SystemExit("prompt words meta mismatch")
        R.put(f"cond.{cond}.words.median", fg(v["median"]), v["median"], sp + ".median")
        R.count(f"cond.{cond}.words.min", v["min"], sp + ".min")
        R.count(f"cond.{cond}.words.max", v["max"], sp + ".max")
        R.put(f"cond.{cond}.chars.median", fg(v["charsMedian"]), v["charsMedian"], sp + ".charsMedian")
        R.count(f"cond.{cond}.requests.n", v["n"], sp + ".n")
    v = pw["pairedC2minusC1"]
    sp = src(f, "conditions", "promptWords", "pairedC2minusC1")
    R.put("cond.C2minusC1.words.median", fg(v["median"]), v["median"], sp + ".median")
    R.count("cond.C2minusC1.words.min", v["min"], sp + ".min")
    R.count("cond.C2minusC1.words.max", v["max"], sp + ".max")
    for cond in ("C1", "C2"):
        v = pw["rulesSectionWords"][cond]
        sp = src(f, "conditions", "promptWords", "rulesSectionWords", cond)
        R.put(f"cond.{cond}.rulesWords.median", fg(v["median"]), v["median"], sp + ".median")
        R.count(f"cond.{cond}.rulesWords.min", v["min"], sp + ".min")
        R.count(f"cond.{cond}.rulesWords.max", v["max"], sp + ".max")
        R.kn(f"cond.{cond}.equalsC0PlusRendering", pw["requestsEqualC0PlusRuntimeRendering"][cond], pw[cond]["n"], src(f, "conditions", "promptWords", "requestsEqualC0PlusRuntimeRendering", cond) + " / n")
    h = c["c2ValidatorHeader"]
    sh = src(f, "conditions", "c2ValidatorHeader")
    R.text("cond.C2.headerLine", h["headerLine"], sh + ".headerLine")
    for i, ph in enumerate(h["phrases"]):
        R.text(f"cond.C2.headerPhrase{i + 1}", ph, sh + f".phrases[{i}]")
    for cond, k in h["requestsContainingBothPhrases"].items():
        R.kn(f"cond.{cond}.header", k, pw[cond]["n"], sh + f".requestsContainingBothPhrases.{cond} / promptWords.{cond}.n")
    R.text("cond.C2.extraFields", ", ".join(c["c2ExtraFieldsPerBlock"]), src(f, "conditions", "c2ExtraFieldsPerBlock"))
    R.count("cond.C2.extraFields.n", len(c["c2ExtraFieldsPerBlock"]), src(f, "conditions", "c2ExtraFieldsPerBlock") + " (count)")
    R.text("cond.C2.extraTopLevel", ", ".join(c["c2TopLevelExtra"]), src(f, "conditions", "c2TopLevelExtra"))
    for cond, v in c["requestsSha256"].items():
        sr = src(f, "conditions", "requestsSha256", cond)
        if not (v["allModelsEqual"] and v["equalsLocalFile"]):
            raise SystemExit(f"requests sha256 check failed for {cond}")
        R.text(f"cond.{cond}.requestsSha12", v["local12"], sr + ".local12 (allModelsEqual and equalsLocalFile)")
    ow = c["obligationWordsTotal"]
    so = src(f, "conditions", "obligationWordsTotal")
    R.count("cond.obligationWords.prose", ow["prose"], so + ".prose")
    R.count("cond.obligationWords.duty", ow["contractObligation"], so + ".contractObligation")
    R.count("cond.obligationWords.block", ow["contractBlock"], so + ".contractBlock")
    for i, r in enumerate(c["obligationWordsPerRule"]):
        slug = r["rule"].split(".")[-1]
        sr = src(f, "conditions", "obligationWordsPerRule", i)
        R.count(f"cond.rule.{slug}.proseWords", r["proseWords"], sr + ".proseWords")
        R.count(f"cond.rule.{slug}.dutyWords", r["contractObligationWords"], sr + ".contractObligationWords")
        R.count(f"cond.rule.{slug}.blockWords", r["contractBlockWords"], sr + ".contractBlockWords")
        R.kn(f"cond.rule.{slug}.active", r["activeInCases"], pw["C2"]["n"], sr + ".activeInCases / promptWords.C2.n")


def contract_group(R, setup):
    f = "setup_facts.json"
    cc = setup["contractCoverage"]
    sc = src(f, "contractCoverage")
    R.count("contract.declared.n", cc["nDeclared"], sc + ".nDeclared")
    R.count("contract.implemented.n", cc["nImplemented"], sc + ".nImplemented")
    R.count("contract.goldOnly.n", cc["nGoldOnly"], sc + ".nGoldOnly")
    for part, name in (("declaredNotImplemented", "declaredNotImplemented"), ("implementedNotDeclared", "implementedNotDeclared"),
                       ("implementedNotDeclaredWithDeclaredCounterpart", "withCounterpart"), ("implementedNotDeclaredNoCounterpart", "noCounterpart"),
                       ("implementedStaticOnly", "staticOnly"), ("implementedObservedOnly", "observedOnly"),
                       ("undeclaredCriticalCodesInClearedCases", "undeclaredCriticalInCleared")):
        R.count(f"contract.{name}.n", len(cc[part]), sc + f".{part} (count)")
        R.text(f"contract.{name}.list", ", ".join(cc[part]) or "none", sc + f".{part}")
    sv = cc["severity"]
    ss = sc + ".severity"
    R.count("contract.severityDiffers.n", len(sv["codesWhoseSeverityDiffersFromRuleJson"]), ss + ".codesWhoseSeverityDiffersFromRuleJson (count)")
    R.text("contract.severityDiffers.list", ", ".join(sv["codesWhoseSeverityDiffersFromRuleJson"]), ss + ".codesWhoseSeverityDiffersFromRuleJson")
    R.text("contract.keysNeverRead.list", ", ".join(sv["contractKeysNeverRead"]), ss + ".contractKeysNeverRead")
    R.text("contract.detectorsReadRuleSeverity", "true" if sv["detectorsOrValidatorReadRuleSeverity"] else "false", ss + ".detectorsOrValidatorReadRuleSeverity")
    R.count("contract.detectors.n", len(cc["detectorRegistry"]), sc + ".detectorRegistry (count)")
    for m in MODELS:
        s = SLUG[m]
        for var, name in (("counterfactualStrict", "strict"), ("counterfactualLenient", "lenient")):
            v = cc[var][m]
            sv_ = sc + f'.{var}["{m}"]'
            R.kn(f"contract.{s}.{name}.clearedUnderFilter", v["clearedUnderFilter"], v["clearedActual"], sv_ + ".clearedUnderFilter / clearedActual")
            R.count(f"contract.{s}.{name}.depend", v["dependOnFilteredChecks"], sv_ + ".dependOnFilteredChecks")
            R.count(f"contract.{s}.{name}.stillBlock", v["ofWhichFilteredValidatorWouldStillBlock"], sv_ + ".ofWhichFilteredValidatorWouldStillBlock")
            R.text(f"contract.{s}.{name}.dependIds", ", ".join(v["dependCases"]) or "none", sv_ + ".dependCases")
        v = cc["clearedCasesUndeclared"][m]
        su = sc + f'.clearedCasesUndeclared["{m}"]'
        R.count(f"contract.{s}.cleared", v["cleared"], su + ".cleared")
        R.kn(f"contract.{s}.anyUndeclared", v["withAnyUndeclaredFail"], v["cleared"], su + ".withAnyUndeclaredFail / cleared")
        R.kn(f"contract.{s}.allCriticalUndeclared", v["allCriticalFailsUndeclared"], v["cleared"], su + ".allCriticalFailsUndeclared / cleared")
        R.text(f"contract.{s}.allCriticalUndeclared.ids", ", ".join(v["allCriticalFailsUndeclaredCases"]) or "none", su + ".allCriticalFailsUndeclaredCases")


def blind_group(R, setup):
    f = "setup_facts.json"
    b = setup["qualificationBlindCases"]
    cases = sorted(b["cases"])
    R.count("blind.n", len(cases), src(f, "qualificationBlindCases", "cases") + " (count)")
    R.text("blind.ids", ", ".join(cases), src(f, "qualificationBlindCases", "cases") + " (keys)")
    fams = {b["cases"][c]["family"] for c in cases}
    if len(fams) != 1:
        raise SystemExit("blind cases span several families")
    R.text("blind.family", fams.pop(), src(f, "qualificationBlindCases", "cases", "*", "family"))
    for cond, v in b["summaryByCondition"].items():
        sv = src(f, "qualificationBlindCases", "summaryByCondition", cond)
        R.kn(f"blind.{cond}.trapFell", v["trapFell"], v["cells"], sv + ".trapFell / cells")
        R.kn(f"blind.{cond}.qualFail", v["qualificationFailCells"], v["cells"], sv + ".qualificationFailCells / cells")
    # cells (case x model) in which the trap fell, and how many of those the qualification rule FAILed
    both = {}
    for cid in cases:
        for m in MODELS:
            for cond, v in b["cases"][cid]["byModel"][m].items():
                fell, qual = both.setdefault(cond, [0, 0])
                both[cond] = [fell + bool(v["trapFellAny"]), qual + bool(v["trapFellAny"] and v["qualificationFail"] > 0)]
    sc = src(f, "qualificationBlindCases", "cases", "*", "byModel", "*")
    for cond, (fell, qual) in sorted(both.items()):
        if fell != b["summaryByCondition"][cond]["trapFell"]:
            raise SystemExit(f"blind cases: {cond} trapFell count mismatch")
        R.kn(f"blind.{cond}.qualFailWhenFell", qual, fell, sc + f".{cond}: cells with trapFellAny and qualificationFail > 0 / cells with trapFellAny")
    fell = sum(both[c][0] for c in ("C0", "C5"))
    qual = sum(both[c][1] for c in ("C0", "C5"))
    R.kn("blind.C0C5.qualFailWhenFell", qual, fell, sc + ".{C0, C5}: cells with trapFellAny and qualificationFail > 0 / cells with trapFellAny (sum of the two conditions)")
    R.count("blind.C0C5.trapFell", fell, sc + ".{C0, C5}: cells with trapFellAny (sum of the two conditions)")
    qf = sum(b["summaryByCondition"][c]["qualificationFailCells"] for c in ("C0", "C5"))
    cells = sum(b["summaryByCondition"][c]["cells"] for c in ("C0", "C5"))
    R.kn("blind.C0C5.qualFail", qf, cells, src(f, "qualificationBlindCases", "summaryByCondition", "{C0,C5}", "qualificationFailCells") + " / cells (sum of the two conditions)")
    R.notes.append(f"资历族盲区：C0/C5 下陷阱落下的 {fell} 个格子（案例 × 模型）中，资格规则 FAIL 的只有 {qual} 个（`blind.C0C5.qualFailWhenFell`）；"
                   f"C0/C5 全部 {cells} 个格子里资格规则 FAIL 共 {qf} 个（`blind.C0C5.qualFail`），其余 {qf - qual} 个落在陷阱未落下的格子。写稿简报 §5.5 的「5 次里只命中 2 次」与此不符，以本键为准。")
    fell_ids = sorted(f"{cid} ({SLUG[m]})" for cid in cases for m in MODELS if b["cases"][cid]["byModel"][m]["C1"]["trapFellAny"])
    R.text("blind.C1.fellCells", ", ".join(fell_ids) or "none", src(f, "qualificationBlindCases", "cases", "*", "byModel", "*", "C1", "trapFellAny"))
    for cid in cases:
        for m in MODELS:
            for cond, v in b["cases"][cid]["byModel"][m].items():
                R.put(f"blind.{cid}.{SLUG[m]}.{cond}.trap", "true" if v["trapFellAny"] else "false", int(v["trapFellAny"]),
                      src(f, "qualificationBlindCases", "cases", cid, "byModel", m, cond, "trapFellAny"))


def example_group(R, S):
    cid = md_field("example_case.md", r"Selected case: `([0-9a-f-]+)`")
    R.text("example.caseId", short(cid), "example_case.md: 'Selected case' line (first 8 hex)")
    dev = {short(x) for x in S["devExclusion"]["caseIds"]}
    in_dev = short(cid) in dev
    R.text("example.inDevSet", "true" if in_dev else "false", "example_case.md 'Selected case' checked against sensitivity.json:devExclusion.caseIds")
    if in_dev:
        raise SystemExit(f"example_case.md selects {short(cid)}, one of the 12 development cases; its selection rule excludes them")
    R.text("example.caseIdFull", cid, "example_case.md: 'Selected case' line")
    R.text("example.family", md_field("example_case.md", r"Family: `([a-z_]+)`"), "example_case.md: 'Family' field")
    R.text("example.rule", md_field("example_case.md", r"anchoring rule: `([a-z_.]+)`"), "example_case.md: 'anchoring rule' field")
    R.text("example.models", md_field("example_case.md", r"Selected case: `[0-9a-f-]+` \(([^;)]+)"), "example_case.md: 'Selected case' line (models that met the rule)")
    models = [m.strip() for m in R.d["example.models"]["text"].split(",")]
    R.count("example.nModels", len(models), "example_case.md: 'Selected case' line (number of models that met the rule)")
    R.count("example.tied.n", int(md_field("example_case.md", r"; (\d+) case\(s\) qualify on")), "example_case.md: 'Selected case' line (cases tied on the maximum number of models)")
    ex = (HERE / "example_case.md").read_text(encoding="utf-8")
    arts = []
    for sec in re.split(r"^## ", ex, flags=re.M)[1:]:
        model = sec.splitlines()[0].strip()
        for sig in re.findall(r"^- substring artifact: signature `([^`]+)`", sec, flags=re.M):
            arts.append((model, sig))
    R.count("example.artifact.n", len(arts), "example_case.md: '- substring artifact' lines (count over traced models)")
    R.text("example.artifact.models", ", ".join(sorted({m for m, _ in arts})) or "none", "example_case.md: model sections with '- substring artifact' lines")
    R.text("example.artifact.signatures", ", ".join(sorted({sg for _, sg in arts})) or "none", "example_case.md: '- substring artifact' signatures")
    R.text("example.contract.rule", md_field("tab1_contract.md", r'"ruleId": "([a-z_.]+)"'), "tab1_contract.md: contract excerpt ruleId")
    rc = md_field("tab1_contract.md", r"## Rendering for case `([0-9a-f-]+)`")
    R.text("example.contract.caseId", short(rc), "tab1_contract.md: 'Rendering for case' heading (first 8 hex)")
    words = re.search(r"Word counts for this rule: prose (\d+); duty text (\d+); rendered block (\d+)\.", (HERE / "tab1_contract.md").read_text(encoding="utf-8"))
    if not words:
        raise SystemExit("tab1_contract.md: word counts not found")
    for name, v in zip(("prose", "duty", "block"), words.groups()):
        R.count(f"example.contract.words.{name}", int(v), "tab1_contract.md: 'Word counts for this rule' line")


def stats_group(R, stats, C, S, RF):
    R.count("stats.bootstrap.B", stats["bootstrapB"], src("tab4_stats.json", "bootstrapB"))
    R.text("stats.bootstrap.seed", str(stats["seed"]), src("tab4_stats.json", "seed"))
    R.text("stats.newcombe.method", "10", src("tab4_contrasts.json", "definitions", "ci") + " (method 10)")
    R.count("stats.newcombe.selfTestVectors", C["newcombeSelfTest"]["vectors"], src("tab4_contrasts.json", "newcombeSelfTest", "vectors"))
    R.count("stats.sens.goldFieldsChecked", S["checks"]["goldFieldsChecked"], src("sensitivity.json", "checks", "goldFieldsChecked"))
    R.text("stats.sens.scoreRowsReproduced", "true" if S["checks"]["scoreRowsReproduced"] else "false", src("sensitivity.json", "checks", "scoreRowsReproduced"))
    R.text("stats.frontier.postHoc", "true" if RF["postHoc"] else "false", src("redactor_frontier.json", "postHoc"))


def attach_text_en(R):
    """English manuscript: add text_en to every key whose text contains Chinese characters or Chinese punctuation.

    text and value are never touched; text_en must be free of Chinese characters / punctuation and carry exactly the
    numbers of text (same digit groups in the same order). Returns the keys that received text_en."""
    need = sorted(k for k, v in R.d.items() if CJK_RE.search(v["text"]))
    missing = [k for k in need if k not in TEXT_EN]
    stale = sorted(set(TEXT_EN) - set(need))
    if missing or stale:
        raise SystemExit(f"TEXT_EN out of date: keys without text_en {missing}; entries not needed {stale}")
    for k in need:
        en = TEXT_EN[k]
        if CJK_RE.search(en):
            raise SystemExit(f"text_en of {k} still contains Chinese characters or punctuation: {en!r}")
        if NUM_RE.findall(en) != NUM_RE.findall(R.d[k]["text"]):
            raise SystemExit(f"text_en of {k} does not carry the same numbers as its text: {en!r}")
        R.d[k]["text_en"] = en
    return need


# ---------------------------------------------------------------- output

def write_md(R):
    counts = {g: 0 for g, _ in GROUPS}
    for k in R.d:
        g = k.split(".")[0]
        if g not in counts:
            raise SystemExit(f"key {k} has no registered group")
        counts[g] += 1
    L = ["# Paper numbers (generated by paper_numbers.py)", "",
         "定义与分母（格式约定见末句）。每个键的精确指标定义与分母以其 source 指向的产物为准，该产物 .md 开头有完整定义；这里只概括。"
         "**main**：tab4_stats / results.json 的主表，Parsed、Schema valid、Validator flagged、Residual critical 以全部 144 例为分母，"
         "陷阱失败 trap（trapFellAny：金标签名落在 supported 侧、需求状态越界或分族额外规则）、需求越界 overclaim、trapRouted、trapStrict 以可解析风险案例为分母，"
         "显式压制 suppressed 与保留 kept（validClaimPreserved，每例有效签名在 supported 侧任一处出现的比例的均值，宽松指标）以可解析匹配对照为分母，"
         "subjRouted 以带主观来源的风险案例（24）为分母；flagged / flaggedRisk / flaggedControl 为包级 BLOCK 或 HUMAN_REVIEW 在 144 / 72 个风险 / 72 个对照上的比例（不可解析计为标记；C0/C1/C2/C5 是对生成产物的离线校验，生成时未执行校验；C3 是 C2 产物的校验报告；C4 是修复后终版的校验）；包级标记不是检测指标；"
         "残留关键违规 residual 的分子只计可解析产物，C4 的 0 与 schema 有效 100% 按构造成立。"
         "**contrast**：两条件都可解析的风险案例配对，b = 前失败后通过（修复），c = 反向（新增），a / d = 两次都失败 / 都通过，diff = (c − b)/n（后减前，pp），"
         "CI 为 Newcombe (1998) method 10（.ciM8 为 method 8，仅供追溯），p 为精确双侧 McNemar；pooled 为三模型配对堆叠（同一批案例在三个模型间重复出现，配对不独立：描述性汇总，区间与 p 未校正聚类）。"
         "**clear**：C2（或 C0）已落陷阱的配对风险案例中 C4 不再落陷阱的比例 b/(a+b)，Wilson 95% CI；pooled 为三模型计数相加（同上，未校正聚类）。"
         "**family**：tab4_families.csv 的分族计数与 tab4_contrasts 的 C2→C4 分族转移，只描述不检验。"
         "**cost**：共同可评分对照 C2→C4 保留率差（按案例 bootstrap，B=10000）；supported 条目数 = bundle.supported_side 条目，配对均值只用两条件都可解析的案例，"
         "all144 变体把不可解析计为 0；对照改动计数的分母见各键 source；isr = interviewSignalRisks 条目数 C4/C2。"
         "**repair**：C4 repairLog 事件（每条日志一个事件）按五类归并；cases = 至少有一个该类事件的案例数。"
         "**validator**：条目级 = C2 supported 侧条目（主定义：每个 FAIL 只归到路径最深的条目），trapFailed = 带陷阱签名的条目被任一规则 FAIL 的比例，"
         "controlFailed = 对照中带有效签名的条目被 FAIL 的比例（误报上界代理）；residual = C4 仍落陷阱的风险案例。"
         "**frontier**（POST HOC）：内容无关变换 S（supported 侧改标/删除比例 p）、R（supported 需求下调比例 q）、X（重置决策边界字段、删除比例 r 的 interviewSignalRisks / 检查清单 / 局限）"
         "作用于冻结 C2 产物后用冻结评分器重打，种子均值；nd = 五个非决策族（60 风险 + 60 对照）；both = kept 与 trapRouted 均不低于 C4。"
         "来源类型策略（09-23 事后设计，已知诱饵全部是 note）：dropNoteCited 把引用 note 类来源的支持侧条目改标，dropNoteOrUnsourced 再加无 sourceId 的条目，*X 变体另加 X(r = 1)；只读案例元数据中的来源类型与条目 sourceIds，不是内容无关变换；xOnly = X 单独作用的参照。"
         "**sens**（POST HOC）：dev = 剔除 12 例开发集（6 风险 + 6 对照）；lift = 关闭 bundle.lift_string_items（gpt-oss）；uni = 签名匹配前做 Unicode 标点归一化。"
         "**setup / cond / contract / blind / example**：setup_facts.json、example_case.md、tab1_contract.md 的方法事实；setup.source.* 为来源类型事实：bait = 风险案例中文本含金标陷阱签名（大小写不敏感子串）的来源，baitGold = 金标 baitSourceIds，subj = 被 detectors.subjective_source_ids 判为主观或转述的来源，<m>.trapItemFail = C2 被 FAIL 的带陷阱签名条目（repair_anatomy 主定义）中由 subjective_claim_boundary 判出的比例。"
         "格式：百分比一位小数加 %；.ci 为 95% 区间（百分比区间不带符号，pp 区间带符号）、.full 为点值加区间；.k / .n / .kn 为计数；"
         "p 值 < 0.001 用两位有效数字科学计数，否则三位小数；pp 差值带符号、负号为 Unicode −（U+2212），陷阱失败差一位小数、保留率差两位小数；"
         "均值一位小数，均值差两位小数；value 为源数值（比例为 0–1 小数，pp 为 pp），区间、比值文本与标识符的 value 为 null。", ""]
    L.append(f"键总数 {len(R.d)}。按组：" + "；".join(f"{g} {counts[g]}" for g, _ in GROUPS) + "。")
    L.append("")
    n_en = sum("text_en" in v for v in R.d.values())
    other = sorted({c for v in R.d.values() for c in v["text"] if ord(c) > 127 and not CJK_RE.match(c)})
    L.append(f"英文稿：text 含汉字或中文标点的键 {n_en} 个"
             + ("，均附 text_en（英文措辞，数字与 text 相同；英文稿优先用 text_en）" if n_en else "，没有键需要 text_en，英文稿直接用 text")
             + "；text 中其余非 ASCII 字符为 " + ("、".join(f"{c}（U+{ord(c):04X}）" for c in other) if other else "无")
             + "，英文 LaTeX 渲染须转义（paper_tables.py 的英文表：− → $-$，→ → $\\to$，– → --）。")
    L.append("")
    if R.notes:
        L += ["## 注意事项（由脚本生成）", ""] + [f"- {n}" for n in R.notes] + [""]
    for g, desc in GROUPS:
        L += [f"## {g} — {desc}（{counts[g]} 个键）", "", "| key | text | source |", "|---|---|---|"]
        for k, v in R.d.items():
            if k.split(".")[0] == g:
                shown = v["text"] + (f" ‖ text_en: {v['text_en']}" if "text_en" in v else "")
                L.append(f"| `{k}` | {shown.replace('|', chr(92) + '|')} | {v['source'].replace('|', chr(92) + '|')} |")
        L.append("")
    return "\n".join(L)


def main():
    results = load_json("results.json")
    stats = load_json("tab4_stats.json")
    C = load_json("tab4_contrasts.json")
    transitions = load_json("c4_transitions.json")
    tab2 = load_json("tab2_benchmark.json")
    RA = load_json("repair_anatomy.json")
    RF = load_json("redactor_frontier.json")
    S = load_json("sensitivity.json")
    setup = load_json("setup_facts.json")
    pr = json.loads((ROOT / "benchmark" / "v4" / "detector_pr.json").read_text(encoding="utf-8"))
    with (HERE / "tab4_families.csv").open(newline="", encoding="utf-8") as fh:
        families_rows = list(csv.DictReader(fh))
    if {r["model"] for r in results} != set(MODELS) or len(results) != 18:
        raise SystemExit("results.json does not hold 3 models x 6 conditions")
    R = Registry()
    bench(R, tab2, setup, pr)
    detector(R, pr)
    main_table(R, results, stats, C, families_rows)
    contrasts_group(R, C, stats, S)
    cost_group(R, stats, transitions, RA)
    repair_group(R, RA, RF, C)
    validator_group(R, RA)
    frontier_group(R, RF, stats)
    frontier_source_group(R, RF, stats)
    sens_group(R, S)
    setup_group(R, setup)
    setup_source_group(R, setup)
    cond_group(R, setup)
    contract_group(R, setup)
    blind_group(R, setup)
    example_group(R, S)
    stats_group(R, stats, C, S, RF)
    en_keys = attach_text_en(R)
    (HERE / "paper_numbers.json").write_text(json.dumps(R.d, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    (HERE / "paper_numbers.md").write_text(write_md(R) + "\n", encoding="utf-8")
    counts = {}
    for k in R.d:
        counts[k.split(".")[0]] = counts.get(k.split(".")[0], 0) + 1
    print(f"paper_numbers.json: {len(R.d)} keys; " + ", ".join(f"{g} {counts.get(g, 0)}" for g, _ in GROUPS))
    print(f"text_en: {len(en_keys)} keys whose text contains Chinese characters or punctuation"
          + (" (" + ", ".join(en_keys) + ")" if en_keys else ""))
    for n in R.notes:
        print("note:", n)


if __name__ == "__main__":
    main()
