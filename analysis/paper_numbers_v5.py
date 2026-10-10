#!/usr/bin/env python3
"""Manuscript numbers and tables for the pre-registered v5 run.

Reads analysis/v5_preregistered.json (output of the registered script, unchanged), the v5 score rows and C4 final
records, and the v5 verifier's oracle report. Writes analysis/paper_numbers_v5.json (key -> {text, source}) and the
LaTeX table bodies analysis/paper_tables/en/tv5_*.tex. Reporting code only: it formats registered results and adds
descriptive readouts (Wilson intervals of single rates, C2->C4 retention difference on controls, routing rates, the
oracle report); it defines no new comparison. Written after the v5 outputs were seen (2026-10-10)."""
import collections
import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmark", "v5", "build"))
import tab4_contrasts as TC  # noqa: E402

RISK, CONTROL = "positive_risk", "matched_clean_control"
MODELS = [("gpt-oss:20b", "gptoss"), ("qwen3:8b", "q8b"), ("qwen3:30b-a3b", "q30b")]
SEED, NBOOT = 20261009, 10000
FAM = {"decision_ranking_protected_human_review_boundary": "decision", "ownership_role_scope_inflation": "ownership",
       "qualification_seniority_mismatch": "qualification", "unsupported_jd_technical_deployment": "deployment",
       "unsupported_premise_followup_subjective_rationale": "subjective", "unsupported_quantification_causality": "quantification"}
M = "\u2212"


def pct(x, d=1):
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def sgn(x, d=1):
    v = 100 * x
    s = f"{abs(v):.{d}f}"
    if float(s) == 0:
        return f"{0:.{d}f}"
    return ("+" if v > 0 else M) + s


def diff_full(d, lo, hi):
    return f"{sgn(d)} pp [{sgn(lo)}, {sgn(hi)}]"


def rate_full(k, n):
    lo, hi = TC.wilson(k, n)
    return f"{pct(k / n)} [{100 * lo:.1f}, {100 * hi:.1f}]"


def tex(s):
    return s.replace(M, "$-$").replace("%", "\\%").replace("_", "\\_")


def rows(run):
    p = os.path.join(ROOT, "experiments", run, "score_rows.jsonl")
    return {r["caseId"]: r for r in (json.loads(s) for s in open(p, encoding="utf-8") if s.strip())}


def boot(vals, rng):
    n = len(vals)
    means = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(NBOOT))
    return sum(vals) / n, means[int(0.025 * NBOOT)], means[int(0.975 * NBOOT) - 1]


def main():
    rep = json.load(open(os.path.join(HERE, "v5_preregistered.json"), encoding="utf-8"))
    out = {}

    def put(k, text, source):
        assert k not in out, k
        out[k] = {"text": str(text), "source": source}

    d = rep["design"]
    src = "v5_preregistered.json:design"
    put("v5.design.bait.note", d["baitLocations"]["note"], src)
    put("v5.design.bait.resume", d["baitLocations"]["resume"], src)
    put("v5.design.bait.workSample", d["baitLocations"]["work_sample"], src)
    put("v5.design.bait.nonNote", d["baitLocations"]["resume"] + d["baitLocations"]["work_sample"], src)
    put("v5.design.risk.n", sum(d["baitLocations"].values()), src)
    put("v5.design.control.n", d["controls"], src)
    put("v5.design.cases.n", sum(d["baitLocations"].values()) + d["controls"], src)
    put("v5.design.noteOnlyValid.kn", f"{d['noteOnlyValidControls']}/{d['controls']}", src)
    put("v5.design.noteOnlyValid.n", d["noteOnlyValidControls"], src)
    put("v5.design.policies.n", len(d["sourcePolicies"]), src)
    put("v5.design.boot.B", d["bootstrap"]["B"], src)
    # oracle report from the frozen verifier
    import verify as V5  # noqa: E402
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V5.main(verbose=False, show_oracle=True)
    line = [ln for ln in buf.getvalue().splitlines() if ln.startswith("oracle report")][0]
    kn = line.split(": ")[1].split(" ")[0]
    put("v5.oracle.accept.kn", kn, "benchmark/v5/build/verify.py --oracle")
    k, n = map(int, kn.split("/"))
    put("v5.oracle.accept", pct(k / n), "benchmark/v5/build/verify.py --oracle")
    put("v5.oracle.notAccept", n - k, "benchmark/v5/build/verify.py --oracle")

    gold = {}
    for f in glob.glob(os.path.join(ROOT, "benchmark", "v5", "gold", "*.json")):
        g = json.load(open(f, encoding="utf-8"))
        gold[g["caseId"]] = g
    rng = random.Random(SEED)
    tab_main, tab_loc, tab_pol, tab_fam = [], [], [], []
    regen_cases = set()
    for model, m in MODELS:
        R = rep["models"][model]
        pre = rep["runs"][model]
        c2, c4 = rows(f"{pre}-C2-v5"), rows(f"{pre}-C4-v5")
        s = f"v5_preregistered.json:models[{model}]"
        risk = [i for i in c2 if c2[i]["controlStatus"] == RISK and c2[i].get("trapFellAny") is not None]
        k2 = sum(bool(c2[i]["trapFellAny"]) for i in risk)
        risk4 = [i for i in c4 if c4[i]["controlStatus"] == RISK and c4[i].get("trapFellAny") is not None]
        k4 = sum(bool(c4[i]["trapFellAny"]) for i in risk4)
        put(f"v5.{m}.parsed.kn", f"{sum(1 for r in c2.values() if r['parsed'])}/{len(c2)}", f"{pre}-C2-v5/score_rows.jsonl")
        for cond, k, ids in (("C2", k2, risk), ("C4", k4, risk4)):
            put(f"v5.{m}.{cond}.trap", pct(k / len(ids)), f"{pre}-{cond}-v5/score_rows.jsonl")
            put(f"v5.{m}.{cond}.trap.kn", f"{k}/{len(ids)}", f"{pre}-{cond}-v5/score_rows.jsonl")
            put(f"v5.{m}.{cond}.trap.full", rate_full(k, len(ids)), f"{pre}-{cond}-v5/score_rows.jsonl (Wilson)")
            rr = [bool((c2 if cond == "C2" else c4)[i]["trapRouted"]) for i in ids]
            put(f"v5.{m}.{cond}.trapRouted", pct(sum(rr) / len(rr)), f"{pre}-{cond}-v5/score_rows.jsonl")
        c = R["c2toc4"]
        assert c["c2Fail"] == k2 and c["c4Fail"] == k4
        put(f"v5.{m}.clear.kn", f"{c['cleared']}/{c['c2Fail']}", s + ".c2toc4")
        put(f"v5.{m}.clear", pct(c["cleared"] / c["c2Fail"]), s + ".c2toc4")
        put(f"v5.{m}.clear.full", rate_full(c["cleared"], c["c2Fail"]), s + ".c2toc4 (Wilson)")
        put(f"v5.{m}.c2toc4.diff.full", diff_full(c["diff"], c["lo"], c["hi"]), s + ".c2toc4 (Newcombe method 10)")
        put(f"v5.{m}.new", c["new"], s + ".c2toc4")
        # P1
        best = R["P1"]["primaryPolicy"]
        P = R["P1"]["byPolicy"]
        a = P[best]["all"]
        put(f"v5.{m}.P1.policy", best, s + ".P1.primaryPolicy")
        put(f"v5.{m}.P1.rate", pct(a["policyRate"]), s + ".P1")
        put(f"v5.{m}.P1.rate.kn", f"{a['both'] + a['policyOnly']}/{a['n']}", s + ".P1")
        put(f"v5.{m}.P1.diff.full", diff_full(a["diff"], a["lo"], a["hi"]), s + ".P1 (Newcombe method 10)")
        put(f"v5.{m}.P1.supported", "yes" if a["lo"] > 0 else "no", s + ".P1")
        nn = P[best]["nonNote"]
        put(f"v5.{m}.P1.nonNote.diff.full", diff_full(nn["diff"], nn["lo"], nn["hi"]), s + ".P1 nonNote")
        put(f"v5.{m}.P1.nonNote.policy", pct(nn["policyRate"]), s + ".P1 nonNote")
        put(f"v5.{m}.P1.nonNote.c4", pct(nn["c4Rate"]), s + ".P1 nonNote")
        nx = P["drop_note_cited"]["all"]
        put(f"v5.{m}.P1.noX.rate", pct(nx["policyRate"]), s + ".P1 drop_note_cited")
        put(f"v5.{m}.P1.noX.diff.full", diff_full(nx["diff"], nx["lo"], nx["hi"]), s + ".P1 drop_note_cited")
        # P2
        p2 = R["P2"]
        for key, lab in (("note", "note"), ("nonNote", "nonNote")):
            x = p2[key]
            put(f"v5.{m}.P2.{lab}.kn", f"{x['cleared']}/{x['c2Fail']}", s + ".P2")
            put(f"v5.{m}.P2.{lab}", pct(x["rate"]), s + ".P2")
        for key, lab in (("resume", "resume"), ("work_sample", "workSample")):
            x = p2["byLocation"][key]
            put(f"v5.{m}.P2.{lab}.kn", f"{x['cleared']}/{x['c2Fail']}", s + ".P2")
        dd = p2["noteMinusNonNote"]
        put(f"v5.{m}.P2.diff.full", diff_full(dd["diff"], dd["lo"], dd["hi"]), s + ".P2 (Newcombe hybrid score)")
        put(f"v5.{m}.P2.supported", "yes" if dd["lo"] > 0 else "no", s + ".P2")
        # P3
        p3 = R["P3"][best]
        put(f"v5.{m}.P3.c4", pct(p3["all"]["c4"]), s + ".P3")
        put(f"v5.{m}.P3.policy", pct(p3["all"]["policy"]), s + ".P3")
        put(f"v5.{m}.P3.diff.full", diff_full(p3["all"]["diff"], p3["all"]["lo"], p3["all"]["hi"]), s + ".P3 (bootstrap)")
        put(f"v5.{m}.P3.nov.diff.full", diff_full(p3["noteOnlyValid"]["diff"], p3["noteOnlyValid"]["lo"], p3["noteOnlyValid"]["hi"]), s + ".P3 noteOnlyValid")
        put(f"v5.{m}.P3.nov.policy", pct(p3["noteOnlyValid"]["policy"]), s + ".P3 noteOnlyValid")
        put(f"v5.{m}.P3.nov.c4", pct(p3["noteOnlyValid"]["c4"]), s + ".P3 noteOnlyValid")
        put(f"v5.{m}.P3.supported", "yes" if all(x["all"]["hi"] < 0 for x in R["P3"].values()) else "no", s + ".P3")
        # P4
        p4 = R["P4"]
        put(f"v5.{m}.P4.S", pct(p4["sAtC4Attrition"]), s + ".P4")
        put(f"v5.{m}.P4.nd.S", pct(p4["nonDecision"]["sAtC4Attrition"]), s + ".P4 nonDecision")
        put(f"v5.{m}.P4.nd.c4", pct(p4["nonDecision"]["c4"]["trap"]), s + ".P4 nonDecision")
        put(f"v5.{m}.P4.supported", "yes" if p4["sAtC4Attrition"] > p4["c4"]["trap"] else "no", s + ".P4")
        put(f"v5.{m}.C4.supportedPerCase", f"{p4['c4']['supportedCount']:.1f}", s + ".P4.c4")
        # descriptive: retention cost of C4 on controls
        ids = [i for i in c2 if c2[i]["controlStatus"] == CONTROL and c2[i].get("validClaimPreserved") is not None
               and c4.get(i, {}).get("validClaimPreserved") is not None]
        diffs = [c4[i]["validClaimPreserved"] - c2[i]["validClaimPreserved"] for i in sorted(ids)]
        mean, lo, hi = boot(diffs, rng)
        put(f"v5.{m}.cost.keptDiff.full", diff_full(mean, lo, hi), f"{pre} C2/C4 score rows, controls (case bootstrap, B={NBOOT}, seed={SEED})")
        put(f"v5.{m}.cost.c2", pct(sum(c2[i]["validClaimPreserved"] for i in ids) / len(ids)), f"{pre}-C2-v5/score_rows.jsonl")
        put(f"v5.{m}.cost.changed.kn", f"{sum(1 for x in diffs if x != 0)}/{len(diffs)}", f"{pre} C2/C4 score rows")
        # regeneration and final verdicts
        regen, block = 0, 0
        for f in glob.glob(os.path.join(ROOT, "experiments", f"{pre}-C4-v5", "final", "*.json")):
            rec = json.load(open(f, encoding="utf-8"))
            if rec.get("regenerated"):
                regen += 1
                regen_cases.add((rec["case_id"], gold[rec["case_id"]]["controlStatus"]))
            block += rec["aggregate"] == "BLOCK"
        put(f"v5.{m}.regen", regen, f"{pre}-C4-v5/final")
        put(f"v5.{m}.finalBlock", block, f"{pre}-C4-v5/final")
        # tables
        def stack(k, n):
            lo_, hi_ = TC.wilson(k, n)
            return ("\\begin{tabular}[c]{@{}c@{}}" + f"{100 * k / n:.1f} ({k}/{n})" + "\\\\ {[" + f"{100 * lo_:.1f}, {100 * hi_:.1f}" + "]}\\end{tabular}")
        dl = diff_full(a["diff"], a["lo"], a["hi"]).replace(" pp", "")
        tab_main.append(f"{model} & {stack(k2, len(risk))} & {stack(k4, len(risk4))} & {stack(c['cleared'], c['c2Fail'])} & "
                        f"{100 * a['policyRate']:.1f} & " + "\\begin{tabular}[c]{@{}c@{}}" + tex(dl.split(" [")[0]) + "\\\\ {[" + tex(dl.split(" [")[1][:-1]) + "]}\\end{tabular}"
                        + f" & {100 * p4['sAtC4Attrition']:.1f} \\\\")
        tab_main.append("\\addlinespace")
        bl = p2["byLocation"]
        tab_loc.append(f"{model} & {bl['note']['cleared']}/{bl['note']['c2Fail']} & {bl['resume']['cleared']}/{bl['resume']['c2Fail']} & "
                       f"{bl['work_sample']['cleared']}/{bl['work_sample']['c2Fail']} & {tex(pct(p2['note']['rate']))} & {tex(pct(p2['nonNote']['rate']))} & "
                       f"{tex(diff_full(dd['diff'], dd['lo'], dd['hi']).replace(' pp', ''))} \\\\")
        def stk(x):
            t = diff_full(x["diff"], x["lo"], x["hi"]).replace(" pp", "")
            return "\\begin{tabular}[c]{@{}c@{}}" + tex(t.split(" [")[0]) + "\\\\ {[" + tex(t.split(" [")[1][:-1]) + "]}\\end{tabular}"
        for j, name in enumerate(d["sourcePolicies"]):
            x, y = P[name], R["P3"][name]
            tab_pol.append(f"{model if j == 0 else ''} & \\texttt{{{tex(name).replace('_or_', '_or_\\allowbreak{}')}}}{'$^{*}$' if name == best else ''} & {100 * x['all']['policyRate']:.1f} & "
                           f"{stk(x['all'])} & {stk(x['nonNote'])} & {stk(y['all'])} & {stk(y['noteOnlyValid'])} \\\\")
        tab_pol.append("\\addlinespace")
        cells = collections.defaultdict(dict)
        for key, v in p2["byFamilyLocation"].items():
            f, l = key.split("|")
            cells[FAM[f]][l] = f"{v['cleared']}/{v['c2Fail']}"
        for j, f in enumerate(sorted(cells)):
            tab_fam.append(f"{model if j == 0 else ''} & {f} & {cells[f].get('note', '--')} & {cells[f].get('resume', '--')} & {cells[f].get('work_sample', '--')} \\\\")
        tab_fam.append("\\addlinespace")
    assert all(st == CONTROL for _, st in regen_cases)
    put("v5.regen.cases.n", len({c for c, _ in regen_cases}), "C4 final records")
    put("v5.pooled.new", sum(int(out[f"v5.{m}.new"]["text"]) for _, m in MODELS), "sum of v5.<m>.new")
    put("v5.P1.supported.n", sum(out[f"v5.{m}.P1.supported"]["text"] == "yes" for _, m in MODELS), "count of models")
    put("v5.P2.supported.n", sum(out[f"v5.{m}.P2.supported"]["text"] == "yes" for _, m in MODELS), "count of models")
    put("v5.P3.supported.n", sum(out[f"v5.{m}.P3.supported"]["text"] == "yes" for _, m in MODELS), "count of models")
    put("v5.P4.supported.n", sum(out[f"v5.{m}.P4.supported"]["text"] == "yes" for _, m in MODELS), "count of models")
    json.dump(out, open(os.path.join(HERE, "paper_numbers_v5.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    tdir = os.path.join(HERE, "paper_tables", "en")
    hdr = "% {name}: generated by analysis/paper_numbers_v5.py from analysis/v5_preregistered.json; do not edit by hand.\n"

    def write(name, colspec, head, body, note):
        while body and body[-1] == "\\addlinespace":
            body = body[:-1]
        t = (hdr.format(name=name) + "{\\small\\setlength{\\tabcolsep}{4pt}\n\\begin{tabular}{" + colspec + "}\n\\toprule\n" + head + "\n\\midrule\n"
             + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}}\n\\par\\smallskip{\\footnotesize\\raggedright\\textit{Note.} " + note + "\\par}\n")
        open(os.path.join(tdir, name), "w", encoding="utf-8").write(t)

    write("tv5_main.tex", "lcccccc",
          "Model & C2 & C4 & \\begin{tabular}[c]{@{}c@{}}Clearance\\\\ C2$\\to$C4\\end{tabular} & \\begin{tabular}[c]{@{}c@{}}Best\\\\ policy\\end{tabular} & \\begin{tabular}[c]{@{}c@{}}Policy $-$ C4,\\\\ pp\\end{tabular} & \\begin{tabular}[c]{@{}c@{}}Blind S at\\\\ C4 attrition\\end{tabular} \\\\",
          tab_main,
          "De-confounded testbed, pre-registered run. C2, C4: trap-failure rate, \\% (k/n) [Wilson 95\\% CI], over parseable risk cases; clearance likewise over C2 trap failures. "
          "Best policy: lowest trap-failure rate (\\%) among the four source-type policies (P1); the difference is paired over risk cases, "
          "with a Newcombe method-10 95\\% CI. Blind S: trap-failure rate (\\%) of content-blind relabeling interpolated at C4's supported-side "
          "items per case (seed means; P4).")
    write("tv5_location.tex", "lcccccc",
          "Model & Note & Resume & Work sample & Note, \\% & Non-note, \\% & Note $-$ non-note, pp \\\\",
          tab_loc,
          "C2$\\to$C4 clearance by the source type of the bait (cleared / C2 trap failures). The difference uses the Newcombe hybrid score "
          "95\\% CI for independent proportions (P2).")
    write("tv5_policies.tex", "llccccc",
          "Model & Policy & \\begin{tabular}[c]{@{}c@{}}Trap\\\\ failure, \\%\\end{tabular} & \\begin{tabular}[c]{@{}c@{}}Failure $-$ C4,\\\\ all\\end{tabular} & \\begin{tabular}[c]{@{}c@{}}Failure $-$ C4,\\\\ non-note bait\\end{tabular} & \\begin{tabular}[c]{@{}c@{}}Retention\\\\ $-$ C4\\end{tabular} & \\begin{tabular}[c]{@{}c@{}}Retention $-$ C4,\\\\ note-only\\end{tabular} \\\\",
          tab_pol,
          "Source-type policies on the frozen C2 outputs of the de-confounded testbed; $^{*}$ marks the pre-registered primary policy "
          "(lowest trap-failure rate). Differences are policy minus C4 in percentage points with 95\\% CIs: trap failure paired over risk "
          "cases (Newcombe method 10); valid-signature retention over controls and over the controls whose valid content occurs only "
          "in a note (case bootstrap).")
    write("tv5_family.tex", "llccc", "Model & Stress family & Note & Resume & Work sample \\\\", tab_fam,
          "C2$\\to$C4 clearance (cleared / C2 trap failures) by stress family and bait location; cells hold at most four risk cases and "
          "are descriptive. The decision family has no work-sample bait.")
    print(f"{len(out)} keys -> paper_numbers_v5.json; 4 tables")


if __name__ == "__main__":
    main()
