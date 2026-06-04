# AgentLibrary -- Master Index
Last Updated: 2026-06-04

Central registry of all specialist agents available to Conductor.

---

## Work Agents

| Agent | Domain | Status | Version |
|---|---|---|---|
| [CodeReviewerAgent](Work/agents/code-reviewer-agent/definition.yaml) | Code quality review, bug detection, best practices | Production | v1.0 |
| [DataAnalystAgent](Work/agents/data-analyst-agent/definition.yaml) | Data analysis, SQL queries, insight extraction | Production | v1.0 |

## Personal Agents

| Agent | Domain | Status | Version |
|---|---|---|---|
| [WriterAgent](Personal/agents/writer-agent/definition.yaml) | Writing, editing, content structuring | Production | v1.0 |

---

## Adding Agents

**Option 1 -- Let Conductor create one:**
Describe a task that needs a specialist. Conductor will draft and save the agent automatically.

**Option 2 -- Write it manually:**
Copy `schema/agent-definition.yaml`, fill in the fields, save to:
- Work agents:     `Work/agents/<slug>/definition.yaml`
- Personal agents: `Personal/agents/<slug>/definition.yaml`
