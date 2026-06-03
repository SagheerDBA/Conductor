"""
Conductor -- app.py

Flask web application. Provides a browser-based chat interface.
Responses stream to the browser in real time via SSE.

Usage:
    python app.py

Then open http://localhost:5002 in your browser.
"""

import json
import os
import queue

from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

_session = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    global _session
    from agents.session import ConductorSession
    import config as cfg

    data   = request.get_json()
    preset = data.get("preset", "full")

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set"}), 400

    cfg.apply_preset(preset)
    preset_info = cfg.PRESETS.get(preset, cfg.PRESETS["full"])

    _session = ConductorSession()
    _session.start()
    return jsonify({
        "status": "ok",
        "preset": preset_info["label"],
        "cost":   preset_info["cost"],
    })


@app.route("/reply", methods=["POST"])
def reply():
    global _session
    if not _session:
        return jsonify({"error": "No active session"}), 400
    data    = request.get_json()
    message = data.get("message", "").strip()
    _session.send_input(message)
    return jsonify({"status": "ok"})


@app.route("/state")
def state():
    global _session
    if not _session:
        return jsonify({"waiting": False, "done": True, "active": False, "last_output": ""})
    return jsonify({
        "waiting":     _session.is_waiting,
        "done":        _session.done,
        "active":      True,
        "last_output": _session.last_output,
    })


@app.route("/events")
def events():
    global _session
    if not _session:
        return jsonify({"error": "No active session"}), 400

    def generate():
        while True:
            try:
                msg = _session.get_output(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") == "session_done":
                    break
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    print()
    print("Conductor")
    print("Local Multi-Agent AI Orchestrator")
    print("=" * 40)
    print()

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("ERROR: ANTHROPIC_API_KEY is not set.")
        print("Set it with:  export ANTHROPIC_API_KEY='your-key-here'")
        print("  (Windows):  $env:ANTHROPIC_API_KEY = 'your-key-here'")
        raise SystemExit(1)

    print("Starting at http://localhost:5002")
    print("Press Ctrl+C to stop.")
    print()
    app.run(host="127.0.0.1", port=5002, debug=False, threaded=True)
