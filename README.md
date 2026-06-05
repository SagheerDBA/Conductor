# Conductor

A local multi-agent AI orchestrator with a persistent specialist library.

Describe any task. Conductor reads its AgentLibrary, selects the right specialist(s),
runs them in parallel when independent, passes findings between them when they depend
on each other, and synthesizes a final answer — all from a single browser session.

---

## What It Does

- **Routes tasks** to matching specialists from the AgentLibrary
- **Runs specialists in parallel** when their tasks are independent
- **Passes context between agents** — each specialist sees the prior agent's findings
- **Creates new agents on demand** — if no specialist exists, Conductor drafts one,
  saves it permanently, and immediately uses it
- **Saves all artifacts** to organized, timestamped output folders
- **Streams every specialist's response** live in its own panel
- **Auto-reconnects** if the browser connection drops during a long task

---

## Quick Start

**0. Check Python**

Conductor requires Python 3.10 or newer.

```bash
python --version
```

If you don't have it:
- **Windows / macOS:** Download from [python.org/downloads](https://www.python.org/downloads). Check **"Add Python to PATH"** during setup.
- **Linux (Ubuntu/Debian):** `sudo apt install python3 python3-pip`

**1. Clone**
```bash
git clone https://github.com/SagheerDBA/Conductor.git
cd Conductor
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Set your API key**
```bash
# macOS / Linux
export ANTHROPIC_API_KEY='your-key-here'

# Windows PowerShell
$env:ANTHROPIC_API_KEY = 'your-key-here'
```

**4. Configure your environment** (optional but recommended)

Edit `config.py`:
```python
ENVIRONMENT_CONTEXT = "Your stack, tools, and constraints here."
OUTPUT_DIR          = "./output"   # where artifacts are saved
WORKSPACE_ROOT      = "~/Projects" # root for create_project
```

**5. Run**
```bash
python app.py
```

Open **http://localhost:5002** in your browser.

---

## How to Use

1. Select **Full** (Opus 4 Conductor + Sonnet 4.6 Specialists) or **Economy** (Sonnet for all)
2. Click **Start Session**
3. Describe your task in plain language
4. Review the routing plan Conductor proposes — including which agents run in parallel
5. Reply **yes** to proceed, or tell it what to change
6. Watch each specialist's live panel as it streams its response
7. Receive a synthesized final answer with all artifacts saved to disk

---

## Parallel Execution Demo

Given this prompt in Economy mode:

> *"I have this query: SELECT * FROM Orders WHERE CustomerID = 123.
> Check performance and security in parallel, then write a dbatools one-liner
> to verify the index."*

Conductor:
1. Ran `CodeReviewerAgent` and `DataAnalystAgent` **simultaneously**
2. Passed both findings to a third specialist via `prior_outputs`
3. Delivered a synthesized answer with a ready-to-run script

**Cost: $0.18 | 42.9k tokens**

---

## Agent Library

Three sample agents ship with the repo. Add your own or let Conductor create them.

| Agent | Category | Domain |
|---|---|---|
| CodeReviewerAgent | Work | Code quality, bugs, security |
| DataAnalystAgent | Work | SQL, data analysis, insights |
| WriterAgent | Personal | Writing, editing, content |

---

## Adding Your Own Agents

**Let Conductor build them:** Describe a task that needs a specialist. Conductor drafts
the full agent definition, saves it permanently, and uses it immediately.

**Write one manually:** Copy `AgentLibrary/schema/agent-definition.yaml`, fill in the
fields, and save to:
- `AgentLibrary/Work/agents/<slug>/definition.yaml` — professional/technical domains
- `AgentLibrary/Personal/agents/<slug>/definition.yaml` — personal domains

---

## Configuration

All settings are in `config.py` and can be overridden with environment variables:

| Setting | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (env var) | Your Anthropic API key |
| `AGENT_LIBRARY_PATH` | `./AgentLibrary` | Where agent definitions live |
| `OUTPUT_DIR` | `./output` | Where artifacts are saved |
| `WORKSPACE_ROOT` | `~/Projects` | Root for `create_project` |
| `ENVIRONMENT_CONTEXT` | (placeholder) | Stack/tools injected into every specialist |
| `SAFECOMMS_SCRIPT` | (empty) | Optional path to a safety-scan script |

---

## Project Structure

```
Conductor/
├── app.py                          -- Flask app, port 5002
├── config.py                       -- all configurable settings
├── requirements.txt
├── agents/
│   ├── orchestrator_agent.py       -- Conductor: system prompt, tools, agentic loop
│   └── session.py                  -- thread/queue wrapper for Flask/SSE
├── tools/
│   ├── library_reader.py           -- list_agents, call_specialist, write_file,
│   │                                  create_agent, create_project, run_safecomms
│   └── gmail_tool.py               -- optional Gmail integration
├── templates/
│   └── index.html                  -- browser UI with live specialist panels
├── AgentLibrary/
│   ├── schema/agent-definition.yaml
│   ├── Work/agents/
│   │   ├── code-reviewer-agent/
│   │   └── data-analyst-agent/
│   └── Personal/agents/
│       └── writer-agent/
└── output/                         -- saved artifacts (gitignored)
```

---

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com)
- Packages: `anthropic`, `flask`, `httpx`, `pyyaml`

The Full preset uses Opus 4 for routing and Sonnet 4.6 for specialists.
A typical multi-agent task costs $0.20–0.80. Economy mode (Sonnet for all) runs at $0.05–0.20.

---

## Gmail Integration (Optional)

`tools/gmail_tool.py` lets the Conductor search and read Gmail threads during sessions.
It reuses OAuth credentials from the [gmail-mcp](https://github.com/gongrzhe/gmail-mcp-server)
server. Set up gmail-mcp first, then the Conductor picks up the stored tokens automatically.

---

## Related Projects

- [AskSQLServer](https://github.com/SagheerDBA/AskSQLServer) — plain-English SQL Server queries
- [SqlRestoreScriptBuilder](https://github.com/SagheerDBA/SqlRestoreScriptBuilder) — generates restore scripts

---

Built by [Sagheer Ahmed](https://sagheerahmed.com)
