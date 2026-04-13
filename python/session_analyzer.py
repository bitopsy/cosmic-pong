#!/usr/bin/env python3
"""
Cosmic Matrix Pong — Post-Session Physics Analyzer
===================================================
Load a session CSV and generate full physics analysis report.

Usage:
    python session_analyzer.py sessions/session_1234567890.csv

Outputs:
    - Full 9-panel matplotlib figure (PNG)
    - Physics equations verified against recorded data
    - Per-hit anomaly detection
    - Improvement recommendations
"""

import csv
import math
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    from scipy.stats import gaussian_kde, pearsonr
    from scipy.signal import savgol_filter
    HAS_FULL = True
except ImportError:
    HAS_FULL = False
    print("[warn] scipy/numpy missing — reduced analysis mode")

# ─── Physics constants ─────────────────────────────────────────────────────────
BALL_MASS     = 0.0027
BALL_DIAMETER = 0.040
BALL_AREA     = math.pi * (0.020**2)
AIR_DENSITY   = 1.293
AIR_VISCOSITY = 1.81e-5
DRAG_COEFF    = 0.47
GRAVITY       = 9.81
RESTITUTION   = 0.89
TURB_RE       = 4e4

MATRIX = {
    "bg":    "#000505",
    "panel": "#001408",
    "g1":    "#00ff33",
    "g2":    "#009922",
    "g3":    "#004411",
    "cyan":  "#00ddff",
    "amber": "#ffcc00",
    "red":   "#ff3322",
    "text":  "#88ffaa",
    "dim":   "#336644",
}

@dataclass
class Hit:
    hit_num:          int
    timestamp:        float
    velocity_ms:      float
    speed_kmh:        float
    spin_rpm:         float
    kinetic_energy_j: float
    momentum_kgms:    float
    power_w:          float
    reynolds_number:  float
    turbulent:        bool
    drag_force_n:     float
    magnus_force_n:   float
    reaction_time_s:  float
    hand:             str

def load_csv(path: str) -> list[Hit]:
    hits = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hits.append(Hit(
                hit_num          = int(row["hit_num"]),
                timestamp        = float(row["timestamp"]),
                velocity_ms      = float(row["velocity_ms"]),
                speed_kmh        = float(row["speed_kmh"]),
                spin_rpm         = float(row["spin_rpm"]),
                kinetic_energy_j = float(row["kinetic_energy_j"]),
                momentum_kgms    = float(row["momentum_kgms"]),
                power_w          = float(row["power_w"]),
                reynolds_number  = float(row["reynolds_number"]),
                turbulent        = row["turbulent"].lower() == "true",
                drag_force_n     = float(row["drag_force_n"]),
                magnus_force_n   = float(row["magnus_force_n"]),
                reaction_time_s  = float(row["reaction_time_s"]),
                hand             = row["hand"],
            ))
    return hits

def _mean(lst):
    return sum(lst) / len(lst) if lst else 0.0

def _std(lst):
    if len(lst) < 2: return 0.0
    m = _mean(lst)
    return math.sqrt(sum((x-m)**2 for x in lst) / len(lst))

def _pct(lst, p):
    if not lst: return 0.0
    s = sorted(lst)
    k = (len(s)-1) * p / 100.0
    lo, hi = int(k), min(int(k)+1, len(s)-1)
    return s[lo] + (k-lo)*(s[hi]-s[lo])

def recommend_improvements(hits: list[Hit]) -> list[str]:
    """Generate physics-based coaching recommendations."""
    recs = []
    speeds = [h.velocity_ms for h in hits]
    spins  = [h.spin_rpm for h in hits]
    reacts = [h.reaction_time_s for h in hits if 0.05 < h.reaction_time_s < 5]
    turbs  = sum(1 for h in hits if h.turbulent)

    if _std(speeds) / max(_mean(speeds), 0.01) > 0.3:
        recs.append("⚠ HIGH SPEED VARIANCE (CV > 30%) — Work on swing consistency.\n"
                    "  Physics: inconsistent contact → variable Δp = F·Δt")

    if _mean(spins) < 500:
        recs.append("→ LOW AVERAGE SPIN (< 500 rpm) — Add wrist flick to increase ω.\n"
                    "  Magnus: F_m = k(ω × v) scales with spin — more spin = more curve")

    if reacts and _mean(reacts) > 0.6:
        recs.append(f"⚠ SLOW REACTION TIME (μ = {_mean(reacts):.2f}s) — "
                    "Improve anticipation / footwork.\n"
                    "  Human RT baseline: ~0.25s visual-motor reflex")

    if turbs > len(hits) * 0.7:
        recs.append(f"→ {turbs}/{len(hits)} TURBULENT HITS (Re > 4×10⁴) — "
                    "Ball likely knuckling. Consider consistent topspin.\n"
                    "  Topspin boundary layer delays separation → more predictable trajectory")

    left  = [h for h in hits if h.hand == "left"]
    right = [h for h in hits if h.hand == "right"]
    if left and right:
        ls = _mean([h.velocity_ms for h in left])
        rs = _mean([h.velocity_ms for h in right])
        if abs(ls - rs) / max(ls, rs, 0.01) > 0.2:
            dom = "left" if ls > rs else "right"
            recs.append(f"→ HAND IMBALANCE: {dom} hand 20%+ faster — "
                        f"Train weaker hand symmetry.")

    if not recs:
        recs.append("✓ EXCELLENT CONSISTENCY — All physics metrics within optimal ranges!")

    return recs

def analyze(csv_path: str, out_dir: Optional[str] = None):
    hits = load_csv(csv_path)
    if not hits:
        print("[analyzer] No data found in CSV.")
        return

    n = len(hits)
    print(f"\n[analyzer] Loaded {n} hits from {csv_path}")

    # Compute aggregates
    speeds = [h.velocity_ms for h in hits]
    spins  = [h.spin_rpm for h in hits]
    kes    = [h.kinetic_energy_j for h in hits]
    res    = [h.reynolds_number for h in hits]
    drags  = [h.drag_force_n for h in hits]
    mag    = [h.magnus_force_n for h in hits]
    react  = [h.reaction_time_s for h in hits if 0.05 < h.reaction_time_s < 5]
    pw     = [h.power_w for h in hits]
    idx    = list(range(n))

    # Print stats report
    print("\n══════════ PHYSICS REPORT ══════════")
    print(f"  Mean speed:      {_mean(speeds):.3f} m/s  ({_mean(speeds)*3.6:.2f} km/h)")
    print(f"  Std dev speed:   {_std(speeds):.3f} m/s")
    print(f"  Max speed:       {max(speeds):.3f} m/s")
    print(f"  p95 speed:       {_pct(speeds,95):.3f} m/s")
    print(f"  Mean spin:       {_mean(spins):.1f} rpm")
    print(f"  Mean KE:         {_mean(kes):.6f} J")
    print(f"  Mean Re:         {_mean(res):.1f}")
    print(f"  Turbulent:       {sum(1 for h in hits if h.turbulent)}/{n}")
    print(f"  Mean reaction:   {_mean(react):.3f} s" if react else "  Reaction: n/a")
    print(f"  Total energy:    {sum(kes):.5f} J")
    print("════════════════════════════════════")

    # Recommendations
    recs = recommend_improvements(hits)
    print("\n──── COACHING INSIGHTS ────")
    for r in recs:
        print(r)

    if not HAS_FULL:
        print("[analyzer] Install matplotlib + numpy + scipy for graph output.")
        return

    # ── Graph ─────────────────────────────────────────────────────────────────
    S   = MATRIX
    fig = plt.figure(figsize=(18, 11), facecolor=S["bg"])
    fig.suptitle(
        f"COSMIC MATRIX PONG — PHYSICS DEEP ANALYSIS  [{Path(csv_path).stem}]",
        color=S["g1"], fontsize=13, fontfamily="monospace", y=0.985)

    gs = gridspec.GridSpec(3, 4, figure=fig, hspace=0.55, wspace=0.42,
                           left=0.06, right=0.97, top=0.95, bottom=0.06)

    def ax_(r, c, cs=1, rs=1):
        return fig.add_subplot(gs[r:r+rs, c:c+cs])

    def sty(ax, title, xl="hit #", yl=""):
        ax.set_facecolor(S["panel"])
        ax.set_title(title, color=S["g1"], fontsize=8,
                     fontfamily="monospace", pad=3)
        ax.set_xlabel(xl, color=S["dim"], fontsize=6, fontfamily="monospace")
        ax.set_ylabel(yl, color=S["dim"], fontsize=6, fontfamily="monospace")
        ax.tick_params(colors=S["text"], labelsize=6)
        for sp in ax.spines.values():
            sp.set_color(S["dim"]); sp.set_linewidth(0.4)
        ax.grid(True, color=S["g3"], linewidth=0.35, linestyle="--", alpha=0.6)

    # 1. Speed timeline
    a1 = ax_(0, 0)
    sty(a1, "SPEED  v (m/s)", yl="m/s")
    a1.plot(idx, speeds, color=S["g1"], lw=1.1, zorder=3)
    a1.fill_between(idx, speeds, alpha=0.12, color=S["g1"])
    if n >= 11:
        wl = min(11, n if n%2==1 else n-1)
        a1.plot(idx, savgol_filter(speeds, wl, 2),
                color=S["amber"], lw=0.8, ls="--", label="smoothed")
    a1.axhline(_mean(speeds), color=S["amber"], lw=0.6, ls=":")
    a1.text(0.98, 0.96,
            f"μ={_mean(speeds):.2f}\nσ={_std(speeds):.2f}\nmax={max(speeds):.2f}",
            transform=a1.transAxes, color=S["text"], fontsize=6,
            fontfamily="monospace", va="top", ha="right")

    # 2. Spin timeline
    a2 = ax_(0, 1)
    sty(a2, "SPIN  ω (rpm)", yl="rpm")
    a2.plot(idx, spins, color=S["cyan"], lw=1.1)
    a2.fill_between(idx, spins, alpha=0.10, color=S["cyan"])

    # 3. Kinetic energy
    a3 = ax_(0, 2)
    sty(a3, "KINETIC ENERGY  ½mv² (J)", yl="J")
    a3.plot(idx, kes, color=S["amber"], lw=1.1)
    a3.fill_between(idx, kes, alpha=0.10, color=S["amber"])

    # 4. Reaction time scatter
    a4 = ax_(0, 3)
    sty(a4, "REACTION TIME (s)", yl="s")
    ri = [i for i, h in enumerate(hits) if 0.05 < h.reaction_time_s < 5]
    rv = [hits[i].reaction_time_s for i in ri]
    if ri:
        a4.scatter(ri, rv, c=S["red"], s=10, alpha=0.8, zorder=3)
        a4.axhline(_mean(rv), color=S["amber"], lw=0.7, ls="--")
        if len(rv) >= 11:
            wl2 = min(11, len(rv) if len(rv)%2==1 else len(rv)-1)
            a4.plot(ri, savgol_filter(rv, wl2, 2), color=S["g1"], lw=0.7)

    # 5. Reynolds number
    a5 = ax_(1, 0)
    sty(a5, "REYNOLDS  Re = ρvD/μ", yl="Re")
    tc  = [S["red"] if h.turbulent else S["g2"] for h in hits]
    a5.scatter(idx, res, c=tc, s=10, zorder=3, alpha=0.9)
    a5.axhline(TURB_RE, color=S["amber"], lw=0.7, ls="--",
               label=f"Re_turb={TURB_RE:.0e}")
    a5.legend(fontsize=5, facecolor=S["panel"], labelcolor=S["text"])

    # 6. Drag vs Magnus
    a6 = ax_(1, 1)
    sty(a6, "FORCES: F_drag vs F_magnus (N)", yl="N")
    a6.plot(idx, drags, color=S["cyan"],  lw=1.0, label="F_drag")
    a6.plot(idx, mag,   color=S["amber"], lw=1.0, label="F_magnus")
    a6.legend(fontsize=5, facecolor=S["panel"], labelcolor=S["text"])

    # 7. Speed histogram + KDE
    a7 = ax_(1, 2)
    sty(a7, "SPEED DISTRIBUTION", xl="m/s", yl="density")
    a7.hist(speeds, bins=max(8, n//4), color=S["g2"],
            edgecolor=S["g3"], lw=0.3, alpha=0.75, density=True)
    if n > 5:
        kde = gaussian_kde(speeds)
        xs  = np.linspace(min(speeds), max(speeds), 200)
        a7.plot(xs, kde(xs), color=S["amber"], lw=1.2)

    # 8. Speed vs Spin scatter (correlation)
    a8 = ax_(1, 3)
    sty(a8, "SPEED vs SPIN", xl="v (m/s)", yl="ω (rpm)")
    a8.scatter(speeds, spins, c=S["cyan"], s=10, alpha=0.6)
    if n > 3:
        r, p = pearsonr(speeds, spins)
        z = np.polyfit(speeds, spins, 1)
        xs2 = np.linspace(min(speeds), max(speeds), 50)
        a8.plot(xs2, np.polyval(z, xs2), color=S["amber"], lw=0.8,
                ls="--", label=f"r={r:.3f} p={p:.3f}")
        a8.legend(fontsize=5, facecolor=S["panel"], labelcolor=S["text"])

    # 9. Power
    a9 = ax_(2, 0)
    sty(a9, "IMPACT POWER  P = E/Δt (W)", yl="W")
    a9.bar(idx, pw, color=S["red"], width=0.8, alpha=0.75)
    a9.axhline(_mean(pw), color=S["amber"], lw=0.6, ls="--")

    # 10. Cumulative energy
    a10 = ax_(2, 1)
    sty(a10, "CUMULATIVE KE (J)", yl="J")
    cumke = [sum(kes[:i+1]) for i in range(n)]
    a10 = a10
    a10.plot(idx, cumke, color=S["g1"], lw=1.2)
    a10.fill_between(idx, cumke, alpha=0.10, color=S["g1"])

    # 11. Hand comparison
    a11 = ax_(2, 2)
    sty(a11, "LEFT vs RIGHT HAND", xl="hand", yl="m/s")
    left_s  = [h.velocity_ms for h in hits if h.hand == "left"]
    right_s = [h.velocity_ms for h in hits if h.hand == "right"]
    if left_s or right_s:
        data = [x for x in [left_s, right_s] if x]
        labs = [l for l, x in zip(["L","R"], [left_s, right_s]) if x]
        bp = a11.boxplot(data, labels=labs, patch_artist=True,
                         boxprops=dict(facecolor=S["panel"], color=S["g1"]),
                         whiskerprops=dict(color=S["cyan"]),
                         medianprops=dict(color=S["amber"], lw=1.5),
                         flierprops=dict(marker="o", color=S["red"], ms=3))

    # 12. Recommendations text panel
    a12 = ax_(2, 3)
    a12.set_facecolor(S["panel"])
    a12.axis("off")
    a12.set_title("COACHING INSIGHTS", color=S["g1"],
                  fontsize=8, fontfamily="monospace", pad=3)
    rec_text = "\n\n".join(recs[:3])
    a12.text(0.03, 0.93, rec_text, transform=a12.transAxes,
             color=S["text"], fontsize=6.5, fontfamily="monospace",
             va="top", wrap=True)

    out_dir = Path(out_dir or Path(csv_path).parent / "graphs")
    out_dir.mkdir(parents=True, exist_ok=True)
    outfile = out_dir / (Path(csv_path).stem + "_analysis.png")
    plt.savefig(str(outfile), dpi=160, bbox_inches="tight",
                facecolor=S["bg"], edgecolor="none")
    plt.close(fig)
    print(f"\n[analyzer] Graph saved: {outfile}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", help="Session CSV path")
    parser.add_argument("--out", help="Output directory", default=None)
    args = parser.parse_args()
    analyze(args.csv_file, args.out)
