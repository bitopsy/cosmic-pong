#!/usr/bin/env python3
"""
Cosmic Matrix Pong — Python Analytics Server
============================================
Receives hit events from Godot via TCP socket.
Processes physics stats, generates graphs, exports CSV/JSON.

Physics computed here:
- Rolling statistics (mean, std dev, percentiles)
- Reynolds number per hit
- Drag coefficient verification
- Magnus force magnitude trending
- Reaction time analysis
- Session trajectory reconstruction
"""

import asyncio
import json
import csv
import math
import time
import argparse
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import deque

# Optional matplotlib — graceful fallback if not installed
try:
    import matplotlib
    matplotlib.use("Agg")  # headless backend for VR environment
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[analytics] matplotlib not available — graph export disabled")

# ─── Physics constants ─────────────────────────────────────────────────────────
BALL_MASS        = 0.0027    # kg  (ITTF regulation)
BALL_DIAMETER    = 0.040     # m
BALL_RADIUS      = 0.020     # m
BALL_AREA        = math.pi * BALL_RADIUS**2
AIR_DENSITY      = 1.293     # kg/m³ at 0°C, 1 atm
AIR_VISCOSITY    = 1.81e-5   # Pa·s dynamic viscosity
DRAG_COEFF       = 0.47      # sphere
MAGNUS_COEFF     = 1.5e-4    # empirical lift constant
GRAVITY          = 9.81      # m/s²
RESTITUTION      = 0.89
TURB_REYNOLDS    = 4e4       # turbulent transition Re

SESSIONS_DIR     = Path(__file__).parent / "sessions"
GRAPHS_DIR       = Path(__file__).parent / "graphs"

# ─── Data structures ───────────────────────────────────────────────────────────
@dataclass
class HitEvent:
    timestamp:       float
    velocity_ms:     float
    speed_kmh:       float
    kinetic_energy_j: float
    spin_rads:       float
    spin_rpm:        float
    reaction_time_s: float
    hand:            str
    magnus_force_mag: float
    drag_force_mag:  float

    # Derived (computed here)
    reynolds_number: float = 0.0
    momentum_kgms:   float = 0.0
    power_w:         float = 0.0
    drag_verified_n: float = 0.0
    magnus_verified_n: float = 0.0
    turbulent:       bool  = False

    def compute_derived(self):
        v = self.velocity_ms
        w = self.spin_rads
        self.reynolds_number    = (AIR_DENSITY * v * BALL_DIAMETER) / AIR_VISCOSITY
        self.momentum_kgms      = BALL_MASS * v
        self.power_w            = self.kinetic_energy_j / max(self.reaction_time_s, 0.001)
        self.drag_verified_n    = 0.5 * AIR_DENSITY * DRAG_COEFF * BALL_AREA * v**2
        self.magnus_verified_n  = MAGNUS_COEFF * w * v  # ≈ |ω × v|
        self.turbulent          = self.reynolds_number > TURB_REYNOLDS

@dataclass
class SessionStats:
    session_id:    str   = ""
    start_time:    float = 0.0
    hits:          list  = field(default_factory=list)  # List[HitEvent]
    hit_count:     int   = 0
    score_left:    int   = 0
    score_right:   int   = 0

    # Computed rolling stats
    mean_speed_ms:    float = 0.0
    std_speed_ms:     float = 0.0
    max_speed_ms:     float = 0.0
    p95_speed_ms:     float = 0.0
    mean_spin_rpm:    float = 0.0
    max_spin_rpm:     float = 0.0
    mean_react_s:     float = 0.0
    std_react_s:      float = 0.0
    total_energy_j:   float = 0.0
    mean_re:          float = 0.0
    turbulent_pct:    float = 0.0

    def update_stats(self):
        if not self.hits:
            return
        speeds  = [h.velocity_ms for h in self.hits]
        spins   = [h.spin_rpm for h in self.hits]
        reacts  = [h.reaction_time_s for h in self.hits if h.reaction_time_s > 0]
        res     = [h.reynolds_number for h in self.hits]
        energies = [h.kinetic_energy_j for h in self.hits]
        turbs   = [h.turbulent for h in self.hits]

        self.hit_count       = len(self.hits)
        self.mean_speed_ms   = _mean(speeds)
        self.std_speed_ms    = _std(speeds)
        self.max_speed_ms    = max(speeds)
        self.p95_speed_ms    = _percentile(speeds, 95)
        self.mean_spin_rpm   = _mean(spins)
        self.max_spin_rpm    = max(spins)
        self.mean_react_s    = _mean(reacts) if reacts else 0.0
        self.std_react_s     = _std(reacts) if reacts else 0.0
        self.total_energy_j  = sum(energies)
        self.mean_re         = _mean(res)
        self.turbulent_pct   = 100.0 * sum(1 for t in turbs if t) / len(turbs)

# ─── Math helpers ─────────────────────────────────────────────────────────────
def _mean(lst: list) -> float:
    return sum(lst) / len(lst) if lst else 0.0

def _std(lst: list) -> float:
    if len(lst) < 2:
        return 0.0
    m = _mean(lst)
    return math.sqrt(sum((x - m)**2 for x in lst) / len(lst))

def _percentile(lst: list, p: int) -> float:
    if not lst:
        return 0.0
    s = sorted(lst)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (k - lo) * (s[hi] - s[lo])

# ─── Graph generation ──────────────────────────────────────────────────────────
MATRIX_STYLE = {
    "bg":     "#000505",
    "panel":  "#001a06",
    "green":  "#00ff33",
    "cyan":   "#00ddff",
    "amber":  "#ffcc00",
    "red":    "#ff4422",
    "dim":    "#006622",
    "grid":   "#003311",
    "text":   "#88ffaa",
}

def generate_session_graphs(session: SessionStats, out_dir: Path) -> list[str]:
    """Generate 6-panel physics analysis figure."""
    if not HAS_MPL:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    outfile = str(out_dir / f"session_{session.session_id}_graphs.png")

    hits   = session.hits
    n      = len(hits)
    if n == 0:
        return []

    # Data extraction
    times  = [h.timestamp - session.start_time for h in hits]
    speeds = [h.velocity_ms for h in hits]
    spins  = [h.spin_rpm for h in hits]
    kes    = [h.kinetic_energy_j for h in hits]
    reacts = [h.reaction_time_s for h in hits]
    res    = [h.reynolds_number for h in hits]
    drags  = [h.drag_verified_n for h in hits]
    magnus = [h.magnus_verified_n for h in hits]
    powers = [h.power_w for h in hits]

    S   = MATRIX_STYLE
    fig = plt.figure(figsize=(16, 10), facecolor=S["bg"])
    fig.suptitle("COSMIC MATRIX PONG — SESSION PHYSICS ANALYSIS",
                 color=S["green"], fontsize=14, fontfamily="monospace", y=0.98)

    gs = fig.add_gridspec(3, 3, hspace=0.55, wspace=0.38,
                          left=0.07, right=0.97, top=0.92, bottom=0.07)

    def _ax(row, col, colspan=1):
        return fig.add_subplot(gs[row, col:col+colspan])

    def _style(ax, title, xlabel, ylabel):
        ax.set_facecolor(S["panel"])
        ax.set_title(title, color=S["green"], fontsize=9, fontfamily="monospace", pad=4)
        ax.set_xlabel(xlabel, color=S["dim"], fontsize=7, fontfamily="monospace")
        ax.set_ylabel(ylabel, color=S["dim"], fontsize=7, fontfamily="monospace")
        ax.tick_params(colors=S["text"], labelsize=7)
        ax.spines[:].set_color(S["dim"])
        ax.spines[:].set_linewidth(0.5)
        ax.grid(True, color=S["grid"], linewidth=0.4, linestyle="--", alpha=0.7)

    idx = list(range(n))

    # ── Panel 1: Speed over hits ──────────────────────────────────────────────
    ax1 = _ax(0, 0)
    _style(ax1, "BALL SPEED  v (m/s)", "hit #", "m/s")
    ax1.plot(idx, speeds, color=S["green"], linewidth=1.2, zorder=3)
    ax1.fill_between(idx, speeds, alpha=0.15, color=S["green"])
    if n >= 3:
        from scipy.signal import savgol_filter  # optional smoothing
        try:
            wl = min(11, n if n % 2 == 1 else n - 1)
            smooth = savgol_filter(speeds, wl, 2)
            ax1.plot(idx, smooth, color=S["amber"], linewidth=0.8,
                     linestyle="--", label="trend", zorder=4)
        except Exception:
            pass
    ax1.axhline(_mean(speeds), color=S["amber"], linewidth=0.7,
                linestyle=":", label=f"μ={_mean(speeds):.2f}")
    ax1.legend(fontsize=6, facecolor=S["panel"], labelcolor=S["text"])

    # ── Panel 2: Spin over hits ───────────────────────────────────────────────
    ax2 = _ax(0, 1)
    _style(ax2, "TOPSPIN  ω (rpm)", "hit #", "rpm")
    ax2.plot(idx, spins, color=S["cyan"], linewidth=1.2)
    ax2.fill_between(idx, spins, alpha=0.12, color=S["cyan"])
    ax2.axhline(_mean(spins), color=S["amber"], linewidth=0.7, linestyle=":")

    # ── Panel 3: Kinetic energy over hits ─────────────────────────────────────
    ax3 = _ax(0, 2)
    _style(ax3, "KINETIC ENERGY  ½mv² (J)", "hit #", "J")
    ax3.plot(idx, kes, color=S["amber"], linewidth=1.2)
    ax3.fill_between(idx, kes, alpha=0.12, color=S["amber"])
    ax3.axhline(_mean(kes), color=S["green"], linewidth=0.7, linestyle=":")

    # ── Panel 4: Reaction time histogram ──────────────────────────────────────
    ax4 = _ax(1, 0)
    _style(ax4, "REACTION TIME  Δt (s)", "time (s)", "count")
    valid_r = [r for r in reacts if 0.05 < r < 5.0]
    if valid_r:
        ax4.hist(valid_r, bins=min(20, n//2 or 1),
                 color=S["red"], edgecolor=S["dim"], linewidth=0.4, alpha=0.85)
        ax4.axvline(_mean(valid_r), color=S["amber"], linewidth=1.0,
                    linestyle="--", label=f"μ={_mean(valid_r):.2f}s")
        ax4.legend(fontsize=6, facecolor=S["panel"], labelcolor=S["text"])

    # ── Panel 5: Reynolds number + turbulence flag ────────────────────────────
    ax5 = _ax(1, 1)
    _style(ax5, "REYNOLDS NUMBER  Re = ρvD/μ", "hit #", "Re")
    turb_colors = [S["red"] if h.turbulent else S["green"] for h in hits]
    ax5.scatter(idx, res, c=turb_colors, s=12, zorder=3, alpha=0.85)
    ax5.axhline(TURB_REYNOLDS, color=S["amber"], linewidth=0.8, linestyle="--",
                label=f"turbulent >{TURB_REYNOLDS:.0e}")
    ax5.text(0.5, 0.05, f"Turbulent: {session.turbulent_pct:.1f}%",
             transform=ax5.transAxes, color=S["amber"], fontsize=7,
             fontfamily="monospace", ha="center")
    lam   = mpatches.Patch(color=S["green"], label="laminar")
    turb  = mpatches.Patch(color=S["red"],   label="turbulent")
    ax5.legend(handles=[lam, turb], fontsize=6,
               facecolor=S["panel"], labelcolor=S["text"])

    # ── Panel 6: Force comparison — Drag vs Magnus ────────────────────────────
    ax6 = _ax(1, 2)
    _style(ax6, "AERODYNAMIC FORCES (N)", "hit #", "N")
    ax6.plot(idx, drags,  color=S["cyan"],  linewidth=1.0, label="F_drag")
    ax6.plot(idx, magnus, color=S["amber"], linewidth=1.0, label="F_magnus")
    ax6.legend(fontsize=6, facecolor=S["panel"], labelcolor=S["text"])

    # ── Panel 7: Speed distribution + stats box ───────────────────────────────
    ax7 = _ax(2, 0)
    _style(ax7, "SPEED DISTRIBUTION", "m/s", "density")
    ax7.hist(speeds, bins=min(20, n), color=S["green"],
             edgecolor=S["dim"], linewidth=0.3, alpha=0.75, density=True)
    if HAS_MPL and n > 5:
        from scipy.stats import gaussian_kde
        try:
            kde = gaussian_kde(speeds)
            xs  = [min(speeds) + i * (max(speeds)-min(speeds))/100 for i in range(101)]
            ax7.plot(xs, [kde(x)[0] for x in xs], color=S["amber"], linewidth=1.0)
        except Exception:
            pass
    stats_txt = (
        f"μ={_mean(speeds):.2f}  σ={_std(speeds):.2f}\n"
        f"p95={_percentile(speeds,95):.2f}  max={max(speeds):.2f}"
    )
    ax7.text(0.97, 0.95, stats_txt, transform=ax7.transAxes,
             color=S["text"], fontsize=6, fontfamily="monospace",
             va="top", ha="right", bbox=dict(boxstyle="round", fc=S["bg"],
             ec=S["dim"], alpha=0.7))

    # ── Panel 8: Power delivered per hit ──────────────────────────────────────
    ax8 = _ax(2, 1)
    _style(ax8, "IMPACT POWER  P = E/Δt (W)", "hit #", "W")
    ax8.bar(idx, powers, color=S["red"], width=0.7, alpha=0.75)
    ax8.axhline(_mean(powers), color=S["amber"], linewidth=0.7, linestyle="--")

    # ── Panel 9: Session summary scoreboard ───────────────────────────────────
    ax9 = _ax(2, 2)
    ax9.set_facecolor(S["panel"])
    ax9.axis("off")
    ax9.set_title("SESSION SUMMARY", color=S["green"],
                  fontsize=9, fontfamily="monospace", pad=4)

    summary_lines = [
        ("Total hits",     f"{session.hit_count}"),
        ("Max speed",      f"{session.max_speed_ms:.2f} m/s"),
        ("Avg speed",      f"{session.mean_speed_ms:.2f} m/s"),
        ("Max spin",       f"{session.max_spin_rpm:.0f} rpm"),
        ("Avg reaction",   f"{session.mean_react_s:.3f} s"),
        ("Total KE",       f"{session.total_energy_j:.4f} J"),
        ("Mean Re",        f"{session.mean_re:.0f}"),
        ("Turbulent hits", f"{session.turbulent_pct:.1f}%"),
    ]
    for i, (label, value) in enumerate(summary_lines):
        y = 0.88 - i * 0.11
        ax9.text(0.05, y, label, transform=ax9.transAxes,
                 color=S["dim"], fontsize=8, fontfamily="monospace")
        ax9.text(0.95, y, value, transform=ax9.transAxes,
                 color=S["amber"], fontsize=8, fontfamily="monospace",
                 ha="right", fontweight="bold")

    plt.savefig(outfile, dpi=150, bbox_inches="tight",
                facecolor=S["bg"], edgecolor="none")
    plt.close(fig)
    print(f"[analytics] Graph saved: {outfile}")
    return [outfile]

# ─── CSV export ───────────────────────────────────────────────────────────────
def export_session_csv(session: SessionStats, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    outfile = out_dir / f"session_{session.session_id}.csv"
    fieldnames = [
        "hit_num", "timestamp", "velocity_ms", "speed_kmh", "spin_rpm",
        "kinetic_energy_j", "momentum_kgms", "power_w",
        "reynolds_number", "turbulent", "drag_force_n", "magnus_force_n",
        "reaction_time_s", "hand"
    ]
    with open(outfile, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i, h in enumerate(session.hits):
            w.writerow({
                "hit_num":          i + 1,
                "timestamp":        f"{h.timestamp:.4f}",
                "velocity_ms":      f"{h.velocity_ms:.4f}",
                "speed_kmh":        f"{h.speed_kmh:.3f}",
                "spin_rpm":         f"{h.spin_rpm:.2f}",
                "kinetic_energy_j": f"{h.kinetic_energy_j:.8f}",
                "momentum_kgms":    f"{h.momentum_kgms:.8f}",
                "power_w":          f"{h.power_w:.4f}",
                "reynolds_number":  f"{h.reynolds_number:.1f}",
                "turbulent":        h.turbulent,
                "drag_force_n":     f"{h.drag_verified_n:.8f}",
                "magnus_force_n":   f"{h.magnus_verified_n:.8f}",
                "reaction_time_s":  f"{h.reaction_time_s:.4f}",
                "hand":             h.hand,
            })
    print(f"[analytics] CSV saved: {outfile}")
    return str(outfile)

# ─── TCP server ───────────────────────────────────────────────────────────────
class AnalyticsServer:
    def __init__(self, port: int):
        self.port    = port
        self.session = SessionStats(
            session_id=str(int(time.time())),
            start_time=time.time()
        )

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info("peername")
        print(f"[analytics] Godot connected from {addr}")

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                data = json.loads(line)
                response = self._process_message(data)
                if response:
                    writer.write((json.dumps(response) + "\n").encode())
                    await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionResetError):
                break
            except json.JSONDecodeError as e:
                print(f"[analytics] JSON error: {e}")

        print(f"[analytics] Godot disconnected")
        writer.close()

    def _process_message(self, data: dict) -> Optional[dict]:
        msg_type = data.get("type", "")

        if msg_type == "hit":
            hit = HitEvent(
                timestamp        = data.get("timestamp", time.time()),
                velocity_ms      = data.get("velocity_ms", 0.0),
                speed_kmh        = data.get("speed_kmh", 0.0),
                kinetic_energy_j = data.get("kinetic_energy_j", 0.0),
                spin_rads        = data.get("spin_rads", 0.0),
                spin_rpm         = data.get("spin_rpm", 0.0),
                reaction_time_s  = data.get("reaction_time_s", 0.0),
                hand             = data.get("hand", "unknown"),
                magnus_force_mag = data.get("magnus_force_mag", 0.0),
                drag_force_mag   = data.get("drag_force_mag", 0.0),
            )
            hit.compute_derived()
            self.session.hits.append(hit)
            self.session.update_stats()

            # Return enriched stats back to Godot
            return {
                "type":           "analytics_update",
                "hit_num":        self.session.hit_count,
                "reynolds":       hit.reynolds_number,
                "turbulent":      hit.turbulent,
                "drag_n":         hit.drag_verified_n,
                "magnus_n":       hit.magnus_verified_n,
                "mean_speed":     self.session.mean_speed_ms,
                "std_speed":      self.session.std_speed_ms,
                "p95_speed":      self.session.p95_speed_ms,
                "turbulent_pct":  self.session.turbulent_pct,
                "total_energy_j": self.session.total_energy_j,
                "momentum_kgms":  hit.momentum_kgms,
                "power_w":        hit.power_w,
                "rolling_avg":    _mean([h.velocity_ms for h in
                                        self.session.hits[-10:]]),
            }

        elif msg_type == "export_csv":
            csv_path = export_session_csv(self.session, SESSIONS_DIR)
            graph_paths = generate_session_graphs(self.session, GRAPHS_DIR)
            return {
                "type":   "export_complete",
                "csv":    csv_path,
                "graphs": graph_paths,
            }

        return None

    async def run(self):
        server = await asyncio.start_server(
            self.handle_client, "127.0.0.1", self.port)
        print(f"[analytics] Server listening on port {self.port}")
        print(f"[analytics] matplotlib: {'available' if HAS_MPL else 'MISSING'}")
        async with server:
            await server.serve_forever()

# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cosmic Matrix Pong Analytics")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    GRAPHS_DIR.mkdir(parents=True, exist_ok=True)

    print("╔══════════════════════════════════════════╗")
    print("║  COSMIC PONG ANALYTICS ENGINE  v1.0      ║")
    print("║  Physics-grade telemetry processing      ║")
    print("╚══════════════════════════════════════════╝")

    srv = AnalyticsServer(args.port)
    asyncio.run(srv.run())
