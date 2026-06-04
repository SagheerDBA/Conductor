import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

_HERE = os.path.dirname(os.path.abspath(__file__))

# Path to the AgentLibrary folder (Work/ and Personal/ agent definitions).
# Defaults to ./AgentLibrary bundled with this repo.
AGENT_LIBRARY_PATH = os.environ.get(
    "AGENT_LIBRARY_PATH",
    os.path.join(_HERE, "AgentLibrary"),
)

# Where write_file saves artifacts (scripts, reports, etc.).
# Defaults to ./output next to this file.
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    os.path.join(_HERE, "output"),
)

# Root folder used by create_project to scaffold new project workspaces.
# Defaults to ~/Projects.
WORKSPACE_ROOT = os.environ.get(
    "WORKSPACE_ROOT",
    os.path.join(os.path.expanduser("~"), "Projects"),
)

# Optional: full path to a SafeComms script for pre-publish safety scanning.
# Leave empty (default) to skip the SafeComms gate.
SAFECOMMS_SCRIPT = os.environ.get("SAFECOMMS_SCRIPT", "")

# Environment context injected into every specialist's prepared_task.
# Describe your stack, tools, and constraints so specialists have the right frame.
# Example: "Python 3.11, Windows Server 2022, SQL Server 2019, dbatools 2.7"
ENVIRONMENT_CONTEXT = os.environ.get(
    "ENVIRONMENT_CONTEXT",
    "Update ENVIRONMENT_CONTEXT in config.py to describe your environment and tools.",
)

ORCHESTRATOR_MODEL = "claude-opus-4-8"
SPECIALIST_MODEL   = "claude-sonnet-4-6"

PRESETS = {
    "full": {
        "ORCHESTRATOR_MODEL": "claude-opus-4-8",
        "SPECIALIST_MODEL":   "claude-sonnet-4-6",
        "label": "Full",
        "cost":  "~$0.20-0.80 per task",
        "note":  "Opus 4 Orchestrator + Sonnet 4.6 Specialists.",
    },
    "economy": {
        "ORCHESTRATOR_MODEL": "claude-sonnet-4-6",
        "SPECIALIST_MODEL":   "claude-sonnet-4-6",
        "label": "Economy",
        "cost":  "~$0.05-0.20 per task",
        "note":  "Sonnet 4.6 for both. Good for testing.",
    },
}


def apply_preset(name: str):
    global ORCHESTRATOR_MODEL, SPECIALIST_MODEL
    preset = PRESETS.get(name, PRESETS["full"])
    ORCHESTRATOR_MODEL = preset["ORCHESTRATOR_MODEL"]
    SPECIALIST_MODEL   = preset["SPECIALIST_MODEL"]
