"""Figure style for the Paper 3 draft (Data-Centric Engineering, CUP layout).

Every data figure is drawn by one script in this folder from a result file
in this folder. The figure is created at its true print size, so a 7 pt tick
label is 7 pt on the page; the paper includes it at the same width, so nothing
is scaled.

Print geometry: Data-Centric Engineering single-column layout
(CUP-JNL-DCE.cls), text width 144 mm (5.67 in); every figure spans it. Fonts: ticks 7 pt, axis labels 8 pt, panel titles 9 pt,
legends 7 pt.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DCE_FULL = 144 / 25.4  # DCE text width, 144 mm
TOC_W, TOC_H = 8 / 2.54, 4 / 2.54  # table-of-contents graphic, 8 x 4 cm

INK = "#333333"
GREY = "#8C8C8C"
IDLE = "#EBEBEB"

# One colour per kind of control, the same meaning in every figure (Okabe-Ito,
# colour-vision-deficiency safe), each with its own line style or marker so the
# figures also read in greyscale:
#   blue   = set by hand and never changed (production indexes, fixed connection splits)
#   orange = learns from the recent history of queries (history-based tuner, reactive controller)
#   green  = reads the laboratory plan (plan-aware tuner, self-driving controller)
#   grey   = no control at all (one shared connection pool; annex figure only)
ARM_COLOURS = {
    "production": "#0072B2",
    "static": "#0072B2",
    "static51": "#56B4E9",
    "static33": "#003D66",
    "history": "#C17D00",      # darkened from #E69F00 for WCAG 2.1 AA 3:1 graphics contrast
    "reactive": "#C17D00",
    "plan": "#009E73",
    "forecast": "#009E73",
    "shared": "#8C8C8C",
}
ARM_STYLES = {"production": (0, (4, 1.6)), "history": (0, (1, 1.2)), "plan": "-"}
ARM_NAMES = {
    "production": "production indexes (set by hand)",
    "history": "history-based tuner",
    "plan": "plan-aware tuner",
    "shared": "one shared pool",
    "static": "fixed split 4:2",
    "static51": "fixed split 5:1",
    "static33": "fixed split 3:3",
    "reactive": "reactive controller (history)",
    "forecast": "self-driving controller (plan)",
}
ARM_MARKERS = {"shared": "X", "static51": "v", "static": "s", "static33": "^", "reactive": "D", "forecast": "o"}


def apply_style():
    plt.rcParams.update({
        "figure.dpi": 100,
        "savefig.dpi": 600,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "axes.grid": True,
        "grid.color": "#DDDDDD",
        "grid.linewidth": 0.5,
        "axes.axisbelow": True,
        "lines.linewidth": 1.4,
        "legend.frameon": False,
        "figure.constrained_layout.use": True,
    })


def save(fig, path, pdf=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=600, facecolor="white")
    if pdf:
        fig.savefig(path.with_suffix(".pdf"), facecolor="white", metadata={"CreationDate": None})
    plt.close(fig)
    print(f"wrote {path}")
