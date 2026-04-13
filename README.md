# 🏓 COSMIC MATRIX PONG
## Physics-Accurate VR Ping Pong for Pico 4
### Godot 4 + Python | Nerdy Physics & Math Edition

```
╔══════════════════════════════════════════╗
║   COSMIC MATRIX PONG — PHYSICS ENGINE    ║
║          Pico 4 VR Edition v1.0          ║
╚══════════════════════════════════════════╝
```

---

## Architecture Overview

```
godot/                      ← Godot 4.2 project (GDScript)
├── scripts/
│   ├── main.gd             ← Core game loop + physics integration
│   ├── stats_hud.gd        ← Floating VR stats panels + mini-graphs
│   ├── terminal_overlay.gd ← Matrix-style scrolling telemetry terminal
│   └── python_bridge.gd    ← TCP bridge to Python analytics
├── scenes/
│   ├── main.tscn           ← Root scene (XR + physics bodies)
│   ├── stats_hud.tscn      ← 3-panel floating stats display
│   └── terminal.tscn       ← Matrix terminal overlay
├── assets/shaders/
│   └── matrix_terminal.gdshader  ← CRT/scanline/phosphor shader
└── project.godot

python/
├── analytics_server.py     ← TCP server, real-time physics processing
├── session_analyzer.py     ← Post-session deep analysis + 12-panel graphs
└── test_physics.py         ← Unit tests (16 physics equations verified ✓)
```

---

## Physics Engine

All equations implemented with real ITTF-spec constants:

| Quantity | Formula | Constants |
|---|---|---|
| Aerodynamic drag | F_d = ½ρC_d A v² | ρ=1.293 kg/m³, C_d=0.47 |
| Magnus force | F_m = k(ω × v) | k=1.5×10⁻⁴ |
| Kinetic energy | E_k = ½mv² | m=2.7g (ITTF) |
| Reynolds number | Re = ρvD/μ | μ=1.81×10⁻⁵ Pa·s |
| Bounce height | h = e²·h₀ | e=0.89 (coefficient of restitution) |
| Momentum | p = mv | m=2.7g |
| Impact power | P = E/Δt | — |
| Turbulence onset | Re > 4×10⁴ | v_crit ≈ 14.0 m/s |

### Gravity Modes (toggle with [BY] button)

| Mode | g (m/s²) | Effect |
|---|---|---|
| Earth | 9.81 | Normal |
| Mars | 3.72 | Floaty, longer rallies |
| Moon | 1.62 | Ultra-slow arcs |
| Jupiter | 24.79 | Brutal, fast drops |
| Zero-G | 0.00 | Pure skill, no gravity |
| Orbital | dynamic | Centripetal gravity field |

---

## VR Features (Pico 4)

- **Haptic feedback** on every hit — amplitude scales with impact KE
  - Soft tap: F ≈ 0.25 amp, 80 Hz
  - Power shot: F ≈ 0.90 amp, 180 Hz
- **90Hz stereo rendering** via OpenXR
- **3 floating stats panels** in VR space:
  1. Live telemetry (speed, spin, KE, forces)
  2. Rolling graphs (speed, spin, KE, reaction time)
  3. Physics reference equations
- Controller shortcuts:
  - `[AX]` — Reset ball
  - `[BY]` — Cycle gravity mode
  - `[Menu]` — Toggle full stats view

---

## Matrix Terminal Display

The green-on-black terminal overlay prints:

```
[0000.123] [HIT #42] v=18.3m/s | ω=1420rpm | KE=0.00045J | F_mag=0.0032N
[0000.456] [BOUNCE]  h≈0.243m  | e=0.89    | F_drag=0.0381N
[0000.789] [GRAVITY] Mode: MOON | g=1.62m/s² [0.00, -1.62, 0.00]
```

Live readout panel (2Hz update):
```
┌─ LIVE TELEMETRY ──────────────────────┐
│ v  18.3m/s       ω  1420rpm           │
│ KE 0.00045J      g  MOON              │
│ Fd 0.0381N       Fm 0.0032N           │
└───────────────────────────────────────┘
```

---

## Python Analytics

### Real-time server (`analytics_server.py`)

Receives events from Godot via TCP port 8765. Computes per-hit:
- Reynolds number + turbulence classification
- Verified drag/Magnus forces from raw data
- Rolling statistics (mean, std, p95)
- Reaction time analysis
- Sends enriched data back to Godot for HUD update

### Post-session analysis (`session_analyzer.py`)

Generates 12-panel physics analysis figure:

1. Speed timeline + Savitzky-Golay trend
2. Spin timeline
3. Kinetic energy per hit
4. Reaction time scatter + trend
5. Reynolds number scatter (green=laminar, red=turbulent)
6. Drag vs Magnus force comparison
7. Speed histogram + KDE curve
8. Speed vs Spin correlation scatter
9. Impact power per hit
10. Cumulative energy
11. Left vs Right hand boxplot
12. Coaching insights panel

### Usage

```bash
# Install dependencies
pip install matplotlib numpy scipy

# Run analytics server (auto-launched by Godot)
python3 python/analytics_server.py --port 8765

# Post-session analysis
python3 python/session_analyzer.py sessions/session_1234567890.csv

# Run physics tests
python3 python/test_physics.py
```

---

## Setup & Installation

### Requirements

- **Godot 4.2+** with OpenXR plugin
- **Pico 4** headset with developer mode enabled
- **Python 3.10+** with pip
- `pip install matplotlib numpy scipy`

### Godot Setup

1. Open `godot/` as a Godot 4 project
2. Enable **OpenXR** in Project Settings → XR
3. Install **GodotXR Tools** from Asset Library
4. Set build target: Android (arm64) for Pico 4

### Pico 4 Deployment

```bash
# Enable ADB on Pico 4 (Settings → General → Developer → USB Debugging)
adb connect [PICO_IP]:5555
# Export from Godot: Project → Export → Android
# Or use Godot's "Run on Device" button
```

### Desktop Testing (no headset)

The game falls back to desktop mode if OpenXR isn't available.
Mouse controls paddle, keyboard shortcuts work.

---

## Stats Exported

Every session exports to CSV with columns:

```
hit_num, timestamp, velocity_ms, speed_kmh, spin_rpm,
kinetic_energy_j, momentum_kgms, power_w,
reynolds_number, turbulent, drag_force_n, magnus_force_n,
reaction_time_s, hand
```

---

## Physics Test Results

```
Ran 16 tests in 0.001s — OK ✓

Verified:
✓ Drag force at 10 m/s:   F_d = 0.0382 N
✓ Drag force at 25 m/s:   F_d = 0.2386 N
✓ Kinetic energy:          E_k = 0.135 J  (m=2.7g, v=10m/s)
✓ Reynolds number:         Re = 28619  (v=10m/s, laminar)
✓ Turbulence threshold:    v_crit ≈ 14.0 m/s
✓ Magnus cross product:    |F_m| = k·|ω×v| = 500·k
✓ Bounce height energy:    h_after = e²·h₀ = 0.238m
✓ ITTF ball spec:          m=2.7g, d=40mm, e=0.89
✓ Spin unit conversion:    ω·9.5493 = rpm
✓ All gravity modes:       0 ≤ g ≤ 30 m/s²
```

---

## License

MIT — build, fork, and nerd out freely.

*"The ball is a rigid body. The universe is your table."*
