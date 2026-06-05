"""
Orchestrator -- app.py

Flask web application. Provides a browser-based chat interface for the
Orchestrator agent. Responses stream to the browser in real time via SSE.

Usage:
    python app.py

Then open http://localhost:5002 in your browser.
(Port 5002: Factory is 5001, SqlBuildAgent is 5000.)
"""

import json
import os
import queue

from flask import Flask, render_template, request, jsonify, Response
from tools.gmail_tool import search_gmail, read_email_thread

app = Flask(__name__)

_session = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    global _session
    from agents.session import OrchestratorSession
    import config as cfg

    data   = request.get_json()
    preset = data.get("preset", "full")

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return jsonify({"error": "ANTHROPIC_API_KEY is not set"}), 400

    cfg.apply_preset(preset)
    preset_info = cfg.PRESETS.get(preset, cfg.PRESETS["full"])

    _session = OrchestratorSession()
    _session.start()
    return jsonify({
        "status": "ok",
        "preset": preset_info["label"],
        "cost":   preset_info["cost"],
    })


_EMAIL_TRIGGERS = (
    "email", "alert", "ticket", "notification", "inbox", "mail",
    "check my", "the alert", "got a", "received a",
)


def _inject_gmail_context(message: str) -> str:
    """If message references work email/alerts, fetch the most recent thread and append it."""
    if not any(t in message.lower() for t in _EMAIL_TRIGGERS):
        return message
    try:
        results = search_gmail("work", "is:unread", max_results=5)
        if results.get("error") or not results.get("results"):
            return message
        first   = results["results"][0]
        thread  = read_email_thread("work", first["thread_id"])
        if thread.get("error") or not thread.get("messages"):
            return message
        lines = ["[WORK GMAIL -- auto-fetched]"]
        for msg in thread["messages"]:
            lines.append(f"\nFrom: {msg['from']}\nDate: {msg['date']}\nSubject: {msg['subject']}\n\n{msg['body']}\n---")
        email_block = "\n".join(lines)
        return (
            "Here is a recent work email thread. Analyze it and route to the right specialist.\n\n"
            + email_block
        )
    except Exception:
        return message


@app.route("/test-gmail")
def test_gmail():
    """Diagnostic: confirm Gmail injection works without involving the Orchestrator AI."""
    result = _inject_gmail_context("check my work email for the alert")
    return jsonify({"injected_length": len(result), "preview": result[:300]})


@app.route("/stop", methods=["POST"])
def stop():
    global _session
    if not _session:
        return jsonify({"error": "No active session"}), 400
    _session.request_stop()
    return jsonify({"status": "ok"})


@app.route("/reply", methods=["POST"])
def reply():
    global _session
    if not _session:
        return jsonify({"error": "No active session"}), 400
    data        = request.get_json()
    message     = data.get("message", "").strip()
    attachments = data.get("attachments", [])

    message = _inject_gmail_context(message)

    if attachments:
        content = []
        if message:
            content.append({"type": "text", "text": message})
        for att in attachments:
            if att.get("type") == "image":
                content.append({
                    "type": "image",
                    "source": {
                        "type":       "base64",
                        "media_type": att["media_type"],
                        "data":       att["data"],
                    }
                })
            elif att.get("type") == "text_file":
                content.append({
                    "type": "text",
                    "text": f"[Attached file: {att['filename']}]\n{att['content']}"
                })
        if not content:
            content = [{"type": "text", "text": "(no input)"}]
        _session.send_input(content)
    else:
        _session.send_input(message or "(no input)")

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
    """
    Server-Sent Events stream.
    Event types:
      agent_message    -- Orchestrator text output
      user_message     -- user reply echoed back
      tool_start       -- list_agents is running
      tool_done        -- list_agents finished
      specialist_start -- a specialist is being called
      specialist_done  -- specialist has responded
      waiting_input    -- Orchestrator waiting for user reply
      session_done     -- session complete
      error            -- something went wrong
      ping             -- keep-alive heartbeat
    """
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    print()
    print("Conductor")
    print("AgentLibrary Specialist Routing and Execution")
    print("=" * 45)
    print()

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("ERROR: ANTHROPIC_API_KEY is not set.")
        print("Set it with:  $env:ANTHROPIC_API_KEY = 'your-key-here'")
        raise SystemExit(1)

    print("Starting at http://localhost:5002")
    print("Press Ctrl+C to stop.")
    print()
    app.run(host="127.0.0.1", port=5002, debug=False, threaded=True)
