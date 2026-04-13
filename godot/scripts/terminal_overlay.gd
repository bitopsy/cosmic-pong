extends Node3D
## TerminalOverlay — Matrix-style terminal rendered on a 3D quad in VR space
## Attach to a Node3D. The SubViewport renders into the quad mesh.
class_name TerminalOverlay

@onready var log_label:    RichTextLabel = $Viewport/VBox/LogScroll
@onready var live_label:   RichTextLabel = $Viewport/VBox/LiveReadout
@onready var cursor_blink: Timer         = $Viewport/CursorTimer

const MAX_LOG_LINES: int  = 40
const LINE_PREFIX: String = "[color=#004408]>[/color] "

var _log_lines:      Array[String] = []
var _cursor_visible: bool          = true
var _live_vals:      Dictionary    = {}

const C_GREEN := "[color=#00ff33]"
const C_CYAN  := "[color=#00ddff]"
const C_AMBER := "[color=#ffcc00]"
const C_DIM   := "[color=#00661a]"
const C_RED   := "[color=#ff3322]"
const C_WHITE := "[color=#ccffdd]"
const C_END   := "[/color]"

func _ready() -> void:
	log_label.bbcode_enabled   = true
	live_label.bbcode_enabled  = true
	log_label.scroll_following = true
	cursor_blink.timeout.connect(_blink_cursor)
	cursor_blink.start(0.5)
	_render_boot_sequence()

func _render_boot_sequence() -> void:
	var lines: Array[String] = [
		"╔══════════════════════════════════════════╗",
		"║   COSMIC MATRIX PONG — PHYSICS ENGINE    ║",
		"║          Pico 4 VR Edition v1.1          ║",
		"╚══════════════════════════════════════════╝",
		"",
		"[BOOT] Initializing OpenXR runtime..........OK",
		"[BOOT] Loading physics constants............OK",
		"[BOOT] Starting Python analytics bridge....OK",
		"[BOOT] Calibrating haptic motors............OK",
		"[BOOT] Mounting XR displays.................OK",
		"",
		"Pull trigger to serve | Left-B = gravity",
		"Right-B = graphs | Menu = physics ref",
		"═══════════════════════════════════════════",
	]
	for line in lines:
		emit_line(line)

func emit_line(text: String) -> void:
	var ts: String      = "[%s]" % _timestamp()
	var colored: String = _colorize_line(text)
	_log_lines.append("%s%s%s %s" % [C_DIM, ts, C_END, colored])
	if _log_lines.size() > MAX_LOG_LINES:
		_log_lines.pop_front()
	_render_log()

func set_live_values(vals: Dictionary) -> void:
	_live_vals = vals
	_render_live()

func _render_log() -> void:
	log_label.text = "\n".join(_log_lines)
	if _cursor_visible:
		log_label.text += "\n%s█%s" % [C_GREEN, C_END]

func _render_live() -> void:
	if _live_vals.is_empty():
		return
	var v:  String = _live_vals.get("v",  "—")
	var sp: String = _live_vals.get("ω",  "—")
	var ke: String = _live_vals.get("KE", "—")
	var fd: String = _live_vals.get("Fd", "—")
	var fm: String = _live_vals.get("Fm", "—")
	var g:  String = _live_vals.get("g",  "—").to_upper()

	live_label.text = (
		"┌─ LIVE TELEMETRY ─────────────────────┐\n" +
		"│ %sv%s  %-10s  %sω%s  %-12s │\n" % [C_GREEN, C_END, v, C_CYAN, C_END, sp] +
		"│ %sKE%s %-11s  %sg%s  %-12s │\n" % [C_AMBER, C_END, ke, C_DIM, C_END, g] +
		"│ %sFd%s %-11s  %sFm%s %-12s │\n" % [C_DIM, C_END, fd, C_DIM, C_END, fm] +
		"└──────────────────────────────────────┘"
	)

func _colorize_line(line: String) -> String:
	if line.begins_with("[HIT"):       return C_GREEN + line + C_END
	elif line.begins_with("[BOUNCE"):  return C_CYAN  + line + C_END
	elif line.begins_with("[POINT"):   return C_AMBER + line + C_END
	elif line.begins_with("[WARN") or line.begins_with("[NET"): return C_AMBER + line + C_END
	elif line.begins_with("[ERROR") or line.begins_with("[FAULT"): return C_RED + line + C_END
	elif line.begins_with("[SYSTEM") or line.begins_with("[BOOT"):  return C_DIM + line + C_END
	elif line.begins_with("[GRAVITY") or line.begins_with("[ORBIT"): return C_AMBER + line + C_END
	elif line.begins_with("╔") or line.begins_with("║") or \
		 line.begins_with("╚") or line.begins_with("═") or \
		 line.begins_with("┌") or line.begins_with("└"):
		return C_GREEN + line + C_END
	else:
		return C_WHITE + line + C_END

func _timestamp() -> String:
	return "%07.3f" % (Time.get_ticks_msec() / 1000.0)

func _blink_cursor() -> void:
	_cursor_visible = !_cursor_visible
	_render_log()
