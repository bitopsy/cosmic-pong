extends Node3D

## Cosmic Matrix Ping Pong — Main Scene
## Physics engine: Newtonian + Magnus Effect + Gravity Fields
## VR: Pico 4 via OpenXR

# ─── Node references ──────────────────────────────────────────────────────────
@onready var ball: RigidBody3D               = $Ball
@onready var paddle_left: XRController3D     = $XROrigin3D/LeftController
@onready var paddle_right: XRController3D    = $XROrigin3D/RightController
@onready var table: StaticBody3D             = $Table
@onready var stats_hud: StatsHUD             = $StatsHUD
@onready var gravity_field: Area3D           = $GravityField
@onready var terminal_overlay: TerminalOverlay = $TerminalOverlay
@onready var xr_origin: XROrigin3D           = $XROrigin3D
@onready var audio_player: AudioStreamPlayer3D = $AudioPlayer
@onready var python_bridge: PythonBridge     = $PythonBridge
@onready var ai_paddle: StaticBody3D         = $AIPaddle

# ─── Physics constants ─────────────────────────────────────────────────────────
const GRAVITY_EARTH:    float = 9.81
const BALL_MASS:        float = 0.0027
const BALL_RADIUS:      float = 0.02
const BALL_RESTITUTION: float = 0.89
const AIR_DENSITY:      float = 1.293
const DRAG_COEFF:       float = 0.47
const MAGNUS_COEFF:     float = 0.00015
const TABLE_FRICTION:   float = 0.35

# ─── Game state ───────────────────────────────────────────────────────────────
var score_left:  int = 0
var score_right: int = 0
var rally_count: int = 0
var current_gravity_mode: String = "earth"
var game_started: bool = false
var serve_side: int = 1  # 1 = player serves, -1 = AI serves
var gravity_modes: Dictionary = {
	"earth":   Vector3(0, -9.81,  0),
	"mars":    Vector3(0, -3.72,  0),
	"moon":    Vector3(0, -1.62,  0),
	"jupiter": Vector3(0, -24.79, 0),
	"zero_g":  Vector3(0,  0,     0),
	"orbital": Vector3(0, -9.81,  0),
}

# ─── Ball physics state ───────────────────────────────────────────────────────
var ball_spin: Vector3      = Vector3.ZERO
var ball_velocity: Vector3  = Vector3.ZERO
var contact_normal: Vector3 = Vector3.ZERO
var magnus_force: Vector3   = Vector3.ZERO
var drag_force: Vector3     = Vector3.ZERO
var impact_velocity: float  = 0.0
var _ball_in_play: bool     = false

# ─── AI opponent state ────────────────────────────────────────────────────────
var _ai_target: Vector3    = Vector3.ZERO
var _ai_speed: float       = 3.5  # m/s
var _ai_error: float       = 0.04 # intentional miss radius (m)

# ─── Session statistics ────────────────────────────────────────────────────────
var session_stats: Dictionary = {
	"hits": 0,
	"max_speed_ms": 0.0,
	"max_spin_rads": 0.0,
	"avg_speed_ms": 0.0,
	"speed_history": [],
	"spin_history": [],
	"impact_angles": [],
	"kinetic_energy_history": [],
	"rally_lengths": [],
	"reaction_times": [],
	"bounce_heights": [],
	"total_distance_m": 0.0,
	"last_hit_time": 0.0,
	"score_left": 0,
	"score_right": 0,
}

# ─── Haptic settings ──────────────────────────────────────────────────────────
const HAPTIC_DURATION_SOFT: float = 0.02
const HAPTIC_DURATION_HARD: float = 0.08
const HAPTIC_FREQ_SOFT:     float = 80.0
const HAPTIC_FREQ_HARD:     float = 180.0
const HAPTIC_AMP_SOFT:      float = 0.25
const HAPTIC_AMP_HARD:      float = 0.9

var xr_interface: XRInterface
var _hit_timestamp: float = 0.0

# ─── Initialization ────────────────────────────────────────────────────────────
func _ready() -> void:
	_init_xr()
	_setup_physics()
	_connect_signals()
	python_bridge.start_analytics_server()
	stats_hud.initialize(session_stats, terminal_overlay)
	terminal_overlay.emit_line("[SYSTEM] Cosmic Matrix Pong v1.1 — ONLINE")
	terminal_overlay.emit_line("[PHYSICS] g = %.2f m/s² | ρ = %.3f kg/m³" % [
		GRAVITY_EARTH, AIR_DENSITY])
	terminal_overlay.emit_line("[VR] Pico 4 — OpenXR interface ready")
	terminal_overlay.emit_line("[CTRL] A/X = reset | B/Y(left) = cycle gravity")
	terminal_overlay.emit_line("[CTRL] B(right) = graphs | Menu = physics ref")
	terminal_overlay.emit_line("[CTRL] Trigger = serve ball")
	_position_ball_for_serve()

func _init_xr() -> void:
	xr_interface = XRServer.find_interface("OpenXR")
	if xr_interface and xr_interface.is_initialized():
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		get_viewport().use_xr = true
		terminal_overlay.emit_line("[XR] OpenXR active — 90Hz stereo")
	else:
		push_warning("OpenXR not available — running in desktop fallback mode")
		terminal_overlay.emit_line("[XR] WARN: Desktop fallback mode")

func _setup_physics() -> void:
	PhysicsServer3D.set_active(true)
	ball.gravity_scale = 0.0   # we apply gravity manually in _integrate_forces
	ball.linear_damp   = 0.0   # we apply drag manually
	ball.angular_damp  = 0.05
	ball.mass          = BALL_MASS
	ball.physics_material_override = PhysicsMaterial.new()
	ball.physics_material_override.bounce    = BALL_RESTITUTION
	ball.physics_material_override.friction  = TABLE_FRICTION
	ball.custom_integrator = true

func _connect_signals() -> void:
	ball.body_entered.connect(_on_ball_collision)
	paddle_left.button_pressed.connect(_on_left_button)
	paddle_right.button_pressed.connect(_on_right_button)
	# Trigger to serve
	paddle_left.input_float_changed.connect(_on_left_input_float)
	paddle_right.input_float_changed.connect(_on_right_input_float)
	gravity_field.body_entered.connect(_on_gravity_field_entered)
	python_bridge.analytics_ready.connect(_on_analytics_update)

# ─── Physics integration (custom per-frame) ───────────────────────────────────
func _integrate_forces(state: PhysicsDirectBodyState3D) -> void:
	ball_velocity = state.linear_velocity
	ball_spin     = state.angular_velocity

	# 1. Gravity
	var g_vec: Vector3 = gravity_modes[current_gravity_mode]
	state.apply_central_force(g_vec * BALL_MASS)

	# 2. Aerodynamic drag  F_d = -½ρCdAv²v̂
	var v_sq: float  = ball_velocity.length_squared()
	var area: float  = PI * BALL_RADIUS * BALL_RADIUS
	drag_force = -0.5 * AIR_DENSITY * DRAG_COEFF * area * v_sq * ball_velocity.normalized()
	state.apply_central_force(drag_force)

	# 3. Magnus effect  F_m = k(ω × v)
	magnus_force = MAGNUS_COEFF * ball_spin.cross(ball_velocity)
	state.apply_central_force(magnus_force)

	# 4. Orbital gravity field
	if current_gravity_mode == "orbital":
		var r_vec: Vector3 = ball.global_position - Vector3.ZERO
		var r: float       = r_vec.length()
		if r > 0.1:
			var orbital_g: float = 9.81 * 4.0 / (r * r)
			state.apply_central_force(-r_vec.normalized() * orbital_g * BALL_MASS)

	# 5. Distance tracker
	session_stats["total_distance_m"] += ball_velocity.length() * state.step

func _physics_process(_delta: float) -> void:
	ball_velocity = ball.linear_velocity
	_update_stats_frame()
	_update_ai_paddle(_delta)
	_check_ball_out_of_bounds()

func _process(_delta: float) -> void:
	_update_terminal_readout()

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_T and event.ctrl_pressed and event.alt_pressed:
			stats_hud.toggle_graphs()

# ─── Serve mechanics ──────────────────────────────────────────────────────────
func _position_ball_for_serve() -> void:
	_ball_in_play = false
	ball.linear_velocity  = Vector3.ZERO
	ball.angular_velocity = Vector3.ZERO
	# Place ball near the server's side
	var x_side: float = serve_side * 0.5
	ball.global_position  = Vector3(x_side, 0.85, 0.0)
	rally_count = 0
	terminal_overlay.emit_line("[SERVE] Pull trigger to serve → side=%s" % (
		"PLAYER" if serve_side == 1 else "AI"))

func _on_left_input_float(action: String, value: float) -> void:
	if action == "trigger" and value > 0.8 and not _ball_in_play:
		_launch_serve()

func _on_right_input_float(action: String, value: float) -> void:
	if action == "trigger" and value > 0.8 and not _ball_in_play:
		_launch_serve()

func _launch_serve() -> void:
	_ball_in_play = true
	# Give ball an initial velocity toward center/net
	var dir: Vector3 = Vector3(-serve_side * 1.0, 0.3, randf_range(-0.3, 0.3)).normalized()
	ball.linear_velocity = dir * 3.5
	ball.angular_velocity = Vector3(randf_range(-5, 5), randf_range(-5, 5), 0)
	terminal_overlay.emit_line("[SERVE] Ball launched at %.1f m/s" % ball.linear_velocity.length())

func _check_ball_out_of_bounds() -> void:
	var pos: Vector3 = ball.global_position
	# Ball fell below table or went too far
	if pos.y < 0.0 or absf(pos.x) > 2.5 or absf(pos.z) > 2.0:
		if _ball_in_play:
			_ball_out_of_bounds(pos)

func _ball_out_of_bounds(pos: Vector3) -> void:
	# Determine who scored based on which side the ball left from
	if pos.x < -2.0:
		# Ball went past player's side → AI scores
		score_right += 1
		terminal_overlay.emit_line("[POINT] AI scores! %d — %d" % [score_left, score_right])
		serve_side = -1  # AI serves next
		_trigger_haptic("left", 0.2, 60.0, 0.6)
		_trigger_haptic("right", 0.2, 60.0, 0.6)
	elif pos.x > 2.0:
		# Ball went past AI's side → Player scores
		score_left += 1
		terminal_overlay.emit_line("[POINT] Player scores! %d — %d" % [score_left, score_right])
		serve_side = 1
		_trigger_haptic("left", 0.08, 180.0, 0.9)
		_trigger_haptic("right", 0.08, 180.0, 0.9)
	else:
		# Fell off side or below
		terminal_overlay.emit_line("[OUT] Ball out of bounds")

	session_stats["score_left"]  = score_left
	session_stats["score_right"] = score_right
	if session_stats["hits"] > 0:
		session_stats["rally_lengths"].append(rally_count)
	stats_hud.update_stats(session_stats)
	await get_tree().create_timer(1.5).timeout
	_position_ball_for_serve()

# ─── AI Paddle ────────────────────────────────────────────────────────────────
func _update_ai_paddle(delta: float) -> void:
	if not _ball_in_play:
		return
	# AI paddle tracks ball on Z and Y axes (paddle on AI's side, X = +1.2)
	var ball_pos: Vector3 = ball.global_position
	# Only react when ball is coming toward AI (positive X velocity)
	if ball_velocity.x > 0:
		_ai_target = Vector3(1.2, clampf(ball_pos.y, 0.75, 1.4),
				clampf(ball_pos.z + randf_range(-_ai_error, _ai_error), -0.6, 0.6))
	var current: Vector3 = ai_paddle.global_position
	var new_pos: Vector3 = current.move_toward(_ai_target, _ai_speed * delta)
	ai_paddle.global_position = new_pos

# ─── Collision handling ────────────────────────────────────────────────────────
func _on_ball_collision(body: Node) -> void:
	impact_velocity = ball_velocity.length()
	var ke: float       = 0.5 * BALL_MASS * impact_velocity * impact_velocity
	var spin_mag: float = ball_spin.length()

	if body.is_in_group("paddle"):
		_handle_paddle_hit(body, ke, spin_mag)
	elif body.is_in_group("ai_paddle"):
		_handle_ai_paddle_hit(ke, spin_mag)
	elif body.is_in_group("table"):
		_handle_table_bounce(ke)
	elif body.is_in_group("net"):
		_handle_net_hit()

func _handle_paddle_hit(paddle: Node3D, ke: float, spin: float) -> void:
	var haptic_amp: float  = clampf(ke / 0.5, HAPTIC_AMP_SOFT, HAPTIC_AMP_HARD)
	var haptic_freq: float = lerpf(HAPTIC_FREQ_SOFT, HAPTIC_FREQ_HARD, haptic_amp)
	var haptic_dur: float  = lerpf(HAPTIC_DURATION_SOFT, HAPTIC_DURATION_HARD, haptic_amp)
	var hand: String = "left" if paddle == paddle_left else "right"
	_trigger_haptic(hand, haptic_dur, haptic_freq, haptic_amp)
	_record_hit(ke, spin, hand)

func _handle_ai_paddle_hit(ke: float, spin: float) -> void:
	# Reflect ball back with slight randomness
	var vel: Vector3 = ball.linear_velocity
	vel.x = -absf(vel.x) * 0.95  # bounce back
	vel.z += randf_range(-0.5, 0.5)
	ball.linear_velocity = vel
	_record_hit(ke, spin, "ai")
	terminal_overlay.emit_line("[AI HIT] v=%.1fm/s" % vel.length())

func _record_hit(ke: float, spin: float, hand: String) -> void:
	var now: float     = Time.get_ticks_msec() / 1000.0
	var reaction: float = now - session_stats["last_hit_time"] if session_stats["last_hit_time"] > 0.0 else 0.0
	session_stats["last_hit_time"] = now
	session_stats["hits"] += 1
	session_stats["speed_history"].append(impact_velocity)
	session_stats["spin_history"].append(spin)
	session_stats["kinetic_energy_history"].append(ke)
	session_stats["reaction_times"].append(reaction)
	session_stats["max_speed_ms"]  = maxf(session_stats["max_speed_ms"], impact_velocity)
	session_stats["max_spin_rads"] = maxf(session_stats["max_spin_rads"], spin)
	rally_count += 1

	if hand != "ai":
		python_bridge.record_hit({
			"timestamp": now,
			"velocity_ms": impact_velocity,
			"speed_kmh": impact_velocity * 3.6,
			"kinetic_energy_j": ke,
			"spin_rads": spin,
			"spin_rpm": spin * 9.549,
			"reaction_time_s": reaction,
			"hand": hand,
			"magnus_force_mag": magnus_force.length(),
			"drag_force_mag": drag_force.length(),
		})
		terminal_overlay.emit_line(
			"[HIT #%d] v=%.1fm/s | ω=%.0frpm | KE=%.4fJ | Fm=%.4fN" % [
			session_stats["hits"], impact_velocity, spin * 9.549, ke, magnus_force.length()])

	session_stats["score_left"]  = score_left
	session_stats["score_right"] = score_right
	stats_hud.update_stats(session_stats)

func _handle_table_bounce(ke: float) -> void:
	var bounce_h: float = ke / (BALL_MASS * GRAVITY_EARTH)
	session_stats["bounce_heights"].append(bounce_h)
	terminal_overlay.emit_line(
		"[BOUNCE] h≈%.3fm | e=%.2f | Fd=%.5fN" % [
		bounce_h, BALL_RESTITUTION, drag_force.length()])

func _handle_net_hit() -> void:
	terminal_overlay.emit_line("[NET] Ball touched net — letting physics decide")
	_trigger_haptic("right", 0.15, 60.0, 0.4)
	_trigger_haptic("left",  0.15, 60.0, 0.4)

# ─── Haptics ──────────────────────────────────────────────────────────────────
func _trigger_haptic(hand: String, duration: float, frequency: float, amplitude: float) -> void:
	var tracker_name: StringName = &"/user/hand/left" if hand == "left" else &"/user/hand/right"
	var tracker: XRPositionalTracker = XRServer.get_tracker(tracker_name)
	if tracker:
		tracker.trigger_haptic_pulse("haptic", frequency, amplitude, duration, 0.0)

# ─── Ball reset ───────────────────────────────────────────────────────────────
func _reset_ball() -> void:
	_position_ball_for_serve()
	terminal_overlay.emit_line("[RESET] Ball reset | g=%s" % current_gravity_mode)

# ─── Gravity mode switching ───────────────────────────────────────────────────
func set_gravity_mode(mode: String) -> void:
	if mode in gravity_modes:
		current_gravity_mode = mode
		var g_vec: Vector3 = gravity_modes[mode]
		terminal_overlay.emit_line(
			"[GRAVITY] Mode: %s | g=%.2fm/s²" % [mode.to_upper(), g_vec.length()])

# ─── Controller buttons ───────────────────────────────────────────────────────
func _on_left_button(button: String) -> void:
	match button:
		"ax_button":   _reset_ball()
		"by_button":   _cycle_gravity()
		"menu_button": stats_hud.toggle_full_view()

func _on_right_button(button: String) -> void:
	match button:
		"ax_button":   _reset_ball()
		"by_button":   stats_hud.toggle_graphs()        # ← fixed: B = graphs toggle
		"menu_button": stats_hud.toggle_full_view()

func _cycle_gravity() -> void:
	var modes: Array = gravity_modes.keys()
	var idx: int     = modes.find(current_gravity_mode)
	idx              = (idx + 1) % modes.size()
	set_gravity_mode(modes[idx])

# ─── Frame stats update ───────────────────────────────────────────────────────
func _update_stats_frame() -> void:
	var spd: float = ball_velocity.length()
	if spd > 0:
		var hist: Array = session_stats["speed_history"]
		if hist.size() > 0:
			var total: float = 0.0
			for v in hist:
				total += v
			session_stats["avg_speed_ms"] = total / hist.size()

func _update_terminal_readout() -> void:
	if Engine.get_process_frames() % 30 == 0:
		terminal_overlay.set_live_values({
			"v":  "%.2fm/s" % ball_velocity.length(),
			"ω":  "%.0frpm" % (ball_spin.length() * 9.549),
			"KE": "%.5fJ"   % (0.5 * BALL_MASS * ball_velocity.length_squared()),
			"Fd": "%.5fN"   % drag_force.length(),
			"Fm": "%.5fN"   % magnus_force.length(),
			"g":  current_gravity_mode,
		})

func _on_gravity_field_entered(body: Node) -> void:
	if body == ball and current_gravity_mode == "orbital":
		terminal_overlay.emit_line("[ORBIT] Ball entered gravity well")

func _on_analytics_update(data: Dictionary) -> void:
	stats_hud.update_graphs(data)
