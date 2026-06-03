# Conductor

A local multi-agent AI orchestrator that builds its own team of specialists on demand.

Describe any task. Conductor reads its AgentLibrary, selects the right specialist(s),
creates new ones if none exist, executes them in sequence, and synthesizes a final answer —
all from a single browser session.

---

## What It Does

- **Routes tasks** to matching specialist agents from its library
- **Creates new agents on demand** — if no specialist exists, Conductor drafts one,
  saves it permanently, and immediately uses it
- **Executes multi-agent chains** in the right order, passing rich context to each
- **Synthesizes** all specialist outputs into one coherent final answer
- **Saves artifacts** to organized, timestamped output folders
- **Live activity panel** shows every agent action in real time

---

## Demo

In one session, Conductor was given this prompt:

> *"I want to do a comparative study of world religions — Christianity, Islam, Judaism,
> Hinduism, and Buddhism. Compare how each answers the question: what happens after death?"*

No religion specialists existed in the library. Conductor:

1. Recognized the gap and decided to create five permanent specialists
2. Created `ChristianityAgent`, `IslamAgent`, `JudaismAgent`, `HinduismAgent`, `BuddhismAgent` — one at a time
3. Called each specialist with a focused afterlife question, capturing internal variations
   (Sunni vs Shia, Theravada vs Mahayana, Catholic vs Orthodox, etc.)
4. Synthesized a graduate-level side-by-side comparison across all five traditions
5. Scaffolded a `ComparativeReligionStudy` project workspace to organize future studies

All from a single prompt. The five agents are permanently saved and available to every
future session.

---

## Quick Start

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

**4. Run**
```bash
python app.py
```

Open **http://localhost:5002** in your browser.

---

## How to Use

1. Select **Full** (Opus 4 Conductor + Sonnet 4.6 Specialists) or **Economy** (Sonnet for all)
2. Click **Start Session**
3. Describe your task in plain language
4. Review the routing plan Conductor proposes
5. Reply **yes** to proceed — or tell it what to change
6. Watch the activity panel on the right as each specialist runs
7. Receive a synthesized final answer

---

## Adding Your Own Agents

**Let Conductor build them:** Describe a task that needs a specialist. Conductor drafts
the full agent definition, saves it to `AgentLibrary/`, and uses it immediately.

**Write one manually:** Copy `AgentLibrary/schema/agent-definition.yaml`, fill in the
fields, and save to:
- `AgentLibrary/Work/agents/<slug>/definition.yaml` — professional/technical domains
- `AgentLibrary/Personal/agents/<slug>/definition.yaml` — personal domains

Agents ship with: name, domain, description, system_prompt, boundaries (does/does_not),
example_use_cases, and tags. Conductor reads these to make routing decisions.

---

## Configuration

Edit `config.py` before running:

```python
AGENT_LIBRARY_PATH = "./AgentLibrary"   # where agents live
OUTPUT_DIR         = "./output"          # where artifacts are saved
WORKSPACE_ROOT     = "~/Projects"        # root for create_project

CONDUCTOR_MODEL  = "claude-opus-4-8"    # routing + synthesis
SPECIALIST_MODEL = "claude-sonnet-4-6"  # specialist calls
```

---

## Project Structure

```
Conductor/
├── app.py                      -- Flask app, port 5002
├── config.py                   -- all configurable settings
├── requirements.txt
├── agents/
│   ├── conductor_agent.py      -- Conductor: system prompt, tools, agentic loop
│   └── session.py              -- thread/queue wrapper for Flask/SSE
├── tools/
│   └── library_reader.py       -- list_agents, call_specialist, write_file,
│                                   create_agent, create_project
├── templates/
│   └── index.html              -- browser UI with live activity panel
├── AgentLibrary/               -- your specialist agents (starts empty)
│   ├── Work/agents/
│   └── Personal/agents/
└── output/                     -- saved artifacts (gitignored)
```

---

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com)
- Packages: `anthropic`, `flask`, `httpx`, `pyyaml`

The Full preset uses Opus 4 for routing and Sonnet 4.6 for specialists.
A typical multi-agent task costs $0.20–0.80. The Economy preset (Sonnet for all)
runs at $0.05–0.20.

---

## Related Projects

- [AskSQLServer](https://github.com/SagheerDBA/AskSQLServer) — plain-English SQL Server queries
- [SqlRestoreScriptBuilder](https://github.com/SagheerDBA/SqlRestoreScriptBuilder) — generates restore scripts

---

Built by [Sagheer Ahmed](https://sagheerahmed.com)
