#!/usr/bin/env python3
"""Chinese manuscript tables -> analysis/paper_tables/zh/*.md (one pipe table + one "注：" paragraph per file).

Every number printed in a table is the `text` of a key in analysis/paper_numbers.json (same formatting as the
manuscript: percentages with one decimal, CIs in square brackets, pp differences with a Unicode minus), except where a
table needs something paper_numbers.json does not register; those cells are read from the source product named in
analysis/paper_tables/SOURCES.md (generated together with the tables):
  - tab01: the contract excerpt and its field values are parsed from tab1_contract.md (its ```json block);
  - tab02: the family -> anchoring rule mapping is read from the frozen gold files (benchmark/v4/gold, read only);
  - tab07: per-model totals are sums of the contrast cells a+b / a+c (paper_numbers keys);
  - tabA2: emitted vs rule-JSON severities and the renamed-counterpart map come from setup_facts.json;
  - tabA4: the worked example is re-traced with example_case.py's own functions (same selection rule, asserted to
    select the case named in example_case.md / paper_numbers example.caseIdFull).
Table titles are not written into the files (the manuscript writes them). No new statistic is computed here.

English LaTeX tables (2026-09-23, TMLR manuscript) -> analysis/paper_tables/en/*.tex from the same keys: booktabs, no
vertical rules, ASCII only, one tabular per file (no table environment, no caption) plus an optional note paragraph;
tmain_* are the three main-text tables, tA_* the appendix tables (English versions of every zh table; the zh tab09 is
split into tA_redaction, tA_source_facts and tA_source_types; tA_contract_json.tex holds the rule JSON of tA_contract).
The manuscript needs \\usepackage{booktabs} and \\usepackage{array}. paper_tables/en/SOURCES.md lists the keys per file.
The zh files and paper_tables/SOURCES.md are unchanged by the English section.

Run after paper_numbers.py, from analysis/:
    python3 paper_tables.py        -> paper_tables/zh/tab*.md, paper_tables/SOURCES.md,
                                      paper_tables/en/*.tex, paper_tables/en/SOURCES.md
Deterministic: two runs give byte-identical files.
"""
import sys

sys.dont_write_bytecode = True  # never leave .pyc files in runtime/ or analysis/

import glob  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "paper_tables" / "zh"
sys.path.insert(0, str(HERE))

MODELS = (("gpt-oss:20b", "gptoss"), ("qwen3:8b", "q8b"), ("qwen3:30b-a3b", "q30b"))
CONDS = ("C0", "C1", "C2", "C3", "C4", "C5")
MINUS = "−"
FAMS = (  # slug, gold family, short Chinese name, descriptive Chinese name
    ("decision", "decision_ranking_protected_human_review_boundary", "决策族", "排序、决策语言与受保护特征"),
    ("ownership", "ownership_role_scope_inflation", "所有权族", "所有权与角色范围夸大"),
    ("qualification", "qualification_seniority_mismatch", "资历族", "资历与资格不符"),
    ("deployment", "unsupported_jd_technical_deployment", "部署族", "无依据的生产部署经验"),
    ("subjective", "unsupported_premise_followup_subjective_rationale", "主观族", "无依据前提、追问与主观理由"),
    ("quantification", "unsupported_quantification_causality", "量化族", "无依据的量化与因果"),
)
RULE_ORDER = ("claim_provenance", "unsupported_quantification", "ownership_scope", "deployment_boundary", "qualification_boundary",
              "human_review_boundary", "subjective_claim_boundary", "evidence_gap_router", "paired_review_bundle_completeness")
ARROW = {"C0toC1": "C0→C1", "C0toC2": "C0→C2", "C1toC2": "C1→C2", "C0toC5": "C0→C5", "C2toC4": "C2→C4", "C0toC4": "C0→C4"}


# ---------------------------------------------------------------- registry access

class Numbers:
    """paper_numbers.json with a record of the keys each table used (for SOURCES.md)."""

    def __init__(self):
        self.d = json.loads((HERE / "paper_numbers.json").read_text(encoding="utf-8"))
        self.used = {}
        self.extra = {}
        self.table = None

    def t(self, key):
        if key not in self.d:
            raise SystemExit(f"{self.table}: paper_numbers.json has no key {key!r}")
        self.used.setdefault(self.table, set()).add(key)
        return self.d[key]["text"]

    def v(self, key):
        self.t(key)
        return self.d[key]["value"]

    def has(self, key):
        return key in self.d

    def source(self, what):
        self.extra.setdefault(self.table, []).append(what)


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def pipe_table(header, rows):
    for r in rows:
        if len(r) != len(header):
            raise SystemExit(f"row width {len(r)} != header width {len(header)}: {r}")
    out = ["| " + " | ".join(cell(h) for h in header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return out


def write(name, header, rows, note, after=None):
    lines = pipe_table(header, rows) + ["", "注：" + note]
    if after:
        lines += [""] + after
    (OUT / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return name


def kn_k(text):
    k, n = text.split("/")
    return int(k), int(n)


def trunc(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n].rstrip() + "…"


# ---------------------------------------------------------------- tables

def tab01(N):
    N.table = "tab01_contract.md"
    md = (HERE / "tab1_contract.md").read_text(encoding="utf-8")
    N.source("tab1_contract.md: ```json contract excerpt (field values; `_annotation` dropped) and 'Implemented codes' line")
    m = re.search(r"```json\n(.*?)\n```", md, flags=re.S)
    if not m:
        raise SystemExit("tab1_contract.md: json block not found")
    rule = json.loads(m.group(1))
    if rule["ruleId"] != N.t("example.contract.rule"):
        raise SystemExit("tab1_contract.md ruleId differs from paper_numbers example.contract.rule")
    impl = re.search(r"Implemented codes for this rule: (.*?) \(codes not in", md)
    impl_codes = re.findall(r"`([a-z_]+)`", impl.group(1)) if impl else []
    never = [x.strip() for x in N.t("contract.keysNeverRead.list").split(",")]
    if sorted(never) != ["maxRegenerations", "provenance", "repair"]:
        raise SystemExit(f"unexpected contract keys never read: {never}")
    if N.t("contract.detectorsReadRuleSeverity") != "false":
        raise SystemExit("setup_facts: detectors/validator read rule severity; tab01 wording needs revising")
    ob, vt, hd, act = rule["obligation"], rule["validationTarget"], rule["handling"], rule["activation"]
    declared = [c["id"] for c in vt["checks"] if not c.get("requiresGold")]
    gold_only = [c["id"] for c in vt["checks"] if c.get("requiresGold")]
    words = (N.t("example.contract.words.prose"), N.t("example.contract.words.duty"), N.t("example.contract.words.block"))
    rows = [
        ("ruleId", f"规则标识；校验器按 ruleId 注册对应的手写检测器（共 {N.t('contract.detectors.n')} 个）", f"`{rule['ruleId']}`"),
        ("title / version / kind", "名称、版本与规则类型（描述性元数据）", f"{rule['title']} / {rule['version']} / {rule['kind']}"),
        ("severity", "规则级严重度；渲染为 C2 契约块的 severity 字段；校验器发出的 finding 严重度由检测器代码写定，不读取本字段", rule["severity"]),
        ("activation", "激活条件；rules.py 据此判定该规则是否对本例渲染（C1、C2）", f"{act['type']}；scopes {', '.join(act['scopes'])}；predicates {', '.join(act['predicates'])}"),
        ("obligation.prose", "C1 散文规则的全文", f"{words[0]} 词：“{trunc(ob['prose'], 60)}”"),
        ("obligation.mustDo", "C2 契约块的 must 条目", f"{len(ob['mustDo'])} 条：“{trunc(ob['mustDo'][0], 60)}”等"),
        ("obligation.mustNot", "C2 契约块的 mustNot 条目", f"{len(ob['mustNot'])} 条：“{trunc(ob['mustNot'][0], 60)}”"),
        ("obligation.route", "C2 契约块的 route：证据不足时的路由去向", f"“{trunc(ob['route'], 60)}”"),
        ("validationTarget.reads", "声明检查读取的产物字段", f"{len(vt['reads'])} 条路径（optimizedCv、supportedClaims、需求证据文本）"),
        ("validationTarget.checks", "声明的检查集合；非 requiresGold 的 id 渲染为 C2 的 checkedBy；requiresGold 的检查只在评分时计算",
         "；".join(f"`{c}`" for c in declared) + "；" + "；".join(f"`{c}`（requiresGold，仅评分）" for c in gold_only)),
        ("validationTarget.witness", "违规时 finding 应记录的证据", f"“{trunc(vt['witness'], 60)}”"),
        ("handling.onFail", "违规处理级别；渲染为 C2 契约块的 onViolation", hd["onFail"]),
        ("handling.repair", "声明的修复动作；运行时不读取（修复器按规则手写）", "；".join(f"`{r['action']}`" for r in hd["repair"]) + "（附 reason 与 requiredFollowUp）"),
        ("handling.maxRegenerations", "声明的再生成上限；运行时不读取（流水线写定至多一次再生成）", str(hd["maxRegenerations"])),
        ("provenance", "规则来源说明；运行时不读取", f"{len(rule['provenance'])} 项：" + " / ".join(rule["provenance"])),
    ]
    excerpt = re.sub(r', "_annotation": "[^"]*"', "", m.group(1))  # the rule file text as tab1_contract.md prints it
    stripped = json.loads(excerpt)
    for c in rule["validationTarget"]["checks"]:
        c.pop("_annotation", None)
    if stripped != rule:
        raise SystemExit("tab01: removing _annotation changed more than that key")
    after = ["```json", excerpt, "```"]
    note = (f"契约取自 `rules/canonical-rules.v2.json` 的 `{rule['ruleId']}` 条目（表后代码块为该条目原文；tab1_contract.py 加注的 `_annotation` 键已去掉）。"
            f"词数按空白切分：散文义务 {words[0]} 词；mustDo + mustNot + route {words[1]} 词；本规则渲染后的整个 C2 块 {words[2]} 词"
            f"（含 severity、applies、checkedBy、onViolation；渲染实例为案例 `{N.t('example.contract.caseId')}`）。"
            f"「运行时不读取」指 `runtime/hrgene/*.py` 中没有读取该键的代码（setup_facts.py 静态检查：{', '.join(never)}）；"
            "契约文件只被 rules.py 用于激活判定与 prompt 渲染，detectors.py 与 validator.py 不读取契约字段。"
            f"本规则声明的校验器检查为 {'、'.join('`' + c + '`' for c in declared)}，校验器实际可发出的 code 为 "
            f"{'、'.join('`' + c + '`' for c in impl_codes)}（未声明者为实现侧追加的检查，全体规则的差异见表 A2）。")
    return write("tab01_contract.md", ("字段", "含义", "本规则取值（简短）"), rows, note, after)


def tab02(N):
    N.table = "tab02_benchmark.md"
    N.source("benchmark/v4/gold/*.json (read only): family -> gold.trap.rule mapping and the families of the anywhereSignatures cases")
    fam_rule, any_fams = {}, {}
    for f in sorted(glob.glob(str(ROOT / "benchmark" / "v4" / "gold" / "*.json"))):
        g = json.loads(Path(f).read_text(encoding="utf-8"))
        if g["controlStatus"] == "positive_risk":
            fam_rule.setdefault(g["family"], set()).add(g["trap"]["rule"])
            if (g.get("trap") or {}).get("anywhereSignatures"):
                any_fams[g["family"]] = any_fams.get(g["family"], 0) + 1
    rows = []
    for slug, fam, short, desc in FAMS:
        rules = fam_rule[fam]
        if len(rules) != 1:
            raise SystemExit(f"{fam}: several anchoring rules {rules}")
        rule = rules.pop()
        if int(N.t(f"bench.trapRule.{rule.split('.')[-1]}.n")) != int(N.t(f"bench.family.{slug}.risk.n")):
            raise SystemExit(f"{fam}: anchoring rule count differs from risk count")
        if N.t(f"bench.family.{slug}.name") != fam:
            raise SystemExit(f"{slug}: family name mismatch")
        rows.append((f"{short}：{desc}（{fam}）", N.t(f"bench.family.{slug}.risk.n"), N.t(f"bench.family.{slug}.control.n"), f"`{rule.split('.')[-1]}`"))
    rows.append(("合计", N.t("bench.risk.n"), N.t("bench.control.n"), f"{N.t('bench.families.n')} 条规则各锚定一族"))
    n_any = int(N.t("bench.anywhereCases.n"))
    if sum(any_fams.values()) != n_any:
        raise SystemExit("anywhereSignatures case count differs from tab2_benchmark.json")
    any_where = "；".join(f"{dict((f, s) for _, f, s, _ in FAMS)[f]} {k} 例" for f, k in sorted(any_fams.items()))
    note = (f"共 {N.t('bench.cases.n')} 例（{N.t('bench.risk.n')} 风险 + {N.t('bench.control.n')} 匹配干净对照，{N.t('bench.families.n')} 个压力族）。"
            f"每例 {N.t('bench.perCase.requirements')} 条岗位需求、{N.t('bench.perCase.propositions')} 条金标命题、{N.t('bench.perCase.evidence')} 个证据来源。"
            "风险案例的陷阱由只出现在诱饵来源中的签名短语锚定（金标 `trap.signatures`），另有陷阱需求的金标状态；"
            "匹配干净对照没有陷阱，其金标给出有效主张签名（`validClaimSignatures`），用于度量有效主张的保留。"
            f"带 `anywhereSignatures`（受保护特征短语，产物任一文本字段出现即计陷阱失败）的案例 {n_any} 例，全部为风险案例（{any_where}）。"
            "锚定规则 = 金标 `trap.rule`，即该族陷阱所对应的规则契约。"
            f"基准与金标于 2026-09-06 冻结（cases+gold 摘要 `{N.t('bench.freeze.casesGold.short')}…`，规则文件摘要 `{N.t('bench.freeze.rules.short')}…`）。")
    return write("tab02_benchmark.md", ("族（英文名）", "风险", "对照", "锚定规则"), rows, note)


def tab03(N):
    N.table = "tab03_models.md"
    rows = []
    for m, s in MODELS:
        if N.t(f"setup.{s}.tag") != m:
            raise SystemExit(f"{m}: tag mismatch")
        other = (f"temperature {N.t(f'setup.{s}.temperature')}，seed {N.t(f'setup.{s}.seed')}，num_ctx {N.t(f'setup.{s}.numCtx')}，"
                 f"num_predict {N.t(f'setup.{s}.numPredict')}，每条件每例 {N.t(f'setup.{s}.repeat')} 次")
        rows.append((m, N.t(f"setup.{s}.quant"), N.t(f"setup.{s}.params"), f"`{N.t(f'setup.{s}.digest12')}`", N.t(f"setup.{s}.think"), other, N.t(f"setup.{s}.ollama")))
    for key in ("temperature", "seed", "numCtx", "numPredict", "repeat"):
        N.t(f"setup.all.{key}")  # registered only when identical for all models
    note = (f"digest 为 Ollama 报告的模型 digest 前 12 位十六进制；各模型在 C0、C1、C2、C5 运行（及 gpt-oss:20b 的 C4 再生成）中的 digest、模型名与 seed 逐输出一致"
            f"（例如 gpt-oss:20b C2 {N.t('setup.gptoss.outputs.C2.kn')} 份输出，不一致 {N.t('setup.gptoss.outputs.C2.mismatches')} 处）。"
            f"think 为 Ollama 的推理开关：gpt-oss:20b 为 `{N.t('setup.gptoss.think')}`，两个 qwen 模型为 `{N.t('setup.q8b.think')}`，这是模型间的配置差异。"
            "解码参数由请求 options 给定，覆盖模型文件的默认采样参数"
            f"（gpt-oss:20b 默认 `{N.t('setup.gptoss.modelfileParameters')}`；qwen 默认 `{N.t('setup.q8b.modelfileParameters')}`）。"
            f"硬件：{N.t('setup.hw.machine')}（{N.t('setup.hw.chip')}，{N.t('setup.hw.memory')}），Ollama {N.t('setup.ollama')}。")
    return write("tab03_models.md", ("模型", "量化", "参数量", "digest", "think", "其余解码参数", "Ollama"), rows, note)


def tab04(N):
    N.table = "tab04_detector.md"
    rows = []
    total = 0
    for r in RULE_ORDER:
        rows.append((f"`{r}`", N.t(f"detector.{r}.mutants"), N.t(f"detector.{r}.precision"), N.t(f"detector.{r}.recall")))
        total += int(N.t(f"detector.{r}.mutants"))
    if total != int(N.t("detector.mutants.n")) or len(RULE_ORDER) != int(N.t("detector.rules.n")):
        raise SystemExit("detector totals differ")
    rows.append(("合计", N.t("detector.mutants.n"), f"最低 {N.t('detector.precision.min')}", f"最低 {N.t('detector.recall.min')}"))
    if N.t("detector.rulesetDigest") != N.t("bench.freeze.rules")[:12]:
        raise SystemExit("detector_pr.json ruleset digest differs from the frozen rules digest")
    note = ("变体数 = 变异注入生成的、按构造违反该规则的变体数（tp + fn）；R = 该规则在这些变体上触发的比例；"
            "P 的误报计入该规则在干净 oracle、近似合法编辑与不违反该规则的变体上的触发。"
            "变体由校验器自身的词表与规则构造，因此这是实现自洽性检查：它说明检测器实现了其设计意图，不是真实模型输出上的精确率或召回率（真实输出上的精确率在本研究中无法估计）。"
            f"误报检查：{N.t('detector.cleanOracles.n')} 份干净 oracle 产物中被标记 {N.t('detector.cleanOracles.kn')}；"
            f"{N.t('detector.nearMisses.n')} 个近似合法编辑（near-miss：逐字引用来源、引用来源中的数字、否定的所有权表述、提及生产部署的缺口、否定式决策清单等）中被标记 {N.t('detector.nearMisses.kn')}。"
            f"变异注入所用规则摘要 `{N.t('detector.rulesetDigest')}…`，与冻结规则文件摘要一致。")
    return write("tab04_detector.md", ("规则", "变体数", "P", "R"), rows, note)


def tab05(N):
    N.table = "tab05_main.md"
    rows = []
    res = set()
    for m, s in MODELS:
        for c in CONDS:
            k = f"main.{s}.{c}"
            schema = N.t(k + ".schemaValid") if c != "C4" else "—"
            if c == "C4":
                res.add((N.t(k + ".residual"), N.t(k + ".schemaValid")))
            rows.append((m, c, N.t(k + ".parsed"), schema, f"{N.t(k + '.trap.full')}（{N.t(k + '.trap.kn')}）", N.t(k + ".trapRouted"),
                         N.t(k + ".kept"), N.t(k + ".flaggedRisk.kn"), N.t(k + ".flaggedControl.kn")))
    if len(res) != 1:
        raise SystemExit(f"C4 residual / schema validity differ across models: {res}")
    resid, schema4 = res.pop()
    note = ("可解析与 schema 有效以全部 144 例为分母（不可解析产物计为无效）。"
            "陷阱失败率 = 冻结评分器的 `trapFellAny`（陷阱签名落在支持侧、陷阱需求被标为 supported 而金标不是、决策族与主观族的分族附加规则）在可解析风险案例上的比例，95% CI 为 Wilson 区间，括号内为 k/n。"
            "陷阱正确路由率 = 可解析风险案例中陷阱未落且被路由的比例（决策族 = 未落；主观族 = 每个金标主观来源出现在 interviewSignalRisks；其余族 = 陷阱需求出现在 missingEvidenceGaps / followUpQuestions 或陷阱签名出现在 unsupportedClaims）。"
            "对照保留率 = 可解析匹配对照上每例金标有效签名在支持侧任一处出现的比例的均值（宽松指标）。"
            "包级标记 = 校验器包级结论为 BLOCK 或 HUMAN_REVIEW 的案例数 / 72（风险或对照；不可解析产物计为标记）；C0、C1、C2、C5 的标记是生成后的离线校验，生成时没有执行校验；包级标记不是检测指标。"
            "C3 = C2 产物（同一批输出加上校验报告），产物指标与 C2 相同。"
            f"C4 = 对冻结 C2 产物的确定性后处理（校验、一次修复、至多一次再生成）；C4 的残留关键违规率（{resid}）与 schema 有效率（{schema4}）按构造成立，未列入（记为「—」）。")
    header = ("模型", "条件", "可解析", "schema 有效", "陷阱失败率 [95% CI]（k/n）", "陷阱正确路由率", "对照保留率", "包级标记：风险", "包级标记：对照")
    return write("tab05_main.md", header, rows, note)


def contrast_row(N, label, key, name):
    n, b, c = N.t(key + ".n"), N.t(key + ".b"), N.t(key + ".c")
    if int(N.v(key + ".discordant")) == 0:
        diff = f"{N.t(key + '.diff')}（0/{n} 个不一致对，不报区间）"
    else:
        diff = N.t(key + ".diff.full")
    return (label, name, n, f"{b}/{c}", diff, N.t(key + ".p"))


def tab06(N):
    N.table = "tab06_contrasts.md"
    rows = []
    for m, s in MODELS:
        for ab in ("C0toC1", "C0toC2", "C1toC2", "C0toC5", "C2toC4", "C0toC4"):
            rows.append(contrast_row(N, m, f"contrast.{s}.{ab}", ARROW[ab]))
    pooled = "三模型堆叠（描述性，区间未校正聚类）"
    for ab in ("C0toC2", "C1toC2", "C0toC5", "C2toC4"):
        rows.append(contrast_row(N, pooled, f"contrast.pooled.{ab}", ARROW[ab]))
    for m, s in MODELS + (("三模型合计（描述性，区间未校正聚类）", "pooled"),):
        k = f"clear.{s}.C2toC4"
        rows.append((m, "C2→C4 清除率", N.t(k + ".n"), f"清除 {N.t(k + '.kn')}", f"{N.t(k + '.full')}（Wilson）", "—"))
    if N.t("contrast.signIdentityIntoC4.holds") != "true":
        raise SystemExit("sign-test identity for contrasts into C4 not confirmed")
    note = ("对比 X→Y 只用两条件下都可解析的风险案例（配对 n）；转出 = X 落陷阱而 Y 未落（b），新增 = X 未落而 Y 落（c）；"
            "差值 = (c − b) / 配对 n，即 Y 的陷阱失败率减 X 的（pp），95% CI 为 Newcombe (1998) 配对差 method 10；p 为精确双侧 McNemar。"
            "c = 0 时精确 McNemar 退化为 b 个不一致对的符号检验，p = 2·0.5^b，只是 b 的函数（进入 C4 的对比凡 c = 0 者均已按此核对）。"
            "C2→C4 的新增为 0 主要由设计决定：修复不向支持侧添加文本、不上调需求状态；其余可能产生新增的路径（主观族需求降级、重复需求去重、再生成）在本数据中也未产生新增。"
            f"qwen3:30b-a3b 的 C0→C5 没有不一致对（0/{N.t('contrast.q30b.C0toC5.n')}），不报区间。"
            "三模型堆叠 = 把三个模型的配对案例叠成一个 2×2 表：同一批案例重复出现三次，配对不独立，只作描述性汇总，区间与 p 未校正聚类。"
            "清除率行：配对 n 列为 C2 已落陷阱的配对风险案例数，清除 = 其中 C4 不再落陷阱的案例数，区间为 Wilson 95% CI。"
            "C1 与 C2 的请求在措辞、字段、校验头部句与长度上都不同（见表 A1），C1→C2 不隔离表示形式。")
    header = ("模型", "对比", "配对 n", "转出/新增", "差值 pp [Newcombe 95% CI]", "精确 McNemar p")
    return write("tab06_contrasts.md", header, rows, note)


def fam_cell(N, s, slug):
    k = f"family.{s}.C2toC4.{slug}"
    c2, c4, rep, new = N.t(k + ".c2fail"), N.t(k + ".c4fail"), N.t(k + ".repaired"), N.t(k + ".new")
    return f"{c2} → {c4}（清除 {rep}{'' if new == '0' else '，新增 ' + new}）"


def tab07(N):
    N.table = "tab07_families.md"
    N.source("tab07 合计行: sums of paper_numbers contrast.<model>.C2toC4.{a, b, c} (C2 failures = a + b, C4 failures = a + c)")
    rows = []
    for slug, fam, short, desc in FAMS:
        rows.append((f"{short}（{fam}）",) + tuple(fam_cell(N, s, slug) for _, s in MODELS))
    rows.append(("其余五族合计",) + tuple(fam_cell(N, s, "other5") for _, s in MODELS))
    tot = []
    for _, s in MODELS:
        k = f"contrast.{s}.C2toC4"
        a, b, c = int(N.v(k + ".a")), int(N.v(k + ".b")), int(N.v(k + ".c"))
        fam_sum = sum(int(N.v(f"family.{s}.C2toC4.{slug}.c2fail")) for slug, *_ in FAMS)
        if fam_sum != a + b:
            raise SystemExit(f"{s}: family C2 failures do not add up")
        tot.append(f"{a + b} → {a + c}（清除 {b}{'' if c == 0 else '，新增 ' + str(c)}）")
    rows.append(("全部六族",) + tuple(tot))
    note = ("每格为该族风险案例在 C2 与 C4 下的陷阱失败数（两条件都可解析的配对案例，每族 12 例），括号内为 C2→C4 清除数；新增为 0 时不写。"
            "分族只描述、不作检验。决策族的陷阱可由 `anywhereSignatures`、决策语言或决策边界字段触发，落点可以在支持侧以外。"
            "决策族占全部清除的比例：" + "；".join(f"{m} {N.t(f'repair.{s}.cleared.decisionShare.kn')}" for m, s in MODELS) + "；"
            "其中清除动作含删除 interviewSignalRisks 条目的决策族案例："
            + "；".join(f"{m} {N.t(f'repair.{s}.cleared.decisionAction.delete_item_interviewSignalRisks')}/{kn_k(N.t(f'repair.{s}.cleared.decisionShare.kn'))[0]}" for m, s in MODELS) + "。")
    header = ("族",) + tuple(m for m, _ in MODELS)
    return write("tab07_families.md", header, rows, note)


def tab08(N):
    N.table = "tab08_cost.md"
    rows = []
    for m, s in MODELS:
        k = f"cost.{s}.C2toC4.keptDiff"
        kept = N.t(k + ".full") if N.has(k + ".full") else f"无变化（{N.t(k + '.n')} 个配对差均为 0）"
        if not N.has(k + ".full") and N.t(f"cost.{s}.controls.keptChanged") != "0":
            raise SystemExit(f"{s}: retention difference without interval although controls changed")
        sup = f"{N.t(f'cost.{s}.supported.all144.c2')} → {N.t(f'cost.{s}.supported.all144.c4')}（{N.t(f'cost.{s}.supported.all144.delta')}）"
        zero = f"{N.t(f'cost.{s}.zeroed.risk')} / {N.t(f'cost.{s}.zeroed.control')}"
        comp = " / ".join(f"{N.t(f'repair.{s}.cat.{c}.events')}（{N.t(f'repair.{s}.cat.{c}.cases')} 例）" for c in ("relabel", "deleteReplace", "moveISR"))
        rows.append((m, kept, sup, zero, N.t(f"cost.{s}.controls.anyRepair.kn"), N.t(f"cost.{s}.controls.relabeledOrRemoved.kn"),
                     N.t(f"cost.{s}.controls.keptChanged.kn"), comp))
    note = ("对照保留差 = 两条件都可解析的匹配对照上每例保留率（金标有效签名在支持侧任一处出现的比例）C4 减 C2 的均值，95% CI 为按案例 bootstrap"
            f"（B = {N.t('stats.bootstrap.B')}）；保留率是宽松指标，签名在支持侧任一处出现即算保留。"
            "每例支持侧条目 = 评分器支持侧条目数（optimizedCv 四区块、supportedClaims、supported / partial 需求项的证据文本与备注）在全部 144 例上的均值（不可解析计 0），括号内为差值。"
            "支持侧归零 = 两条件都可解析、C4 支持侧条目数为 0 的案例数（风险 / 对照）。"
            "有修复动作的对照 = repairLog 非空的对照；支持侧被改动的对照 = 至少一个支持侧条目被改标、移出或删除的对照；保留率改变的对照 = 两条件都可评分且保留率不同的对照。"
            "修复动作构成 = C4 repairLog 事件数（括号内为至少有一个该类事件的案例数，风险与对照合计）：改标 = 支持侧主张移入 unsupportedClaims；"
            "删除或替换 = 删除条目或证据、替换文本字段（含受保护特征与决策语言条目）；移入风险项 = 主观内容移入 interviewSignalRisks。"
            "另有需求状态 / 结构与其他结构性事件，未列入本表。"
            f"qwen3:30b-a3b 的保留率无变化，但 {N.t('cost.q30b.controls.relabeledOrRemoved.kn')} 个对照的支持侧条目被改标或删除。"
            f"gpt-oss:20b 的支持侧条目降幅主要来自无 sourceId 的 optimizedCv 裸字符串条目（C2 共 {N.t('cost.gptoss.bare.stringItems')} 条）被 `claim_has_source` 整体改标；"
            f"关闭字符串提升后其保留差为 {N.t('sens.lift.gptoss.keptDiff.off.full')}（见表 10）。")
    header = ("模型", "对照保留 C2→C4 差 [95% CI]", "每例支持侧条目 C2→C4", "支持侧归零案例（风险 / 对照）", "有修复动作的对照",
              "支持侧被改动的对照", "保留率改变的对照", "修复动作构成（改标 / 删除或替换 / 移入风险项）")
    return write("tab08_cost.md", header, rows, note)


def tab09(N):
    N.table = "tab09_redaction.md"
    rows = []
    for m, s in MODELS:
        f = f"frontier.{s}"
        nd_gap = int(N.v(f + ".nd.gap"))
        if nd_gap > 2:
            nd = f"{N.t(f + '.nd.C4.trap')} vs {N.t(f + '.nd.S.attrition')}"
        else:
            nd = f"不比较（C2 {N.t(f + '.nd.C2.trap.kn')} → C4 {N.t(f + '.nd.C4.trap.kn')}，仅差 {nd_gap} 例）"
        kept_only = f"{N.t(f + '.grid.keptOnly.trap')}（保留 {N.t(f + '.grid.keptOnly.kept')}）"
        at_or_below = N.t(f + ".grid.atOrBelowC4.kn")
        mk = N.t(f + ".grid.atOrBelowC4.maxKept")
        at_or_below += f"（最高保留 {mk}）" if mk != "–" else "（无此类配置）"
        rows.append((m, N.t(f + ".C2.trap"), f"{N.t(f + '.C4.trap')} / {N.t(f + '.C4.kept')}", N.t(f + ".S.attrition"), N.t(f + ".S.retention"),
                     f"{N.t(f + '.S.floor')}（{N.t(f + '.S.floor.kn')}）", nd, kept_only, at_or_below, N.t(f + ".grid.both.kn")))
    # two source-type policy rows (POST HOC, 2026-09-23); each cell lists the three models in MODELS order, separated by "；"
    for pol, lab in (("dropNoteCited", "drop_note_cited"), ("dropNoteOrUnsourced", "drop_note_or_unsourced")):
        own, nd_c, x_c, le_c, both_c = [], [], [], [], []
        for m, s in MODELS:
            f = f"frontier.{s}"
            own.append(f"{N.t(f'{f}.{pol}.trap')} / {N.t(f'{f}.{pol}.kept')}")
            if int(N.v(f + ".nd.gap")) > 2:
                nd_c.append(f"{N.t(f + '.nd.C4.trap')} vs {N.t(f'{f}.{pol}.nd.trap')}")
            else:
                nd_c.append(f"不比较（该策略 {N.t(f'{f}.{pol}.nd.trap.kn')}）")
            x_c.append(f"{N.t(f'{f}.{pol}X.trap')} / {N.t(f'{f}.{pol}X.kept')}")
            le_c.append(f"{sum(N.t(f'{f}.{p}.atOrBelowC4') == 'true' for p in (pol, pol + 'X'))}/2")
            both_c.append(f"{sum(N.t(f'{f}.{p}.bothC4') == 'true' for p in (pol, pol + 'X'))}/2")
        rows.append((f"{lab}（来源类型策略）", "—", "；".join(own), "—", "—", "—", "；".join(nd_c), "；".join(x_c), "；".join(le_c), "；".join(both_c)))
    routed = "；".join(f"{m} {N.t(f'frontier.{s}.dropNoteCited.trapRouted')} / {N.t(f'frontier.{s}.dropNoteOrUnsourced.trapRouted')} / "
                      f"{N.t(f'frontier.{s}.dropNoteCitedX.trapRouted')} / {N.t(f'frontier.{s}.dropNoteOrUnsourcedX.trapRouted')}（C4 {N.t(f'frontier.{s}.C4.trapRouted')}）"
                      for m, s in MODELS)
    subj_x = sorted({N.t(f"frontier.{s}.{p}X.subjRouted") for _, s in MODELS for p in ("dropNoteCited", "dropNoteOrUnsourced")})
    note = ("POST HOC、探索性；结论只对本网格与本组种子成立，不是对所有内容无关变换的界。"
            "内容无关变换只按结构位置、状态枚举与随机种子选择条目，不读金标、陷阱签名、词表、校验器结果或条目文本，作用于冻结 C2 产物后用冻结评分器重打，取种子均值："
            "S(p) 把比例 p 的支持侧条目改标（移入 unsupportedClaims）或删除；R(q) 把比例 q 的 supported 需求项降为 partial_evidence；"
            "X(r) 把决策边界字段重置为修复器的常量值，并删除比例 r 的 interviewSignalRisks / 人工复核清单 / 局限条目。"
            "同删减量 / 同保留率盲目 = S 改标曲线在 C4 的每例支持侧条目数 / 对照保留率处的线性插值陷阱失败率；S 地板 = 支持侧全部移除（保留率 0%）时的陷阱失败率，"
            f"三模型合计的地板失败 {N.t('frontier.pooled.floor.kn')} 中决策族 {N.t('frontier.pooled.floor.decisionFamily')} 例（其中 `anywhereSignatures` 触发 {N.t('frontier.pooled.floor.decisionAnywhere')} 例，"
            f"短语落在 interviewSignalRisks 的 {N.t('frontier.pooled.floor.field.interviewSignalRisks')} 例），需求状态越界 {N.t('frontier.pooled.floor.requirementOverclaim')} 例，"
            f"主观族附加规则 {N.t('frontier.pooled.floor.subjectiveExtra')} 例；修复器的 `_fix_requirements` 在三次运行中下调需求状态 "
            + "/".join(N.t(f"repair.{s}.fixReq.downgrades") for _, s in MODELS) + " 次。"
            "非决策族 = 五个非决策族（60 风险 + 60 对照），在子集上重算曲线与 C4 坐标；C2 与 C4 在该子集上只差 2 例的模型不作比较。"
            f"扩展网格 = S×R×X 每模型 {N.t('frontier.gptoss.grid.nConfigs')} 个配置（p、模式、q、r）；「保留率 ≥ C4 时最低陷阱」取保留率不低于 C4 的配置中陷阱失败率最低者；"
            "「陷阱 ≤ C4 的配置数」为陷阱失败率不高于 C4 的配置数；双约束 = 保留率与陷阱正确路由率都不低于 C4。"
            "陷阱失败率分母为可解析风险案例（72），保留率分母为可解析对照；C4 点取自同一产物（gpt-oss:20b 的 C4 保留率在 72 个对照上计算）。"
            f"末两行为来源类型策略（{N.t('frontier.design.sourcePolicies.designedOn')} 事后设计，设计时已知诱饵全部是备注类来源，"
            f"金标诱饵中备注占 {N.t('setup.source.baitGold.note.kn')}）："
            "drop_note_cited 把引用备注类来源（按案例元数据中的来源类型判定）的支持侧条目改标，drop_note_or_unsourced 另加无 sourceId 的条目；"
            "二者只读来源类型与条目 sourceIds，不读金标、陷阱签名、词表、校验器结果或条目文本，但不是内容无关变换。"
            "策略行每格依次为 gpt-oss:20b；qwen3:8b；qwen3:30b-a3b。策略行中，「C4 陷阱 / 保留」列为该策略自身的陷阱 / 保留；"
            "「非决策族」列为 C4 vs 该策略（C2 与 C4 只差 2 例的模型不比较）；「扩展网格」列为 +X 变体（策略后再施加 X(r = 1)）的陷阱 / 保留；"
            "「陷阱 ≤ C4」与「双约束」两列的分母为该策略的两个变体（不加 / 加 X）。"
            f"陷阱正确路由率（drop_note_cited / drop_note_or_unsourced / 二者加 X）：{routed}；加 X 后主观来源路由率为 {'、'.join(subj_x)}（X 清空 interviewSignalRisks）。")
    header = ("模型 / 策略", "C2 陷阱", "C4 陷阱 / 保留", "同删减量盲目", "同保留率盲目", "S 地板（保留 0%）", "非决策族：C4 vs 同删减量盲目",
              "扩展网格：保留率 ≥ C4 时最低陷阱", "陷阱 ≤ C4 的配置数", "满足双约束的配置数")
    return write("tab09_redaction.md", header, rows, note)


def tab10(N):
    N.table = "tab10_sensitivity.md"
    rows = []
    for m, s in MODELS:
        d = f"sens.dev.{s}"
        trap = f"{N.t(d + '.all.C4.trap.full')} / {N.t(d + '.excl.C4.trap.full')}"
        clear = (f"{N.t(d + '.all.C2toC4.clear.kn')} = {N.t(d + '.all.C2toC4.clear.full')} / "
                 f"{N.t(d + '.excl.C2toC4.clear.kn')} = {N.t(d + '.excl.C2toC4.clear.full')}")
        kd = []
        for part in ("all", "excl"):
            k = f"{d}.{part}.keptDiff"
            kd.append(N.t(k + ".full") if N.has(k + ".full") else "无变化")
        u = f"sens.uni.{s}.C4.trap"
        uni = f"{N.t(u + '.norm.full')}（{N.t(u + '.norm.kn')}；原 {N.t(u + '.official.kn')}）"
        if s == "gptoss":
            lift = (f"C2 陷阱 {N.t('sens.lift.gptoss.C2.trap.official.kn')} → {N.t('sens.lift.gptoss.C2.trap.off.kn')}；"
                    f"保留差 {N.t('sens.lift.gptoss.keptDiff.official')} → {N.t('sens.lift.gptoss.keptDiff.off.full')}")
        else:
            lift = "不适用（无裸字符串条目）"
        rows.append((m, trap, clear, " / ".join(kd), uni, lift))
    if N.t("sens.lift.qwenIdentity") != "true":
        raise SystemExit("lift_string_items is not the identity on the qwen outputs")
    note = ("POST HOC 敏感性。剔除开发样板 = 去掉 09-05 用于迭代检测器、评分器与修复器的 "
            f"{N.t('sens.dev.n')} 例（{N.t('sens.dev.nRisk')} 风险 + {N.t('sens.dev.nControl')} 对照，qwen3:8b 试点输出文件名给出），在其余 66 + 66 例上重算；"
            "每格「全集 / 剔除」。陷阱失败率与清除率为 Wilson 95% CI；对照保留差为 C2→C4 每例保留率差的均值与按案例 bootstrap 区间，「无变化」表示所有配对差为 0。"
            "Unicode 归一化 = 签名匹配前把 U+2010–U+2015、U+2212 映射为 ASCII 连字符，弯引号映射为直引号，U+00A0 映射为空格，输出文本与签名同时映射，其余评分不变。"
            "关闭字符串提升 = 在进程内把 `bundle.lift_string_items`（09-07 看到 gpt-oss 数据后加入）换成不提升的副本，校验、修复与评分同时生效，C4 由冻结修复流水线从 C2 输出离线重建；"
            f"两个 qwen 模型的产物没有裸字符串条目，提升是恒等变换（不适用）。关闭提升后 gpt-oss:20b 的 C4 陷阱为 {N.t('sens.lift.gptoss.C4.trap.off.kn')}（原 {N.t('sens.lift.gptoss.C4.trap.official.kn')}）。")
    header = ("模型", "C4 陷阱：全集 / 剔除开发样板", "C2→C4 清除率：全集 / 剔除", "对照保留差：全集 / 剔除", "Unicode 归一化后 C4 陷阱",
              "关闭字符串提升（仅 gpt-oss）：C2 陷阱与保留差")
    return write("tab10_sensitivity.md", header, rows, note)


def tabA1(N):
    N.table = "tabA1_conditions.md"
    ident = "；".join(f"{m} {N.t(f'cond.{s}.C0C5.identical.kn')}" for m, s in MODELS)
    regen = "、".join(N.t(f"repair.{s}.regenerated") for _, s in MODELS)
    extra = N.t("cond.C2.extraFields").replace(", ", "、")
    rows = [
        ("C0", f"基线：JSON 模式（format = \"{N.t('cond.C0.format')}\"），prompt 含完整的输出契约描述，不含规则", N.t("cond.C0.words.median"), "—",
         f"否（{N.t('cond.C0.header.kn')}）", "—"),
        ("C1", f"system 消息加入散文规则部分（`render_prose` 渲染本例激活的规则）；{N.t('cond.C1.equalsC0PlusRendering.kn')} 条请求等于 C0 + 该渲染",
         N.t("cond.C1.words.median"), N.t("cond.C1.rulesWords.median"), f"否（{N.t('cond.C1.header.kn')}）", "—"),
        ("C2", f"system 消息加入契约规则部分（`render_contract`：must / mustNot / route，另加 {extra} 与顶层 {N.t('cond.C2.extraTopLevel')}）及校验头部句；"
               f"{N.t('cond.C2.equalsC0PlusRendering.kn')} 条请求等于 C0 + 该渲染", N.t("cond.C2.words.median"), N.t("cond.C2.rulesWords.median"),
         f"是（{N.t('cond.C2.header.kn')}）", "—"),
        ("C3", "无新请求：C2 产物加上离线校验报告", "—", "—", "—", "—"),
        ("C4", f"无新生成请求：对冻结 C2 产物校验、一次修复、至多一次再生成（再生成请求数 {regen}，按 gpt-oss:20b、qwen3:8b、qwen3:30b-a3b）", "—", "—", "—", "—"),
        ("C5", f"与 C0 只差 format 字段：值为产物 JSON Schema（`{N.t('cond.C5.schemaFile')}`，约束解码）；另两个不同的键为条件标签与请求 id",
         N.t("cond.C5.words.median"), "—", f"否（{N.t('cond.C5.header.kn')}）", ident),
    ]
    diff_keys = N.t("cond.C0C5.diffKeys")
    if diff_keys != "condition, format, request_id" or N.t("cond.C0C5.diffMetaKeys.n") != "0":
        raise SystemExit(f"C0/C5 request difference changed: {diff_keys}")
    note = (f"词数 = system 与 user 消息按空白切分的词数，取每条件 {N.t('cond.C0.requests.n')} 条请求的中位数；规则部分词数 = 同一案例 C1 / C2 的 system 消息词数减去 C0 的。"
            f"逐案配对的 C2 − C1 词数中位数为 {N.t('cond.C2minusC1.words.median')}（范围 {N.t('cond.C2minusC1.words.min')}–{N.t('cond.C2minusC1.words.max')}）。"
            f"校验头部句 = C2 规则部分的首句：“{N.t('cond.C2.headerLine')}”，统计同时含「{N.t('cond.C2.headerPhrase1')}」与「{N.t('cond.C2.headerPhrase2')}」的请求；"
            "C2 生成时并不执行校验，也不送回修复（C3 只是事后的离线校验）。"
            f"C0 与 C5 的 {N.t('cond.C0C5.linesDiffer.kn')} 条请求逐键比较，只有 {diff_keys} 三个顶层键不同。"
            "逐字节相同 = 同一案例 C0 与 C5 输出的 content 字符串在 UTF-8 下完全相同（分母 144）。"
            "四个生成条件的请求文件对三个模型逐字节相同（requests sha256 前 12 位："
            + "；".join(f"{c} `{N.t(f'cond.{c}.requestsSha12')}`" for c in ("C0", "C1", "C2", "C5")) + "）。")
    header = ("条件", "请求相对 C0 的差异", "prompt 中位词数", "规则部分中位词数", "是否含校验头部句", "与 C0 逐字节相同的输出数（仅 C5）")
    return write("tabA1_conditions.md", header, rows, note)


def tabA2(N):
    N.table = "tabA2_contract_coverage.md"
    N.source("setup_facts.json: contractCoverage.codeTable (emitted vs rule-JSON severity) and contractCoverage.counterpartMap (hand-assigned renamed counterparts)")
    N.source("RECORDS.md 2026-09-05 entry (text only): the requirement-level licensing checks were added while iterating on the C0 pilot")
    sf = json.loads((HERE / "setup_facts.json").read_text(encoding="utf-8"))["contractCoverage"]
    cmap = sf["counterpartMap"]
    table = {c["code"]: c for c in sf["codeTable"]}
    dni = [x.strip() for x in N.t("contract.declaredNotImplemented.list").split(",")]
    wc = [x.strip() for x in N.t("contract.withCounterpart.list").split(",")]
    nc = [x.strip() for x in N.t("contract.noCounterpart.list").split(",")]
    sev = [x.strip() for x in N.t("contract.severityDiffers.list").split(",")]
    if sorted(cmap) != sorted(wc):
        raise SystemExit("counterpartMap differs from contract.withCounterpart.list")
    impl_for = {d: sorted(k for k, v in cmap.items() if v == d) for d in dni}
    if any(not v for v in impl_for.values()):
        raise SystemExit("a declared-but-not-implemented check has no renamed implementation")
    sev_txt = "；".join(f"`{c}`（发出 {'/'.join(table[c]['emittedSeverities'])}，契约 {'/'.join(table[c]['ruleJsonSeverity'])}）" for c in sev)
    strict = "；".join(f"{m} {N.t(f'contract.{s}.strict.depend')}/{N.t(f'contract.{s}.cleared')}" for m, s in MODELS)
    lenient = "；".join(f"{m} {N.t(f'contract.{s}.lenient.depend')}/{N.t(f'contract.{s}.cleared')}" for m, s in MODELS)
    strict_ids = "；".join(f"{m}: {N.t(f'contract.{s}.strict.dependIds')}" for m, s in MODELS)
    lenient_ids = "；".join(f"{m}: {N.t(f'contract.{s}.lenient.dependIds')}" for m, s in MODELS)
    rows = [
        ("声明的校验器检查（非 requiresGold）", N.t("contract.declared.n"), "各规则 `validationTarget.checks` 中不带 requiresGold 的 id"),
        ("仅评分的金标检查（requiresGold）", N.t("contract.goldOnly.n"), "校验器不运行，只在评分时计算"),
        ("实现的 code", N.t("contract.implemented.n"), "静态解析 detectors.py / validator.py 或在三个模型的校验报告中观测到"),
        ("声明但无同名实现", N.t("contract.declaredNotImplemented.n"),
         "；".join(f"`{d}`（改名实现为 {'、'.join('`' + x + '`' for x in impl_for[d])}）" for d in dni)),
        ("实现但未声明：改名对应", N.t("contract.withCounterpart.n"), "；".join(f"`{k}` → `{cmap[k]}`" for k in wc)),
        ("实现但未声明：无对应", N.t("contract.noCounterpart.n"), "、".join(f"`{k}`" for k in nc)),
        ("发出严重度与契约 JSON 不同", N.t("contract.severityDiffers.n"), sev_txt),
        ("严格反事实：被清除案例中依赖未声明检查", strict, strict_ids),
        ("宽松反事实（改名对应视为已声明）", lenient, lenient_ids),
    ]
    note = ("按 code 名称精确匹配契约声明与实现。改名对应是人工指定的对应关系（setup_facts.py 的 counterpartMap），即实现以不同名称覆盖了一个声明的检查。"
            "无对应的 6 个 code 中，四个需求级许可检查（`requirement_*_unlicensed`）是 2026-09-05 依据开发样板（C0 试点）迭代检测器时加入的（RECORDS.md）。"
            "被清除案例 = C2 落陷阱而 C4 未落的风险案例（分母即各模型的清除数）。"
            "严格反事实：只保留 code 属于声明集合的 finding，用冻结修复器对冻结 C2 产物重新修复，修复后仍落陷阱即记为依赖未声明检查；"
            "宽松反事实把改名对应视为已声明；两者都不模拟再生成"
            f"（受限校验器下仍为 BLOCK、本应触发再生成的案例：严格 {'/'.join(N.t(f'contract.{s}.strict.stillBlock') for _, s in MODELS)}，按三模型顺序）。"
            "校验器与检测器不读取契约文件的字段；二者的一致性由规则夹具与变异注入测试维护，而非由编译保证。")
    return write("tabA2_contract_coverage.md", ("项目", "数量", "明细"), rows, note)


def tabA3(N):
    N.table = "tabA3_validator.md"
    rows = []
    for m, s in MODELS:
        flags = []
        for c in ("C0", "C1", "C2", "C5"):
            if c == "C2":
                for side in ("flaggedRisk", "flaggedControl"):
                    if N.t(f"main.{s}.C2.{side}.kn") != N.t(f"main.{s}.C3.{side}.kn"):
                        raise SystemExit(f"{s}: C2 and C3 package flags differ")
                c = "C3"
            flags.append(f"{N.t(f'main.{s}.{c}.flaggedRisk.kn')}；{N.t(f'main.{s}.{c}.flaggedControl.kn')}")
        v = f"validator.{s}"
        rows.append((m, *flags, f"{N.t(v + '.item.trapFailed.kn')}（{N.t(v + '.item.trapFailed')}）",
                     f"{N.t(v + '.item.controlFailed.kn')}（{N.t(v + '.item.controlFailed')}）",
                     N.t(v + ".residual.n"), N.t(v + ".residual.c3Flagged.kn"), N.t(v + ".residual.c3TrapRuleFail.kn")))
    note = ("包级标记 = 校验器包级结论为 BLOCK 或 HUMAN_REVIEW 的案例数（每格「风险；对照」，分母各 72，不可解析计为标记）；BLOCK 当且仅当存在严重度为 critical 的 FAIL。"
            "C0、C1、C5 为生成后的离线校验；C2/C3 为同一批 C2 产物的校验（两者逐例相同）。"
            f"gpt-oss:20b 在 JSON 模式下的 schema 有效率低（C2 为 {N.t('main.gptoss.C2.schemaValid')}），schema 检查失败即为 critical FAIL，因此几乎全部被标记；包级标记不是检测指标。"
            "条目级（C2，主定义）：条目 = 评分器支持侧的每个条目；每个 FAIL finding 归到路径最深的包含它的条目；"
            "陷阱条目 = 文本含金标陷阱签名（非否定）的条目，召回 = 被任一规则 FAIL 的陷阱条目比例；"
            "对照代理 = 对照中含金标有效签名的条目被 FAIL 的比例，是条目级误报的上界代理（一个条目可能同时含有效主张与越界内容）。"
            f"被陷阱自身锚定规则 FAIL 的陷阱条目：{'；'.join(m + ' ' + N.t(f'validator.{s}.item.trapFailedOnTrapRule.kn') for m, s in MODELS)}。"
            "C4 残留事件 = C4 仍落陷阱的风险案例；修复前包级标记与「陷阱规则 FAIL」（金标锚定规则在报告中任一 FAIL）取自同一 C2 产物的 C3 报告。"
            f"残留事件的 C4 终版校验均为 ACCEPT（{'；'.join(m + ' ' + N.t(f'validator.{s}.residual.c4Accept.kn') for m, s in MODELS)}），"
            "这部分由修复后再校验的选择机制决定，只作描述；残留存在说明校验器与评分器判据不同，但二者共享否定与决策词表逻辑，独立性有限。")
    header = ("模型", "C0 包级标记（风险；对照）", "C1", "C2/C3", "C5", "条目级：C2 陷阱条目被 FAIL", "条目级：对照有效签名条目被 FAIL（误报上界代理）",
              "C4 残留事件数", "残留事件修复前包级标记", "残留事件修复前陷阱规则 FAIL")
    return write("tabA3_validator.md", header, rows, note)


def containing_token(context, sig):
    """The signature match widened to the surrounding word / number (e.g. 'to prod' -> 'to production', '5 years' -> '2.5 years')."""
    i = context.lower().find(sig.lower())
    if i < 0:
        raise SystemExit(f"artifact context does not contain {sig!r}")
    a, b = i, i + len(sig)
    while a > 0 and (context[a - 1].isalnum() or context[a - 1] in ".,"):
        a -= 1
    while b < len(context) and context[b].isalnum():
        b += 1
    return context[a:b]


def short_path(p):
    return p.replace("$.hiringEvidencePacket.", "").replace("$.optimizedCv.", "optimizedCv.")


def tabA4(N):
    N.table = "tabA4_example.md"
    N.source("example_case.py functions (dev_ids, select, trace_model) re-run on the frozen C2/C4 run files; selected case asserted equal to paper_numbers example.caseIdFull")
    N.source("setup_facts.json: contractCoverage.counterpartMap (renamed counterpart of the finding codes in the example)")
    import example_case as EX  # noqa: E402  (no import-time side effects beyond sys.path / hrgene import)
    from hrgene.rules import RuleSet  # noqa: E402
    rs = RuleSet(os.path.join(str(ROOT), "rules", "canonical-rules.v2.json"))
    gold = {g["caseId"]: g for g in (EX.load_json(f) for f in sorted(glob.glob(os.path.join(EX.BENCH, "gold", "*.json"))))}
    cid, models, tied, hist, status = EX.select(gold, EX.dev_ids())
    if cid != N.t("example.caseIdFull") or ", ".join(models) != N.t("example.models"):
        raise SystemExit("example_case selection differs from example_case.md / paper_numbers")
    case = EX.load_json(os.path.join(EX.BENCH, "cases", cid + ".json"))
    g = gold[cid]
    cmap = json.loads((HERE / "setup_facts.json").read_text(encoding="utf-8"))["contractCoverage"]["counterpartMap"]
    rows, codes, triggers, arts_all, reqs, genuine = [], set(), set(), [], [], {}
    for m, prefix in EX.MODELS:
        if m not in models:
            continue
        t = EX.trace_model(m, prefix, case, g, rs.lex)
        genuine[m] = t["c2"]["trapRequirementOverclaimed"] is True or any(
            set(it["signatures"]) - {a["signature"] for a in it["substringArtifacts"]} for it in t["items"])
        for it in t["items"]:
            art = {a["signature"] for a in it["substringArtifacts"]}
            sigs = "、".join(f"`{x}`" + ("（子串假象）" if x in art else "") for x in it["signatures"])
            for a in sorted(it["substringArtifacts"], key=lambda a: a["signature"]):
                x = (m, a["signature"], containing_token(a["context"], a["signature"]))
                if x not in arts_all:
                    arts_all.append(x)
            seen, fs = set(), []
            for f in it["findings"]:
                key = (f["rule"], f["code"], f["severity"], f["status"])
                if key not in seen:
                    seen.add(key)
                    fs.append(f"{f['rule']} / `{f['code']}`（{f['severity']}，{f['status']}）")
                    if f["status"] == "FAIL":
                        codes.add(f["code"])
            triggers.update(e["code"] for e in it["repairLog"])
            rep = "；".join(dict.fromkeys(f"`{e['action']}`（{e['code']}）" for e in it["repairLog"])) or "无"
            where = "、".join(short_path(p) for p in it["c4Locations"]) or "已删除"
            where += "（仍在支持侧）" if it["c4StillSupportedSide"] else "（不在支持侧）"
            rows.append((m, f"`{short_path(it['path'])}`：“{trunc(it['text'], 90)}”；签名 {sigs}", "；".join(fs) or "无", rep, where))
        reqs.append(f"{m}：" + "，".join(f"`{r['requirementId']}` {r['c2Status'] or 'absent'} → {r['c4Status'] or 'absent'}（金标 {r['goldStatus']}）" for r in t["requirements"])
                    + f"；包级结论 C2 {t['c2Aggregate']} → C4 {t['c4']['aggregate']}")
    renamed = sorted(c for c in codes if c in cmap)
    slug = dict(MODELS)
    sid = N.t("example.caseId")
    strict = [m for m in models if sid in N.t(f"contract.{slug[m]}.strict.dependIds")]
    lenient = [m for m in models if sid in N.t(f"contract.{slug[m]}.lenient.dependIds")]
    fam = dict((f, s) for _, f, s, _ in FAMS)[g["family"]]
    others = [m for m, _ in EX.MODELS if m not in models]
    note = (f"示例案例 `{N.t('example.caseId')}`（{fam}，锚定规则 `{g['trap']['rule'].split('.')[-1]}`）按固定规则选出（2026-09-23 修订）："
            f"排除 {N.t('sens.dev.n')} 个开发样板与决策族，在尽可能多的模型上 C2 落陷阱且 C4 清除（本例 {N.t('example.nModels')} 个模型；并列 {N.t('example.tied.n')} 例时按 caseId 取第一个）；"
            + (f"{'、'.join(others)} 在该例 C2 未落陷阱，未列入。" if others else "")
            + "表中每行是 C2 产物中含金标陷阱签名的一个支持侧条目（文本截断至 90 字符）；finding 为 C4 输入校验（即对冻结 C2 产物的校验）中落在该条目路径上或其内部的 finding，同一规则与 code 只列一次；"
            "修复动作为 C4 repairLog 在该路径上的条目；C4 位置为终版产物中文本相同（否则包含该文本）的字段。"
            + (f"「子串假象」：签名只作为非词边界子串出现（{'；'.join(f'{m} 的 `{x}` 只出现在 “{tok}” 中' for m, x, tok in arts_all)}），"
               "冻结评分器的逐字子串匹配仍计为命中，这是评分器假阳性的一种形态；"
               + ("同一产物中另有词边界上的签名命中，该模型的 C2 陷阱失败不依赖这些假象。" if all(genuine[m] for m, _, _ in arts_all)
                  else "、".join(sorted({m for m, _, _ in arts_all if not genuine[m]})) + " 的 C2 陷阱失败只由这些假象命中构成。") if arts_all else "")
            + (f"表中 FAIL 的 code 里，{'、'.join(f'`{c}` 是契约声明检查 `{cmap[c]}` 的改名实现' for c in renamed)}（见表 A2）；"
               f"本例的修复动作由 {'、'.join('`' + c + '`' for c in sorted(triggers))} 触发。" if renamed else "")
            + (f"在只保留声明 code 的严格反事实下，本例对 {'、'.join(strict)} 不再被清除；"
               + ("把改名对应视为已声明时仍被清除。" if not lenient else f"把改名对应视为已声明时对 {'、'.join(lenient)} 仍不被清除。") if strict else "")
            + "陷阱需求状态（C2 → C4）：" + "；".join(reqs) + "。")
    header = ("模型", "C2 中含签名的支持侧条目（截断）", "校验器 finding", "修复动作", "C4 位置")
    return write("tabA4_example.md", header, rows, note)


# ================================================================ English LaTeX tables (paper_tables/en/*.tex)
#
# Same numbers as the Chinese tables (paper_numbers.json text, never recomputed), typeset for the TMLR manuscript:
# booktabs rules, no vertical rules, ASCII only (LaTeX escapes for the Unicode minus, arrow and dash of the texts),
# \small or \footnotesize, natural width <= \textwidth = 6.5in. Each file holds one tabular (no table environment, no
# caption) and optionally one note paragraph "\par\smallskip{\footnotesize ...}"; tA_contract_json.tex holds the
# JSON excerpt of Table tA_contract as escaped \ttfamily paragraphs (no verbatim, safe in any context).
# Packages the manuscript must load: booktabs, array (p-columns with \raggedright\arraybackslash), amsmath not needed.

OUT_EN = HERE / "paper_tables" / "en"
TEX_CHARS = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
             "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "<": r"\textless{}",
             ">": r"\textgreater{}", "|": r"\textbar{}", "`": r"\textasciigrave{}",
             MINUS: "$-$", "→": r"$\to$", "–": "--", "—": "---", "…": r"\ldots{}",
             "‘": "`", "’": "'", "“": "``", "”": "''", " ": "~", "×": r"$\times$",
             "≥": r"$\ge$", "≤": r"$\le$"}
EN_FAMS = {  # slug -> (short English name, descriptive English name)
    "decision": ("Decision", "ranking, protected attributes and the human-review boundary"),
    "ownership": ("Ownership", "role-scope inflation"),
    "qualification": ("Qualification", "seniority and qualification mismatch"),
    "deployment": ("Deployment", "unsupported production deployment named in the job description"),
    "subjective": ("Subjective", "unsupported premise, follow-up and subjective rationale"),
    "quantification": ("Quantification", "unsupported quantification and causality"),
}
SRC_POLS = (("dropNoteCited", "drop_note_cited"), ("dropNoteOrUnsourced", "drop_note_or_unsourced"),
            ("dropNoteCitedX", "drop_note_cited+X"), ("dropNoteOrUnsourcedX", "drop_note_or_unsourced+X"))
ARROW_EN = {k: v.replace("→", r"$\to$") for k, v in ARROW.items()}


def tex(s):
    """Escape a plain string for LaTeX text mode; any non-ASCII character without a mapping is an error."""
    s, out = str(s), []
    for i, ch in enumerate(s):
        if ch in TEX_CHARS:
            out.append(TEX_CHARS[ch])
        elif ch == "-" and s[i + 1:i + 2] == "-":
            out.append("-{}")  # keep ASCII "--" in data from becoming an en dash
        elif ch == "'" and (i == 0 or s[i - 1] in " ([/"):
            out.append("`")  # opening single quote in prose (e.g. an artifact quoting a source)
        elif ord(ch) < 128:
            out.append(ch)
        else:
            raise SystemExit(f"no LaTeX mapping for {ch!r} (U+{ord(ch):04X}) in {s!r}")
    return "".join(out)


def tt(s):
    """Identifier in \\texttt with break points after underscores, dots and slashes."""
    body = tex(s).replace(r"\_", r"\_\allowbreak{}")
    body = re.sub(r"([./])", lambda m: m.group(1) + r"\allowbreak{}", body).replace("[", r"\allowbreak{}[")
    return r"\texttt{" + body + "}"


def pct(text):
    """'60.6%' -> '60.6' (the column header carries the unit)."""
    if not text.endswith("%"):
        raise SystemExit(f"not a percentage text: {text!r}")
    return text[:-1]


def ppn(text):
    """'−33.8 pp' -> '$-$33.8' (the column header carries the unit)."""
    if not text.endswith(" pp"):
        raise SystemExit(f"not a pp text: {text!r}")
    return tex(text[:-3])


def pval(text):
    """'8.4e-06' -> '$8.4\\times10^{-6}$'; '0.503' stays."""
    m = re.fullmatch(r"(\d\.\d)e-0*(\d+)", text)
    if m:
        return "$" + m.group(1) + r"\times10^{-" + m.group(2) + "}$"
    if not re.fullmatch(r"\d\.\d{3}", text):
        raise SystemExit(f"unexpected p-value text {text!r}")
    return text


def stack(a, b):
    """Two-line centred cell (point estimate over interval)."""
    return r"\begin{tabular}[c]{@{}c@{}}" + a + r"\\ {" + b + r"}\end{tabular}"


def hstack(*lines):
    """Multi-line column header (bottom-aligned); '\\\\ {}' keeps a following '[' from being read as an option."""
    return r"\begin{tabular}[b]{@{}c@{}}" + r"\\ {}".join(lines) + r"\end{tabular}"


def trunc_en(s, n):
    s = " ".join(str(s).split())
    return tex(s) if len(s) <= n else tex(s[:n].rstrip()) + r"\ldots{}"


def quote_en(s, n=60):
    return "``" + trunc_en(s, n) + "''"


def P(width):
    """Ragged-right paragraph column (needs the array package)."""
    return r">{\raggedright\arraybackslash}p{" + width + "}"


def trow(*cells):
    return " & ".join(cells) + r" \\"


def plural(n, word):
    return f"{n} {word}" + ("" if int(n) == 1 else "s")


def write_tex(name, colspec, body, note=None, size=r"\small", sep=None):
    """One tabular (+ optional note paragraph) -> paper_tables/en/<name>; ASCII only."""
    L = [f"% {name}: generated by analysis/paper_tables.py from analysis/paper_numbers.json; do not edit by hand.",
         "% One tabular plus an optional note; needs booktabs and array. The caption is written in the manuscript.",
         "{" + size + (r"\setlength{\tabcolsep}{" + sep + "}" if sep else ""),
         r"\begin{tabular}{" + colspec + "}"] + body + [r"\end{tabular}}"]
    if note:
        L.append(r"\par\smallskip{\footnotesize\raggedright\textit{Note.} " + note + r"\par}")
    text = "\n".join(L) + "\n"
    bad = sorted({c for c in text if ord(c) > 127})
    if bad:
        raise SystemExit(f"{name}: non-ASCII characters {bad}")
    (OUT_EN / name).write_text(text, encoding="ascii")
    return name


def en_models_header(first):
    return trow(first, *(tex(m) for m, _ in MODELS))


# ---------------------------------------------------------------- main-text tables

def en_tmain_trap(N):
    name = "tmain_trap.tex"
    N.table = "en/" + name
    conds = ("C0", "C1", "C2", "C4", "C5")
    body = [r"\toprule",
            trow("", r"\multicolumn{5}{c}{Trap-failure rate, \% (k/n) [95\% CI]}", r"Clearance, \%"),
            r"\cmidrule(lr){2-6}\cmidrule(lr){7-7}",
            trow("Model", *conds, r"C2$\to$C4"),
            r"\midrule"]
    for i, (m, s) in enumerate(MODELS):
        for f in ("trap.kn", "trap.ci"):
            if N.t(f"main.{s}.C3.{f}") != N.t(f"main.{s}.C2.{f}"):
                raise SystemExit(f"{s}: C3 and C2 trap-failure rates differ")
        cells = []
        for c in conds:
            k = f"main.{s}.{c}.trap"
            cells.append(stack(f"{pct(N.t(k))} ({N.t(k + '.kn')})", tex(N.t(k + ".ci"))))
        k = f"clear.{s}.C2toC4"
        cells.append(stack(f"{pct(N.t(k))} ({N.t(k + '.kn')})", tex(N.t(k + ".ci"))))
        body.append(trow(tex(m), *cells))
        if i < len(MODELS) - 1:
            body.append(r"\addlinespace")
    body.append(r"\bottomrule")
    note = ("C3 is omitted: it scores the same artifacts as C2 and has the same rates. Trap-failure rate: share of "
            r"parseable risk cases in which the frozen scorer records a gold trap failure (\texttt{trapFellAny}); "
            r"k/n = failures / parseable risk cases; brackets: Wilson 95\% CI \citep{wilson1927probable}. "
            "Clearance: among risk cases that fail under C2 and are parseable under both C2 and C4, the share that no "
            "longer fails under C4. C0: no rules (JSON mode); C1: prose-rules prompt; C2: contract prompt; C4: the "
            "frozen C2 artifacts after validation and bounded repair (one repair pass, at most one regeneration); "
            "C5: schema-constrained decoding, no rules.")
    return write_tex(name, "lcccccc", body, note, size=r"\small")


def en_contrast_row(N, label, key, name):
    n, b, c = N.t(key + ".n"), N.t(key + ".b"), N.t(key + ".c")
    if int(N.v(key + ".discordant")) == 0:
        if N.v(key + ".diff") != 0 or b != "0" or c != "0":
            raise SystemExit(f"{key}: zero discordant pairs but nonzero flips or difference")
        diff = "0 discordant pairs"
    elif key.startswith("contrast.pooled."):
        diff = ppn(N.t(key + ".diff"))
    else:
        diff = ppn(N.t(key + ".diff")) + " " + tex(N.t(key + ".diff.ci"))
    p = "--" if key.startswith("contrast.pooled.") else pval(N.t(key + ".p"))
    return trow(label, name, n, f"{b}/{c}", diff, p)


def en_contrast_body(N, contrasts, pooled_contrasts, clearance=False):
    body = [r"\toprule",
            trow("Model", "Contrast", "$n$", "Out/in", r"Difference, pp [95\% CI]", "$p$"),
            r"\midrule"]
    for m, s in MODELS:
        for i, ab in enumerate(contrasts):
            body.append(en_contrast_row(N, tex(m) if i == 0 else "", f"contrast.{s}.{ab}", ARROW_EN[ab]))
        body.append(r"\midrule")
    if pooled_contrasts:
        body.append(trow(r"\multicolumn{6}{l}{\textit{Pooled over the three models (descriptive point estimates only)}}"))
    for i, ab in enumerate(pooled_contrasts):
        body.append(en_contrast_row(N, "Pooled" if i == 0 else "", f"contrast.pooled.{ab}", ARROW_EN[ab]))
    if clearance:
        body += [r"\midrule",
                 trow(r"\multicolumn{6}{l}{\textit{C2$\to$C4 clearance: $n$ = C2 trap failures (paired); "
                      r"cleared k/n, \% [Wilson 95\% CI]}}")]
        for m, s in MODELS + (("Pooled (descriptive)", "pooled"),):
            k = f"clear.{s}.C2toC4"
            rate = pct(N.t(k))
            if s != "pooled":
                rate += " " + tex(N.t(k + ".ci"))
            body.append(trow(tex(m), r"C2$\to$C4", N.t(k + ".n"), N.t(k + ".kn"), rate, "--"))
    body.append(r"\bottomrule")
    return body


def en_contrast_note(N, full):
    for _, s in MODELS:
        if N.t(f"contrast.{s}.C2toC4.c") != "0":
            raise SystemExit(f"{s}: C2->C4 adds trap failures; the note on c = 0 needs revising")
    if N.t("contrast.signIdentityIntoC4.holds") != "true":
        raise SystemExit("sign-test identity for contrasts into C4 not confirmed")
    note = ("Risk cases parseable under both conditions ($n$). Out: trap failure under the first condition only ($b$); "
            "in: under the second condition only ($c$). Difference $=(c-b)/n$, the second condition's trap-failure rate "
            "minus the first's, in percentage points, with the Newcombe method-10 95\\% CI for paired proportions "
            r"\citep{newcombe1998improved}; $p$: exact two-sided McNemar test \citep{mcnemar1947note}. When $c=0$ the "
            r"exact test reduces to a sign test on the $b$ discordant pairs, $p=2\cdot0.5^{b}$, a function of $b$ alone. "
            "C2$\\to$C4 adds no failure ($c=0$) mainly by design: repair adds no text to the supported side and never "
            "upgrades a requirement status; the other paths that could add one (subjective-family downgrade, "
            "requirement deduplication, regeneration) added none in these data. "
            f"qwen3:30b-a3b has no discordant C0$\\to$C5 pair (0/{N.t('contrast.q30b.C0toC5.n')}), so no interval is "
            "reported. Intervals and tests are pointwise, without multiplicity adjustment. "
            "C1 and C2 differ in wording, fields, the validator header sentence "
            "and length, so C1$\\to$C2 does not isolate the representation of the rules.")
    if full:
        note += (" Clearance rows: $n$ = paired risk cases that fail under C2; k = those no longer failing under C4; "
                 r"Wilson 95\% CI for per-model estimates. Pooled rows repeat each case across models, so only "
                 "counts and point estimates are reported, without intervals or tests.")
    return note


def en_tmain_contrasts(N):
    name = "tmain_contrasts.tex"
    N.table = "en/" + name
    ab = ("C0toC2", "C1toC2", "C0toC5", "C2toC4")
    return write_tex(name, "llrcll", en_contrast_body(N, ab, ()), en_contrast_note(N, False), size=r"\small")


def best_src_policy(N, s):
    """Lowest trap-failure rate among the four source-type policies (ties must agree on retention and routing)."""
    f = f"frontier.{s}"
    best = min(N.v(f"{f}.{p}.trap") for p, _ in SRC_POLS)
    win = [(p, lab) for p, lab in SRC_POLS if N.v(f"{f}.{p}.trap") == best]
    sig = {(N.t(f"{f}.{p}.trap"), N.t(f"{f}.{p}.kept"), N.t(f"{f}.{p}.trapRouted")) for p, _ in win}
    if len(sig) != 1:
        raise SystemExit(f"{s}: tied source-type policies differ in retention or routing: {win}")
    if [lab for _, lab in win] == ["drop_note_cited+X", "drop_note_or_unsourced+X"]:
        label = "both +X variants, identical"
    else:
        label = " = ".join(tt(lab) for _, lab in win)
    return win[0][0], label


def en_tmain_cost_baselines(N):
    name = "tmain_cost_baselines.tex"
    N.table = "en/" + name
    for p, _ in SRC_POLS:
        for _, s in MODELS:
            if N.t(f"frontier.{s}.{p}.bothC4") != "false":
                raise SystemExit(f"{s} {p}: a source-type policy reaches both C4 retention and routing; revise the table")
    kd, sup, chg, c4, nd, grid, both, best, bkept, brouted, pboth = ([] for _ in range(11))
    for m, s in MODELS:
        k = f"cost.{s}.C2toC4.keptDiff"
        if N.has(k + ".full"):
            kd.append(ppn(N.t(k)) + " " + tex(N.t(k + ".ci")))
        else:
            if N.t(f"cost.{s}.controls.keptChanged") != "0" or N.v(k) != 0:
                raise SystemExit(f"{s}: retention difference without interval although controls changed")
            kd.append(f"no change (all {N.t(k + '.n')} paired differences 0)")
        sup.append(f"{N.t(f'cost.{s}.supported.all144.c2')} $\\to$ {N.t(f'cost.{s}.supported.all144.c4')}")
        chg.append(N.t(f"cost.{s}.controls.relabeledOrRemoved.kn"))
        f = f"frontier.{s}"
        c4.append(f"{pct(N.t(f + '.C4.trap'))} / {pct(N.t(f + '.C4.kept'))}")
        gap = int(N.v(f + ".nd.gap"))
        if gap > 2:
            nd.append(f"{pct(N.t(f + '.nd.C4.trap'))} vs.\\ {pct(N.t(f + '.nd.S.attrition'))}")
        else:
            nd.append(f"not compared (C2 {N.t(f + '.nd.C2.trap.kn')}, C4 {N.t(f + '.nd.C4.trap.kn')})")
        grid.append(f"{pct(N.t(f + '.grid.keptOnly.trap'))} ({pct(N.t(f + '.grid.keptOnly.kept'))})")
        both.append(N.t(f + ".grid.both.kn"))
        p, label = best_src_policy(N, s)
        best.append(f"{pct(N.t(f'{f}.{p}.trap'))} ({label})")
        bkept.append(f"{pct(N.t(f'{f}.{p}.kept'))} ({pct(N.t(f + '.C4.kept'))})")
        brouted.append(f"{pct(N.t(f'{f}.{p}.trapRouted'))} ({pct(N.t(f + '.C4.trapRouted'))})")
        pboth.append(N.t(f + ".srcPolicies.both.kn"))
    ncol = str(len(MODELS) + 1)
    body = [r"\toprule", en_models_header(""), r"\midrule",
            trow(r"\multicolumn{" + ncol + r"}{l}{\textit{Cost on matched clean controls, C2$\to$C4}}"),
            trow(r"Retention difference, pp [95\% CI]", *kd),
            trow("Controls with supported-side items relabeled, moved or deleted", *chg),
            trow(r"Supported-side items per case (C2 $\to$ C4)", *sup),
            r"\midrule",
            trow(r"\multicolumn{" + ncol + r"}{l}{\textit{Content-blind and source-type baselines (post hoc), "
                 r"trap-failure rate and retention in \%}}"),
            trow("C4: trap-failure rate / retention", *c4),
            trow("Non-decision families: C4 vs.\\ content-blind S at C4's attrition", *nd),
            trow(r"S$\times$R$\times$X grid: lowest trap-failure rate with retention $\ge$ C4 (its retention)", *grid),
            trow(r"Grid configurations with retention and trap routing both $\ge$ C4", *both),
            trow("Best source-type policy: trap-failure rate", *best),
            trow(r"\quad its retention (C4)", *bkept),
            trow(r"\quad its trap routing rate (C4)", *brouted),
            trow(r"Source-type policies with retention and trap routing both $\ge$ C4", *pboth),
            r"\bottomrule"]
    note = ("Retention: per matched clean control, the share of gold valid-claim signatures that appear anywhere on the "
            "supported side (a lenient metric), averaged over controls; the difference is C4 minus C2 on controls "
            f"parseable under both, with a case-level bootstrap 95\\% CI (B = {N.t('stats.bootstrap.B')}) "
            r"\citep{efron1979bootstrap}. For qwen3:30b-a3b every paired difference is 0, so no interval is reported, "
            f"although {N.t('cost.q30b.controls.relabeledOrRemoved.kn')} of its controls had supported-side items "
            "changed. Supported-side items: mean per case over all "
            f"{N.t('bench.cases.n')} cases (unparseable artifacts count as 0). The baselines are post hoc and "
            "exploratory: they transform the frozen C2 artifacts and rescore them with the frozen scorer (S and the grid: "
            f"means over seeds {N.t('frontier.design.seeds')}); the readouts hold for this grid and these seeds only. "
            "S relabels or deletes a fraction of supported-side items chosen by position and seed only; "
            "``at C4's attrition'' interpolates the S curve at C4's supported items per case. Non-decision families: "
            f"the five families other than decision ({N.t('frontier.gptoss.nd.controlN')} risk and "
            f"{N.t('frontier.gptoss.nd.controlN')} control cases); for qwen3:30b-a3b, C2 and C4 differ there by "
            f"{N.t('frontier.q30b.nd.gap')} cases only. Grid: {N.t('frontier.gptoss.grid.nConfigs')} configurations "
            "per model of S, R (downgrade of supported requirements) and X (reset of decision-boundary fields and "
            "deletion of interview-signal risks, checklist and limitation items). Source-type policies "
            f"({N.t('frontier.design.sourcePolicies.n')}; designed after it was known that all bait sources are notes) "
            "move supported-side items that cite a note (and, in two of them, items without a source ID), optionally "
            "followed by X with $r=1$; they read only source types and item source IDs and are not content-blind. "
            "Best policy: lowest trap-failure rate among the four.")
    return write_tex(name, P("5.2cm") + P("3.3cm") * 3, body, note, size=r"\small", sep="4pt")


# ---------------------------------------------------------------- appendix tables

def read_contract_excerpt(N):
    """The rule excerpt of tab1_contract.md exactly as tab01 reads it: (rule dict, excerpt text, implemented codes)."""
    md = (HERE / "tab1_contract.md").read_text(encoding="utf-8")
    m = re.search(r"```json\n(.*?)\n```", md, flags=re.S)
    if not m:
        raise SystemExit("tab1_contract.md: json block not found")
    rule = json.loads(m.group(1))
    if rule["ruleId"] != N.t("example.contract.rule"):
        raise SystemExit("tab1_contract.md ruleId differs from paper_numbers example.contract.rule")
    impl = re.search(r"Implemented codes for this rule: (.*?) \(codes not in", md)
    impl_codes = re.findall(r"`([a-z_]+)`", impl.group(1)) if impl else []
    excerpt = re.sub(r', "_annotation": "[^"]*"', "", m.group(1))
    for c in rule["validationTarget"]["checks"]:
        c.pop("_annotation", None)
    if json.loads(excerpt) != rule:
        raise SystemExit("contract excerpt: removing _annotation changed more than that key")
    return rule, excerpt, impl_codes


def en_tA_benchmark(N):
    name = "tA_benchmark.tex"
    N.table = "en/" + name
    N.source("benchmark/v4/gold/*.json (read only): family -> gold.trap.rule mapping and the families of the anywhereSignatures cases")
    fam_rule, any_fams = {}, {}
    for f in sorted(glob.glob(str(ROOT / "benchmark" / "v4" / "gold" / "*.json"))):
        g = json.loads(Path(f).read_text(encoding="utf-8"))
        if g["controlStatus"] == "positive_risk":
            fam_rule.setdefault(g["family"], set()).add(g["trap"]["rule"])
            if (g.get("trap") or {}).get("anywhereSignatures"):
                any_fams[g["family"]] = any_fams.get(g["family"], 0) + 1
    body = [r"\toprule", trow("Stress family (gold family identifier)", "Risk", "Control", "Anchoring rule"), r"\midrule"]
    for slug, fam, _, _ in FAMS:
        rules = fam_rule[fam]
        if len(rules) != 1:
            raise SystemExit(f"{fam}: several anchoring rules {rules}")
        rule = sorted(rules)[0].split(".")[-1]
        if int(N.t(f"bench.trapRule.{rule}.n")) != int(N.t(f"bench.family.{slug}.risk.n")) or N.t(f"bench.family.{slug}.name") != fam:
            raise SystemExit(f"{fam}: benchmark table inconsistent with paper_numbers")
        short, desc = EN_FAMS[slug]
        body.append(trow(f"{short}: {tex(desc)}\\newline {{\\footnotesize {tt(fam)}}}", N.t(f"bench.family.{slug}.risk.n"),
                         N.t(f"bench.family.{slug}.control.n"), tt(rule)))
    body += [r"\midrule", trow("Total", N.t("bench.risk.n"), N.t("bench.control.n"), f"one rule per family ({N.t('bench.families.n')})"),
             r"\bottomrule"]
    n_any = int(N.t("bench.anywhereCases.n"))
    if sum(any_fams.values()) != n_any:
        raise SystemExit("anywhereSignatures case count differs from tab2_benchmark.json")
    fam_slug = {f: s for s, f, _, _ in FAMS}
    any_where = "; ".join(f"{EN_FAMS[fam_slug[f]][0].lower()} family {k}" for f, k in sorted(any_fams.items()))
    note = (f"{N.t('bench.cases.n')} cases ({N.t('bench.risk.n')} risk cases and {N.t('bench.control.n')} matched clean "
            f"controls in {N.t('bench.families.n')} stress families). Each case has "
            f"{N.t('bench.perCase.requirements')} job requirements, {N.t('bench.perCase.propositions')} gold propositions "
            f"and {N.t('bench.perCase.evidence')} evidence sources. A risk case's trap is anchored by signature phrases "
            r"absent from non-bait evidence sources (gold \texttt{trap.signatures}) and by the gold status of the trap "
            "requirement; a matched clean control has no trap, and its gold lists valid-claim signatures "
            r"(\texttt{validClaimSignatures}) used to measure retention. "
            f"{n_any} cases carry \\texttt{{anywhereSignatures}} (protected-attribute phrases that count as a trap failure "
            f"in any text field of the artifact), all of them risk cases ({any_where}). Anchoring rule: gold "
            r"\texttt{trap.rule}, the rule contract that the family's trap targets. Benchmark and gold were frozen on "
            f"2026-09-06 before generation (cases+gold digest \\texttt{{{N.t('bench.freeze.casesGold.short')}}}\\ldots, "
            f"rules-file digest \\texttt{{{N.t('bench.freeze.rules.short')}}}\\ldots).")
    return write_tex(name, P("8.6cm") + "rrl", body, note, size=r"\small")


def en_tA_contract(N):
    name = "tA_contract.tex"
    N.table = "en/" + name
    N.source("tab1_contract.md: ```json contract excerpt (field values; `_annotation` dropped) and 'Implemented codes' line")
    rule, _, impl_codes = read_contract_excerpt(N)
    never = [x.strip() for x in N.t("contract.keysNeverRead.list").split(",")]
    if sorted(never) != ["maxRegenerations", "provenance", "repair"] or N.t("contract.detectorsReadRuleSeverity") != "false":
        raise SystemExit("setup_facts: contract keys read at run time changed; tA_contract wording needs revising")
    ob, vt, hd, act = rule["obligation"], rule["validationTarget"], rule["handling"], rule["activation"]
    declared = [c["id"] for c in vt["checks"] if not c.get("requiresGold")]
    gold_only = [c["id"] for c in vt["checks"] if c.get("requiresGold")]
    words = (N.t("example.contract.words.prose"), N.t("example.contract.words.duty"), N.t("example.contract.words.block"))
    rows = [
        (tt("ruleId"), f"Rule identifier; the validator registers one hand-written detector per ruleId ({N.t('contract.detectors.n')} in total)", tt(rule["ruleId"])),
        (tt("title") + " / " + tt("version") + " / " + tt("kind"), "Name, version and rule type (descriptive metadata)",
         f"{tex(rule['title'])} / {tex(rule['version'])} / {tt(rule['kind'])}"),
        (tt("severity"), "Rule-level severity, rendered as the severity field of the C2 contract block; the severity of a "
         "finding is fixed in detector code, which does not read this field", tex(rule["severity"])),
        (tt("activation"), "Activation condition; rules.py uses it to decide whether the rule is rendered for a case (C1, C2)",
         f"{tt(act['type'])}; scopes {', '.join(tt(x) for x in act['scopes'])}; predicates {', '.join(tt(x) for x in act['predicates'])}"),
        (tt("obligation.prose"), "Full text of the C1 prose rule", f"{words[0]} words: " + quote_en(ob["prose"])),
        (tt("obligation.mustDo"), "The must items of the C2 contract block",
         plural(len(ob["mustDo"]), "item") + (", e.g., " if len(ob["mustDo"]) > 1 else ": ") + quote_en(ob["mustDo"][0])),
        (tt("obligation.mustNot"), "The mustNot items of the C2 contract block",
         plural(len(ob["mustNot"]), "item") + (", e.g., " if len(ob["mustNot"]) > 1 else ": ") + quote_en(ob["mustNot"][0])),
        (tt("obligation.route"), "The route of the C2 contract block: where content goes when the evidence is insufficient", quote_en(ob["route"])),
        (tt("validationTarget.reads"), "Artifact fields read by the declared checks",
         plural(len(vt["reads"]), "path") + " (optimizedCv, supportedClaims, requirement evidence text)"),
        (tt("validationTarget.checks"), "Declared checks; ids without requiresGold are rendered as checkedBy in C2; "
         "requiresGold checks are computed only when scoring",
         "; ".join(tt(c) for c in declared) + "; " + "; ".join(tt(c) + " (requiresGold, scoring only)" for c in gold_only)),
        (tt("validationTarget.witness"), "Evidence a finding should record", quote_en(vt["witness"])),
        (tt("handling.onFail"), "Handling level, rendered as onViolation in the C2 contract block", tex(hd["onFail"])),
        (tt("handling.repair"), "Declared repair action; not read at run time (the repairer is hand-written per rule)",
         "; ".join(tt(r["action"]) for r in hd["repair"]) + " (with reason and requiredFollowUp)"),
        (tt("handling.maxRegenerations"), "Declared regeneration limit; not read at run time (the pipeline hard-codes at most one regeneration)",
         str(hd["maxRegenerations"])),
        (tt("provenance"), "Origin of the rule; not read at run time",
         plural(len(rule["provenance"]), "entry").replace("entrys", "entries") + ": " + " / ".join(tt(x) for x in rule["provenance"])),
    ]
    body = [r"\toprule", trow("Field", "Meaning", "Value in this rule (abridged)"), r"\midrule"] + [trow(*r) for r in rows] + [r"\bottomrule"]
    note = (f"The contract is the {tt(rule['ruleId'])} entry of {tt('rules/canonical-rules.v2.json')}; its full text is "
            r"listed separately (the \texttt{\_annotation} keys added by the analysis script are dropped). Word counts "
            f"split on white space: prose obligation {words[0]} words; mustDo + mustNot + route {words[1]} words; the whole "
            f"rendered C2 block of this rule {words[2]} words (including severity, applies, checkedBy and onViolation; "
            f"rendered for case {tt(N.t('example.contract.caseId'))}). ``Not read at run time'': no code in "
            f"{tt('runtime/hrgene/*.py')} reads the key ({', '.join(tt(x) for x in never)}); the contract file is read only "
            "by rules.py, for activation and prompt rendering, and detectors.py and validator.py read no contract field. "
            f"This rule declares the validator check {', '.join(tt(c) for c in declared)}; the validator can emit the codes "
            f"{', '.join(tt(c) for c in impl_codes)} (undeclared codes are checks added in the implementation; the "
            "contract-coverage table lists the differences for all rules).")
    return write_tex(name, P("3.2cm") + P("6.0cm") + P("5.9cm"), body, note, size=r"\footnotesize", sep="4pt")


def en_tA_contract_json(N):
    """The rule excerpt as escaped \\ttfamily paragraphs with hanging indentation (wraps long strings; no verbatim)."""
    name = "tA_contract_json.tex"
    N.table = "en/" + name
    N.source("tab1_contract.md: ```json contract excerpt (`_annotation` dropped), printed line by line")
    _, excerpt, _ = read_contract_excerpt(N)
    L = [f"% {name}: generated by analysis/paper_tables.py from analysis/tab1_contract.md; do not edit by hand.",
         "% JSON text of the rule in tA_contract.tex as escaped typewriter paragraphs (long strings wrap with a hanging",
         "% indent). No verbatim, so it can sit in any environment; place it in a figure or table float or in the text.",
         r"{\footnotesize\ttfamily\raggedright\frenchspacing"]
    for line in excerpt.split("\n"):
        ind = len(line) - len(line.lstrip(" "))
        text = r"\textquotesingle{}".join(tex(part) for part in line.lstrip(" ").split("'"))  # straight quotes as in the file
        L.append(r"\hangindent=" + f"{ind + 2}em" + r"\hangafter=1\noindent\hspace*{" + f"{ind}em" + "}" + text + r"\par")
    L.append("}")
    text = "\n".join(L) + "\n"
    if any(ord(c) > 127 for c in text):
        raise SystemExit(f"{name}: non-ASCII characters")
    (OUT_EN / name).write_text(text, encoding="ascii")
    return name


def en_tA_models(N):
    name = "tA_models.tex"
    N.table = "en/" + name
    body = [r"\toprule", trow("Model", "Quantization", "Parameters", "Digest", "think", "Ollama"), r"\midrule"]
    for m, s in MODELS:
        if N.t(f"setup.{s}.tag") != m:
            raise SystemExit(f"{m}: tag mismatch")
        for key in ("temperature", "seed", "numCtx", "numPredict", "repeat"):
            if N.t(f"setup.{s}.{key}") != N.t(f"setup.all.{key}"):  # setup.all.* is registered only when identical
                raise SystemExit(f"{m}: decoding parameter {key} differs from the other models")
        body.append(trow(tex(m), tex(N.t(f"setup.{s}.quant")), tex(N.t(f"setup.{s}.params")), tt(N.t(f"setup.{s}.digest12")),
                         tt(N.t(f"setup.{s}.think")), tex(N.t(f"setup.{s}.ollama"))))
    body.append(r"\bottomrule")
    A = "setup.all."
    note = (f"All models: temperature {N.t(A + 'temperature')}, seed {N.t(A + 'seed')}, {tt('num_ctx')} "
            f"{N.t(A + 'numCtx')}, {tt('num_predict')} {N.t(A + 'numPredict')}, {N.t(A + 'repeat')} generation per case "
            "and condition. Digest: first 12 hexadecimal digits of the model digest reported by Ollama; digest, model name and seed are "
            "identical across all outputs of each model in C0, C1, C2 and C5 (and gpt-oss:20b's C4 regeneration), e.g., "
            f"gpt-oss:20b C2: {N.t('setup.gptoss.outputs.C2.kn')} outputs, {N.t('setup.gptoss.outputs.C2.mismatches')} "
            f"mismatches. think: Ollama's reasoning switch ({tt(N.t('setup.gptoss.think'))} for gpt-oss:20b, "
            f"{tt(N.t('setup.q8b.think'))} for both qwen models), a configuration difference between the models. "
            "Decoding parameters are set in the request options and override the model files' default sampling "
            f"parameters (gpt-oss:20b: {tt(N.t('setup.gptoss.modelfileParameters'))}; qwen: "
            f"{tt(N.t('setup.q8b.modelfileParameters'))}). Hardware: {tex(N.t('setup.hw.machine'))} "
            f"({tex(N.t('setup.hw.chip'))}, {tex(N.t('setup.hw.memory'))}), Ollama {tex(N.t('setup.ollama'))}.")
    return write_tex(name, "llrlll", body, note, size=r"\small")


def en_tA_detector(N):
    name = "tA_detector.tex"
    N.table = "en/" + name
    body = [r"\toprule", trow("Rule", "Mutants", "P", "R"), r"\midrule"]
    total = 0
    for r in RULE_ORDER:
        body.append(trow(tt(r), N.t(f"detector.{r}.mutants"), N.t(f"detector.{r}.precision"), N.t(f"detector.{r}.recall")))
        total += int(N.t(f"detector.{r}.mutants"))
    if total != int(N.t("detector.mutants.n")) or len(RULE_ORDER) != int(N.t("detector.rules.n")):
        raise SystemExit("detector totals differ")
    if N.t("detector.rulesetDigest") != N.t("bench.freeze.rules")[:12]:
        raise SystemExit("detector_pr.json ruleset digest differs from the frozen rules digest")
    body += [r"\midrule", trow("Total / minimum", N.t("detector.mutants.n"), N.t("detector.precision.min"), N.t("detector.recall.min")),
             r"\bottomrule"]
    note = ("Mutants: variants produced by mutation injection that violate the rule by construction (tp + fn); R: share of "
            "them on which the rule fires; false positives for P count firings on clean oracle artifacts, near-miss "
            "legitimate edits and mutants that do not violate the rule. The mutants are built from the validator's own "
            "lexicons and rules, so this is an implementation self-consistency check: it shows that the detectors "
            "implement their design intent, not precision or recall on real model outputs (precision on real outputs "
            f"cannot be estimated in this study). False-alarm checks: {N.t('detector.cleanOracles.kn')} of "
            f"{N.t('detector.cleanOracles.n')} clean oracle artifacts flagged; {N.t('detector.nearMisses.kn')} of "
            f"{N.t('detector.nearMisses.n')} near-miss edits flagged (verbatim quotes of a source, numbers taken from a "
            "source, negated ownership wording, gaps that mention production deployment, negated decision checklists, "
            f"etc.). The rules digest used for mutation ({tt(N.t('detector.rulesetDigest'))}\\ldots) equals the frozen "
            "rules-file digest.")
    return write_tex(name, "lrrr", body, note, size=r"\small")


def en_tA_main_full(N):
    name = "tA_main_full.tex"
    N.table = "en/" + name
    body = [r"\toprule",
            trow("", "", "", "", "", "", "", r"\multicolumn{2}{c}{Bundle flags}"),
            r"\cmidrule(lr){8-9}",
            trow("Model", "Cond.", "Parsed", hstack("Schema", "valid"), hstack("Trap-failure rate", r"[95\% CI] (k/n)"),
                 hstack("Trap", "routing"), "Retention", "Risk", "Control"),
            r"\midrule"]
    res = set()
    for i, (m, s) in enumerate(MODELS):
        for j, c in enumerate(CONDS):
            k = f"main.{s}.{c}"
            if c == "C4":
                res.add((N.t(k + ".residual"), N.t(k + ".schemaValid")))
                schema = "--"
            else:
                schema = pct(N.t(k + ".schemaValid"))
            body.append(trow(tex(m) if j == 0 else "", c, pct(N.t(k + ".parsed")), schema,
                             f"{pct(N.t(k + '.trap'))} {tex(N.t(k + '.trap.ci'))} ({N.t(k + '.trap.kn')})",
                             pct(N.t(k + ".trapRouted")), pct(N.t(k + ".kept")), N.t(k + ".flaggedRisk.kn"), N.t(k + ".flaggedControl.kn")))
        body.append(r"\midrule" if i < len(MODELS) - 1 else r"\bottomrule")
    if len(res) != 1:
        raise SystemExit(f"C4 residual / schema validity differ across models: {res}")
    resid, schema4 = res.pop()
    note = (r"All rates in \%. Parsed and schema valid: share of all "
            f"{N.t('bench.cases.n')} cases (an unparseable artifact counts as invalid). Trap-failure rate: share of "
            r"parseable risk cases with a gold trap failure (\texttt{trapFellAny}: a trap signature on the supported side, "
            "a trap requirement marked supported against the gold status, or a family-specific extra rule of the decision "
            r"and subjective families), Wilson 95\% CI, k/n in parentheses. Trap routing: share of parseable risk cases in "
            "which the trap did not fire and was routed (decision family: no trap failure; subjective family: every gold "
            r"subjective source appears in \texttt{interviewSignalRisks}; other families: the trap requirement appears in "
            r"\texttt{missingEvidenceGaps} or \texttt{followUpQuestions}, or a trap signature appears in "
            r"\texttt{unsupportedClaims}). Retention: mean over parseable matched controls of the share of gold valid-claim "
            "signatures that appear anywhere on the supported side (lenient). Bundle flags: cases whose bundle-level "
            f"validator verdict is BLOCK or HUMAN\\_REVIEW, out of {N.t('bench.risk.n')} risk cases or {N.t('bench.control.n')} controls (unparseable counts as "
            "flagged); for C0, C1, C2 and C5 this is an offline validation after generation, not an intervention; bundle "
            "flags are not a detection metric. C3 = the C2 artifacts plus a validation report, so its artifact metrics "
            "equal C2's. C4 = deterministic post-processing of the frozen C2 artifacts (validation, one repair pass, at "
            f"most one regeneration); its residual critical-violation rate ({pct(resid)}\\%) and schema validity "
            f"({pct(schema4)}\\%) follow from all final artifacts being non-BLOCK in these runs and are shown as --.")
    return write_tex(name, "llrrlrrrr", body, note, size=r"\small", sep="4pt")


def en_tA_contrasts_full(N):
    name = "tA_contrasts_full.tex"
    N.table = "en/" + name
    body = en_contrast_body(N, ("C0toC1", "C0toC2", "C1toC2", "C0toC5", "C2toC4", "C0toC4"),
                            ("C0toC2", "C1toC2", "C0toC5", "C2toC4"), clearance=True)
    return write_tex(name, "llrcll", body, en_contrast_note(N, True), size=r"\small")


def en_fam_cell(N, s, slug):
    k = f"family.{s}.C2toC4.{slug}"
    c2, c4, rep, new = N.t(k + ".c2fail"), N.t(k + ".c4fail"), N.t(k + ".repaired"), N.t(k + ".new")
    return f"{c2} $\\to$ {c4} ({rep} cleared{'' if new == '0' else ', ' + new + ' new'})"


def en_tA_families(N):
    name = "tA_families.tex"
    N.table = "en/" + name
    N.source("total row: sums of paper_numbers contrast.<model>.C2toC4.{a, b, c} (C2 failures = a + b, C4 failures = a + c)")
    body = [r"\toprule", en_models_header("Family"), r"\midrule"]
    for slug, *_ in FAMS:
        body.append(trow(EN_FAMS[slug][0], *(en_fam_cell(N, s, slug) for _, s in MODELS)))
    body += [r"\midrule", trow("Other five families", *(en_fam_cell(N, s, "other5") for _, s in MODELS))]
    tot = []
    for _, s in MODELS:
        k = f"contrast.{s}.C2toC4"
        a, b, c = int(N.v(k + ".a")), int(N.v(k + ".b")), int(N.v(k + ".c"))
        if sum(int(N.v(f"family.{s}.C2toC4.{slug}.c2fail")) for slug, *_ in FAMS) != a + b:
            raise SystemExit(f"{s}: family C2 failures do not add up")
        tot.append(f"{a + b} $\\to$ {a + c} ({b} cleared{'' if c == 0 else ', ' + str(c) + ' new'})")
    body += [trow("All six families", *tot), r"\bottomrule"]
    share = "; ".join(f"{m} {N.t(f'repair.{s}.cleared.decisionShare.kn')}" for m, s in MODELS)
    isr = "; ".join(f"{m} {N.t(f'repair.{s}.cleared.decisionAction.delete_item_interviewSignalRisks')}/"
                    f"{kn_k(N.t(f'repair.{s}.cleared.decisionShare.kn'))[0]}" for m, s in MODELS)
    note = ("Each cell: trap failures of the family's risk cases under C2 $\\to$ under C4 (paired cases parseable under "
            f"both conditions; {N.t('bench.family.decision.risk.n')} risk cases per family), with the number cleared by "
            "C4 (no case is added). Families are described, not tested. A decision-family trap can fire through "
            r"\texttt{anywhereSignatures}, decision language or decision-boundary fields, so it can sit outside the "
            f"supported side. Decision-family share of all clearances: {tex(share)}; decision-family clearances whose repair "
            f"deleted an \\texttt{{interviewSignalRisks}} item: {tex(isr)}.")
    return write_tex(name, "llll", body, note, size=r"\small")


def en_tA_cost(N):
    name = "tA_cost.tex"
    N.table = "en/" + name
    rows = {k: [] for k in ("kd", "sup", "zero", "any", "chg", "kept", "rel", "del", "isr")}
    for m, s in MODELS:
        k = f"cost.{s}.C2toC4.keptDiff"
        if N.has(k + ".full"):
            rows["kd"].append(ppn(N.t(k)) + " " + tex(N.t(k + ".ci")))
        else:
            if N.t(f"cost.{s}.controls.keptChanged") != "0":
                raise SystemExit(f"{s}: retention difference without interval although controls changed")
            rows["kd"].append(f"no change (all {N.t(k + '.n')} paired differences 0)")
        rows["sup"].append(f"{N.t(f'cost.{s}.supported.all144.c2')} $\\to$ {N.t(f'cost.{s}.supported.all144.c4')} "
                           f"({tex(N.t(f'cost.{s}.supported.all144.delta'))})")
        rows["zero"].append(f"{N.t(f'cost.{s}.zeroed.risk')} / {N.t(f'cost.{s}.zeroed.control')}")
        rows["any"].append(N.t(f"cost.{s}.controls.anyRepair.kn"))
        rows["chg"].append(N.t(f"cost.{s}.controls.relabeledOrRemoved.kn"))
        rows["kept"].append(N.t(f"cost.{s}.controls.keptChanged.kn"))
        for key, cat in (("rel", "relabel"), ("del", "deleteReplace"), ("isr", "moveISR")):
            rows[key].append(f"{N.t(f'repair.{s}.cat.{cat}.events')} ({N.t(f'repair.{s}.cat.{cat}.cases')})")
    body = [r"\toprule", en_models_header("Quantity"), r"\midrule",
            trow(r"Retention difference on controls, C2$\to$C4, pp [95\% CI]", *rows["kd"]),
            trow(r"Supported-side items per case, C2 $\to$ C4 (difference)", *rows["sup"]),
            trow("Cases with an empty supported side under C4 (risk / control)", *rows["zero"]),
            trow("Controls with any repair action", *rows["any"]),
            trow("Controls with supported-side items relabeled, moved or deleted", *rows["chg"]),
            trow("Controls whose retention changed", *rows["kept"]),
            r"\midrule",
            trow(r"Repair events (cases): relabel to \texttt{unsupportedClaims}", *rows["rel"]),
            trow("Repair events (cases): delete or replace", *rows["del"]),
            trow(r"Repair events (cases): move to \texttt{interviewSignalRisks}", *rows["isr"]),
            r"\bottomrule"]
    note = ("Retention difference: mean over matched controls parseable under both conditions of the per-case retention "
            "(share of gold valid-claim signatures that appear anywhere on the supported side; lenient) under C4 minus "
            f"C2, with a case-level bootstrap 95\\% CI (B = {N.t('stats.bootstrap.B')}). Supported-side items per case: "
            "number of scorer supported-side items (the four optimizedCv sections, supportedClaims, and the evidence "
            f"text and notes of supported or partial requirements), mean over all {N.t('bench.cases.n')} cases "
            "(unparseable = 0). Empty supported side: cases parseable under both conditions whose C4 artifact has no "
            "supported-side item. Controls with any repair action: non-empty repair log; supported side changed: at "
            "least one supported-side item relabeled, moved out or deleted; retention changed: controls scorable under "
            "both conditions whose retention differs. Repair events: entries of the C4 repair logs (in parentheses, cases "
            "with at least one such event, risk and control together). Relabel: a supported-side claim moved to "
            "unsupportedClaims; delete or replace: deleted items or evidence and replaced text fields (including "
            "protected-attribute and decision-language items); move: subjective content moved to "
            "interviewSignalRisks. Requirement-status, structural and other events are not listed. qwen3:30b-a3b's "
            f"retention does not change, yet {N.t('cost.q30b.controls.relabeledOrRemoved.kn')} of its controls had "
            "supported-side items relabeled or deleted. Most of gpt-oss:20b's drop in supported-side items comes from "
            f"optimizedCv items written as bare strings without a source ID ({N.t('cost.gptoss.bare.stringItems')} in C2), "
            f"which {tt('claim_has_source')} relabels wholesale; with string lifting switched off its retention "
            f"difference is {tex(N.t('sens.lift.gptoss.keptDiff.off'))} ({N.t('sens.lift.gptoss.keptDiff.off.changed')} of {N.t('sens.lift.gptoss.keptDiff.off.n')} paired controls change; sensitivity table).")
    return write_tex(name, P("5.8cm") + P("3.1cm") * 3, body, note, size=r"\small", sep="4pt")


def en_tA_redaction(N):
    name = "tA_redaction.tex"
    N.table = "en/" + name
    r = {k: [] for k in ("c2", "c4", "att", "ret", "floor", "fdec", "freq", "fsub", "ndc", "ndatt", "ndret", "ndfloor",
                         "low", "kept", "le", "both", "du")}
    for m, s in MODELS:
        f = f"frontier.{s}"
        r["c2"].append(pct(N.t(f + ".C2.trap")) + f" ({N.t(f + '.C2.trap.kn')})")
        r["c4"].append(f"{pct(N.t(f + '.C4.trap'))} / {pct(N.t(f + '.C4.kept'))}")
        r["att"].append(pct(N.t(f + ".S.attrition")))
        r["ret"].append(pct(N.t(f + ".S.retention")))
        r["floor"].append(f"{pct(N.t(f + '.S.floor'))} ({N.t(f + '.S.floor.kn')})")
        r["fdec"].append(f"{N.t(f + '.floor.decisionFamily')} ({N.t(f + '.floor.decisionAnywhere')})")
        r["freq"].append(N.t(f + ".floor.requirementOverclaim"))
        r["fsub"].append(N.t(f + ".floor.subjectiveExtra"))
        r["ndc"].append(f"{N.t(f + '.nd.C2.trap.kn')} $\\to$ {N.t(f + '.nd.C4.trap.kn')}")
        if int(N.v(f + ".nd.gap")) > 2:
            r["ndatt"].append(f"{pct(N.t(f + '.nd.C4.trap'))} vs.\\ {pct(N.t(f + '.nd.S.attrition'))}")
            r["ndret"].append(f"{pct(N.t(f + '.nd.C4.trap'))} vs.\\ {pct(N.t(f + '.nd.S.retention'))}")
        else:
            r["ndatt"].append(f"not compared ({N.t(f + '.nd.gap')} cases apart)")
            r["ndret"].append("not compared")
        r["ndfloor"].append(pct(N.t(f + ".nd.S.floor")))
        r["low"].append(f"{pct(N.t(f + '.grid.lowest.trap'))} ({pct(N.t(f + '.grid.lowest.kept'))})")
        r["kept"].append(f"{pct(N.t(f + '.grid.keptOnly.trap'))} ({pct(N.t(f + '.grid.keptOnly.kept'))})")
        mk = N.t(f + ".grid.atOrBelowC4.maxKept")
        r["le"].append(N.t(f + ".grid.atOrBelowC4.kn") + (f" ({pct(mk)})" if mk != "–" else " (none)"))
        r["both"].append(N.t(f + ".grid.both.kn"))
        r["du"].append(f"{pct(N.t(f + '.dropUnsourced.trap'))} / {pct(N.t(f + '.dropUnsourced.kept'))}")
    ncol = str(len(MODELS) + 1)
    sec = lambda t: trow(r"\multicolumn{" + ncol + r"}{l}{\textit{" + t + "}}")  # noqa: E731
    body = [r"\toprule", en_models_header(r"Readout (trap-failure rate and retention in \%)"), r"\midrule",
            sec("All six families"),
            trow("C2 trap-failure rate (k/n)", *r["c2"]),
            trow("C4 trap-failure rate / retention", *r["c4"]),
            trow("S at C4's attrition (supported items per case)", *r["att"]),
            trow("S at C4's retention", *r["ret"]),
            trow("S floor: all supported-side items removed (k/n)", *r["floor"]),
            trow(r"\quad floor failures: decision family (via \texttt{anywhereSignatures})", *r["fdec"]),
            trow(r"\quad floor failures: requirement overclaim", *r["freq"]),
            trow(r"\quad floor failures: subjective-family extra rule", *r["fsub"]),
            r"\midrule", sec("Five non-decision families"),
            trow(r"Trap failures, C2 $\to$ C4 (k/n)", *r["ndc"]),
            trow("C4 vs.\\ S at C4's attrition", *r["ndatt"]),
            trow("C4 vs.\\ S at C4's retention", *r["ndret"]),
            trow("S floor", *r["ndfloor"]),
            r"\midrule", sec(f"Extended S$\\times$R$\\times$X grid ({N.t('frontier.gptoss.grid.nConfigs')} configurations per model)"),
            trow("Lowest trap-failure rate, any configuration (its retention)", *r["low"]),
            trow(r"Lowest trap-failure rate with retention $\ge$ C4 (its retention)", *r["kept"]),
            trow(r"Configurations with trap-failure rate $\le$ C4 (their highest retention)", *r["le"]),
            trow(r"Configurations with retention and trap routing both $\ge$ C4", *r["both"]),
            r"\midrule",
            trow(r"Fixed policy \texttt{drop\_unsourced}: trap-failure rate / retention", *r["du"]),
            r"\bottomrule"]
    for _, s in MODELS:
        if N.t(f"frontier.{s}.grid.nConfigs") != N.t("frontier.gptoss.grid.nConfigs"):
            raise SystemExit("grid size differs across models")
    note = ("Post hoc and exploratory; the readouts hold for this grid and these seeds only and do not bound all "
            "content-blind transformations. The transformations choose items only by structural position, status "
            "enumeration and random seed (no gold, trap signatures, lexicons, validator results or item text), are "
            "applied to the frozen C2 artifacts and are rescored with the frozen scorer; values are means over seeds "
            f"{N.t('frontier.design.seeds')}. S($p$) relabels (moves to unsupportedClaims) or deletes a fraction $p$ of "
            "supported-side items; R($q$) downgrades a fraction $q$ of supported requirements to partial evidence; X($r$) "
            "resets the decision-boundary fields to the repairer's constants and deletes a fraction $r$ of the "
            "interview-signal risk, human-review checklist and limitation items. ``S at C4's attrition / retention'': "
            "trap-failure rate on the S relabel curve, linearly interpolated at C4's supported items per case / C4's "
            "retention. S floor: trap-failure rate with the whole supported side removed (retention 0\\%); over the three "
            f"models {N.t('frontier.pooled.floor.kn')} floor failures, of which {N.t('frontier.pooled.floor.decisionFamily')} "
            f"are decision-family cases ({N.t('frontier.pooled.floor.decisionAnywhere')} triggered by "
            r"\texttt{anywhereSignatures}, " f"{N.t('frontier.pooled.floor.field.interviewSignalRisks')} with the phrase in "
            r"\texttt{interviewSignalRisks}), " f"{N.t('frontier.pooled.floor.requirementOverclaim')} requirement overclaims "
            f"and {N.t('frontier.pooled.floor.subjectiveExtra')} subjective-family extra-rule failures; the repairer's "
            f"{tt('_fix_requirements')} downgraded a requirement status "
            + "/".join(N.t(f"repair.{s}.fixReq.downgrades") for _, s in MODELS) + " times in the three runs. "
            "Non-decision families: the five families other than decision, with the curves and C4 coordinates recomputed "
            "on that subset; a model whose C2 and C4 differ by at most 2 cases there is not compared. Grid: configurations "
            f"of $p \\in \\{{{N.t('frontier.design.p')}\\}}$ with relabel or delete mode, $q \\in \\{{{N.t('frontier.design.q')}\\}}$ "
            f"and $r \\in \\{{{N.t('frontier.design.r')}\\}}$. Trap-failure denominators: parseable risk cases; retention: "
            r"parseable controls. \texttt{drop\_unsourced} relabels every supported-side item without a source ID.")
    return write_tex(name, P("6.9cm") + "lll", body, note, size=r"\small", sep="5pt")


def en_tA_source_facts(N):
    name = "tA_source_facts.tex"
    N.table = "en/" + name
    S = "setup.source."
    subj = "; ".join((N.t(S + "subj.baitGold.kn"), N.t(S + "subj.controlNote.kn"), N.t(S + "subj.resume.kn"), N.t(S + "subj.workSample.kn")))
    if N.t(S + "bait.nonNote") != "0" or N.t(S + "trapSig.nonNote") != "0":
        raise SystemExit("a bait or trap signature sits in a non-note source; revise tA_source_facts")
    ncol = str(len(MODELS) + 1)
    span = lambda t: r"\multicolumn{" + str(len(MODELS)) + "}{l}{" + t + "}"  # noqa: E731
    body = [r"\toprule", en_models_header("Fact"), r"\midrule",
            trow(r"\multicolumn{" + ncol + r"}{l}{\textit{Testbed (same for all models)}}"),
            trow("Sources per case: resume items / work sample / notes",
                 span(f"{N.t(S + 'resume.perCase')} / {N.t(S + 'workSample.perCase')} / {N.t(S + 'note.perCase')} "
                      f"({N.t(S + 'n')} sources in all)")),
            trow("Gold bait sources that are notes", span(N.t(S + "baitGold.note.kn"))),
            trow("Risk-case sources containing a trap signature that are notes", span(N.t(S + "bait.note.kn"))),
            trow("Risk-case notes that are gold bait sources", span(N.t(S + "riskNote.baitGold.kn"))),
            trow("Trap-signature occurrences: in notes only / in a resume item or work sample / in no source",
                 span(f"{N.t(S + 'trapSig.noteOnly')} / {N.t(S + 'trapSig.nonNote')} / {N.t(S + 'trapSig.noSource')} "
                      f"(of {N.t(S + 'trapSig.n')})")),
            trow("Control valid-claim signatures found only in notes", span(N.t(S + "validCtl.onlyNote.kn"))),
            trow("Classed subjective or hearsay by the validator's source lexicon: gold baits; control notes; resume "
                 "items; work samples", span(subj)),
            r"\midrule",
            trow(r"\multicolumn{" + ncol + r"}{l}{\textit{C2 supported-side items containing a trap signature (trap items)}}"),
            trow("Trap items citing a note", *(N.t(f"{S}{s}.trapItem.citeNote.kn") for _, s in MODELS)),
            trow("Trap items without a source ID", *(N.t(f"{S}{s}.trapItem.noSource.kn") for _, s in MODELS)),
            trow("Trap items FAILed by any rule", *(N.t(f"validator.{s}.item.trapFailed.kn") for _, s in MODELS)),
            trow(r"\quad of these, FAILed by \texttt{subjective\_claim\_boundary}",
                 *(N.t(f"{S}{s}.trapItemFail.subj.kn") for _, s in MODELS)),
            trow(r"\quad of these, FAILed by that rule only", *(N.t(f"{S}{s}.trapItemFail.subjOnly.kn") for _, s in MODELS)),
            r"\bottomrule"]
    for _, s in MODELS:
        fail_n = kn_k(N.t(f"{S}{s}.trapItemFail.subj.kn"))[1]
        if fail_n != kn_k(N.t(f"validator.{s}.item.trapFailed.kn"))[0]:
            raise SystemExit(f"{s}: failed trap items differ between setup_facts and repair_anatomy")
        if N.t(f"{S}{s}.trapItemFail.subj.citedAsSupport") != str(kn_k(N.t(f"{S}{s}.trapItemFail.subj.kn"))[0]):
            raise SystemExit(f"{s}: subjective_claim_boundary FAILs are not all subjective_source_cited_as_support")
    note = ("Source types come from the case metadata (resume item, work sample, note). Gold bait sources: the gold "
            r"\texttt{baitSourceIds} of the risk cases; sources containing a trap signature: case-insensitive substring "
            "match of a gold trap signature in the source text. Every validator FAIL of "
            r"\texttt{subjective\_claim\_boundary} on a C2 trap item is the code \texttt{subjective\_source\_cited\_as\_support}. "
            "Item level as in the validator table: each FAIL finding is assigned to the deepest supported-side item that "
            "contains its path.")
    return write_tex(name, P("7.3cm") + "lll", body, note, size=r"\small")


def en_tA_source_types(N):
    name = "tA_source_types.tex"
    N.table = "en/" + name
    body = [r"\toprule",
            trow("Policy", hstack("Items moved", "(cases)"), hstack("Trap,", r"\% (k/n)"), hstack("Non-decision", r"trap, \% (k/n)"),
                 hstack("Retention,", r"\%"), hstack("Trap", r"routing, \%"), hstack("Subjective", r"routing, \%")),
            r"\midrule"]
    for i, (m, s) in enumerate(MODELS):
        f = f"frontier.{s}"
        if N.t(f + ".xOnly.trap") != N.t(f + ".grid.xOnly.trap"):
            raise SystemExit(f"{s}: X-only reference differs from the grid configuration p = 0, q = 0, r = 1")
        body.append(trow(r"\multicolumn{7}{l}{\textit{" + tex(m) + "}}"))
        body.append(trow(r"\quad C2 (reference)", "--", f"{pct(N.t(f + '.C2.trap'))} ({N.t(f + '.C2.trap.kn')})",
                         f"{pct(N.t(f + '.nd.C2.trap'))} ({N.t(f + '.nd.C2.trap.kn')})", pct(N.t(f + ".C2.kept")),
                         pct(N.t(f + ".C2.trapRouted")), pct(N.t(f + ".C2.subjRouted"))))
        body.append(trow(r"\quad C4 (reference)", "--", f"{pct(N.t(f + '.C4.trap'))} ({N.t(f + '.C4.trap.kn')})",
                         f"{pct(N.t(f + '.nd.C4.trap'))} ({N.t(f + '.nd.C4.trap.kn')})", pct(N.t(f + ".C4.kept")),
                         pct(N.t(f + ".C4.trapRouted")), pct(N.t(f + ".C4.subjRouted"))))
        body.append(trow(r"\quad X only, $r=1$ (reference)", "--", f"{pct(N.t(f + '.xOnly.trap'))} ({N.t(f + '.xOnly.trap.kn')})",
                         f"{pct(N.t(f + '.xOnly.nd.trap'))} ({N.t(f + '.xOnly.nd.trap.kn')})", pct(N.t(f + ".grid.xOnly.kept")),
                         pct(N.t(f + ".grid.xOnly.trapRouted")), pct(N.t(f + ".grid.xOnly.subjRouted"))))
        for p, lab in SRC_POLS:
            g = f"{f}.{p}"
            body.append(trow(r"\quad " + tt(lab), f"{N.t(g + '.moved')} ({kn_k(N.t(g + '.movedCases.kn'))[0]})",
                             f"{pct(N.t(g + '.trap'))} ({N.t(g + '.trap.kn')})", f"{pct(N.t(g + '.nd.trap'))} ({N.t(g + '.nd.trap.kn')})",
                             pct(N.t(g + ".kept")), pct(N.t(g + ".trapRouted")), pct(N.t(g + ".subjRouted"))))
        body.append(r"\midrule" if i < len(MODELS) - 1 else r"\bottomrule")
    le = "; ".join(f"{m} {N.t(f'frontier.{s}.srcPolicies.atOrBelowC4.kn')}" for m, s in MODELS)
    bo = "; ".join(f"{m} {N.t(f'frontier.{s}.srcPolicies.both.kn')}" for m, s in MODELS)
    subj_x = sorted({N.t(f"frontier.{s}.{p}X.subjRouted") for _, s in MODELS for p in ("dropNoteCited", "dropNoteOrUnsourced")})
    if subj_x != ["0.0%"]:
        raise SystemExit(f"+X variants route subjective sources ({subj_x}); revise the note")
    note = (f"Post hoc: the {N.t('frontier.design.sourcePolicies.n')} deterministic source-type policies were designed on "
            f"{N.t('frontier.design.sourcePolicies.designedOn')}, after all other results were known and after it was known "
            f"that all bait sources are notes ({N.t('setup.source.baitGold.note.kn')} gold bait sources). They read only the "
            "source types in the case metadata and the source IDs of supported-side items (no gold, signatures, lexicons, "
            "validator results or item text), but source type is correlated with the traps, so they are not content-blind. "
            r"\texttt{drop\_note\_cited} relabels every supported-side item that cites a note; \texttt{drop\_note\_or\_unsourced} "
            "also relabels items without a source ID; +X then applies X($r=1$): decision-boundary reset and deletion of all "
            "interview-signal risk, checklist and limitation items, which sets the subjective-source routing rate to 0 by "
            "construction. For both qwen models the C2 artifacts have no supported-side item without a source ID, so the "
            "two base policies coincide. Items moved: supported-side items relabeled (cases with at least one). Trap: "
            f"parseable risk cases; non-decision trap: the five non-decision families; point estimates, no intervals. "
            f"Policies with trap-failure rate $\\le$ C4: {tex(le)}; with retention and trap routing both $\\ge$ C4: {tex(bo)}.")
    return write_tex(name, "l" + "r" * 6, body, note, size=r"\footnotesize", sep="4pt")


def en_tA_sensitivity(N):
    name = "tA_sensitivity.tex"
    N.table = "en/" + name
    if N.t("sens.lift.qwenIdentity") != "true":
        raise SystemExit("lift_string_items is not the identity on the qwen outputs")
    r = {k: [] for k in ("t_all", "t_ex", "c_all", "c_ex", "k_all", "k_ex", "uni", "l_c2", "l_c4", "l_kd")}
    for m, s in MODELS:
        d = f"sens.dev.{s}"
        full = lambda key: tex(N.t(key)).replace(r"\%", "", 1)  # noqa: E731  '5.6% [2.2, 13.4]' -> '5.6 [2.2, 13.4]'
        r["t_all"].append(full(d + ".all.C4.trap.full"))
        r["t_ex"].append(full(d + ".excl.C4.trap.full"))
        r["c_all"].append(f"{full(d + '.all.C2toC4.clear.full')} ({N.t(d + '.all.C2toC4.clear.kn')})")
        r["c_ex"].append(f"{full(d + '.excl.C2toC4.clear.full')} ({N.t(d + '.excl.C2toC4.clear.kn')})")
        for part, key in (("all", "k_all"), ("excl", "k_ex")):
            k = f"{d}.{part}.keptDiff"
            if N.has(k + ".full"):
                r[key].append(tex(N.t(k + ".full")).replace(" pp", "", 1))
            else:
                if N.t(k + ".changed") != "0":
                    raise SystemExit(f"{k}: no interval although controls changed")
                r[key].append("no change")
        u = f"sens.uni.{s}.C4.trap"
        r["uni"].append(f"{full(u + '.norm.full')} ({N.t(u + '.norm.kn')}; official {N.t(u + '.official.kn')})")
        if s == "gptoss":
            r["l_c2"].append(f"{N.t('sens.lift.gptoss.C2.trap.official.kn')} $\\to$ {N.t('sens.lift.gptoss.C2.trap.off.kn')}")
            r["l_c4"].append(f"{N.t('sens.lift.gptoss.C4.trap.official.kn')} $\\to$ {N.t('sens.lift.gptoss.C4.trap.off.kn')}")
            r["l_kd"].append(f"{ppn(N.t('sens.lift.gptoss.keptDiff.official'))} $\\to$ "
                             f"{tex(N.t('sens.lift.gptoss.keptDiff.off')).replace(' pp', '', 1)} ({N.t('sens.lift.gptoss.keptDiff.off.changed')}/{N.t('sens.lift.gptoss.keptDiff.off.n')} changed)")
        else:
            for key in ("l_c2", "l_c4", "l_kd"):
                r[key].append("n/a")
    body = [r"\toprule", en_models_header(r"Quantity (\% or pp [95\% CI])"), r"\midrule",
            trow("C4 trap-failure rate, all cases", *r["t_all"]),
            trow("C4 trap-failure rate, development cases excluded", *r["t_ex"]),
            trow(r"C2$\to$C4 clearance, all cases (k/n)", *r["c_all"]),
            trow(r"C2$\to$C4 clearance, development cases excluded (k/n)", *r["c_ex"]),
            trow(r"Retention difference C2$\to$C4, all cases", *r["k_all"]),
            trow(r"Retention difference C2$\to$C4, development cases excluded", *r["k_ex"]),
            r"\midrule",
            trow("C4 trap-failure rate with Unicode punctuation normalized (k/n)", *r["uni"]),
            r"\midrule",
            trow(r"String lifting off: C2 trap failures, official $\to$ off", *r["l_c2"]),
            trow(r"String lifting off: C4 trap failures, official $\to$ off", *r["l_c4"]),
            trow(r"String lifting off: retention difference C2$\to$C4, official $\to$ off", *r["l_kd"]),
            r"\bottomrule"]
    note = (f"Post hoc sensitivity analyses. Development cases excluded: the {N.t('sens.dev.n')} cases "
            f"({N.t('sens.dev.nRisk')} risk, {N.t('sens.dev.nControl')} control; identified by the file names of the qwen3:8b "
            "pilot outputs) used to iterate on the detectors, scorer and repairer are removed and everything is recomputed "
            r"on the remaining cases. Trap-failure and clearance rates: Wilson 95\% CI; retention difference: mean per-case "
            "C2$\\to$C4 difference with a case-level bootstrap interval; ``no change'': every paired difference is 0. "
            "Unicode normalization: before signature matching, U+2010--U+2015 and U+2212 become an ASCII hyphen, curly quotes "
            "straight quotes and U+00A0 a space, in outputs and signatures alike; scoring is otherwise unchanged. String "
            r"lifting off: \texttt{bundle.lift\_string\_items} (added after the gpt-oss:20b outputs had been seen) is "
            "replaced in-process by a non-lifting copy for validation, repair and scoring, and C4 is rebuilt offline from "
            "the C2 outputs with the frozen repair pipeline; the qwen artifacts contain no bare-string items, so lifting is "
            "the identity for them (n/a).")
    return write_tex(name, P("5.4cm") + P("3.3cm") * 3, body, note, size=r"\small", sep="4pt")


def en_tA_conditions(N):
    name = "tA_conditions.tex"
    N.table = "en/" + name
    ident = "; ".join(f"{tex(m)} {N.t(f'cond.{s}.C0C5.identical.kn')}" for m, s in MODELS)
    regen = ", ".join(N.t(f"repair.{s}.regenerated") for _, s in MODELS)
    extra = ", ".join(tt(x.strip()) for x in N.t("cond.C2.extraFields").split(","))
    rows = [
        ("C0", f"Baseline: JSON mode (format = {tt(chr(34) + N.t('cond.C0.format') + chr(34))}); the prompt describes the full "
               "output contract and contains no rules", N.t("cond.C0.words.median"), "--", f"no ({N.t('cond.C0.header.kn')})", "--"),
        ("C1", f"System message adds the prose rules section ({tt('render_prose')} of the rules active for the case); "
               f"{N.t('cond.C1.equalsC0PlusRendering.kn')} requests equal C0 plus this rendering",
         N.t("cond.C1.words.median"), N.t("cond.C1.rulesWords.median"), f"no ({N.t('cond.C1.header.kn')})", "--"),
        ("C2", f"System message adds the contract rules section ({tt('render_contract')}: must / mustNot / route, plus "
               f"{extra} and the top-level {tt(N.t('cond.C2.extraTopLevel'))}) and the validator header sentence; "
               f"{N.t('cond.C2.equalsC0PlusRendering.kn')} requests equal C0 plus this rendering",
         N.t("cond.C2.words.median"), N.t("cond.C2.rulesWords.median"), f"yes ({N.t('cond.C2.header.kn')})", "--"),
        ("C3", "No new request: the C2 artifacts plus an offline validation report", "--", "--", "--", "--"),
        ("C4", "No new generation request: validation of the frozen C2 artifacts, one repair pass, at most one "
               f"regeneration (regeneration requests: {regen} for gpt-oss:20b, qwen3:8b, qwen3:30b-a3b)", "--", "--", "--", "--"),
        ("C5", f"Differs from C0 only in the format field, whose value is the artifact JSON Schema "
               f"({tt(N.t('cond.C5.schemaFile'))}, constrained decoding); the two other differing keys are the condition "
               "label and the request id", N.t("cond.C5.words.median"), "--", f"no ({N.t('cond.C5.header.kn')})", ident),
    ]
    diff_keys = N.t("cond.C0C5.diffKeys")
    if diff_keys != "condition, format, request_id" or N.t("cond.C0C5.diffMetaKeys.n") != "0":
        raise SystemExit(f"C0/C5 request difference changed: {diff_keys}")
    body = [r"\toprule",
            trow("Cond.", "Request relative to C0", hstack("Prompt", "words"), hstack("Rule", "words"), hstack("Validator", "header"),
                 hstack("Outputs identical", "to C0 (C5 only)")),
            r"\midrule"] + [trow(*r) for r in rows] + [r"\bottomrule"]
    note = (f"Words: white-space tokens of the system and user messages, median over the {N.t('cond.C0.requests.n')} "
            "requests of a condition; rule-section words: system-message words of C1 or C2 minus those of C0 for the same "
            f"case. The per-case C2 $-$ C1 difference has median {N.t('cond.C2minusC1.words.median')} words (range "
            f"{N.t('cond.C2minusC1.words.min')}--{N.t('cond.C2minusC1.words.max')}). Validator header sentence: the first "
            f"sentence of the C2 rules section, ``{tex(N.t('cond.C2.headerLine'))}''; counted are requests that contain both "
            f"``{tex(N.t('cond.C2.headerPhrase1'))}'' and ``{tex(N.t('cond.C2.headerPhrase2'))}''. No validation runs and "
            "nothing is sent back for repair during C2 generation (C3 is an offline validation afterwards). A key-by-key "
            f"comparison of the {N.t('cond.C0C5.linesDiffer.kn')} C0 and C5 requests finds only the top-level keys "
            f"{', '.join(tt(x.strip()) for x in diff_keys.split(','))} different. Identical outputs: the C0 and C5 output "
            f"strings of a case are byte-identical in UTF-8 (out of {N.t('cond.C0.requests.n')}). The request files of the "
            "four generation conditions are byte-identical across the three models (first 12 hex digits of the requests "
            "SHA-256: " + "; ".join(f"{c} {tt(N.t(f'cond.{c}.requestsSha12'))}" for c in ("C0", "C1", "C2", "C5")) + ").")
    return write_tex(name, "l" + P("6.4cm") + "rr" + P("1.5cm") + P("2.9cm"), body, note, size=r"\small", sep="4pt")


def en_tA_contract_coverage(N):
    name = "tA_contract_coverage.tex"
    N.table = "en/" + name
    N.source("setup_facts.json: contractCoverage.codeTable (emitted vs rule-JSON severity) and contractCoverage.counterpartMap (hand-assigned renamed counterparts)")
    N.source("RECORDS.md 2026-09-05 entry (text only): the requirement-level licensing checks were added while iterating on the C0 pilot")
    sf = json.loads((HERE / "setup_facts.json").read_text(encoding="utf-8"))["contractCoverage"]
    cmap = sf["counterpartMap"]
    table = {c["code"]: c for c in sf["codeTable"]}
    dni = [x.strip() for x in N.t("contract.declaredNotImplemented.list").split(",")]
    wc = [x.strip() for x in N.t("contract.withCounterpart.list").split(",")]
    nc = [x.strip() for x in N.t("contract.noCounterpart.list").split(",")]
    sev = [x.strip() for x in N.t("contract.severityDiffers.list").split(",")]
    if sorted(cmap) != sorted(wc):
        raise SystemExit("counterpartMap differs from contract.withCounterpart.list")
    impl_for = {d: sorted(k for k, v in cmap.items() if v == d) for d in dni}
    if any(not v for v in impl_for.values()):
        raise SystemExit("a declared-but-not-implemented check has no renamed implementation")
    sev_txt = "; ".join(f"{tt(c)} (emitted {'/'.join(table[c]['emittedSeverities'])}, contract {'/'.join(table[c]['ruleJsonSeverity'])})" for c in sev)
    strict = "; ".join(f"{tex(m)} {N.t(f'contract.{s}.strict.depend')}/{N.t(f'contract.{s}.cleared')}" for m, s in MODELS)
    lenient = "; ".join(f"{tex(m)} {N.t(f'contract.{s}.lenient.depend')}/{N.t(f'contract.{s}.cleared')}" for m, s in MODELS)
    strict_ids = "; ".join(f"{tex(m)}: {tt(N.t(f'contract.{s}.strict.dependIds'))}" for m, s in MODELS)
    lenient_ids = "; ".join(f"{tex(m)}: {tt(N.t(f'contract.{s}.lenient.dependIds'))}" for m, s in MODELS)
    rows = [
        ("Declared validator checks (not requiresGold)", N.t("contract.declared.n"), r"ids without requiresGold in each rule's \texttt{validationTarget.checks}"),
        ("Gold-only checks (requiresGold)", N.t("contract.goldOnly.n"), "not run by the validator; computed only when scoring"),
        ("Implemented codes", N.t("contract.implemented.n"), "parsed statically from detectors.py / validator.py or observed in the three models' validation reports"),
        ("Declared, no implementation of the same name", N.t("contract.declaredNotImplemented.n"),
         "; ".join(f"{tt(d)} (implemented as {', '.join(tt(x) for x in impl_for[d])})" for d in dni)),
        ("Implemented, undeclared: renamed counterpart", N.t("contract.withCounterpart.n"), "; ".join(f"{tt(k)} $\\to$ {tt(cmap[k])}" for k in wc)),
        ("Implemented, undeclared: no counterpart", N.t("contract.noCounterpart.n"), ", ".join(tt(k) for k in nc)),
        ("Emitted severity differs from the contract JSON", N.t("contract.severityDiffers.n"), sev_txt),
        ("Strict counterfactual: cleared cases that depend on undeclared checks", strict, strict_ids),
        ("Lenient counterfactual (renamed counterparts count as declared)", lenient, lenient_ids),
    ]
    body = [r"\toprule", trow("Item", "Count", "Details"), r"\midrule"] + [trow(*r) for r in rows] + [r"\bottomrule"]
    note = ("Declared checks and implemented codes are matched by exact name. A renamed counterpart is a hand-assigned "
            "correspondence (counterpartMap in setup\\_facts.py): the implementation covers a declared check under another "
            f"name. Of the {N.t('contract.noCounterpart.n')} codes without a counterpart, the four requirement-level licensing "
            r"checks (\texttt{requirement\_*\_unlicensed}) were added on 2026-09-05 while the detectors were iterated on the "
            "development cases (C0 pilot). Cleared cases: risk cases that fail under C2 and not under C4 (denominator = each "
            "model's clearances). Strict counterfactual: only findings whose code is declared are kept, the frozen repairer "
            "re-repairs the frozen C2 artifact, and a case that still fails depends on undeclared checks; the lenient "
            "counterfactual counts renamed counterparts as declared. Neither simulates regeneration (cases still BLOCKed "
            "under the restricted validator, which would have triggered regeneration, strict: "
            + "/".join(N.t(f"contract.{s}.strict.stillBlock") for _, s in MODELS) + " in model order). The validator and "
            "detectors read no field of the contract file. Rule fixtures and "
            "mutation tests check selected behaviors without enforcing declaration--implementation equivalence.")
    return write_tex(name, P("4.4cm") + P("2.4cm") + P("8.6cm"), body, note, size=r"\footnotesize", sep="4pt")


def en_tA_validator(N):
    name = "tA_validator.tex"
    N.table = "en/" + name
    flags = {c: [] for c in ("C0", "C1", "C3", "C5")}
    r = {k: [] for k in ("trap", "own", "ctl", "res", "rflag", "rrule", "racc")}
    for m, s in MODELS:
        for side in ("flaggedRisk", "flaggedControl"):
            if N.t(f"main.{s}.C2.{side}.kn") != N.t(f"main.{s}.C3.{side}.kn"):
                raise SystemExit(f"{s}: C2 and C3 bundle flags differ")
        for c in flags:
            flags[c].append(f"{N.t(f'main.{s}.{c}.flaggedRisk.kn')}; {N.t(f'main.{s}.{c}.flaggedControl.kn')}")
        v = f"validator.{s}"
        r["trap"].append(f"{N.t(v + '.item.trapFailed.kn')} ({pct(N.t(v + '.item.trapFailed'))})")
        r["own"].append(N.t(v + ".item.trapFailedOnTrapRule.kn"))
        r["ctl"].append(f"{N.t(v + '.item.controlFailed.kn')} ({pct(N.t(v + '.item.controlFailed'))})")
        r["res"].append(N.t(v + ".residual.n"))
        r["rflag"].append(N.t(v + ".residual.c3Flagged.kn"))
        r["rrule"].append(N.t(v + ".residual.c3TrapRuleFail.kn"))
        r["racc"].append(N.t(v + ".residual.c4Accept.kn"))
    ncol = str(len(MODELS) + 1)
    sec = lambda t: trow(r"\multicolumn{" + ncol + r"}{l}{\textit{" + t + "}}")  # noqa: E731
    body = [r"\toprule", en_models_header("Quantity"), r"\midrule",
            sec("Bundle-level flags, BLOCK or HUMAN\\_REVIEW (risk; control)"),
            trow("C0", *flags["C0"]), trow("C1", *flags["C1"]), trow("C2 (= C3)", *flags["C3"]), trow("C5", *flags["C5"]),
            r"\midrule", sec("Item level, C2 supported side"),
            trow(r"Trap items FAILed by any rule (\%)", *r["trap"]),
            trow("Trap items FAILed by the trap's own anchoring rule", *r["own"]),
            trow(r"Control items with a valid signature FAILed (\%)", *r["ctl"]),
            r"\midrule", sec("C4 residual events (risk cases still failing under C4)"),
            trow("Residual events", *r["res"]),
            trow("Flagged at bundle level before repair", *r["rflag"]),
            trow("With a FAIL of the trap's anchoring rule before repair", *r["rrule"]),
            trow("Accepted by the final C4 validation", *r["racc"]),
            r"\bottomrule"]
    note = ("Bundle-level flag: the validator's bundle verdict is BLOCK or HUMAN\\_REVIEW (out of "
            f"{N.t('bench.risk.n')} risk cases and {N.t('bench.control.n')} controls; unparseable counts as flagged); BLOCK if and only if a FAIL of critical severity exists. C0, C1 and "
            "C5: offline validation after generation; C2 and C3 validate the same C2 artifacts (identical case by case). "
            f"gpt-oss:20b's schema validity under JSON mode is low (C2: {tex(N.t('main.gptoss.C2.schemaValid'))}) and a "
            "failed schema check is a critical FAIL, so nearly all of its bundles are flagged; bundle flags are not a "
            "detection metric. Item level (C2, primary definition): items are the scorer's supported-side items, and each "
            "FAIL finding is assigned to the deepest item containing its path; trap items contain a gold trap signature "
            "(not negated); control items contain a gold valid-claim signature, and an item can hold a valid claim and "
            "out-of-bounds content at once. This rate describes potentially unnecessary edits, rather than estimating a false-positive rate. Residual events: risk cases that still fail under C4; "
            "their pre-repair bundle flag and trap-rule FAIL (any FAIL of the gold anchoring rule) come from the C3 report "
            "of the same C2 artifact. That all residual events are accepted by the final validation follows in part from "
            "the selection (revalidation after repair); residual events show that validator and "
            "scorer use different criteria, but they share negation and decision lexicon logic, so they are not independent.")
    return write_tex(name, P("6.6cm") + "lll", body, note, size=r"\small")


def en_tA_example(N):
    name = "tA_example.tex"
    N.table = "en/" + name
    N.source("example_case.py functions (dev_ids, select, trace_model) re-run on the frozen C2/C4 run files; selected case asserted equal to paper_numbers example.caseIdFull")
    N.source("setup_facts.json: contractCoverage.counterpartMap (renamed counterpart of the finding codes in the example)")
    import example_case as EX  # noqa: E402
    from hrgene.rules import RuleSet  # noqa: E402
    rs = RuleSet(os.path.join(str(ROOT), "rules", "canonical-rules.v2.json"))
    gold = {g["caseId"]: g for g in (EX.load_json(f) for f in sorted(glob.glob(os.path.join(EX.BENCH, "gold", "*.json"))))}
    cid, models, tied, hist, status = EX.select(gold, EX.dev_ids())
    if cid != N.t("example.caseIdFull") or ", ".join(models) != N.t("example.models"):
        raise SystemExit("example_case selection differs from example_case.md / paper_numbers")
    case = EX.load_json(os.path.join(EX.BENCH, "cases", cid + ".json"))
    g = gold[cid]
    cmap = json.loads((HERE / "setup_facts.json").read_text(encoding="utf-8"))["contractCoverage"]["counterpartMap"]
    body = [r"\toprule", trow("C2 supported-side item containing a signature (truncated)", "Validator findings",
                              "Repair action", "C4 location"), r"\midrule"]
    codes, triggers, arts_all, reqs, genuine, first = set(), set(), [], [], {}, True
    for m, prefix in EX.MODELS:
        if m not in models:
            continue
        if not first:
            body.append(r"\midrule")
        first = False
        body.append(trow(r"\multicolumn{4}{l}{\textit{" + tex(m) + "}}"))
        t = EX.trace_model(m, prefix, case, g, rs.lex)
        genuine[m] = t["c2"]["trapRequirementOverclaimed"] is True or any(
            set(it["signatures"]) - {a["signature"] for a in it["substringArtifacts"]} for it in t["items"])
        for it in t["items"]:
            art = {a["signature"] for a in it["substringArtifacts"]}
            sigs = ", ".join(tt(x) + (" (substring artifact)" if x in art else "") for x in it["signatures"])
            for a in sorted(it["substringArtifacts"], key=lambda a: a["signature"]):
                x = (m, a["signature"], containing_token(a["context"], a["signature"]))
                if x not in arts_all:
                    arts_all.append(x)
            seen, fs = set(), []
            for f in it["findings"]:
                key = (f["rule"], f["code"], f["severity"], f["status"])
                if key not in seen:
                    seen.add(key)
                    fs.append(f"{tt(f['rule'])} / {tt(f['code'])} ({tex(f['severity'])}, {tex(f['status'])})")
                    if f["status"] == "FAIL":
                        codes.add(f["code"])
            triggers.update(e["code"] for e in it["repairLog"])
            rep = "; ".join(dict.fromkeys(f"{tt(e['action'])} ({tt(e['code'])})" for e in it["repairLog"])) or "none"
            where = ", ".join(tt(short_path(p)) for p in it["c4Locations"]) or "deleted"
            where += " (still on the supported side)" if it["c4StillSupportedSide"] else " (not on the supported side)"
            item = f"{tt(short_path(it['path']))}: {quote_en(it['text'], 90)}; signatures {sigs}"
            body.append(trow(item, "; ".join(fs) or "none", rep, where))
        reqs.append(f"{tex(m)}: " + ", ".join(f"{tt(r['requirementId'])} {tt(r['c2Status'] or 'absent')} $\\to$ "
                                               f"{tt(r['c4Status'] or 'absent')} (gold {tt(r['goldStatus'])})" for r in t["requirements"])
                    + f"; bundle verdict C2 {tex(t['c2Aggregate'])} $\\to$ C4 {tex(t['c4']['aggregate'])}")
    body.append(r"\bottomrule")
    renamed = sorted(c for c in codes if c in cmap)
    slug = dict(MODELS)
    sid = N.t("example.caseId")
    strict = [m for m in models if sid in N.t(f"contract.{slug[m]}.strict.dependIds")]
    lenient = [m for m in models if sid in N.t(f"contract.{slug[m]}.lenient.dependIds")]
    fam_slug = {f: s for s, f, _, _ in FAMS}
    others = [m for m, _ in EX.MODELS if m not in models]
    note = (f"Example case {tt(sid)} ({EN_FAMS[fam_slug[g['family']]][0].lower()} family, anchoring rule "
            f"{tt(g['trap']['rule'].split('.')[-1])}), chosen by a fixed rule: exclude the {N.t('sens.dev.n')} development "
            "cases and the decision family, and take the risk case that fails under C2 and is cleared by C4 for the most "
            f"models (here {N.t('example.nModels')}; the first caseId among {N.t('example.tied.n')} tied cases). "
            + (f"{', '.join(tex(m) for m in others)} did not fail this case under C2 and is not listed. " if others else "")
            + "Each row is one supported-side item of the C2 artifact that contains a gold trap signature (text truncated "
            "at 90 characters); findings are those of the C4 input validation (the validation of the frozen C2 artifact) "
            "on or inside the item's path, each rule and code listed once; the repair action is the C4 repair-log entry "
            "on that path; the C4 location is the field of the final artifact holding the same text (else a field "
            "containing it). "
            + (("Substring artifact: the signature occurs only inside a longer word ("
                + "; ".join(f"{tex(m)}: {tt(x)} only within ``{tex(tok)}''" for m, x, tok in arts_all)
                + "), which the frozen scorer's verbatim substring match still counts. Here the longer word has the same meaning; "
                + ("the same artifact also contains word-boundary signature hits, so the model's C2 trap failure does not "
                   "depend on these artifacts. " if all(genuine[m] for m, _, _ in arts_all)
                   else ", ".join(sorted({tex(m) for m, _, _ in arts_all if not genuine[m]}))
                   + ": the C2 trap failure consists of these artifact hits only. ")) if arts_all else "")
            + (("Among the FAIL codes, " + "; ".join(f"{tt(c)} is the renamed implementation of the declared check "
                                                    f"{tt(cmap[c])}" for c in renamed)
                + f" (contract-coverage table); the repair actions are triggered by {', '.join(tt(c) for c in sorted(triggers))}. ")
               if renamed else "")
            + ((f"Under the strict counterfactual that keeps only declared codes, this case is no longer cleared for "
                f"{', '.join(tex(m) for m in strict)}; "
                + ("counting renamed counterparts as declared, it is cleared again. " if not lenient
                   else f"counting renamed counterparts as declared, it is still not cleared for {', '.join(tex(m) for m in lenient)}. "))
               if strict else "")
            + "Trap requirement statuses (C2 $\\to$ C4): " + "; ".join(reqs) + ".")
    return write_tex(name, P("5.0cm") + P("4.2cm") + P("2.9cm") + P("3.2cm"), body, note, size=r"\footnotesize", sep="3pt")


EN_TABLES = (en_tmain_trap, en_tmain_contrasts, en_tmain_cost_baselines,
             en_tA_benchmark, en_tA_contract, en_tA_contract_json, en_tA_models, en_tA_detector, en_tA_main_full,
             en_tA_contrasts_full, en_tA_families, en_tA_cost, en_tA_redaction, en_tA_source_facts, en_tA_source_types,
             en_tA_sensitivity, en_tA_conditions, en_tA_contract_coverage, en_tA_validator, en_tA_example)


def sources_md_en(N, names):
    L = ["# paper_tables/en — data sources (generated by paper_tables.py)", "",
         "Every table in `en/` prints paper_numbers.json texts (LaTeX-escaped; percent signs and ' pp' moved into the "
         "headers; p-values as a x 10^-b), except the reads listed per table below. Same data as the Chinese tables in "
         "`zh/`; nothing is recomputed.", ""]
    for name in names:
        keys = sorted(N.used.get("en/" + name, ()))
        groups = {}
        for k in keys:
            groups[k.split(".")[0]] = groups.get(k.split(".")[0], 0) + 1
        L += [f"## en/{name}", "",
              f"- paper_numbers.json: {len(keys)} keys (" + ", ".join(f"{g} {n}" for g, n in sorted(groups.items())) + ")"]
        L += [f"- direct read: {x}" for x in N.extra.get("en/" + name, [])]
        L.append("")
    (OUT_EN / "SOURCES.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------- main

def sources_md(N, names):
    L = ["# paper_tables — data sources (generated by paper_tables.py)", "",
         "Every table in `zh/` prints paper_numbers.json texts, except the reads listed per table below. "
         "Keys are grouped by their first segment; the full list is reproducible by re-running the script.", ""]
    for name in names:
        keys = sorted(N.used.get(name, ()))
        groups = {}
        for k in keys:
            groups[k.split(".")[0]] = groups.get(k.split(".")[0], 0) + 1
        L.append(f"## zh/{name}")
        L.append("")
        L.append(f"- paper_numbers.json: {len(keys)} keys (" + ", ".join(f"{g} {n}" for g, n in sorted(groups.items())) + ")")
        for x in N.extra.get(name, []):
            L.append(f"- direct read: {x}")
        L.append("")
    (HERE / "paper_tables" / "SOURCES.md").write_text("\n".join(L), encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    N = Numbers()
    names = [f(N) for f in (tab01, tab02, tab03, tab04, tab05, tab06, tab07, tab08, tab09, tab10, tabA1, tabA2, tabA3, tabA4)]
    sources_md(N, names)
    OUT_EN.mkdir(parents=True, exist_ok=True)
    en_names = [f(N) for f in EN_TABLES]
    sources_md_en(N, en_names)
    stray = sorted(set(p.name for p in OUT.glob("*.md")) - set(names))
    stray_en = sorted(set(p.name for p in OUT_EN.glob("*.tex")) - set(en_names))
    for n in names:
        print("wrote", OUT.relative_to(HERE) / n)
    for n in en_names:
        print("wrote", OUT_EN.relative_to(HERE) / n)
    if stray:
        print("note: files in paper_tables/zh not written by this run:", ", ".join(stray))
    if stray_en:
        print("note: files in paper_tables/en not written by this run:", ", ".join(stray_en))


if __name__ == "__main__":
    main()
