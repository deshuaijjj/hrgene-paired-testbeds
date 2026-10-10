#!/usr/bin/env python3
"""Paired contrasts of the gold trap failure (trapFellAny) on risk cases, with Newcombe (1998) intervals.

Reads the formal runs straight from experiments/*-full/score_rows.jsonl — the same run set as collect.py
(three models x C0-C5; C3b/C4b version checks, pilots and smokes excluded; C3 = C2 outputs re-validated
offline, taken from the C2 score rows plus the C3 validation reports). Nothing is regenerated or rescored.

(1) Per model, risk cases, trapFellAny: C0->C1, C1->C2, C0->C2, C2->C4, C0->C4, C0->C5. Paired n (both arms
    scorable), repaired b, new c, unchanged fail / pass, both paired rates, difference after - before (pp),
    Newcombe (1998) method-10 95% CI for the paired difference, exact two-sided McNemar p.
(2) Clearance C2->C4 = b / (C2 failures among paired cases), Wilson 95% CI; per model and pooled.
(3) Three models pooled by stacking pairs: C1->C2, C0->C5, C0->C2, C2->C4.
(4) Descriptive C2->C4 family counts (no tests): decision family vs the other five, and each family.
(5) Package-level validator flag rate (aggregate BLOCK or HUMAN_REVIEW), risk vs control, for C3 (= C2
    outputs) and the generation conditions C0, C1, C5 (their flags are offline scores).
(6) Assertion: wherever c = 0, the exact McNemar p equals min(1, 2 * 0.5**b) (sign test on b discordant
    pairs); reported for every contrast into C4.
Standard library only; deterministic (no resampling). Writes tab4_contrasts.json / .md next to this file.
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXPERIMENTS = ROOT / "experiments"
Z = 1.959963984540054  # two-sided 95% normal quantile
RISK, CONTROL = "positive_risk", "matched_clean_control"
DECISION_FAMILY = "decision_ranking_protected_human_review_boundary"
CONDITIONS = ("C0", "C1", "C2", "C3", "C4", "C5")
MODEL_CONTRASTS = (("C0", "C1"), ("C1", "C2"), ("C0", "C2"), ("C2", "C4"), ("C0", "C4"), ("C0", "C5"))
POOLED_CONTRASTS = (("C1", "C2"), ("C0", "C5"), ("C0", "C2"), ("C2", "C4"))
FLAG_CONDITIONS = ("C0", "C1", "C3", "C5")
FLAGGED = ("BLOCK", "HUMAN_REVIEW")

# Newcombe (1998) Stat Med 17:2635-2650, Table III: (e, f, g, h) -> method 8 and method 10 limits (4 d.p.).
# Used only as a self-test of the implementation below; not a result of this study.
NEWCOMBE_TABLE_III = (
    ((36, 12, 2, 0), (0.0569, 0.3404), (0.0569, 0.3404)),
    ((20, 12, 2, 16), (0.0618, 0.3242), (0.0562, 0.3292)),
    ((18, 12, 2, 18), (0.0618, 0.3239), (0.0562, 0.3290)),
    ((36, 14, 0, 0), (0.1528, 0.4167), (0.1528, 0.4167)),
    ((35, 14, 0, 1), (0.1573, 0.4149), (0.1461, 0.4175)),
    ((18, 14, 0, 18), (0.1504, 0.3910), (0.1441, 0.3963)),
    ((2, 97, 1, 0), (0.8721, 0.9854), (0.8721, 0.9854)),
    ((1, 97, 1, 1), (0.8737, 0.9850), (0.8736, 0.9850)),
    ((0, 29, 1, 0), (0.6666, 0.9882), (0.6666, 0.9882)),
    ((2, 98, 0, 0), (0.9178, 0.9945), (0.9178, 0.9945)),
    ((1, 98, 0, 1), (0.9174, 0.9916), (0.9171, 0.9916)),
    ((0, 30, 0, 0), (0.8395, 1.0), (0.8395, 1.0)),
)


# ---------------------------------------------------------------- statistics

def wilson(k, n):
    """Wilson score interval without continuity correction (roots of |pi - p| = z sqrt(pi(1-pi)/n))."""
    if not n:
        return None, None
    p = k / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def newcombe_paired(e, f, g, h, corrected_phi=True):
    """Newcombe (1998) square-and-add interval for theta = (e+f)/n - (e+g)/n on a paired 2x2 table.

    e = both positive, f = positive on the first proportion only, g = positive on the second only, h = both
    negative. Wilson intervals (no continuity correction) for both marginals; phi = (eh - fg)/sqrt(margins),
    0 if any margin is 0. corrected_phi=True is method 10 (numerator replaced by max(eh - fg - n/2, 0) when
    eh > fg); False is method 8 (plain phi).
    """
    n = e + f + g + h
    p1, p2 = (e + f) / n, (e + g) / n
    l1, u1 = wilson(e + f, n)
    l2, u2 = wilson(e + g, n)
    denom = (e + f) * (g + h) * (e + g) * (f + h)
    num = e * h - f * g
    if corrected_phi and num > 0:
        num = max(num - n / 2, 0.0)
    phi = 0.0 if denom == 0 else num / math.sqrt(denom)
    theta = p1 - p2
    dl1, du1, dl2, du2 = p1 - l1, u1 - p1, p2 - l2, u2 - p2
    lower = theta - math.sqrt(max(0.0, dl1 * dl1 - 2 * phi * dl1 * du2 + du2 * du2))
    upper = theta + math.sqrt(max(0.0, du1 * du1 - 2 * phi * du1 * dl2 + dl2 * dl2))
    return max(-1.0, lower), min(1.0, upper)


def mcnemar_exact(b, c):
    """Exact two-sided McNemar p: 2 * P(X <= min(b, c)), X ~ Bin(b + c, 1/2), capped at 1 (as tab4_stats.py)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def self_test():
    for cells, m8, m10 in NEWCOMBE_TABLE_III:
        for corrected, ref in ((False, m8), (True, m10)):
            got = newcombe_paired(*cells, corrected_phi=corrected)
            # 1.5e-4: the published table is rounded (one cell is truncated) to four decimals.
            if any(abs(x - y) > 1.5e-4 for x, y in zip(got, ref)):
                raise SystemExit(f"Newcombe self-test failed for {cells} method {10 if corrected else 8}: {got} vs {ref}")
    return len(NEWCOMBE_TABLE_III)


# ---------------------------------------------------------------- run discovery (same set as collect.py)

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def model_of(run_dir):
    cfg = run_dir / "config.json"
    if cfg.exists():
        c = read_json(cfg)
        model = c.get("model") or (c.get("identity") or {}).get("model")
        if model:
            return model
    summ = run_dir / "summary.json"
    if summ.exists():
        src = read_json(summ).get("sourceRun")
        if src and (run_dir.parent / Path(src).name).is_dir():
            return model_of(run_dir.parent / Path(src).name)
    raise SystemExit(f"{run_dir.name}: cannot resolve model")


def score_rows(run_dir, condition):
    rows = [json.loads(s) for s in (run_dir / "score_rows.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    summary = read_json(run_dir / "score.json")
    if len(rows) != summary["n"]:
        raise SystemExit(f"{run_dir.name}: score row count differs from score.json")
    cfg = run_dir / "config.json"
    if cfg.exists() and read_json(cfg).get("n_requests") not in (None, len(rows)):
        raise SystemExit(f"{run_dir.name}: incomplete score")
    by_case = {r["caseId"]: r for r in rows}
    if len(by_case) != len(rows) or any(r["condition"] != condition for r in rows):
        raise SystemExit(f"{run_dir.name}: duplicate case ids or unexpected condition label")
    return by_case


def discover():
    runs = {}
    for path in sorted(EXPERIMENTS.glob("*-full")):
        cond = path.name.split("-")[-2]
        if not path.is_dir() or cond not in CONDITIONS:
            continue  # C3b / C4b are version checks, not conditions
        key = (model_of(path), cond)
        if key in runs:
            raise SystemExit(f"two formal runs for {key}: {runs[key].name}, {path.name}")
        runs[key] = path
    models = sorted({m for m, _ in runs}, key=lambda m: (min(runs[(m, c)].name[:8] for c in CONDITIONS if (m, c) in runs), m))
    for m in models:
        missing = [c for c in CONDITIONS if (m, c) not in runs]
        if missing:
            raise SystemExit(f"{m}: missing formal runs for {missing}")
    return models, runs


def load_model(model, runs):
    rows = {c: score_rows(runs[(model, c)], c) for c in ("C0", "C1", "C2", "C4", "C5")}
    c2_name = runs[(model, "C2")].name
    for derived in ("C3", "C4"):
        src = read_json(runs[(model, derived)] / "summary.json").get("sourceRun")
        if Path(src).name != c2_name:
            raise SystemExit(f"{model} {derived}: sourceRun {src} is not the formal C2 run {c2_name}")
    # C3: the C2 score rows with the package flag taken from the offline C3 validation reports.
    reports = [read_json(p) for p in sorted((runs[(model, "C3")] / "validations").glob("*.json"))]
    by_case = {r["case_id"]: r for r in reports}
    if len(by_case) != len(reports) or set(by_case) != set(rows["C2"]):
        raise SystemExit(f"{model} C3: validation report coverage differs from C2")
    c3 = {}
    for cid, original in rows["C2"].items():
        rep = by_case[cid]
        flagged = rep["validation"]["aggregate"] in FLAGGED
        if rep["request_id"] != original["requestId"] or flagged != original["validatorFlagged"]:
            raise SystemExit(f"{model} C3: report differs from C2 score row for {cid}")
        c3[cid] = {**original, "condition": "C3", "validatorFlagged": flagged}
    rows["C3"] = c3
    ref = rows["C2"]
    for cond, rs in rows.items():
        if set(rs) != set(ref) or any((rs[i]["controlStatus"], rs[i]["family"]) != (ref[i]["controlStatus"], ref[i]["family"]) for i in ref):
            raise SystemExit(f"{model} {cond}: case set or case metadata differs from C2")
    return rows


# ---------------------------------------------------------------- contrasts

def pair_counts(before, after, ids=None):
    """Risk cases with trapFellAny non-null under both conditions. Returns cell counts and paired ids."""
    ids = sorted(i for i in (ids if ids is not None else before)
                 if before[i]["controlStatus"] == RISK and before[i].get("trapFellAny") is not None
                 and after[i].get("trapFellAny") is not None)
    a = sum(1 for i in ids if before[i]["trapFellAny"] and after[i]["trapFellAny"])
    b = sum(1 for i in ids if before[i]["trapFellAny"] and not after[i]["trapFellAny"])
    c = sum(1 for i in ids if not before[i]["trapFellAny"] and after[i]["trapFellAny"])
    cells = {"a": a, "b": b, "c": c, "d": len(ids) - a - b - c}
    cells["newCaseIds"] = [i for i in ids if not before[i]["trapFellAny"] and after[i]["trapFellAny"]]
    return cells, ids


def marginal(rows):
    vals = [r["trapFellAny"] for r in rows.values() if r["controlStatus"] == RISK and r.get("trapFellAny") is not None]
    k, n = sum(bool(v) for v in vals), len(vals)
    return {"k": k, "n": n, "p": k / n if n else None}


def sign_identity(b, c):
    """If one discordant cell is 0, exact McNemar reduces to 2 * 0.5**k with k the other cell."""
    if min(b, c) != 0:
        return {"applies": False}
    k = max(b, c)
    expected = min(1.0, 2 * 0.5 ** k)
    p = mcnemar_exact(b, c)
    if not math.isclose(p, expected, rel_tol=1e-12, abs_tol=0.0):
        raise SystemExit(f"McNemar identity failed: b={b} c={c} p={p} 2*0.5^k={expected}")
    return {"applies": True, "k": k, "twoTimesHalfPowK": expected, "holds": True}


def contrast(cells, before_rows=None, after_rows=None):
    a, b, c, d = cells["a"], cells["b"], cells["c"], cells["d"]
    n = a + b + c + d
    # Newcombe notation with the first proportion = after: e = both fail, f = new, g = repaired, h = both pass.
    lo, hi = newcombe_paired(a, c, b, d, corrected_phi=True)
    lo8, hi8 = newcombe_paired(a, c, b, d, corrected_phi=False)
    out = {"pairedN": n, "repaired": b, "new": c, "unchangedFail": a, "unchangedPass": d,
           "before": {"k": a + b, "p": (a + b) / n}, "after": {"k": a + c, "p": (a + c) / n},
           "diff": (c - b) / n, "diffPP": 100 * (c - b) / n,
           "ciPP": [100 * lo, 100 * hi], "ciMethod": "Newcombe 1998 method 10",
           "ciPP_method8_uncorrectedPhi": [100 * lo8, 100 * hi8],
           "discordant": b + c, "exactP": mcnemar_exact(b, c), "signIdentity": sign_identity(b, c)}
    if "newCaseIds" in cells:
        out["newCaseIds"] = cells["newCaseIds"]
    if before_rows is not None:
        out["marginalBefore"] = marginal(before_rows)
        out["marginalAfter"] = marginal(after_rows)
    return out


def add_cells(x, y):
    return {k: x[k] + y[k] for k in "abcd"}


def family_counts(rows_c2, rows_c4, families):
    groups = [("decisionFamily", {DECISION_FAMILY}), ("otherFiveFamilies", set(families) - {DECISION_FAMILY})]
    groups += [(f"family:{f}", {f}) for f in families]
    out = {}
    for name, fams in groups:
        ids = [i for i in rows_c2 if rows_c2[i]["family"] in fams]
        cells, paired = pair_counts(rows_c2, rows_c4, ids)
        out[name] = {"families": sorted(fams), "pairedN": len(paired), "repaired": cells["b"], "new": cells["c"],
                     "c2Failures": cells["a"] + cells["b"], "c4Failures": cells["a"] + cells["c"]}
    return out


def flag_rates(rows):
    out = {}
    for status, label in ((RISK, "risk"), (CONTROL, "control")):
        sel = [r for r in rows.values() if r["controlStatus"] == status]
        k = sum(1 for r in sel if r["validatorFlagged"])
        lo, hi = wilson(k, len(sel))
        out[label] = {"k": k, "n": len(sel), "p": k / len(sel), "lo": lo, "hi": hi,
                      "unparsed": sum(1 for r in sel if not r["parsed"]),
                      "unparsedFlagged": sum(1 for r in sel if not r["parsed"] and r["validatorFlagged"])}
    return out


# ---------------------------------------------------------------- consistency with existing products

def crosscheck_existing(report):
    checks = {}
    stats_path = HERE / "tab4_stats.json"
    if stats_path.exists():
        stats = read_json(stats_path)
        n_ok = 0
        for model, entry in stats.get("models", {}).items():
            for name, t in entry.get("mcnemar", {}).items():
                mine = report["models"][model]["contrasts"][name]
                fields = ("pairedN", "repaired", "new", "unchangedFail", "unchangedPass")
                if any(t[f] != mine[f] for f in fields) or not math.isclose(t["exactP"], mine["exactP"], rel_tol=1e-12):
                    raise SystemExit(f"{model} {name}: differs from tab4_stats.json")
                n_ok += 1
        checks["tab4_stats.json mcnemar contrasts"] = {"checked": n_ok, "allEqual": True}
    results_path = HERE / "results.json"
    if results_path.exists():
        n_ok = 0
        for r in read_json(results_path):
            m, cond = r["model"], r["condition"]
            if m not in report["models"]:
                continue
            flags = report["models"][m]["flagRates"].get(cond)
            if flags is not None:
                k = flags["risk"]["k"] + flags["control"]["k"]
                if abs(k / (flags["risk"]["n"] + flags["control"]["n"]) - r["validatorFlagged"]) > 1e-9:
                    raise SystemExit(f"{m} {cond}: flag rate differs from results.json")
                n_ok += 1
            for name, t in report["models"][m]["contrasts"].items():
                for side, c in (("marginalBefore", name.split("->")[0]), ("marginalAfter", name.split("->")[1])):
                    if c == cond and abs(t[side]["p"] - r["trapFellAny"]) > 1e-9:
                        raise SystemExit(f"{m} {cond}: trapFellAny differs from results.json")
        checks["results.json validatorFlagged and trapFellAny"] = {"flagRowsChecked": n_ok, "allEqual": True}
    return checks


# ---------------------------------------------------------------- output

def pp(v):
    return f"{v:+.1f}"


def pct(v):
    return f"{100 * v:.1f}"


def fmt_p(p):
    return f"{p:.2e}" if p < 1e-3 else f"{p:.3f}"


def contrast_row(label, t):
    ci = f"[{pp(t['ciPP'][0])}, {pp(t['ciPP'][1])}]"
    if t["discordant"] == 0:
        ci += " †"
    return (f"| {label} | {t['pairedN']} | {t['repaired']} | {t['new']} | {t['unchangedFail']} | {t['unchangedPass']} | "
            f"{pct(t['before']['p'])} ({t['before']['k']}) | {pct(t['after']['p'])} ({t['after']['k']}) | "
            f"{pp(t['diffPP'])} {ci} | {fmt_p(t['exactP'])} |")


def write_md(report):
    models = report["modelOrder"]
    md = ["# 风险案例配对对比、清除率与包级标记（tab4_contrasts.py 生成）", "",
          "定义与分母：陷阱失败 = 冻结评分器的 `trapFellAny`（金标陷阱失败事件，含签名命中、需求状态越界与分族额外规则），"
          "只在风险案例（positive_risk，每模型 72 例）上定义，不可解析产物为空值。配对对比 X→Y 的配对 n = 在 X 与 Y 下 `trapFellAny` 都非空的风险案例数；"
          "修复 b = X 失败且 Y 未失败的配对案例数，新增 c = X 未失败且 Y 失败，同失败 = 两者都失败，同通过 = 两者都未失败；"
          "两条件的率 = 该条件失败数 / 配对 n（括号内为失败数）；差值 = (c − b) / 配对 n，即后 − 前，单位 pp。"
          "95% CI 为 Newcombe (1998) 配对差方法 10：两个边际率各取无连续性校正的 Wilson 区间，用 φ 系数平方相加合成，"
          "φ 的分子 ad − bc 在 ad > bc 时换成 max(ad − bc − n/2, 0)，任一边际为 0 时 φ = 0（标准库自实现，并对 Newcombe 1998 表 III 的方法 8/10 数值自检通过）。"
          "p 为精确 McNemar 双侧 p = min(1, 2·P(X ≤ min(b, c)))，X ~ Bin(b + c, 1/2)。"
          "清除率 = C2→C4 的 b / C2 失败的配对案例数（= b + 同失败），Wilson 95% CI。"
          "三模型合并 = 把三个模型的配对案例堆叠成一个 2×2 表后计算同样的量（案例在模型间重复出现，合并不是独立样本）。"
          "分族计数只描述、不检验（每族 12 个风险案例）。包级标记率 = 校验器聚合结论为 BLOCK 或 HUMAN_REVIEW 的案例数 / 该组全部案例（风险 72、对照 72，含不可解析产物；不可解析产物一律被标记）；"
          "C3 = 对冻结 C2 产物的离线校验，C0、C1、C5 的标记同样是生成后离线打分，生成时没有执行校验。包级标记不是检测指标。", ""]

    md += ["## 1. 逐模型配对对比（风险案例，trapFellAny）", "",
           "| 模型 · 对比 | 配对 n | 修复 b | 新增 c | 同失败 | 同通过 | 前 % | 后 % | 差值 pp [Newcombe 95% CI] | 精确 McNemar p |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for m in models:
        for name, t in report["models"][m]["contrasts"].items():
            md.append(contrast_row(f"{m} · {name}", t))
    md += ["", "† 不一致对为 0：差值恒为 0，方法 10 区间只反映两个 Wilson 边际与 φ 校正，不作为区间估计报告。", "",
           "各条件自身可评分分母上的边际失败率（未配对，供对照正文百分比）：", "",
           "| 模型 | " + " | ".join(CONDITIONS) + " |", "|---|" + "---|" * len(CONDITIONS)]
    for m in models:
        cells = []
        for cond in CONDITIONS:
            mg = report["models"][m]["marginalTrapFellAny"][cond]
            cells.append(f"{pct(mg['p'])} ({mg['k']}/{mg['n']})")
        md.append(f"| {m} | " + " | ".join(cells) + " |")

    md += ["", "## 2. 清除率 C2→C4", "",
           "| 模型 | 清除 b | C2 失败（配对） | C4 仍失败 | 清除率 % [Wilson 95% CI] |", "|---|---|---|---|---|"]
    for m in models + ["pooled"]:
        cl = report["pooled"]["clearanceC2toC4"] if m == "pooled" else report["models"][m]["clearanceC2toC4"]
        label = "三模型合并" if m == "pooled" else m
        md.append(f"| {label} | {cl['cleared']} | {cl['c2Failures']} | {cl['stillFailing']} | {pct(cl['p'])} [{pct(cl['lo'])}, {pct(cl['hi'])}] |")

    md += ["", "## 3. 三模型合并（堆叠配对）", "",
           "| 对比 | 配对 n | 修复 b | 新增 c | 同失败 | 同通过 | 前 % | 后 % | 差值 pp [Newcombe 95% CI] | 精确 McNemar p |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for name, t in report["pooled"]["contrasts"].items():
        md.append(contrast_row(name, t))

    md += ["", "## 4. C2→C4 分族计数（描述，不检验）", "",
           "| 模型 | 分组 | 配对 n | 修复 | 新增 | C2 失败 | C4 失败 |", "|---|---|---|---|---|---|---|"]
    for m in models:
        for name, g in report["models"][m]["familiesC2toC4"].items():
            label = {"decisionFamily": "决策族", "otherFiveFamilies": "其余五族"}.get(name, name.replace("family:", ""))
            md.append(f"| {m} | {label} | {g['pairedN']} | {g['repaired']} | {g['new']} | {g['c2Failures']} | {g['c4Failures']} |")

    md += ["", "## 5. 包级标记率（BLOCK 或 HUMAN_REVIEW），风险 / 对照", "",
           "| 模型 | 条件 | 风险 k/n (%) | 对照 k/n (%) | 不可解析（风险 / 对照） |", "|---|---|---|---|---|"]
    for m in models:
        for cond in FLAG_CONDITIONS:
            f = report["models"][m]["flagRates"][cond]
            r, c = f["risk"], f["control"]
            label = "C3（= C2 产物离线校验）" if cond == "C3" else f"{cond}（离线打分）"
            md.append(f"| {m} | {label} | {r['k']}/{r['n']} ({pct(r['p'])}) | {c['k']}/{c['n']} ({pct(c['p'])}) | {r['unparsed']} / {c['unparsed']} |")

    md += ["", "## 6. 断言：进入 C4 的对比中 McNemar p 与 2·0.5^b", ""]
    for item in report["signIdentityIntoC4"]:
        if item["applies"]:
            md.append(f"- {item['scope']} · {item['contrast']}：c = 0，b = {item['k']}，p = {fmt_p(item['exactP'])} = 2·0.5^{item['k']}（断言通过）")
        else:
            md.append(f"- {item['scope']} · {item['contrast']}：c = {item['new']} ≠ 0，恒等式不适用，p = {fmt_p(item['exactP'])}")
    md += ["", "c = 0 时精确 McNemar 退化为 b 个不一致对的符号检验，p 只是 b 的函数；C2→C4 的 c = 0 是修复器的设计属性，p 只进表或补充材料。",
           "", "JSON 中另附 `ciPP_method8_uncorrectedPhi`（Newcombe 方法 8，φ 不校正）仅供与早期手算值核对，正文使用方法 10。"]
    (HERE / "tab4_contrasts.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return md


def main():
    n_selftest = self_test()
    models, runs = discover()
    report = {"script": "tab4_contrasts.py", "modelOrder": models,
              "definitions": {
                  "outcome": "trapFellAny on positive_risk cases (null = unparsed, excluded)",
                  "pairedN": "risk cases with trapFellAny non-null under both conditions",
                  "repaired": "failed before, not after (b)", "new": "not before, failed after (c)",
                  "diff": "(c - b) / pairedN = after rate - before rate on paired cases",
                  "ci": "Newcombe (1998) method 10: Wilson marginals without continuity correction, phi numerator max(ad-bc-n/2,0) if ad>bc, phi=0 if a margin is 0",
                  "exactP": "two-sided exact McNemar, min(1, 2*P(X<=min(b,c))), X~Bin(b+c,1/2)",
                  "clearance": "C2->C4 repaired / C2 failures among paired risk cases; Wilson 95% CI",
                  "pooled": "pairs of the three models stacked into one 2x2 table",
                  "flagRate": "aggregate BLOCK or HUMAN_REVIEW / all cases of the group (72 risk, 72 control), unparsed included"},
              "newcombeSelfTest": {"source": "Newcombe 1998 Table III, methods 8 and 10", "vectors": n_selftest, "passed": True},
              "runs": {m: {c: runs[(m, c)].name for c in CONDITIONS} for m in models},
              "models": {}, "pooled": {}}
    pooled_cells = {name: {"a": 0, "b": 0, "c": 0, "d": 0} for name in (f"{x}->{y}" for x, y in POOLED_CONTRASTS)}
    for m in models:
        rows = load_model(m, runs)
        families = sorted({r["family"] for r in rows["C2"].values()})
        if len(families) != 6 or DECISION_FAMILY not in families:
            raise SystemExit(f"{m}: unexpected family set {families}")
        entry = {"contrasts": {}, "marginalTrapFellAny": {c: marginal(rows[c]) for c in CONDITIONS}}
        for x, y in MODEL_CONTRASTS:
            cells, _ = pair_counts(rows[x], rows[y])
            entry["contrasts"][f"{x}->{y}"] = contrast(cells, rows[x], rows[y])
            if f"{x}->{y}" in pooled_cells:
                pooled_cells[f"{x}->{y}"] = add_cells(pooled_cells[f"{x}->{y}"], cells)
        t = entry["contrasts"]["C2->C4"]
        c2_fail = t["repaired"] + t["unchangedFail"]
        lo, hi = wilson(t["repaired"], c2_fail)
        entry["clearanceC2toC4"] = {"cleared": t["repaired"], "c2Failures": c2_fail, "stillFailing": t["unchangedFail"],
                                    "p": t["repaired"] / c2_fail, "lo": lo, "hi": hi}
        entry["familiesC2toC4"] = family_counts(rows["C2"], rows["C4"], families)
        entry["flagRates"] = {c: flag_rates(rows[c]) for c in FLAG_CONDITIONS}
        report["models"][m] = entry
    report["pooled"]["contrasts"] = {name: contrast(cells) for name, cells in pooled_cells.items()}
    cl = [report["models"][m]["clearanceC2toC4"] for m in models]
    k, n = sum(x["cleared"] for x in cl), sum(x["c2Failures"] for x in cl)
    lo, hi = wilson(k, n)
    report["pooled"]["clearanceC2toC4"] = {"cleared": k, "c2Failures": n, "stillFailing": n - k, "p": k / n, "lo": lo, "hi": hi}
    # (6) sign-test identity for every contrast into C4 (per model and pooled).
    ident = []
    for scope, contrasts in [(m, report["models"][m]["contrasts"]) for m in models] + [("pooled", report["pooled"]["contrasts"])]:
        for name, t in contrasts.items():
            if name.endswith("->C4"):
                ident.append({"scope": scope, "contrast": name, "repaired": t["repaired"], "new": t["new"],
                              "exactP": t["exactP"], **t["signIdentity"]})
    report["signIdentityIntoC4"] = ident
    report["consistency"] = crosscheck_existing(report)
    (HERE / "tab4_contrasts.json").write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md = write_md(report)
    print("\n".join(md))


if __name__ == "__main__":
    main()
