#!/usr/bin/env python3
"""Figure 1 -- HRgene architecture schematic (English and Chinese versions).

    python3 paper/figures/fig1_architecture.py

Writes fig1_architecture_{en,zh}.{pdf,png,svg} next to this script (PNG at 300 dpi). The English PDF is the TMLR
figure: 6.5 in wide (= \\textwidth; include at width=\\textwidth, no scaling), all text 7-8 pt at that size, TrueType
(Type 42) fonts. The layout checker (`Canvas.check`) fails the run if any text leaves its box, overlaps other text, an
arrow or a box it does not belong to, or is set outside 7-9 pt. Deterministic: PDF CreationDate, SVG Date and PNG
Software metadata are removed and the SVG hash salt is fixed, so two runs produce byte-identical files.

What the figure shows, and where each element comes from in the frozen runtime (read-only; `check_runtime()` asserts
the structural claims before anything is drawn):
  left    rules/canonical-rules.v2.json (9 rules; fields activation / obligation / validationTarget / handling /
          severity / provenance) -> rules.py render_prose (C1) / render_contract (C2, block keys incl. checkedBy), only
          for the rules whose activation fired -> prompts.py (C0/C5 no rules; C5 = C0 request + JSON-schema `format`)
          -> paired bundle (optimizedCv + hiringEvidencePacket)
  middle  validator.py + detectors.py: one detector per ruleId in DETECTORS, all run on every bundle, lexicon driven,
          no LLM call; the rule-9 detector includes the JSON Schema check; every rule except the schema check reads a
          copy in which bare-string claims are lifted to unsourced claim objects (bundle.lift_string_items).
          Findings are FAIL / UNRESOLVED; bundle flag BLOCK (critical FAIL) > HUMAN_REVIEW (any other finding) > ACCEPT.
          detectors.py / validator.py read no contract field (the contract declares the check set only; the
          validator object still loads the contract through rules.py for the activation trace, the ruleset digest and
          the lexicon path, none of which changes a finding or the bundle flag).
  right   repair.py (one deterministic pass: route to unsupportedClaims with a follow-up, remove items, move
          subjective content to interviewSignalRisks; neutral-text and boundary-flag resets, requirement downgrade,
          gap / structure fill; every change logged) and pipeline.py (re-validate; if still BLOCK or unparsable, at most
          one regeneration with the findings, which is validated, repaired and re-validated and kept if not worse).
  bottom  frozen scorer (benchmark/v4/score.py -> scoring.py) and gold; the scorer shares textmatch negation, the
          decision lexicon and the string lifting with the validator; gold is read by neither validator nor repairer.
Condition tags: C0 JSON mode, no rules; C1 prose rules; C2 contract blocks; C3 = C2 output + validation report;
C4 = C2 output + validation + bounded repair; C5 = C0 + schema-constrained decoding. No result numbers appear.
"""
import json
import logging
import os
import sys
import warnings

sys.dont_write_bytecode = True

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.normpath(os.path.join(HERE, "..", ".."))

# ---------------------------------------------------------------- geometry (1 unit = 0.05 in = 3.6 pt)
W_IN, H_IN = 6.5, 4.85
XU, YU = W_IN * 20, H_IN * 20
UNIT_PT = 3.6
DPI = 300
FONT_MIN, FONT_MAX = 7.0, 9.0   # TMLR legibility window at final size (figure is placed at 100 %)
BODY, TITLE = 7.0, 8.0
STEP = 2.5                       # body line pitch (units) = 9 pt

# ---------------------------------------------------------------- palette (Okabe-Ito edges, light tints as fills)
INK = "#1f1f1d"
MUTED = "#55544f"
ARROW = "#45453f"
FAINT = "#85847e"
PILL = "#33332f"
GEN = ("#0072B2", "#eaf2f9")      # generation side (edge, fill)
VAL = ("#D55E00", "#fcefe6")      # validator
REP = ("#009E73", "#e6f5f0")      # repair / delivery
HUM = ("#55544f", "#f3f3f1")      # human review
EVAL = ("#85847e", "#ffffff")     # evaluation boxes
EVAL_BAND = "#eeeeeb"
STATUS = {"BLOCK": "#b3261e", "HUMAN_REVIEW": "#8a5a00", "ACCEPT": "#00754f", "FAIL": "#b3261e", "UNRESOLVED": "#8a5a00"}

CJK_CANDIDATES = ["STHeiti", "Hiragino Sans GB", "Arial Unicode MS", "PingFang SC", "Heiti SC"]
LATIN = "Arial"
MONO = "DejaVu Sans Mono"


# ---------------------------------------------------------------- runtime consistency checks (read-only)
def check_runtime():
    """Fail loudly if the figure's structural claims no longer match the frozen runtime."""
    sys.path.insert(0, os.path.join(PROJ, "runtime"))
    from hrgene import detectors, pipeline, prompts, rules  # noqa: WPS433

    with open(os.path.join(PROJ, "rules", "canonical-rules.v2.json"), encoding="utf-8") as f:
        contract = json.load(f)
    rs = contract["rules"]
    assert len(rs) == 9, "expected 9 rules"
    for r in rs:
        for k in ("activation", "obligation", "validationTarget", "handling", "severity", "provenance"):
            assert k in r, (r["ruleId"], k)
    ordered = [r["ruleId"] for r in sorted(rs, key=lambda r: r["order"])]
    assert [rid for rid, _ in detectors.DETECTORS] == ordered, "one detector per ruleId, in rule order"
    assert ordered[8] == "hrgene.paired_review_bundle_completeness", "rule 9 is the completeness rule"
    assert prompts.GENERATION_CONDITIONS == {"C0": "none", "C1": "prose", "C2": "contract", "C5": "none"}
    assert set(pipeline.ORDER) == {"ACCEPT", "HUMAN_REVIEW", "BLOCK"}
    # the C2 contract block keys shown in the obligations box
    ruleset = rules.RuleSet()
    empty_case = {"roleContext": {"jobDescription": "", "requirements": []}, "candidate": {"evidence": []}}
    rendered = ruleset.render_contract(empty_case)
    blocks = json.loads(rendered.split("\n", 1)[1])["rules"]
    assert blocks and set(blocks[0]) == {"rule", "severity", "applies", "must", "mustNot", "route", "checkedBy", "onViolation"}
    src = {n: open(os.path.join(PROJ, "runtime", "hrgene", n + ".py"), encoding="utf-8").read()
           for n in ("detectors", "validator", "scoring", "repair", "pipeline", "rules")}
    # rendering covers the active rules only; every detector runs on every bundle
    assert "only_active=True" in src["rules"] and "self.active_rules(case) if only_active" in src["rules"]
    assert "for rule_id, fn in DETECTORS:" in src["validator"]
    # the schema check lives in the rule-9 detector; bare strings are lifted for every rule but the schema check
    assert "schema_lite.validate(bundle" in src["detectors"]
    assert "B.lift_string_items(bundle)" in src["validator"] and "B.lift_string_items(bundle)" in src["scoring"]
    # bundle flag: BLOCK iff a critical FAIL; HUMAN_REVIEW for any other FAIL / UNRESOLVED
    assert 'aggregate = "BLOCK" if crit else ("HUMAN_REVIEW" if anyf else "ACCEPT")' in src["validator"]
    # detectors / validator never read contract fields; scorer and detectors share textmatch + lexicons
    for n in ("detectors", "validator"):
        for key in ("obligation", "validationTarget", "handling", "provenance", "maxRegenerations", "requiresGold", "checks", "onFail"):
            for pat in (f'["{key}"]', f'.get("{key}"', f"['{key}']", f".get('{key}'"):
                assert pat not in src[n], (n, pat)
    assert "tm.is_negated" in src["scoring"] and 'family_hits(t, lex, "decision", negation=True)' in src["scoring"]
    assert '"decision", negation=True' in src["detectors"]
    assert "gold" not in src["repair"].lower() and "import scoring" not in src["detectors"]
    # repair: route with a follow-up, move subjective content, one pass; regeneration only if still BLOCK / unparsable
    assert '"requiredFollowUp": fup' in src["repair"] and '"move_claim_to_interview_signal_risk"' in src["repair"]
    assert 'needsRegeneration=(after["aggregate"] == "BLOCK")' in src["pipeline"]
    assert 'ORDER[cand_agg] <= ORDER[final["aggregate"]]' in src["pipeline"]


# ---------------------------------------------------------------- text
# Segment kinds: t text, b bold, g grey, m mono, gm grey mono, pill (condition tag), num (numbered bullet),
# st (status token), sp (spacer). A third tuple element sets the gap before the segment in em.
TEXT = {
    "en": {
        "A_title": [("b", "Rule contract")],
        "A_file": [("gm", "canonical-rules.v2.json")],
        "A_sub": [("t", "9 rules, each with the fields:")],
        "A_fields": ["activation  τ", "obligation  d", "validation target  φ", "handling  σ/ρ", "severity", "provenance"],
        "AB": [("g", "rendered for the active rules (τ)")],
        "B_title": [("b", "Generation-side obligations")],
        "B_rows": [[("pill", "C0"), ("pill", "C5"), ("t", "no rules rendered")],
                   [("pill", "C1"), ("t", "prose: one numbered item per rule")],
                   [("pill", "C2"), ("pill", "C3"), ("pill", "C4"), ("t", "contract blocks (JSON):")]],
        "B_keys": [[("m", "must · mustNot · route ·")], [("m", "severity · applies ·")], [("m", "checkedBy · onViolation")]],
        "C_title": [("b", "LLM (Ollama, open weights)")],
        "C_rows": [[("t", "JSON-mode decoding")], [("pill", "C5"), ("t", "schema-constrained decoding")]],
        "D_title": [("b", "Paired bundle (model output)")],
        "D_rows": [[("t", "evidence-grounded CV rewrite")], [("t", "+ Hiring Evidence Packet (HEP)")]],
        "decl": [[("g", "declared check set ("), ("gm", "checkedBy", 0), ("g", ");", 0)],
                 [("g", "detectors hand-written per rule,")],
                 [("g", "reading no contract field")]],
        "V_title": [("b", "Validator (deterministic)")],
        "V_rows": [[("t", "9 detectors, one per rule ("), ("m", "ruleId", 0), ("t", "),", 0)],
                   [("t", "all run on every bundle")],
                   [("t", "lexicon-driven; no LLM calls")],
                   [("t", "rule 9 includes a JSON Schema check")],
                   [("g", "bare strings read as unsourced claims")]],
        "V_item": [("b", "Item-level findings")],
        "V_item_rows": [("FAIL", [("t", "violation")]), ("UNRESOLVED", [("t", "needs a human")])],
        "V_agg": [("b", "Bundle-level flag")],
        "V_agg_rows": [("BLOCK", [("t", "any critical FAIL")]),
                       ("HUMAN_REVIEW", [("t", "any other finding")]),
                       ("ACCEPT", [("t", "no finding")])],
        "R_title": [("b", "Bounded repair (one pass)")],
        "R_sub": [("g", "deterministic; logged; re-validated")],
        "R_items": [("1", [[("t", "route supported-side claims to")], [("m", "unsupportedClaims"), ("t", "+ follow-up")]]),
                    ("2", [[("t", "remove violating evidence and")], [("t", "decision / protected-trait items")]]),
                    ("3", [[("t", "move subjective content to")], [("m", "interviewSignalRisks")]])],
        "R_other": [[("g", "also: neutral-text and flag resets,")], [("g", "requirement downgrade, structure fill")]],
        "R_regen": [[("b", "still BLOCK or unparseable:")],
                    [("t", "one regeneration by the same model")],
                    [("t", "with the findings, validated and")],
                    [("t", "repaired again; kept if not worse")]],
        "P_title": [("b", "Repaired bundle")],
        "P_l1": [("t", "bundle + repair log + re-validation")],
        "H_title": [("b", "Qualified human review")],
        "H_l1": [("t", "no hiring decision is intended")],
        "D_S": [("pill", "C0"), ("pill", "C1"), ("pill", "C2"), ("pill", "C5")],
        "C3_S": [[("pill", "C3")], [("g", "report only")]],
        "shared": [[("g", "shares negation,")], [("g", "decision-lexicon and")], [("g", "string-lifting code")]],
        "E_label": [[("b", "Evaluation side")], [("g", "frozen; measurement only")], [("g", "gold is read by neither")],
                    [("g", "validator nor repairer")]],
        "S1_title": [("b", "Frozen scorer"), ("gm", "score.py")],
        "S1_rows": [[("t", "per case: trap failure (trap signature on the supported side, trap")],
                    [("t", "requirement overclaimed, or a family check); valid-signature retention")],
                    [("t", "substring match (case-insensitive); negated matches do not count")]],
        "S2_title": [("b", "ID-level gold (frozen)")],
        "S2_rows": [[("t", "trap signatures")], [("t", "valid signatures")], [("t", "requirement statuses")]],
        "legend": [("C0", "JSON mode, no rules"), ("C1", "C0 + prose rules"), ("C2", "C0 + contract blocks"),
                   ("C3", "C2 output + validation report"), ("C4", "C2 output + validation + repair"),
                   ("C5", "C0 + schema-constrained decoding")],
    },
    "zh": {
        "A_title": [("b", "规则契约")],
        "A_file": [("gm", "canonical-rules.v2.json")],
        "A_sub": [("t", "9 条规则，每条含以下字段：")],
        "A_fields": ["激活  τ", "生成侧义务  d", "校验目标  φ", "处置  σ/ρ", "严重度", "溯源"],
        "AB": [("g", "只渲染已激活的规则（τ）")],
        "B_title": [("b", "生成侧义务（写入提示）")],
        "B_rows": [[("pill", "C0"), ("pill", "C5"), ("t", "不渲染规则")],
                   [("pill", "C1"), ("t", "散文：每条规则一个编号条目")],
                   [("pill", "C2"), ("pill", "C3"), ("pill", "C4"), ("t", "契约块（JSON）：")]],
        "B_keys": [[("m", "must · mustNot · route ·")], [("m", "severity · applies ·")], [("m", "checkedBy · onViolation")]],
        "C_title": [("b", "LLM（Ollama，开源权重）")],
        "C_rows": [[("t", "JSON 模式解码")], [("pill", "C5"), ("t", "按 JSON Schema 约束解码")]],
        "D_title": [("b", "配对包（模型输出）")],
        "D_rows": [[("t", "证据化简历改写")], [("t", "+ 招聘证据包（HEP）")]],
        "decl": [[("g", "契约声明检查集合（"), ("gm", "checkedBy", 0), ("g", "）；", 0)],
                 [("g", "检测器按规则手写，")],
                 [("g", "不读取任何契约字段")]],
        "V_title": [("b", "校验器（确定性）")],
        "V_rows": [[("t", "9 个检测器，按"), ("m", "ruleId"), ("t", "各一个，")],
                   [("t", "每个包都运行全部检测器")],
                   [("t", "词表驱动，不调用 LLM")],
                   [("t", "规则 9 含 JSON Schema 检查")],
                   [("g", "裸字符串按无来源主张读取")]],
        "V_item": [("b", "条目级 finding")],
        "V_item_rows": [("FAIL", [("t", "违规")]), ("UNRESOLVED", [("t", "待人工判断")])],
        "V_agg": [("b", "包级标记")],
        "V_agg_rows": [("BLOCK", [("t", "存在关键 FAIL")]),
                       ("HUMAN_REVIEW", [("t", "其他 finding")]),
                       ("ACCEPT", [("t", "无 finding")])],
        "R_title": [("b", "有界修复（一次）")],
        "R_sub": [("g", "确定性；逐项记日志；修复后再校验")],
        "R_items": [("1", [[("t", "supported 侧主张改标为")], [("m", "unsupportedClaims"), ("t", "（附追问）", 0)]]),
                    ("2", [[("t", "删除违规证据项及含决策 /")], [("t", "受保护特征的条目")]]),
                    ("3", [[("t", "主观内容移入")], [("m", "interviewSignalRisks")]])],
        "R_other": [[("g", "另：中性文本与边界标志重置、")], [("g", "需求状态下调、缺口与结构补全")]],
        "R_regen": [[("b", "仍为 BLOCK 或无法解析时：")],
                    [("t", "同一模型附 findings 再生成一次，")],
                    [("t", "再经校验与修复；不劣于前者则保留")]],
        "P_title": [("b", "修复后的配对包")],
        "P_l1": [("t", "配对包 + 修复日志 + 再校验结果")],
        "H_title": [("b", "人工复核")],
        "H_l1": [("t", "系统不做录用决定")],
        "D_S": [("pill", "C0"), ("pill", "C1"), ("pill", "C2"), ("pill", "C5")],
        "C3_S": [[("pill", "C3")], [("g", "只报告")]],
        "shared": [[("g", "共享否定、决策")], [("g", "词表与字符串")], [("g", "提升代码")]],
        "E_label": [[("b", "评测侧")], [("g", "冻结，仅用于测量")], [("g", "校验器与修复器")], [("g", "不读取金标")]],
        "S1_title": [("b", "冻结评分器"), ("gm", "score.py")],
        "S1_rows": [[("t", "逐例判定陷阱失败：陷阱签名进入 supported 侧、陷阱")],
                    [("t", "需求被高报或族特定检查成立；计算有效签名保留率")],
                    [("t", "子串匹配（不区分大小写），被否定的匹配不计")]],
        "S2_title": [("b", "ID 级金标（冻结）")],
        "S2_rows": [[("t", "陷阱签名（只在诱饵中）")], [("t", "有效签名")], [("t", "需求状态")]],
        "legend": [("C0", "JSON 模式，无规则"), ("C1", "C0 + 散文规则"), ("C2", "C0 + 契约块"),
                   ("C3", "C2 产物 + 校验报告"), ("C4", "C2 产物 + 校验 + 修复"), ("C5", "C0 + schema 约束解码")],
    },
}


# ---------------------------------------------------------------- drawing helpers
class Canvas:
    def __init__(self, lang):
        self.lang = lang
        if lang == "zh":
            cjk = self._pick_cjk()
            self.sans = [LATIN, cjk]
            # STHeiti ships a light (300) and a medium (400) face: use light for body text, medium for bold.
            self.w_reg = 300 if cjk == "STHeiti" else "normal"
        else:
            self.sans = [LATIN]
            self.w_reg = "normal"
        self.fig = plt.figure(figsize=(W_IN, H_IN))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, XU)
        self.ax.set_ylim(0, YU)
        self.ax.axis("off")
        self.renderer = self.fig.canvas.get_renderer()
        self.items = []      # (kind, artist, owner-rect or None)
        self.segments = []   # arrow / line segments as rectangles, for collision checks
        self.boxes = []      # every drawn box, for checking free-standing labels

    @staticmethod
    def _pick_cjk():
        names = {f.name for f in font_manager.fontManager.ttflist}
        for n in CJK_CANDIDATES:
            if n in names:
                return n
        raise SystemExit("no CJK font found among " + ", ".join(CJK_CANDIDATES))

    # -- text primitives
    def _style(self, kind):
        """kind -> (family, weight, color)"""
        return {
            "t": (self.sans, self.w_reg, INK),
            "b": (self.sans, "bold", INK),
            "g": (self.sans, self.w_reg, MUTED),
            "m": ([MONO], "normal", INK),
            "gm": ([MONO], "normal", MUTED),
        }[kind]

    def _width(self, artist):
        bb = artist.get_window_extent(self.renderer)
        return bb.width / self.fig.dpi * 20.0

    def line(self, x, y, segs, size=BODY, ha="left", owner=None, bold_size=None):
        """Draw one line of mixed segments on a common baseline. Bold segments use `bold_size` (default: size)."""
        em = size / UNIT_PT
        placed = []
        for seg in segs:
            kind, s = seg[0], seg[1]
            gap = (seg[2] if len(seg) > 2 else 0.3) * em
            if kind == "pill":
                t = self.ax.text(0, 0, s, fontsize=BODY, color="white", ha="center", va="baseline", zorder=8,
                                 family=[LATIN], weight="bold")
                placed.append((kind, t, self._width(t) + 1.1, gap if placed else 0))
            elif kind == "num":
                t = self.ax.text(0, 0, s, fontsize=BODY, color="white", ha="center", va="baseline", zorder=8,
                                 family=[LATIN], weight="bold")
                placed.append((kind, t, 2.3, 0))
            elif kind == "st":
                t = self.ax.text(0, 0, s, fontsize=size, color=STATUS[s], ha="left", va="baseline", zorder=6,
                                 family=[MONO], weight="bold")
                placed.append((kind, t, self._width(t), gap if placed else 0))
            elif kind == "sp":
                placed.append((kind, None, 1.6 * em, 0))
            else:
                fam, wt, col = self._style(kind)
                fs = (bold_size or size) if kind == "b" else size
                t = self.ax.text(0, 0, s, fontsize=fs, color=col, ha="left", va="baseline", zorder=6, family=fam, weight=wt)
                placed.append((kind, t, self._width(t), gap if placed else 0))
        total, prev, widths = 0.0, None, []
        for kind, t, w, gap in placed:
            if prev in ("pill", "num"):
                gap = 0.4 if kind == "pill" else 0.7
            widths.append((kind, t, w, gap))
            total += gap + w
            prev = kind
        x0 = {"left": x, "center": x - total / 2, "right": x - total}[ha]
        cx = x0
        cap = 0.36 * BODY / UNIT_PT      # half the cap height of 7 pt text, in units
        for kind, t, w, gap in widths:
            cx += gap
            if kind == "pill":
                h = 2.25
                yc = y + cap
                patch = FancyBboxPatch((cx, yc - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.6",
                                       fc=PILL, ec="none", zorder=7)
                self.ax.add_patch(patch)
                t.set_position((cx + w / 2, y))
                self.items.append(("pill", patch, owner))
            elif kind == "num":
                yc = y + cap
                c = Circle((cx + 1.15, yc), 1.15, fc=REP[0], ec="none", zorder=7)
                self.ax.add_patch(c)
                t.set_position((cx + 1.15, y))
                self.items.append(("pill", c, owner))
            elif t is not None:
                t.set_position((cx, y))
                self.items.append(("text", t, owner))
            cx += w
        return cx

    def lines(self, x, y, rows, step=STEP, **kw):
        for i, segs in enumerate(rows):
            self.line(x, y - i * step, segs, **kw)
        return y - (len(rows) - 1) * step

    # -- shapes
    def box(self, x0, y0, x1, y1, colors, lw=0.9, ls="-", r=1.1, z=2, register=True):
        ec, fc = colors
        p = FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle=f"round,pad=0,rounding_size={r}",
                           fc=fc, ec=ec, lw=lw, ls=ls, zorder=z)
        self.ax.add_patch(p)
        if register:
            self.boxes.append((x0, y0, x1, y1))
        return (x0, y0, x1, y1)

    def arrow(self, p0, p1, color=ARROW, lw=0.9, ls="-", head=True):
        style = "-|>" if head else "-"
        a = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=8, lw=lw, color=color, ls=ls,
                            shrinkA=0, shrinkB=0, zorder=4, joinstyle="miter", capstyle="butt")
        self.ax.add_patch(a)
        self._seg(p0, p1)

    def polyline(self, pts, color=ARROW, lw=0.9, ls="-"):
        xs, ys = zip(*pts)
        self.ax.add_line(Line2D(xs, ys, color=color, lw=lw, ls=ls, zorder=4, solid_capstyle="butt",
                                dash_capstyle="butt"))
        for a, b in zip(pts, pts[1:]):
            self._seg(a, b)

    def _seg(self, a, b, pad=0.3):
        self.segments.append((min(a[0], b[0]) - pad, min(a[1], b[1]) - pad, max(a[0], b[0]) + pad, max(a[1], b[1]) + pad))

    # -- layout checks
    def _bbox_units(self, artist):
        bb = artist.get_window_extent(self.renderer)
        inv = self.ax.transData.inverted()
        (x0, y0), (x1, y1) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
        return (x0, y0, x1, y1)

    def check(self):
        problems = []
        boxes = [(k, self._bbox_units(a), o, a) for k, a, o in self.items]
        texts = [(bb, o, a) for k, bb, o, a in boxes if k == "text"]
        pills = [(bb, o, a) for k, bb, o, a in boxes if k == "pill"]

        def ov(a, b, tol=0.05):
            return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol

        def name(a):
            return a.get_text() if hasattr(a, "get_text") else "pill"

        for t in self.ax.texts:
            if not FONT_MIN <= t.get_fontsize() <= FONT_MAX:
                problems.append(f"font size {t.get_fontsize()} pt outside {FONT_MIN}-{FONT_MAX}: {t.get_text()!r}")
        for bb, o, a in texts + pills:
            label = name(a)
            if bb[0] < 0.3 or bb[1] < 0.3 or bb[2] > XU - 0.3 or bb[3] > YU - 0.3:
                problems.append(f"outside figure: {label!r}")
            if o is not None:
                m = 0.45
                if bb[0] < o[0] + m or bb[2] > o[2] - m or bb[1] < o[1] + m or bb[3] > o[3] - m:
                    problems.append(f"outside its box: {label!r} {tuple(round(v, 2) for v in bb)} vs {o}")
            else:
                for bx in self.boxes:
                    if ov(bb, (bx[0] - 0.3, bx[1] - 0.3, bx[2] + 0.3, bx[3] + 0.3)):
                        problems.append(f"free label touches a box: {label!r} vs {bx}")
            for s in self.segments:
                if ov(bb, s):
                    problems.append(f"crosses an arrow/line: {label!r}")
        allb = texts + pills
        for i in range(len(allb)):
            for j in range(i + 1, len(allb)):
                a, b = allb[i], allb[j]
                if ov(a[0], b[0]):
                    ta, tb = name(a[2]), name(b[2])
                    # a pill / bullet and its own label overlap by construction
                    if "pill" in (ta, tb) and (ta in ("C0", "C1", "C2", "C3", "C4", "C5", "1", "2", "3") or
                                               tb in ("C0", "C1", "C2", "C3", "C4", "C5", "1", "2", "3")):
                        continue
                    problems.append(f"overlap: {ta!r} / {tb!r}")
        return problems


# ---------------------------------------------------------------- figure
def draw(lang):
    T = TEXT[lang]
    cv = Canvas(lang)
    PAD = 1.3                    # text inset inside a box (units)

    LX0, LX1 = 1.5, 40.5
    MX0, MX1 = 49.0, 85.5
    RX0, RX1 = 92.5, XU - 1.5
    BAND_TOP = 15.8
    TOP = YU - 1.8

    def title_row(y, segs, owner):
        cv.line(owner[0] + PAD, y, segs, owner=owner, bold_size=TITLE)

    # ---- left column: contract -> obligations -> LLM -> paired bundle
    A = cv.box(LX0, TOP - 20.2, LX1, TOP, GEN)
    y = TOP - 2.7
    title_row(y, T["A_title"], A)
    cv.line(LX0 + PAD, y - 2.6, T["A_file"], owner=A)
    cv.line(LX0 + PAD, y - 5.1, T["A_sub"], owner=A)
    fw = (LX1 - LX0 - 2 * PAD - 1.0) / 2
    for i, label in enumerate(T["A_fields"]):
        col, row = i % 2, i // 2
        fx0 = LX0 + PAD + col * (fw + 1.0)
        fy1 = y - 6.4 - row * 3.3
        chip = cv.box(fx0, fy1 - 2.9, fx0 + fw, fy1, (GEN[0], "#ffffff"), lw=0.6, r=0.7, z=3)
        cv.line(fx0 + fw / 2, fy1 - 2.05, [("t", label)], ha="center", owner=chip)

    B_TOP = A[1] - 3.6
    cv.arrow((8.0, A[1]), (8.0, B_TOP))
    cv.line(9.4, A[1] - 2.4, T["AB"])
    B = cv.box(LX0, B_TOP - 19.6, LX1, B_TOP, GEN)
    y = B_TOP - 2.7
    title_row(y, T["B_title"], B)
    y = cv.lines(LX0 + PAD, y - 2.8, T["B_rows"], step=2.65, owner=B)
    cv.lines(LX0 + PAD + 2.6, y - 2.6, T["B_keys"], step=2.4, owner=B)

    C_TOP = B[1] - 3.0
    cv.arrow((20.0, B[1]), (20.0, C_TOP))
    C = cv.box(LX0, C_TOP - 9.8, LX1, C_TOP, GEN)
    title_row(C_TOP - 2.7, T["C_title"], C)
    cv.lines(LX0 + PAD, C_TOP - 5.4, T["C_rows"], step=2.65, owner=C)

    D_TOP = C[1] - 3.0
    cv.arrow((20.0, C[1]), (20.0, D_TOP))
    D = cv.box(LX0, D_TOP - 9.6, LX1, D_TOP, GEN)
    title_row(D_TOP - 2.7, T["D_title"], D)
    cv.lines(LX0 + PAD, D_TOP - 5.3, T["D_rows"], owner=D)

    # ---- declaration link: contract -> validator (dashed; declares the check set, not read at run time)
    V_TOP = TOP - 15.0
    DECL_Y = TOP - 4.8
    cv.polyline([(LX1, DECL_Y), (82.5, DECL_Y), (82.5, V_TOP + 1.6)], color=FAINT, lw=0.8, ls=(0, (3, 2)))
    cv.arrow((82.5, V_TOP + 1.8), (82.5, V_TOP), color=FAINT, lw=0.8)
    cv.lines(MX0 + 0.6, DECL_Y - 2.9, T["decl"])

    # ---- validator
    V = cv.box(MX0, D[1], MX1, V_TOP, VAL)
    y = V_TOP - 2.7
    title_row(y, T["V_title"], V)
    y = cv.lines(MX0 + PAD, y - 2.7, T["V_rows"], owner=V)
    IX0, IX1 = MX0 + 1.2, MX1 - 1.2
    VI_H, VA_H = 9.4, 11.5
    gap = (y - 0.8 - V[1] - VI_H - VA_H) / 3       # spread the two sub-boxes over the validator's height
    assert gap > 1.6, "validator content does not fit"
    VI = cv.box(IX0, y - 0.8 - gap - VI_H, IX1, y - 0.8 - gap, (VAL[0], "#ffffff"), lw=0.6, r=0.7, z=3)
    cv.line(IX0 + 1.2, VI[3] - 2.4, T["V_item"], owner=VI)
    for i, (tok, desc) in enumerate(T["V_item_rows"]):
        yy = VI[3] - 4.9 - i * STEP
        cv.line(IX0 + 1.2, yy, [("st", tok)], owner=VI)
        cv.line(IX0 + 1.2 + 15.3, yy, desc, owner=VI)
    VA = cv.box(IX0, VI[1] - gap - VA_H, IX1, VI[1] - gap, (VAL[0], "#ffffff"), lw=0.6, r=0.7, z=3)
    cv.line(IX0 + 1.2, VA[3] - 2.4, T["V_agg"], owner=VA)
    for i, (tok, desc) in enumerate(T["V_agg_rows"]):
        yy = VA[3] - 4.9 - i * STEP
        cv.line(IX0 + 1.2, yy, [("st", tok)], owner=VA)
        cv.line(IX0 + 1.2 + 15.3, yy, desc, owner=VA)

    # paired bundle -> validator (C3, C4)
    DV_Y = D[1] + 3.2
    cv.arrow((LX1, DV_Y), (MX0, DV_Y))
    cv.line((LX1 + MX0) / 2, DV_Y + 1.5, [("pill", "C3"), ("pill", "C4")], ha="center")

    # ---- condition legend (top right)
    for i, (c, desc) in enumerate(T["legend"]):
        cv.line(RX0 + 0.3, TOP - 1.6 - i * STEP, [("pill", c), ("g", desc)])

    # ---- bounded repair
    R_TOP = TOP - 1.6 - 5 * STEP - 2.3
    n_regen = len(T["R_regen"])
    R_H = 2.7 + 2.5 + 3 * (2 * STEP + 0.35) + 2 * STEP + 0.2 + (n_regen * STEP + 2.2) + 2.1
    R = cv.box(RX0, R_TOP - R_H, RX1, R_TOP, REP)
    x = RX0 + PAD
    y = R_TOP - 2.7
    title_row(y, T["R_title"], R)
    cv.line(x, y - 2.5, T["R_sub"], owner=R)
    y -= 2.5
    for num, rows in T["R_items"]:
        y -= STEP + 0.35
        cv.line(x, y, [("num", num)] + rows[0], owner=R)
        cv.line(x + 3.0, y - STEP, rows[1], owner=R)
        y -= STEP
    y = cv.lines(x, y - STEP - 0.2, T["R_other"], owner=R)
    RG = cv.box(RX0 + 1.2, y - 1.3 - n_regen * STEP - 0.9, RX1 - 1.2, y - 1.3, (REP[0], "#ffffff"), lw=0.6,
                ls=(0, (2.5, 1.6)), r=0.7, z=3)
    cv.lines(RX0 + 2.4, RG[3] - 2.4, T["R_regen"], owner=RG)
    assert RG[1] > R[1] + 0.8, "repair content does not fit"

    # validator <-> repair (C4)
    VR_Y = R_TOP - 8.0
    cv.arrow((MX1, VR_Y), (RX0, VR_Y))
    cv.line((MX1 + RX0) / 2, VR_Y + 1.5, [("pill", "C4")], ha="center")
    cv.arrow((RX0, VR_Y - 5.0), (MX1, VR_Y - 5.0))

    # ---- repaired bundle; human review
    P = cv.box(RX0, R[1] - 2.6 - 6.8, RX1, R[1] - 2.6, REP)
    cv.arrow(((RX0 + RX1) / 2, R[1]), ((RX0 + RX1) / 2, P[3]))
    title_row(P[3] - 2.6, T["P_title"], P)
    cv.line(RX0 + PAD, P[3] - 5.1, T["P_l1"], owner=P)
    Hb = cv.box(RX0, P[1] - 2.6 - 6.8, RX1, P[1] - 2.6, HUM)
    cv.arrow(((RX0 + RX1) / 2, P[1]), ((RX0 + RX1) / 2, Hb[3]))
    title_row(Hb[3] - 2.6, T["H_title"], Hb)
    cv.line(RX0 + PAD, Hb[3] - 5.1, T["H_l1"], owner=Hb)
    assert Hb[1] > BAND_TOP + 3.2, f"right column does not fit above the evaluation band ({Hb[1]:.2f})"

    # ---- evaluation band
    band = FancyBboxPatch((0.8, 0.8), XU - 1.6, BAND_TOP - 0.8, boxstyle="round,pad=0,rounding_size=1.0",
                          fc=EVAL_BAND, ec="none", zorder=0)
    cv.ax.add_patch(band)
    S1 = cv.box(28.5, 1.9, 91.5, BAND_TOP - 1.1, EVAL, lw=0.8)
    S2 = cv.box(96.5, 1.9, RX1, BAND_TOP - 1.1, EVAL, lw=0.8)
    cv.arrow((S2[0], 7.6), (S1[2], 7.6))
    lab = T["E_label"]
    cv.line(2.4, S1[3] - 2.6, lab[0], bold_size=TITLE)
    cv.lines(2.4, S1[3] - 5.2, lab[1:], step=2.4)
    cv.line(S1[0] + PAD, S1[3] - 2.6, T["S1_title"], owner=S1, bold_size=TITLE)
    cv.lines(S1[0] + PAD, S1[3] - 5.2, T["S1_rows"], step=2.4, owner=S1)
    cv.line(S2[0] + PAD, S2[3] - 2.6, T["S2_title"], owner=S2, bold_size=TITLE)
    cv.lines(S2[0] + PAD, S2[3] - 5.2, T["S2_rows"], step=2.4, owner=S2)

    # flows into the scorer
    cv.arrow((33.0, D[1]), (33.0, S1[3]))                         # C0 C1 C2 C5 bundles
    cv.line(31.6, (D[1] + S1[3]) / 2 - 0.7, T["D_S"], ha="right")
    cv.arrow((77.0, V[1]), (77.0, S1[3]))                         # C3: C2 bundle + report
    cv.line(78.3, V[1] - 3.3, T["C3_S"][0])
    cv.line(78.3, V[1] - 5.9, T["C3_S"][1])
    cv.polyline([(RX0, (P[1] + P[3]) / 2), (89.5, (P[1] + P[3]) / 2), (89.5, S1[3] + 0.9)])   # C4: repaired bundle
    cv.arrow((89.5, S1[3] + 1.0), (89.5, S1[3]))
    cv.line(90.7, S1[3] + 1.9, [("pill", "C4")])
    # shared matching code between scorer and validator (dashed, no direction)
    cv.polyline([(53.0, S1[3]), (53.0, V[1])], color=FAINT, lw=0.8, ls=(0, (3, 2)))
    cv.lines(54.3, V[1] - 2.9, T["shared"], step=2.4)
    return cv


def save(cv, lang):
    base = os.path.join(HERE, f"fig1_architecture_{lang}")
    cv.fig.savefig(base + ".svg", format="svg", metadata={"Date": None})
    cv.fig.savefig(base + ".pdf", format="pdf", metadata={"CreationDate": None})
    cv.fig.savefig(base + ".png", format="png", dpi=DPI, metadata={"Software": None})
    plt.close(cv.fig)
    return [base + ext for ext in (".svg", ".pdf", ".png")]


def main():
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    plt.rcParams.update({
        "svg.hashsalt": "hrgene-v4-fig1",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
        "path.simplify": False,
    })
    check_runtime()
    written = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for lang in ("en", "zh"):
            cv = draw(lang)
            problems = cv.check()
            if problems:
                for p in problems:
                    print(f"[{lang}] layout: {p}", file=sys.stderr)
                raise SystemExit(f"layout check failed for {lang} ({len(problems)} problem(s))")
            written += save(cv, lang)
    glyph = [str(w.message) for w in caught if "Glyph" in str(w.message) or "missing from" in str(w.message)]
    if glyph:
        raise SystemExit("missing glyphs: " + "; ".join(sorted(set(glyph))[:5]))
    for p in written:
        print(os.path.relpath(p, PROJ))


if __name__ == "__main__":
    main()
