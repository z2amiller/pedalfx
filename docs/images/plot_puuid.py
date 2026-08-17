import json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator

counts = json.load(open(sys.argv[1]))
out = sys.argv[2]
N = len(counts); tot = sum(counts)
ranks = list(range(1, N + 1))
import math
keep = sorted(set([i for i in range(1, min(N, 3000) + 1)] +
                  [int(round(10 ** (k / 400))) for k in range(0, int(math.log10(N) * 400) + 1)] + [N]))
keep = [i for i in keep if 1 <= i <= N]
# also keep every step change so the staircase tail is exact
prev = None
for i, c in enumerate(counts, 1):
    if c != prev:
        keep.append(i); keep.append(i - 1 if i > 1 else 1)
        prev = c
keep = sorted(set(k for k in keep if 1 <= k <= N))
xr = keep; yr = [counts[i - 1] for i in keep]

# cumulative-coverage landmarks
cum, marks = 0, {}
for i, c in enumerate(counts, 1):
    cum += c
    for f in (0.5, 0.9):
        if f not in marks and cum >= f * tot:
            marks[f] = i
first_single = next(i for i, c in enumerate(counts, 1) if c == 1)

INK, MUTED, GRID, HUE = "#333333", "#6b6b6b", "#dddddd", "#2f6fdb"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": MUTED, "text.color": INK, "axes.titlecolor": INK,
    "svg.fonttype": "none",
})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4), dpi=100)
fig.patch.set_facecolor("white"); fig.patch.set_alpha(1)

def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.patch.set_facecolor("white")

thousands = FuncFormatter(lambda v, _: f"{v/1000:g}k" if v >= 1000 else f"{v:g}")

# --- linear panel: the "L" ---
ax1.plot(xr, yr, color=HUE, linewidth=2)
ax1.fill_between(xr, yr, color=HUE, alpha=0.08, linewidth=0)
style(ax1)
ax1.set_title("Linear axes: the “L”", loc="left", fontsize=11, fontweight="bold")
ax1.set_xlabel("EasyEDA footprints (puuid), ranked by number of LCSC parts")
ax1.set_ylabel("LCSC parts sharing the footprint")
ax1.xaxis.set_major_formatter(thousands); ax1.yaxis.set_major_formatter(thousands)
ax1.set_xlim(0, N); ax1.set_ylim(0, counts[0] * 1.08)
ax1.annotate("R0603 · 17,335 parts", xy=(1, counts[0]), xytext=(N * 0.08, counts[0] * 0.97),
             fontsize=9, color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
ax1.annotate(f"{N - first_single + 1:,} footprints used by exactly one part\n(73 % of footprints, 13 % of parts)",
             xy=(N * 0.6, 1), xytext=(N * 0.28, counts[0] * 0.28), fontsize=9, color=INK,
             arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))

# --- log-log panel: the structure ---
ax2.plot(xr, yr, color=HUE, linewidth=2)
style(ax2)
ax2.set_xscale("log"); ax2.set_yscale("log")
ax2.set_title("Log–log axes: same data", loc="left", fontsize=11, fontweight="bold")
ax2.set_xlabel("footprint rank (log)")
ax2.set_ylabel("LCSC parts per footprint (log)")
ax2.xaxis.set_major_formatter(thousands); ax2.yaxis.set_major_formatter(thousands)
ax2.xaxis.set_major_locator(LogLocator(base=10, numticks=6))
ax2.set_xlim(0.8, N * 1.4); ax2.set_ylim(0.7, counts[0] * 1.6)
for f, label, xt, yt in ((0.5, "50 % of parts", marks[0.5] * 0.06, 60),
                         (0.9, "90 % of parts", marks[0.9] * 0.10, 28)):
    r = marks[f]; c = counts[r - 1]
    ax2.plot([r], [c], "o", ms=7, color=HUE, mec="white", mew=1.5)
    ax2.annotate(f"{label}\nin top {r:,} footprints", xy=(r, c), xytext=(xt, yt),
                 fontsize=9, ha="center", color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
ax2.annotate("R0603 / R0805 / R0402 / R1206", xy=(1, counts[0]), xytext=(2.5, counts[0] * 1.02),
             fontsize=9, va="center", color=INK)
ax2.annotate("62,630 singletons: connectors, FPC,\nmodules — footprint named after the MPN",
             xy=(N * 0.75, 1), xytext=(N * 1.3, 400), fontsize=9, ha="right", color=INK,
             arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))

fig.suptitle(f"{tot:,} in-stock LCSC parts share {N:,} EasyEDA footprints (May 2026 crawl)",
             x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(out, format="svg", bbox_inches="tight", facecolor="white")
fig.savefig(out.replace(".svg", ".png"), format="png", dpi=160, bbox_inches="tight", facecolor="white")
print("marks", marks, "first_single", first_single)
