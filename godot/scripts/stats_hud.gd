extends Node3D
class_name StatsHUD
## StatsHUD — Floating physics/math stats panel for Cosmic Matrix Pong
## Three panels: LiveStats (left) | Graphs (center) | PhysicsRef (right)

# ─── Panel references ──────────────────────────────────────────────────────────
@onready var panel_live:    SubViewport    = $LivePanel/Viewport
@onready var panel_graphs:  SubViewport    = $GraphPanel/Viewport
@onready var panel_physics: SubViewport    = $PhysicsPanel/Viewport
@onready var label_v:       RichTextLabel  = $LivePanel/Viewport/VBox/Speed
@onready var label_spin:    RichTextLabel  = $LivePanel/Viewport/VBox/Spin
@onready var label_ke:      RichTextLabel  = $LivePanel/Viewport/VBox/KineticE
@onready var label_magnus:  RichTextLabel  = $LivePanel/Viewport/VBox/Magnus
@onready var label_drag:    RichTextLabel  = $LivePanel/Viewport/VBox/Drag
@onready var label_scores:  RichTextLabel  = $LivePanel/Viewport/VBox/Scores
@onready var label_rally:   RichTextLabel  = $LivePanel/Viewport/VBox/Rally
@onready var graph_speed:   TextureRect    = $GraphPanel/Viewport/Graphs/SpeedGraph
@onready var graph_spin:    TextureRect    = $GraphPanel/Viewport/Graphs/SpinGraph
@onready var graph_ke:      TextureRect    = $GraphPanel/Viewport/Graphs/KEGraph
@onready var graph_react:   TextureRect    = $GraphPanel/Viewport/Graphs/ReactGraph

# ─── Layout constants ──────────────────────────────────────────────────────────
const PANEL_WIDTH:  int = 512
const GRAPH_HEIGHT: int = 88
const MAX_HIST:     int = 100

# ─── Graph ring buffers ────────────────────────────────────────────────────────
var speed_buf:  Array[float] = []
var spin_buf:   Array[float] = []
var ke_buf:     Array[float] = []
var react_buf:  Array[float] = []

# ─── Theme colors ──────────────────────────────────────────────────────────────
const COL_GREEN: Color = Color(0.0,  1.0,  0.2,  1.0)
const COL_CYAN:  Color = Color(0.0,  0.9,  1.0,  1.0)
const COL_AMBER: Color = Color(1.0,  0.8,  0.0,  1.0)
const COL_RED:   Color = Color(1.0,  0.2,  0.1,  1.0)
const COL_DIM:   Color = Color(0.0,  0.4,  0.06, 0.6)
const COL_BG:    Color = Color(0.0,  0.03, 0.01, 0.92)

var _graphs_visible:  bool = true
var _physics_visible: bool = true
var _session_stats:   Dictionary
var _terminal:        TerminalOverlay

# ─── Initialization ────────────────────────────────────────────────────────────
func initialize(stats: Dictionary, terminal: TerminalOverlay) -> void:
	_session_stats = stats
	_terminal = terminal
	_apply_terminal_theme()
	_build_physics_reference_panel()
	# Ensure all panels are visible on start
	$LivePanel.visible    = true
	$GraphPanel.visible   = true
	$PhysicsPanel.visible = true
	_terminal.emit_line("[HUD] Stats overlay initialized — 3 panels visible")
	_terminal.emit_line("[HUD] Left-B = gravity | Right-B = graphs | Menu = physics ref")

func _apply_terminal_theme() -> void:
	for panel_name in ["LivePanel", "GraphPanel", "PhysicsPanel"]:
		var mesh: MeshInstance3D = get_node(panel_name + "/MeshInstance3D")
		if mesh:
			mesh.material_override = _make_panel_material()

func _make_panel_material() -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color      = COL_BG
	mat.emission_enabled  = true
	mat.emission          = COL_GREEN * 0.18
	mat.flags_transparent = true
	mat.cull_mode         = BaseMaterial3D.CULL_DISABLED
	return mat

# ─── Live stats update ─────────────────────────────────────────────────────────
func update_stats(stats: Dictionary) -> void:
	_session_stats = stats
	var spd: float   = stats.get("max_speed_ms", 0.0)
	var avg: float   = stats.get("avg_speed_ms", 0.0)
	var hits: int    = stats.get("hits", 0)
	var sl: int      = stats.get("score_left", 0)
	var sr: int      = stats.get("score_right", 0)

	_set_label(label_v,
		"[color=#00ff33]SPEED[/color]  v = [b]%.2f m/s[/b]  (%.1f km/h)\n" % \
		[avg, avg * 3.6] +
		"  max = [color=#ffcc00]%.2f m/s[/color]" % spd)

	var spin_hist: Array = stats.get("spin_history", [])
	if spin_hist.size() > 0:
		var spin: float = spin_hist.back()
		_set_label(label_spin,
			"[color=#00ccff]SPIN[/color]   ω = [b]%.1f rpm[/b]  (%.2f rad/s)\n" % \
			[spin * 9.549, spin] +
			"  max = [color=#ffcc00]%.1f rpm[/color]" % (stats.get("max_spin_rads", 0.0) * 9.549))
	else:
		_set_label(label_spin,
			"[color=#00ccff]SPIN[/color]   ω = [b]0 rpm[/b]  (0.00 rad/s)\n  max = 0 rpm")

	var ke_hist: Array = stats.get("kinetic_energy_history", [])
	if ke_hist.size() > 0:
		var ke: float = ke_hist.back()
		_set_label(label_ke,
			"[color=#ff6633]KE[/color]     E = [b]%.5f J[/b]\n" % ke +
			"  p = %.6f kg·m/s" % (0.0027 * avg))
	else:
		_set_label(label_ke, "[color=#ff6633]KE[/color]     E = [b]0.00000 J[/b]\n  p = 0 kg·m/s")

	_set_label(label_magnus,
		"[color=#00ccff]MAGNUS[/color]  Fm = [b]%.5f N[/b]" % 0.0)

	_set_label(label_drag,
		"[color=#00ccff]DRAG[/color]    Fd = [b]%.5f N[/b]" % 0.0)

	_set_label(label_scores,
		"[center][color=#00ff33][b]%d[/b][/color] — [color=#00ccff][b]%d[/b][/color][/center]" % \
		[sl, sr])

	_set_label(label_rally,
		"Rally [b]%d[/b] hits | Dist: %.1f m" % [hits, stats.get("total_distance_m", 0.0)])

	_update_graph_buffers(stats)
	_redraw_graphs()

func _set_label(lbl: RichTextLabel, text: String) -> void:
	lbl.bbcode_enabled = true
	lbl.text = text

# ─── Mini graph drawing via Image ──────────────────────────────────────────────
func _update_graph_buffers(stats: Dictionary) -> void:
	var push := func(buf: Array, arr: Array) -> void:
		if arr.size() > 0:
			buf.append(arr.back())
			if buf.size() > MAX_HIST:
				buf.pop_front()
	push.call(speed_buf,  stats.get("speed_history", []))
	push.call(spin_buf,   stats.get("spin_history", []))
	push.call(ke_buf,     stats.get("kinetic_energy_history", []))
	push.call(react_buf,  stats.get("reaction_times", []))

func _redraw_graphs() -> void:
	graph_speed.texture = _draw_graph(speed_buf,  COL_GREEN, "SPEED m/s")
	graph_spin.texture  = _draw_graph(spin_buf,   COL_CYAN,  "SPIN rpm")
	graph_ke.texture    = _draw_graph(ke_buf,     COL_AMBER, "KE Joules")
	graph_react.texture = _draw_graph(react_buf,  COL_RED,   "REACT s")

func _draw_graph(data: Array, col: Color, _label: String) -> ImageTexture:
	var img := Image.create(PANEL_WIDTH, GRAPH_HEIGHT, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0.02, 0.01, 0.95))

	if data.size() < 2:
		return ImageTexture.create_from_image(img)

	var mn: float = data[0]
	var mx: float = data[0]
	for v in data:
		mn = minf(mn, v)
		mx = maxf(mx, v)
	if absf(mx - mn) < 0.0001:
		mx = mn + 0.0001

	# Grid lines
	for gi in range(4):
		var gy: int = int(GRAPH_HEIGHT * gi / 4)
		for px in range(PANEL_WIDTH):
			if px % 8 < 3:
				img.set_pixel(px, gy, Color(0.1, 0.3, 0.1, 0.4))

	# Data line
	for i in range(data.size() - 1):
		var x0: int = int(i * (PANEL_WIDTH - 1) / float(data.size() - 1))
		var x1: int = int((i + 1) * (PANEL_WIDTH - 1) / float(data.size() - 1))
		var y0: int = GRAPH_HEIGHT - 1 - int((data[i]   - mn) / (mx - mn) * (GRAPH_HEIGHT - 2))
		var y1: int = GRAPH_HEIGHT - 1 - int((data[i+1] - mn) / (mx - mn) * (GRAPH_HEIGHT - 2))
		_draw_line_img(img, x0, y0, x1, y1, col)
		# Area fill
		for py in range(min(y0, y1), GRAPH_HEIGHT):
			if _px_ok(x0, py):
				img.set_pixel(x0, py, COL_DIM)

	# Current value dot
	var lx: int = PANEL_WIDTH - 1
	var ly: int = GRAPH_HEIGHT - 1 - int((data.back() - mn) / (mx - mn) * (GRAPH_HEIGHT - 2))
	_draw_dot(img, lx, ly, COL_AMBER, 3)

	return ImageTexture.create_from_image(img)

func _draw_line_img(img: Image, x0: int, y0: int, x1: int, y1: int, c: Color) -> void:
	var dx: int  = absi(x1 - x0)
	var dy: int  = absi(y1 - y0)
	var sx: int  = 1 if x0 < x1 else -1
	var sy: int  = 1 if y0 < y1 else -1
	var err: int = dx - dy
	while true:
		if _px_ok(x0, y0):
			img.set_pixel(x0, y0, c)
		if x0 == x1 and y0 == y1:
			break
		var e2: int = 2 * err
		if e2 > -dy:
			err -= dy; x0 += sx
		if e2 < dx:
			err += dx; y0 += sy

func _draw_dot(img: Image, cx: int, cy: int, c: Color, r: int) -> void:
	for dx in range(-r, r + 1):
		for dy in range(-r, r + 1):
			if dx * dx + dy * dy <= r * r:
				if _px_ok(cx + dx, cy + dy):
					img.set_pixel(cx + dx, cy + dy, c)

func _px_ok(x: int, y: int) -> bool:
	return x >= 0 and x < PANEL_WIDTH and y >= 0 and y < GRAPH_HEIGHT

# ─── Physics reference panel ───────────────────────────────────────────────────
func _build_physics_reference_panel() -> void:
	var lbl: RichTextLabel = panel_physics.get_node("PhysicsRef")
	if not lbl:
		return
	lbl.bbcode_enabled = true
	lbl.text = """[color=#00ff33][b]■ PHYSICS REFERENCE[/b][/color]

[color=#00ccff]Drag Force (N):[/color]
  F_d = ½ρC_d·A·v²
  ρ=1.293 kg/m³  C_d=0.47

[color=#00ccff]Magnus Force (N):[/color]
  F_m = k(ω × v)
  k = 1.5×10⁻⁴

[color=#00ccff]Kinetic Energy (J):[/color]
  E_k = ½mv²   m=2.7g

[color=#00ccff]Restitution:[/color]
  e = v_out/v_in ≈ 0.89

[color=#00ccff]Reynolds Number:[/color]
  Re = ρvD/μ
  turbulent if Re > 4×10⁴

[color=#00ccff]Impulse-Momentum:[/color]
  Δp = F·Δt = m·Δv

[color=#ffcc00]CONTROLS:[/color]
  Left A/X = reset ball
  Left B/Y = cycle gravity
  Right B   = toggle graphs
  Menu      = physics ref"""

# ─── Visibility toggles ────────────────────────────────────────────────────────
func toggle_graphs() -> void:
	_graphs_visible = !_graphs_visible
	$GraphPanel.visible = _graphs_visible
	if _terminal:
		_terminal.emit_line("[HUD] Graph panel %s" % ("ON" if _graphs_visible else "OFF"))

func toggle_full_view() -> void:
	_physics_visible = !_physics_visible
	$PhysicsPanel.visible = _physics_visible
	if _terminal:
		_terminal.emit_line("[HUD] Physics ref panel %s" % ("ON" if _physics_visible else "OFF"))

func update_graphs(python_data: Dictionary) -> void:
	if "rolling_avg" in python_data:
		pass  # extend: overlay rolling avg on speed graph
