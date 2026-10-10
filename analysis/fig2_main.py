#!/usr/bin/env python3
"""Figure 2 -- gold trap-failure rate on risk cases, by condition and model (fig2_main), and the frozen
residual-critical-violation metric by condition (fig2b_residual; appendix only, because C4 = 0 there holds by
construction, PAPER_SPEC section 7 item 10).

    python3 fig2_main.py        # writes fig2_main.{pdf,png,svg} and fig2b_residual.{pdf,png,svg}

Data: bar heights and denominators come from analysis/results.json (unchanged from the previous version of this
figure); the whiskers are the Wilson 95% intervals that tab4_stats.py already wrote to analysis/tab4_stats.json for the
same k/n (the script checks that both files agree before drawing). No number is typed by hand.

Layout for TMLR: 6.5 in wide (= \\textwidth, include at width=\\textwidth), all text 7 pt at that size, no title
and no conclusion text inside the figure (both belong to the caption), Okabe-Ito colours plus a hatch per model
(readable in greyscale and under colour-vision deficiency). Vector PDF with TrueType (Type 42) fonts, PNG at 300 dpi
for the Chinese draft, SVG. Output is byte-reproducible: fixed SVG hash salt, no dates in PDF/SVG/PNG metadata.
Model order follows the paper (gpt-oss:20b, qwen3:8b, qwen3:30b-a3b); condition order follows Table 1 / tab4_stats.
"""
import json
import os
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_ORDER = ["gpt-oss:20b", "qwen3:8b", "qwen3:30b-a3b"]
# Okabe-Ito: blue / bluish green / vermillion; same model -> colour mapping as fig3_frontier.py
COLORS = {"gpt-oss:20b": "#0072B2", "qwen3:8b": "#009E73", "qwen3:30b-a3b": "#D55E00"}
HATCHES = {"gpt-oss:20b": "", "qwen3:8b": "////", "qwen3:30b-a3b": "\\\\\\\\"}
ORDER = ["C0", "C1", "C2", "C5", "C3", "C4"]
GEN, POST = ["C0", "C1", "C2", "C5"], ["C3", "C4"]
DESC = {"C0": "no rules", "C1": "prose rules", "C2": "contract", "C5": "schema-constrained",
        "C3": "validation report", "C4": "validation + repair"}
GROUPS = [(GEN, "separate generations"), (POST, "applied to the C2 outputs")]
INK, MUTED, GRID = "#1f1f1e", "#5f5e5a", "#e3e2de"
WIDTH_IN = 6.5
FONT = 7.0

FIGS = {
    "fig2_main": {"metric": "trapFellAny", "ylabel": "Trap-failure rate (%)", "ymax": 80, "yticks": range(0, 81, 20)},
    # C4 = 0 on this metric by construction (BLOCK iff a critical FAIL; C4 not-repairable = 0): no interval is drawn
    # for it and the zero bars carry a label instead of an empty slot.
    "fig2b_residual": {"metric": "residualCriticalViolationRate", "ylabel": "Residual critical violation (%)",
                       "ymax": 106, "yticks": range(0, 101, 25), "byConstruction": ["C4"]},
}


def check_fonts(fig, lo=7.0, hi=9.0):
    """TMLR legibility: every visible text in the figure is set at lo-hi pt at the final 6.5 in width."""
    from matplotlib.text import Text
    bad = [(t.get_text(), t.get_fontsize()) for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()
           and not lo <= t.get_fontsize() <= hi]
    if bad:
        raise SystemExit(f"font sizes outside {lo}-{hi} pt: {bad[:5]}")


def load(metric):
    """{(model, condition): (p, n, lo, hi)}; p and n from results.json, lo/hi from tab4_stats.json (same k/n)."""
    rows = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
    stats = json.load(open(os.path.join(HERE, "tab4_stats.json"), encoding="utf-8"))["models"]
    out = {}
    for m in MODEL_ORDER:
        for c in ORDER:
            rs = [r for r in rows if r["model"] == m and r["condition"] == c and r.get(metric) is not None]
            if not rs:
                continue
            p, n = rs[-1][metric], rs[-1][metric + "_n"]
            s = stats[m]["proportions"][c][metric]
            if s["n"] != n or abs(s["p"] - p) > 1e-12:
                raise SystemExit(f"results.json and tab4_stats.json disagree for {m} {c} {metric}: {p}/{n} vs {s['p']}/{s['n']}")
            out[(m, c)] = (p, n, s["lo"], s["hi"])
    return out


def xpos():
    """Group centres; a wider gap separates the generation conditions from the C2 post-processing conditions."""
    return {c: i + (0.45 if c in POST else 0.0) for i, c in enumerate(ORDER)}


def draw(name, spec):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    data = load(spec["metric"])
    fig = plt.figure(figsize=(WIDTH_IN, 2.4))
    ax = fig.add_axes([0.085, 0.265, 0.905, 0.635])
    X = xpos()
    bw = 0.25
    for j, m in enumerate(MODEL_ORDER):
        cs = [c for c in ORDER if (m, c) in data]
        xs = [X[c] + (j - 1) * (bw + 0.02) for c in cs]
        ps = [100 * data[(m, c)][0] for c in cs]
        ax.bar(xs, ps, width=bw, color=COLORS[m], hatch=HATCHES[m], edgecolor="white", linewidth=0.5, zorder=2)
        ci = [(x, c) for x, c in zip(xs, cs) if c not in spec.get("byConstruction", [])]
        eb = ax.errorbar([x for x, _ in ci], [100 * data[(m, c)][0] for _, c in ci],
                         yerr=[[100 * (data[(m, c)][0] - data[(m, c)][2]) for _, c in ci],
                               [100 * (data[(m, c)][3] - data[(m, c)][0]) for _, c in ci]],
                         fmt="none", ecolor=INK, elinewidth=0.6, capsize=1.6, capthick=0.6, zorder=3, label="Wilson 95% interval")
    for c in spec.get("byConstruction", []):
        if any(data[(m, c)][0] != 0 for m in MODEL_ORDER if (m, c) in data):
            raise SystemExit(f"{c} was expected to be 0 by construction on {spec['metric']}")
        ax.text(X[c], 1.5, "0 by construction", ha="center", va="bottom", color=MUTED, fontsize=FONT)
    sep = (X["C5"] + X["C3"]) / 2
    ax.axvline(sep, color=MUTED, lw=0.6, ls=(0, (3, 2)), zorder=1)
    ax.set_xlim(X["C0"] - 0.55, X["C4"] + 0.55)
    ax.set_ylim(0, spec["ymax"])
    ax.set_yticks(list(spec["yticks"]))
    ax.set_ylabel(spec["ylabel"])
    ax.set_xticks([X[c] for c in ORDER])
    ax.set_xticklabels([f"{c}\n{DESC[c]}" for c in ORDER])
    ax.tick_params(axis="x", length=0, pad=3)
    ax.grid(axis="y", color=GRID, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_bounds(0, max(spec["yticks"]))
    # group brackets under the tick labels (axes-fraction y, data x)
    tr = ax.get_xaxis_transform()
    for conds, label in GROUPS:
        x0, x1 = X[conds[0]] - 0.42, X[conds[-1]] + 0.42
        y = -0.215
        ax.plot([x0, x0, x1, x1], [y + 0.035, y, y, y + 0.035], transform=tr, color=MUTED, lw=0.6, clip_on=False)
        ax.text((x0 + x1) / 2, y - 0.03, label, transform=tr, ha="center", va="top", color=MUTED, fontsize=FONT)
    handles = [Patch(facecolor=COLORS[m], edgecolor="white", hatch=HATCHES[m], linewidth=0.5, label=m) for m in MODEL_ORDER]
    handles.append(eb)   # errorbar container: drawn as a vertical whisker in the legend
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=4, frameon=False, fontsize=FONT,
              handlelength=1.6, handleheight=0.9, columnspacing=1.6, borderaxespad=0.3, borderpad=0.1)
    check_fonts(fig)
    base = os.path.join(HERE, name)
    fig.savefig(base + ".pdf", metadata={"CreationDate": None})
    fig.savefig(base + ".svg", metadata={"Date": None})
    fig.savefig(base + ".png", dpi=300, metadata={"Software": None})
    plt.close(fig)
    return data


def main():
    import matplotlib
    matplotlib.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"], "font.size": FONT,
        "axes.labelsize": FONT, "xtick.labelsize": FONT, "ytick.labelsize": FONT, "legend.fontsize": FONT,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "ytick.major.size": 2.5,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
        "hatch.linewidth": 0.55, "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "svg.hashsalt": "hrgene-fig2", "path.simplify": False,
    })
    for name, spec in FIGS.items():
        data = draw(name, spec)
        print(f"{name}.{{pdf,png,svg}} written ({len(data)} bars)")


if __name__ == "__main__":
    main()
