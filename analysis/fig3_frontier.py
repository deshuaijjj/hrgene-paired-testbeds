#!/usr/bin/env python3
"""Figure 3 -- C4 next to content-blind redaction baselines (POST HOC, exploratory). Reads analysis/redactor_frontier.json
(written by redactor_frontier.py; this script never re-runs the redactor).

(a) valid-signature retention on matched controls x trap-failure rate on risk cases, full sample: the S relabel curve
    per model (content-blind, supported side only; seed means), the C2 and C4 points and the fixed drop_unsourced
    policy (small open diamond; drawn inside the C2 marker so that both stay visible where they coincide, as on the two
    qwen models).
(b) trap-routing rate x trap-failure rate on risk cases: the S+X configurations of the extended grid (q = 0, i.e. R
    off; seed means) and C4.

Encoding: model = Okabe-Ito colour + marker shape (circle / square / triangle) + line style of the S curve, so the
figure reads in greyscale and under colour-vision deficiency; role = fill (C2 open, C4 filled with a dark ring,
grid configurations small and translucent, drop_unsourced a small open diamond).

TMLR layout: 6.5 in wide (= \\textwidth), all text 7 pt at that size (panel tags 8 pt), no title and no conclusion
text inside the figure (both belong to the caption). Vector PDF with TrueType (Type 42) fonts, PNG at 300 dpi for the
Chinese draft, SVG. Byte-reproducible: fixed SVG hash salt, no dates in PDF/SVG/PNG metadata. Model colours match
fig2_main.py.

    python3 fig3_frontier.py                # writes fig3_frontier.{pdf,png,svg}
"""
import json
import os
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_ORDER = ["gpt-oss:20b", "qwen3:8b", "qwen3:30b-a3b"]
COLORS = {"gpt-oss:20b": "#0072B2", "qwen3:8b": "#009E73", "qwen3:30b-a3b": "#D55E00"}
MARKERS = {"gpt-oss:20b": "o", "qwen3:8b": "s", "qwen3:30b-a3b": "^"}
LINESTYLES = {"gpt-oss:20b": "-", "qwen3:8b": (0, (4, 1.6)), "qwen3:30b-a3b": (0, (4, 1.2, 1.2, 1.2))}
# marker sizes (points); triangles get a little more area so they read as large as circles and squares
SIZE = {"o": 1.0, "s": 0.9, "^": 1.12}
INK, MUTED, GRID = "#1f1f1e", "#5f5e5a", "#e3e2de"
WIDTH_IN, HEIGHT_IN = 6.5, 2.9
FONT = 7.0


def check_fonts(fig, lo=7.0, hi=9.0):
    """TMLR legibility: every visible text in the figure is set at lo-hi pt at the final 6.5 in width."""
    from matplotlib.text import Text
    bad = [(t.get_text(), t.get_fontsize()) for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()
           and not lo <= t.get_fontsize() <= hi]
    if bad:
        raise SystemExit(f"font sizes outside {lo}-{hi} pt: {bad[:5]}")


def main():
    R = json.load(open(os.path.join(HERE, "redactor_frontier.json"), encoding="utf-8"))["models"]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    matplotlib.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"], "font.size": FONT,
        "axes.labelsize": FONT, "xtick.labelsize": FONT, "ytick.labelsize": FONT, "legend.fontsize": FONT,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "svg.hashsalt": "hrgene-fig3",
        "path.simplify": False,
    })
    models = [m for m in MODEL_ORDER if m in R]
    fig = plt.figure(figsize=(WIDTH_IN, HEIGHT_IN))
    ax1 = fig.add_axes([0.075, 0.275, 0.405, 0.665])
    ax2 = fig.add_axes([0.580, 0.275, 0.405, 0.665], sharey=ax1)

    def ms(m, base):
        return base * SIZE[MARKERS[m]]

    # (a) retention x trap failure, full sample
    for m in models:
        e, c, mk = R[m], COLORS[m], MARKERS[m]
        cur = e["curves"]["relabel"]
        ax1.plot([100 * q["kept"] for q in cur], [100 * q["trap"] for q in cur], color=c, lw=1.0, ls=LINESTYLES[m], zorder=2)
        ax1.plot([100 * e["C2"]["kept"]], [100 * e["C2"]["trap"]], ls="", marker=mk, ms=ms(m, 7.0), mfc="white", mec=c,
                 mew=1.1, zorder=4)
        du = e["fixed"]["drop_unsourced"]
        ax1.plot([100 * du["kept"]], [100 * du["trap"]], ls="", marker="D", ms=3.0, mfc="white", mec=c, mew=0.9, zorder=4.5)
        ax1.plot([100 * e["C4"]["kept"]], [100 * e["C4"]["trap"]], ls="", marker=mk, ms=ms(m, 6.0), mfc=c, mec=INK,
                 mew=0.7, zorder=5)
    ax1.set_xlabel("Valid-signature retention on controls (%)")
    ax1.set_ylabel("Trap-failure rate on risk cases (%)")
    ax1.set_xlim(-3, 103)
    ax1.set_xticks(range(0, 101, 20))

    # (b) trapRouted x trap failure: S+X grid configurations (q = 0, R off) and C4
    for m in models:
        e, c, mk = R[m], COLORS[m], MARKERS[m]
        pts = [x for x in e["xGrid"]["configs"] if x["q"] == 0]
        ax2.plot([100 * x["trapRouted"] for x in pts], [100 * x["trap"] for x in pts], ls="", marker=mk, ms=ms(m, 3.3),
                 mfc=c, mec="none", alpha=0.5, zorder=3)
        ax2.plot([100 * e["C4"]["trapRouted"]], [100 * e["C4"]["trap"]], ls="", marker=mk, ms=ms(m, 6.0), mfc=c, mec=INK,
                 mew=0.7, zorder=5)
    ax2.set_xlabel("Trap routing rate on risk cases (%)")
    ax2.tick_params(labelleft=True)
    ax1.set_ylim(0, 52)
    ax1.set_yticks(range(0, 51, 10))

    for ax, tag in ((ax1, "(a)"), (ax2, "(b)")):
        ax.grid(color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.text(-0.13, 1.0, tag, transform=ax.transAxes, fontsize=8, fontweight="bold", color=INK, va="bottom", ha="left")

    # legend, row-major: models (line style + marker + colour), then the roles in neutral grey
    handles = [Line2D([], [], color=COLORS[m], lw=1.0, ls=LINESTYLES[m], marker=MARKERS[m], ms=ms(m, 4.6),
                      mfc=COLORS[m], mec=INK, mew=0.5, label=m) for m in models]
    handles.append(Line2D([], [], color=MUTED, lw=1.0, label="S relabel curve (a)"))
    handles += [Line2D([], [], ls="", marker="o", ms=6.2, mfc="white", mec=MUTED, mew=1.1, label="C2 (a)"),
                Line2D([], [], ls="", marker="o", ms=5.4, mfc=MUTED, mec=INK, mew=0.7, label="C4 (a, b)"),
                Line2D([], [], ls="", marker="D", ms=3.0, mfc="white", mec=MUTED, mew=0.9, label="drop_unsourced (a)"),
                Line2D([], [], ls="", marker="o", ms=3.3, mfc=MUTED, mec="none", alpha=0.5, label="S+X grid configuration (b)")]
    ncol = 4
    rows = [handles[i:i + ncol] for i in range(0, len(handles), ncol)]
    colmajor = [rows[r][k] for k in range(ncol) for r in range(len(rows)) if k < len(rows[r])]
    fig.legend(handles=colmajor, loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=ncol, frameon=False,
               fontsize=FONT, handlelength=2.6, columnspacing=1.8, handletextpad=0.6, borderaxespad=0.25)
    check_fonts(fig)
    fig.savefig(os.path.join(HERE, "fig3_frontier.pdf"), metadata={"CreationDate": None})
    fig.savefig(os.path.join(HERE, "fig3_frontier.svg"), metadata={"Date": None})
    fig.savefig(os.path.join(HERE, "fig3_frontier.png"), dpi=300, metadata={"Software": None})
    plt.close(fig)
    print("fig3_frontier.{pdf,png,svg} written")


if __name__ == "__main__":
    main()
