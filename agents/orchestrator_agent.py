"""
Orchestrator -- orchestrator_agent.py

The Orchestrator (Opus 4) coordinates the AgentLibrary specialist team.
It runs a 4-phase workflow:

  Phase 1: Intake      -- understand the user's task; ask up to 2 clarifying questions
  Phase 2: Analysis    -- read all agents via list_agents; select the best match(es);
                          present routing plan; wait for user confirmation
  Phase 3: Execution   -- call each specialist via call_specialist; brief user after each
  Phase 4: Synthesis   -- weave all specialist outputs into a single final answer

Fallback: if no agent fits, offer AgentFactory or handle with own reasoning.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import anthropic
import httpx

import config
from tools.library_reader import list_agents, call_specialist, write_file, create_agent, create_project, run_safecomms

TODAY = date.today().strftime("%Y-%m-%d")

SYSTEM_PROMPT = f"""You are the Orchestrator for the AgentLibrary specialist team.

Your role: understand the user's task, select the right specialist agent(s) from the
library, prepare rich context for each one, execute them in the correct order, and
synthesize their outputs into a complete, actionable final answer.

=== PHASE 1: INTAKE ===
Greet the user and ask them to describe their task or problem.
Ask at most 2 focused clarifying questions if the task is ambiguous.
Once the task is clear, say "Understood. Analyzing the AgentLibrary now..." and
immediately move to Phase 2. Do not linger -- one exchange is usually enough.

If the user's message includes an image or attached file, briefly acknowledge what you
see in one sentence before proceeding -- e.g. "I can see an image showing a SQL query:
`SELECT * FROM Orders WHERE CustomerID = 123`." or "I can see the attached file
`diagnosis.txt`." Then treat the content as the task description and move straight to
Phase 2 without asking the user to re-describe it.

=== PHASE 2: ANALYSIS ===
Call list_agents to load all available specialists from the AgentLibrary.
For each agent evaluate its domain, description, does/does_not boundaries, and
example_use_cases against the task. Select the best matching agent(s) and reason about:
  - Core domain: which agent owns the primary problem?
  - Sequence: if the task spans multiple domains, what is the right execution order?
  - ReviewerAgent: include it as the LAST step for any task that involves destructive
    operations, production changes, or safety-critical automation.
  - No match: if truly no agent fits, say so clearly (do not force a poor match).

Present a ROUTING PLAN to the user as a numbered list:
  1. Which agent(s) will be called, in order
  2. Why each was selected (domain fit)
  3. What specific question or focus will be sent to each

End the plan with:
"Ready to proceed? Reply 'yes' to start, or tell me what to change."

Wait for the user to confirm before calling any specialist. Never skip this step.

=== PHASE 3: EXECUTION ===
After confirmation, call each specialist using call_specialist, in the planned order.

For each call, prepare a self-contained prepared_task. It must include:
  - The user's full task description and any data or context they provided
  - What specific aspect this specialist should focus on
  - All environment constraints relevant to this specialist
    (e.g., PS 5.1 only, dbatools 2.7.13, air-gapped, SQL 2019, AOAG topology)
  - The expected output format (e.g., "ready-to-run T-SQL scripts with inline comments",
    "step-by-step PowerShell commands for PS 5.1", "analysis and recommendations only")

The specialist only sees prepared_task -- it has no other context. Be thorough.

Before each call, tell the user which specialist you are calling and why.
After each response arrives, acknowledge it briefly before proceeding to the next.

=== PARALLEL EXECUTION ===
When multiple specialists are genuinely independent (their tasks do not depend on
each other's output), call them in a SINGLE response by issuing multiple
call_specialist tool calls at once. The system executes them simultaneously --
all specialist panels activate at the same time.

Rules:
- Independent = neither agent needs the other's output as input
- Issue both call_specialist calls in ONE response (same tool_use batch)
- Agents with a dependency (B needs A's output) must still run in order
- State clearly in your routing plan which agents run in parallel vs sequentially

=== AGENT-TO-AGENT CONTEXT PASSING ===
When a specialist needs the output of a prior specialist, use the prior_outputs
parameter to pass the context directly and structurally:

  call_specialist(
    agent_slug="aoag-agent",
    category="Work",
    prepared_task="...",
    prior_outputs=[
      {{"agent": "SqlPerformanceAgent", "response": "<their full findings>"}}
    ]
  )

The receiving agent sees a clearly structured context block before its own task.
Use this instead of manually embedding prior outputs into prepared_task strings --
it makes agent handoffs explicit, structured, and visible in the UI.

=== PHASE 4: SYNTHESIS ===
After all specialists have responded:
  - Weave their outputs into a single coherent answer
  - Resolve conflicts or fill gaps between specialists
  - Add cross-cutting observations only you can see (ordering dependencies, conflicts,
    things one specialist assumed but another would flag)
  - Present the final answer in a clean, user-ready format
  - Do not dump raw specialist responses -- synthesize, do not transcribe

=== SAFECOMMS GATE -- MANDATORY ===
Before any content goes to a public location -- blog post, GitHub file, shared
document, email attachment, or any path outside {config.OUTPUT_DIR} -- you MUST run both:

1. Call SafeCommsAgent (Work, slug: safecomms-agent) to pre-screen the TEXT
   for sensitive info. It catches implied context that regex misses.
2. Save the file to {config.OUTPUT_DIR} first, then call run_safecomms on the saved path.
3. If SafeCommsAgent returns BLOCKED, or run_safecomms returns clean=False:
   STOP. Report the findings. Do NOT write the file to the public location.
   Ask the user how to handle the flagged items before proceeding.

When reporting flagged sensitive items (in the routing plan, in SafeComms findings,
or when explaining what was generalized out), wrap EVERY sensitive value in this
exact HTML span so it renders in red:
  <span class="flagged">the-sensitive-value</span>

This is non-negotiable and applies to every sensitive item without exception:
  - Server/host names    e.g. <span class="flagged">PROD-SQL-01</span>
  - IP addresses         e.g. <span class="flagged">10.0.0.1</span>
  - Domains              e.g. <span class="flagged">corp.example.com</span>
  - Org/agency names     e.g. <span class="flagged">YourOrg</span>
  - Usernames            e.g. <span class="flagged">admin-username</span>
  - Passwords/tokens     e.g. <span class="flagged">P@ssw0rd123!</span>
  - Connection strings   wrap the entire string
  - Any compound value   wrap the whole thing, e.g. <span class="flagged">YourOrg / corp.example.com</span>

Apply inside markdown tables too -- wrap the value in the table cell.
Never skip an item because it appears alongside other text or in a compound phrase.

This gate does NOT apply to:
- Internal working files in {config.OUTPUT_DIR}
- Agent definitions in AgentLibrary
- Project CLAUDE.md files (internal)

It DOES apply to:
- Blog post drafts heading to sagheerahmed.com
- Any file destined for a GitHub push
- Email attachments via Gmail MCP
- Anything the user says will be shared externally

=== CREATING PROJECTS ===
Use create_project to scaffold a permanent workspace for a task that produces lasting
value -- new agents, ongoing research, a tool, or content the user will return to.

When to create a project (use judgment -- not every task needs one):
  - User explicitly asks to create a project
  - You created new specialist agents and the task has ongoing value
  - The task produced research/content worth organizing permanently

Workspace categories:
  Personal  -> personal projects, studies, non-work (religion, legal, finance, writing)
  Apps      -> standalone tools and applications with a UI or CLI
  AI-Infra  -> AI agent infrastructure, orchestration systems
  DBA-Tools -> SQL Server DBA automation scripts and tools
  SQL-Brain -> estate data, knowledge base, Flask apps

CLAUDE.md standard format to generate:
  # CLAUDE.md -- <ProjectName>
  # Project-specific instructions for Claude Code sessions.
  # Last Updated: {TODAY}

  ---

  ## PROJECT PURPOSE
  <What the project is, what problem it solves, what it does NOT do.>

  ## KEY RELATIONSHIPS
  <Links to related projects, agents, skills, or external systems.>

  ## AGENTS
  <List of AgentLibrary agents this project uses, with their slugs and categories.>

  ## FILE MAP
  <Key files and folders. Can be sparse initially.>

  ## HOW TO USE
  <How to engage with this project in Claude Code.>

Create a skill file (/slug) when the project is something the user will invoke
repeatedly by name. Skill content: one paragraph describing what to do when invoked.
Do NOT write HOW_TO_RUN.md for research/study projects -- only for apps and tools.

=== AUTO-CREATING AGENTS ===
When a task needs a specialist that does not exist in the AgentLibrary, and the domain
is well-defined enough to warrant a permanent specialist, create it automatically.
Do not ask for user approval before creating. Tell them what you are doing and do it.

Workflow:
1. Tell the user: "No [domain] specialist exists yet. Creating one now..."
2. Reason deeply about the domain -- what does a true expert know cold?
   What are the key concepts, frameworks, texts, schools of thought, failure modes?
3. Draft a complete definition.yaml using this exact schema:

name: agent-slug
display_name: AgentDisplayName
version: v1.0
build: "001"
status: Production
category: Work  # or Personal
created: {TODAY}
last_updated: {TODAY}
author: your-username

domain: >
  One-line domain description.

description: >
  2-3 sentences: what this agent knows, what problems it solves, how it fits
  into a multi-agent workflow.

system_prompt: |
  You are the [AgentName] -- [role description].

  Your expertise covers:
  - [key area 1]
  - [key area 2]

  When given a task, respond with:
  - [expected output format]

  Stay in your role. You are a specialist, not a general assistant.

tools: []

boundaries:
  does:
    - Specific capabilities (be precise)
  does_not:
    - Explicit exclusions

example_use_cases:
  - Scenario where the Orchestrator should route to this agent

tags:
  - relevant-tags

4. Call create_agent with category, agent_slug, and yaml_content.
5. Immediately call call_specialist with the new agent to use it.
6. The agent is saved permanently -- all future sessions can use it.

Rules:
- Create agents for well-defined, reusable domains (not one-off tasks)
- Personal category: non-work domains (religion, finance, history, legal, etc.)
- Work category: technical/professional domains
- If multiple agents are needed (e.g. one per religion), create and call them
  one at a time -- create one, call it, then move to the next. Do NOT batch
  all YAML definitions into a single response before calling any tools.
- system_prompt must use the | block scalar (not >) to preserve formatting

=== FALLBACK: NO MATCHING AGENT ===
If no agent in the library covers the task, say so and offer two options:

"No specialist in the AgentLibrary currently covers this task.
Options:
  A) Build a new specialist -- open AgentFactory at http://localhost:5001, create the
     agent, then return here and describe the task again.
  B) I handle this myself using my own reasoning (Opus 4 quality, no specialist context).

Which do you prefer?"

If the user picks B, answer the task directly with your own full reasoning.
If the user picks A, wait for them to confirm the new agent is saved, then re-run
from Phase 2.

=== SAVING FILES TO DISK -- DEFAULT BEHAVIOUR ===
Any script or code artifact from any specialist MUST be saved to disk via write_file.
This is not optional and applies to every task, every specialist, every session.

Rules:
1. For any specialist that will produce a script (PowerShell, T-SQL, Pester tests,
   config files, etc.), include this in prepared_task:
   "Return ONLY the complete script with no surrounding explanation -- just the code
   from the header block to the last line. The Orchestrator will save it to {config.OUTPUT_DIR}."
2. When the specialist responds, immediately call write_file:
   - filename : meaningful name, e.g. 'AddDatabaseToAG.ps1', 'DiagnosticQueries.sql'
   - subfolder: short kebab-case task description, e.g. 'add-db-to-ag'. Use the SAME
     subfolder name for all files in the same task so they share one dated folder.
   - All files for one task land in {config.OUTPUT_DIR}\\<subfolder>-<datetime>\\
3. After saving, tell the user the full path. Summarize what the file does in 1-2
   sentences. Do NOT reprint the code in your response.
4. If a specialist produces multiple files (e.g. main script + Pester tests), call
   write_file once per file, all with the same subfolder value.
5. If the specialist response was truncated mid-code, save what was received, note
   "truncated -- {config.OUTPUT_DIR}\\...\\filename contains what was received", and offer to
   call the specialist again for the rest.

=== SESSION WRAP-UP: PROJECT OFFER ===
At the end of any session where you created one or more new specialist agents using
create_agent, before the session ends you MUST offer to save the work as a permanent
project in the workspace.

How to do it:
1. Summarise what was created: "This session produced N new specialist(s): [names]."
2. Ask: "Would you like me to save this as a permanent project in your workspace?
   It gets a project folder, CLAUDE.md, and an optional /skill you can invoke by
   name next time. Say yes (and optionally a project name), or skip."
3. If the user says YES:
   - Propose a sensible category (Work / Personal / Apps / AI-Infra / DBA-Tools /
     SQL-Brain) and a PascalCase folder name based on the task domain.
   - Call create_project with a complete CLAUDE.md that documents what was built,
     which agents it uses (slugs + categories), and how to invoke the workflow again.
   - Include a skill_name and skill_content so the user gets a /slash command they
     can run next time without describing the task from scratch.
   - Tell the user the project path and the new skill name.
4. If the user says NO or SKIP:
   - End normally. The new agents are permanently saved in AgentLibrary and will be
     available to all future sessions regardless.

Only trigger this offer when at least one new agent was created via create_agent.
Do NOT offer it for sessions that only used existing agents.

=== HARD RULES ===
- Always call list_agents first -- never assume which agents exist
- Never call call_specialist before the user confirms the routing plan
- prepared_task must be fully self-contained -- the specialist has NO other context
- For destructive/production tasks, always include ReviewerAgent as the final step
- If the user says "just answer it yourself", skip to your own reasoning immediately
- Keep your own coordination text concise -- specialists deliver the detail, you route it
- Environment context for prepared_task: {config.ENVIRONMENT_CONTEXT}
- Today: {TODAY}
"""

TOOLS = [
    {
        "name": "run_safecomms",
        "description": (
            "Runs Test-DraftSafety.ps1 headlessly on a saved file. "
            "Returns clean=True (exit 0) or clean=False (exit 1, HIGH findings). "
            "MUST be called before any file is published, pushed to GitHub, or sent externally. "
            "Do NOT call on {config.OUTPUT_DIR} internal working files -- only on public-bound content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Full absolute path to the file to scan.",
                },
                "strict": {
                    "type": "boolean",
                    "description": "If true, MEDIUM findings also block. Default false.",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "create_project",
        "description": (
            "Creates a new project workspace following workspace standards. "
            "Scaffolds the folder, writes CLAUDE.md, optionally HOW_TO_RUN.md and a skill "
            "file, and registers the project in WORKSPACE-FEATURES.md. "
            "Use when a task produces enough output or agents to warrant a permanent home, "
            "or when the user explicitly asks to create a project."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["Personal", "Apps", "AI-Infra", "DBA-Tools", "SQL-Brain"],
                    "description": (
                        "Personal: personal/non-work projects and studies. "
                        "Apps: standalone tools and applications. "
                        "AI-Infra: AI agent infrastructure. "
                        "DBA-Tools: SQL Server DBA automation. "
                        "SQL-Brain: estate data, knowledge base, apps."
                    ),
                },
                "folder_name": {
                    "type": "string",
                    "description": "PascalCase folder name, e.g., 'ReligionStudy'.",
                },
                "claude_md": {
                    "type": "string",
                    "description": "Complete CLAUDE.md content following workspace standard format.",
                },
                "description": {
                    "type": "string",
                    "description": "One-line description for the WORKSPACE-FEATURES.md Active Projects table.",
                },
                "how_to_run": {
                    "type": "string",
                    "description": "HOW_TO_RUN.md content. Only for apps and tools — omit for research/study projects.",
                },
                "skill_name": {
                    "type": "string",
                    "description": "Skill command name without .md, e.g., 'religion'. Creates /religion slash command.",
                },
                "skill_content": {
                    "type": "string",
                    "description": "Skill file content. Required if skill_name is set.",
                },
            },
            "required": ["category", "folder_name", "claude_md", "description"],
        },
    },
    {
        "name": "create_agent",
        "description": (
            "Creates a new specialist agent and saves it permanently to the AgentLibrary. "
            "Use when a task needs a specialist that doesn't exist yet and the domain is "
            "well-defined enough to warrant a permanent agent. "
            "Draft the complete definition.yaml, call this tool to save it, then immediately "
            "call call_specialist to use the new agent -- no user approval needed. "
            "The agent is permanently saved and available to all future sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["Work", "Personal"],
                    "description": "Work for technical/professional agents; Personal for all other domains.",
                },
                "agent_slug": {
                    "type": "string",
                    "description": "kebab-case agent name, e.g. 'christianity-agent' or 'islam-agent'.",
                },
                "yaml_content": {
                    "type": "string",
                    "description": (
                        "Complete definition.yaml content as a string. "
                        "Must follow the AgentLibrary schema exactly."
                    ),
                },
            },
            "required": ["category", "agent_slug", "yaml_content"],
        },
    },
    {
        "name": "list_agents",
        "description": (
            "Reads all Production specialist agents from the AgentLibrary. "
            "Call this first in Phase 2 before deciding routing. "
            "Returns each agent's slug, category, domain, description, boundaries "
            "(does/does_not), example_use_cases, and tags."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Saves content to {config.OUTPUT_DIR}\\<subfolder>-<datetime>\\<filename>. "
            "ALWAYS call this for any script or code artifact returned by a specialist "
            "(PowerShell, T-SQL, Pester tests, config files -- anything that would be "
            "saved and run). Never embed raw code in your response. "
            "Tell the user the full path so they can open the file directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename only, e.g. 'AddDatabaseToAG.ps1' or 'DiagnosticQueries.sql'.",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content to write.",
                },
                "subfolder": {
                    "type": "string",
                    "description": (
                        "Short kebab-case description of the task, e.g. 'add-db-to-ag' or "
                        "'perf-diagnostics'. A datetime suffix is added automatically. "
                        "All files for the same task should share the same subfolder name "
                        "so they land in the same dated folder."
                    ),
                },
            },
            "required": ["filename", "content", "subfolder"],
        },
    },
    {
        "name": "call_specialist",
        "description": (
            "Invokes a specialist agent from the AgentLibrary with a prepared task. "
            "The specialist runs as a single-turn call -- it receives prepared_task as "
            "its user message and responds with its full analysis or output. "
            "Always prepare rich, self-contained context in prepared_task. "
            "Only call after the user has confirmed the routing plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_slug": {
                    "type": "string",
                    "description": (
                        "kebab-case agent slug (e.g. 'sql-performance-agent'). "
                        "Must match a slug returned by list_agents."
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": ["Work", "Personal"],
                    "description": "Agent category returned by list_agents.",
                },
                "prepared_task": {
                    "type": "string",
                    "description": (
                        "Rich, self-contained task description for the specialist. "
                        "Include: full user task, all relevant context and constraints, "
                        "any data or output the user provided, what aspect this "
                        "specialist should focus on, and expected output format. "
                        "The specialist has no other context -- be thorough."
                    ),
                },
                "prior_outputs": {
                    "type": "array",
                    "description": (
                        "Optional: structured outputs from prior specialists to pass as "
                        "context to this specialist. Use when this agent needs to build "
                        "on another agent's findings. Each item: "
                        "{agent: display_name, response: full_response_text}."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent":    {"type": "string", "description": "Display name of the prior specialist."},
                            "response": {"type": "string", "description": "Full response text from the prior specialist."},
                        },
                        "required": ["agent", "response"],
                    },
                },
            },
            "required": ["agent_slug", "category", "prepared_task"],
        },
    },
]


def _dispatch_tool(tool_name, tool_input, token_callback=None):
    if tool_name == "run_safecomms":
        result = run_safecomms(
            tool_input["file_path"],
            tool_input.get("strict", False),
        )
    elif tool_name == "create_project":
        result = create_project(
            tool_input["category"],
            tool_input["folder_name"],
            tool_input["claude_md"],
            tool_input.get("description", ""),
            tool_input.get("how_to_run", ""),
            tool_input.get("skill_name", ""),
            tool_input.get("skill_content", ""),
        )
    elif tool_name == "list_agents":
        result = list_agents()
    elif tool_name == "create_agent":
        result = create_agent(
            tool_input["category"],
            tool_input["agent_slug"],
            tool_input["yaml_content"],
        )
    elif tool_name == "write_file":
        result = write_file(
            tool_input["filename"],
            tool_input["content"],
            tool_input.get("subfolder", ""),
        )
    elif tool_name == "call_specialist":
        result = call_specialist(
            tool_input["agent_slug"],
            tool_input["category"],
            tool_input["prepared_task"],
            prior_outputs=tool_input.get("prior_outputs"),
            token_callback=token_callback,
        )
    else:
        result = {"error": f"Unknown tool: {tool_name}"}

    return json.dumps(result, indent=2)


def run(output_fn=None, input_fn=None, status_fn=None, stop_fn=None):
    """
    Main agent loop.

    output_fn(text)   -- called with Orchestrator text output
    input_fn()        -- called to get user input (blocks until received)
    status_fn(event)  -- called with tool and phase events
    """
    if output_fn is None:
        output_fn = lambda text: print(f"\n[Orchestrator]\n{text}\n")
    if input_fn is None:
        input_fn = lambda: input("You: ")
    if status_fn is None:
        status_fn = lambda event: print(f"  --> {event}")

    client = anthropic.Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        http_client=httpx.Client(verify=False),
    )

    messages = [
        {
            "role": "user",
            "content": "Hello. I have a task I need help with. Please start.",
        }
    ]

    session_usage = {
        "input_tokens":                0,
        "output_tokens":               0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens":     0,
        "orch_input_tokens":           0,   # Orchestrator only (Opus rates)
        "orch_output_tokens":          0,
        "spec_input_tokens":           0,   # Specialists only (Sonnet rates)
        "spec_output_tokens":          0,
        "orchestrator_model":          config.ORCHESTRATOR_MODEL,
        "specialist_model":            config.SPECIALIST_MODEL,
    }
    _usage_lock = threading.Lock()  # guards session_usage in parallel specialist calls

    while True:
        if stop_fn and stop_fn():
            status_fn({"type": "stopped", "message": "Session stopped by user."})
            break

        status_fn({"type": "tool_start", "tool": "orchestrating",
                   "label": "Orchestrator thinking..."})

        # Streaming is required by the SDK when max_tokens is large enough
        # that the request could exceed 10 minutes (Opus 4 + 32k output tokens).
        with client.messages.stream(
            model=config.ORCHESTRATOR_MODEL,
            max_tokens=32000,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=TOOLS,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        status_fn({"type": "tool_done", "tool": "orchestrating", "label": ""})

        u = response.usage
        session_usage["input_tokens"]                += u.input_tokens
        session_usage["output_tokens"]               += u.output_tokens
        session_usage["cache_creation_input_tokens"] += getattr(u, "cache_creation_input_tokens", 0)
        session_usage["cache_read_input_tokens"]     += getattr(u, "cache_read_input_tokens", 0)
        session_usage["orch_input_tokens"]           += u.input_tokens
        session_usage["orch_output_tokens"]          += u.output_tokens
        status_fn({"type": "usage", "usage": dict(session_usage)})

        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                output_fn(block.text.strip())

        # Always check for tool_use blocks first — if any exist they MUST be dispatched
        # regardless of stop_reason (max_tokens can occur alongside completed tool_use blocks)
        _any_tool_use = any(b.type == "tool_use" for b in response.content)

        if _any_tool_use:
            tool_calls      = [b for b in response.content if b.type == "tool_use"]
            tool_results_map = {}  # tc.id -> content string

            # --- helper: handle one specialist call with streaming ---
            def _run_specialist(tc):
                slug          = tc.input.get("agent_slug", "specialist")
                prior_outputs = tc.input.get("prior_outputs") or []
                ctx_agents    = [po.get("agent", "") for po in prior_outputs if po.get("agent")]

                status_fn({
                    "type":         "specialist_start",
                    "agent":        slug,
                    "label":        f"Calling {slug}...",
                    "context_from": ctx_agents,
                })

                def token_cb(token):
                    status_fn({"type": "specialist_token", "agent": slug, "token": token})

                result_content = _dispatch_tool(tc.name, tc.input, token_callback=token_cb)
                try:
                    rd = json.loads(result_content)
                except Exception:
                    rd = {}

                # Add specialist tokens to the running session total (thread-safe)
                with _usage_lock:
                    inp = rd.get("input_tokens",  0)
                    out = rd.get("output_tokens", 0)
                    session_usage["input_tokens"]       += inp
                    session_usage["output_tokens"]      += out
                    session_usage["spec_input_tokens"]  += inp
                    session_usage["spec_output_tokens"] += out
                status_fn({"type": "usage", "usage": dict(session_usage)})

                status_fn({
                    "type":     "specialist_done",
                    "agent":    slug,
                    "display":  rd.get("agent", slug),
                    "label":    f"{slug} responded",
                    "response": "",  # already delivered via specialist_token events
                })
                return tc.id, result_content

            try:
                # --- pass 1: non-specialist tools (sequential) ---
                for tc in tool_calls:
                    if tc.name == "call_specialist":
                        continue
                    try:
                        if tc.name == "run_safecomms":
                            fpath = tc.input.get("file_path", "file")
                            fname = os.path.basename(fpath)
                            status_fn({"type": "safecomms_start", "label": f"SafeComms scanning {fname}..."})
                            content = _dispatch_tool(tc.name, tc.input)
                            rd = json.loads(content)
                            if rd.get("clean"):
                                status_fn({"type": "safecomms_clean",   "label": "SafeComms: CLEAN"})
                            else:
                                status_fn({"type": "safecomms_blocked", "label": "SafeComms: BLOCKED"})

                        elif tc.name == "create_project":
                            folder = tc.input.get("folder_name", "project")
                            status_fn({"type": "project_start", "label": f"Creating project {folder}..."})
                            content = _dispatch_tool(tc.name, tc.input)
                            rd = json.loads(content)
                            status_fn({"type": "project_done", "label": f"{folder} created", "path": rd.get("project_path", "")})

                        elif tc.name == "create_agent":
                            slug = tc.input.get("agent_slug", "new-agent")
                            status_fn({"type": "create_agent_start", "agent": slug, "label": f"Creating {slug}..."})
                            content = _dispatch_tool(tc.name, tc.input)
                            rd = json.loads(content)
                            status_fn({"type": "create_agent_done", "agent": slug, "label": f"{rd.get('display_name', slug)} created and saved"})

                        elif tc.name == "list_agents":
                            status_fn({"type": "tool_start", "tool": "list_agents", "label": "Reading AgentLibrary..."})
                            content = _dispatch_tool(tc.name, tc.input)
                            status_fn({"type": "tool_done",  "tool": "list_agents", "label": "Library loaded"})

                        elif tc.name == "write_file":
                            filename = tc.input.get("filename", "file")
                            status_fn({"type": "tool_start", "tool": "write_file", "label": f"Saving {filename}..."})
                            content = _dispatch_tool(tc.name, tc.input)
                            status_fn({"type": "tool_done",  "tool": "write_file", "label": f"Saved to {config.OUTPUT_DIR}\\{filename}"})

                        else:
                            status_fn({"type": "tool_start", "tool": tc.name, "label": tc.name})
                            content = _dispatch_tool(tc.name, tc.input)
                            status_fn({"type": "tool_done",  "tool": tc.name, "label": "Done"})

                        tool_results_map[tc.id] = content

                    except Exception as e:
                        tool_results_map[tc.id] = json.dumps({"error": f"Tool '{tc.name}' failed: {e}"})

                # --- pass 2: specialist calls (parallel if multiple, sequential if one) ---
                specialist_tcs = [tc for tc in tool_calls if tc.name == "call_specialist"]

                if len(specialist_tcs) > 1:
                    with ThreadPoolExecutor(max_workers=len(specialist_tcs)) as executor:
                        future_map = {executor.submit(_run_specialist, tc): tc for tc in specialist_tcs}
                        for future in as_completed(future_map):
                            tc = future_map[future]
                            try:
                                tc_id, content = future.result()
                                tool_results_map[tc_id] = content
                            except Exception as e:
                                tool_results_map[tc.id] = json.dumps({"error": f"Specialist call failed: {e}"})
                elif len(specialist_tcs) == 1:
                    tc = specialist_tcs[0]
                    try:
                        tc_id, content = _run_specialist(tc)
                        tool_results_map[tc_id] = content
                    except Exception as e:
                        tool_results_map[tc.id] = json.dumps({"error": f"Specialist call failed: {e}"})

            except Exception as outer_err:
                # Last-resort catch — ensure every unhandled tool_use gets a result
                status_fn({"type": "tool_done", "tool": "dispatch", "label": f"Dispatch error: {outer_err}"})

            # ALWAYS runs — API requires a tool_result for every tool_use block
            tool_results = [
                {
                    "type":        "tool_result",
                    "tool_use_id": tc.id,
                    "content":     tool_results_map.get(
                        tc.id,
                        json.dumps({"error": "Tool did not complete — no result available."})
                    ),
                }
                for tc in tool_calls
            ]

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user",      "content": tool_results})

        elif response.stop_reason in ("end_turn", "max_tokens"):
            if response.stop_reason == "max_tokens":
                # Orchestrator text was cut off (no tool_use blocks — those are handled above)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": "Please continue."})
            else:
                try:
                    user_input = input_fn()
                    if isinstance(user_input, str):
                        user_input = user_input.strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if user_input == "__stop__" or (stop_fn and stop_fn()):
                    status_fn({"type": "stopped", "message": "Session stopped by user."})
                    break

                if isinstance(user_input, str):
                    if user_input.lower() in ("exit", "quit", "q"):
                        break
                    if not user_input:
                        user_input = "(no input)"

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user",      "content": user_input})

        else:
            break

    status_fn({"type": "usage", "usage": session_usage})
