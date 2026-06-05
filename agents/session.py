"""
Orchestrator -- session.py

Runs the Orchestrator agent in a background thread so Flask can stream
responses to the browser via SSE without blocking.

Uses the same two-queue pattern as AgentFactory:
  _out : agent -> browser  (messages, tool events, waiting-for-input signal)
  _in  : browser -> agent  (user replies)
"""

import queue
import threading

from agents import orchestrator_agent


class OrchestratorSession:

    def __init__(self):
        self._out              = queue.Queue()
        self._in               = queue.Queue()
        self._thread           = None
        self.done              = False
        self._waiting          = False
        self._last_output      = ""
        self._stop_requested   = False

    def request_stop(self):
        self._stop_requested = True
        # Unblock any pending input_fn wait so the loop can exit
        self._in.put("__stop__")

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def send_input(self, message):
        self._in.put(message)

    def get_output(self, timeout: float = 60):
        return self._out.get(timeout=timeout)

    @property
    def is_waiting(self) -> bool:
        return self._waiting

    @property
    def last_output(self) -> str:
        return self._last_output

    def _output_fn(self, text: str):
        self._last_output = text
        self._out.put({"type": "agent_message", "text": text})

    def _input_fn(self) -> str:
        self._waiting = True
        self._out.put({"type": "waiting_input"})
        result = self._in.get()
        self._waiting = False
        return result

    def _status_fn(self, event: dict):
        self._out.put(event)

    def _stop_fn(self) -> bool:
        return self._stop_requested

    def _run(self):
        try:
            orchestrator_agent.run(
                output_fn=self._output_fn,
                input_fn=self._input_fn,
                status_fn=self._status_fn,
                stop_fn=self._stop_fn,
            )
        except Exception as e:
            self._out.put({"type": "error", "message": str(e)})
        finally:
            self.done = True
            self._out.put({"type": "session_done"})
