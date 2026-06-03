"""
Conductor -- config.py

All configurable settings. Edit this file before running.
"""

import os

# --- Required ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --- Paths ---
# Agent definitions live here. Can be absolute or relative to this file.
AGENT_LIBRARY_PATH = os.path.join(os.path.dirname(__file__), "AgentLibrary")

# Artifacts (scripts, docs, drafts) are saved here.
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Workspace root for create_project (set to your projects folder).
WORKSPACE_ROOT = os.path.expanduser("~/Projects")

# --- Models ---
CONDUCTOR_MODEL = "claude-opus-4-8"    # Orchestrator -- routing, synthesis, agent creation
SPECIALIST_MODEL = "claude-sonnet-4-6" # Specialists  -- single-turn domain responses

PRESETS = {
    "full": {
        "CONDUCTOR_MODEL":  "claude-opus-4-8",
        "SPECIALIST_MODEL": "claude-sonnet-4-6",
        "label": "Full",
        "cost":  "~$0.20-0.80 per task",
        "note":  "Opus 4 Conductor + Sonnet 4.6 Specialists. Recommended.",
    },
    "economy": {
        "CONDUCTOR_MODEL":  "claude-sonnet-4-6",
        "SPECIALIST_MODEL": "claude-sonnet-4-6",
        "label": "Economy",
        "cost":  "~$0.05-0.20 per task",
        "note":  "Sonnet 4.6 for all. Good for testing and development.",
    },
}


def apply_preset(name: str):
    global CONDUCTOR_MODEL, SPECIALIST_MODEL
    preset = PRESETS.get(name, PRESETS["full"])
    CONDUCTOR_MODEL  = preset["CONDUCTOR_MODEL"]
    SPECIALIST_MODEL = preset["SPECIALIST_MODEL"]
