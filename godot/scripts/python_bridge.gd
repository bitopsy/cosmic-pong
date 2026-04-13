extends Node
## PythonBridge — Godot ↔ Python socket bridge
## Sends hit events to Python analytics server, receives processed stats back
## Python runs a local HTTP server on port 8765
class_name PythonBridge
signal analytics_ready(data: Dictionary)
signal export_complete(filepath: String)

const HOST:    String = "127.0.0.1"
const PORT:    int    = 8765
const TIMEOUT: float  = 0.1  # non-blocking

var _client: StreamPeerTCP
var _connected: bool    = false
var _send_queue: Array  = []
var _recv_buffer: String = ""
var _python_process: int = -1

func _ready() -> void:
	_client = StreamPeerTCP.new()

func start_analytics_server() -> void:
	# Launch Python analytics process
	var python_script: String = ProjectSettings.globalize_path(
		"res://../../python/analytics_server.py")
	_python_process = OS.create_process(
		"python3", [python_script, "--port", str(PORT)], false)
	await get_tree().create_timer(0.5).timeout
	_connect_to_python()

func _connect_to_python() -> void:
	var err: Error = _client.connect_to_host(HOST, PORT)
	if err == OK:
		_connected = true
		print("[PythonBridge] Connected to analytics server on port %d" % PORT)
	else:
		push_warning("[PythonBridge] Could not connect — analytics offline")

func _process(_delta: float) -> void:
	if not _connected:
		return

	# Flush send queue
	while _send_queue.size() > 0:
		var payload: String = JSON.stringify(_send_queue.pop_front()) + "\n"
		_client.put_data(payload.to_utf8_buffer())

	# Check for incoming data
	var available: int = _client.get_available_bytes()
	if available > 0:
		var data: Array = _client.get_partial_data(available)
		if data[0] == OK:
			_recv_buffer += data[1].get_string_from_utf8()
			_process_recv_buffer()

func _process_recv_buffer() -> void:
	while "\n" in _recv_buffer:
		var idx: int    = _recv_buffer.find("\n")
		var line: String = _recv_buffer.substr(0, idx)
		_recv_buffer     = _recv_buffer.substr(idx + 1)
		var parsed: Variant = JSON.parse_string(line)
		if parsed is Dictionary:
			analytics_ready.emit(parsed)

func record_hit(hit_data: Dictionary) -> void:
	hit_data["type"] = "hit"
	_send_queue.append(hit_data)

func export_session_csv() -> void:
	_send_queue.append({"type": "export_csv"})

func _exit_tree() -> void:
	if _python_process > 0:
		OS.kill(_python_process)
	_client.disconnect_from_host()
