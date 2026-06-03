"""
Conductor -- conductor_agent.py

The Conductor (Opus 4) coordinates a library of specialist agents.
It runs a 4-phase workflow:

  Phase 1: Intake      -- understand the task; ask up to 2 clarifying questions
  Phase 2: Analysis    -- read all agents; select best match(es); present routing plan
  Phase 3: Execution   -- call each specialist in order; save artifacts to output/
  Phase 4: Synthesis   -- weave all specialist outputs into a final answer

Auto-creation: when no agent fits, Conductor drafts and saves a new specialist
permanently to AgentLibrary, then immediately uses it.
"""

import json
import os
from datetime import date

import anthropic
import httpx

import config
from tools.library_reader import (
    list_agents, call_specialist, write_file, create_agent, create_project
)

TODAY = date.today().strftime("%Y-%m-%d")

SYSTEM_PROMPT = f"""You are Conductor -- a local multi-agent AI orchestrator.

Your role: understand the user's task, select the right specialist agent(s) from the
AgentLibrary, prepare rich context for each one, execute them in the correct order,
and synthesize their outputs into a complete, actionable final answer.

=== PHASE 1: INTAKE ===
Greet the user and ask them to describe their task or problem.
Ask at most 2 focused clarifying questions if needed.
Once the task is clear, say "Understood. Analyzing the AgentLibrary now..." and
move immediately to Phase 2.

=== PHASE 2: ANALYSIS ===
Call list_agents to load all available specialists.
Evaluate each agent's domain, description, boundaries, and example_use_cases.
Select the best matching agent(s) and reason about:
  - Core domain: which agent owns the primary problem?
  - Sequence: if the task spans multiple domains, what is the right order?
  - No match: if no agent fits, plan to create one (see AUTO-CREATING AGENTS).

Present a ROUTING PLAN as a numbered list:
  1. Which agent(s) will be called, in order
  2. Why each was selected
  3. What specific focus will be sent to each

End with: "Ready to proceed? Reply 'yes' to start, or tell me what to change."
Wait for confirmation before calling any specialist.

=== PHASE 3: EXECUTION ===
After confirmation, call each specialist using call_specialist, in planned order.
For each call, prepare a self-contained prepared_task that includes:
  - The user's full task description and any data they provided
  - What specific aspect this specialist should focus on
  - Any environment or constraint details relevant to this specialist
  - Expected output format

For any script or large code artifact returned by a specialist, call write_file
immediately. Tell the user the saved path. Summarize what the file contains in
1-2 sentences. Do NOT reprint raw code in your response.

=== PHASE 4: SYNTHESIS ===
After all specialists have responded:
  - Weave outputs into one coherent answer
  - Resolve conflicts or fill gaps between specialists
  - Add cross-cutting observations only you can see
  - Present the final answer cleanly

=== SAVING ARTIFACTS ===
Any script, document, or large code artifact from any specialist MUST be saved
via write_file. Use a descriptive subfolder name (e.g. 'sql-perf-diagnostics').
All files for one task share the same subfolder so they land in one dated folder.
Tell the user: "Saved to output/<subfolder>-<datetime>/<filename>"

=== AUTO-CREATING AGENTS ===
When a task needs a specialist that does not exist, and the domain is well-defined
enough for a permanent specialist, create it automatically. No user approval needed.
Tell them: "No [domain] specialist exists yet. Creating one now..."

Create agents one at a time -- create one, call it, then move to the next.
Do NOT batch all YAML definitions in one response before calling any tools.

Draft definition.yaml using this exact schema:

name: agent-slug
display_name: AgentDisplayName
version: v1.0
build: "001"
status: Production
category: Work  # or Personal
created: {TODAY}
last_updated: {TODAY}
author: Conductor

domain: >
  One-line domain description.

description: >
  2-3 sentences: what this agent knows, what it solves, how it fits multi-agent work.

system_prompt: |
  You are the [AgentName] -- [role description].

  Your expertise covers:
  - [key area]

  Stay in your role. You are a specialist, not a general assistant.

tools: []

boundaries:
  does:
    - Specific capabilities
  does_not:
    - Explicit exclusions

example_use_cases:
  - Scenario where Conductor should route here

tags:
  - relevant-tags

=== CREATING PROJECTS ===
Use create_project when a task produces lasting value -- new agents, ongoing
research, or content the user will return to.

Workspace root is configured in config.py (WORKSPACE_ROOT).
Categories: Work, Personal, or any folder structure that makes sense.

CLAUDE.md format:
  # CLAUDE.md -- ProjectName
  ## PURPOSE
  ## AGENTS
  ## FILE MAP
  ## HOW TO USE

=== FALLBACK: NO MATCHING AGENT ===
If no agent fits AND the domain is too narrow for a permanent specialist:
"No specialist in AgentLibrary covers this task.
Options:
  A) I create a permanent specialist for this domain right now.
  B) I handle this myself using my own Opus-level reasoning.
Which do you prefer?"

=== HARD RULES ===
- Always call list_agents first -- never assume which agents exist
- Never call call_specialist before the user confirms the routing plan
- prepared_task must be self-contained -- the specialist has NO other context
- Write all code artifacts to output/ -- never embed raw code in your response
- Create and call agents one at a time -- never batch all YAMLs first
- Keep your coordination text concise -- specialists deliver the detail
- Today: {TODAY}
"""

TOOLS = [
    {
        "name": "list_agents",
        "description": (
            "Reads all specialist agents from AgentLibrary. "
            "Call this first in Phase 2 before deciding routing."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "call_specialist",
        "description": (
            "Invokes a specialist agent with a prepared task (single-turn). "
            "Only call after the user confirms the routing plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_slug":    {"type": "string"},
                "category":      {"type": "string", "enum": ["Work", "Personal"]},
                "prepared_task": {"type": "string"},
            },
            "required": ["agent_slug", "category", "prepared_task"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Saves content to output/<subfolder>-<datetime>/<filename>. "
            "ALWAYS use for any script or large artifact from a specialist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename":  {"type": "string"},
                "content":   {"type": "string"},
                "subfolder": {"type": "string"},
            },
            "required": ["filename", "content", "subfolder"],
        },
    },
    {
        "name": "create_agent",
        "description": (
            "Creates a new specialist agent and saves it permanently to AgentLibrary. "
            "Use when no existing agent covers the task domain. "
            "Create one agent at a time -- do not batch."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category":     {"type": "string", "enum": ["Work", "Personal"]},
                "agent_slug":   {"type": "string"},
                "yaml_content": {"type": "string"},
            },
            "required": ["category", "agent_slug", "yaml_content"],
        },
    },
    {
        "name": "create_project",
        "description": (
            "Scaffolds a new project workspace under WORKSPACE_ROOT. "
            "Use when a task produces lasting value worth organizing permanently."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category":    {"type": "string"},
                "folder_name": {"type": "string"},
                "claude_md":   {"type": "string"},
                "description": {"type": "string"},
                "how_to_run":  {"type": "string"},
            },
            "required": ["category", "folder_name", "claude_md", "description"],
        },
    },
]


def _dispatch_tool(tool_name, tool_input):
    if tool_name == "list_agents":
        result = list_agents()
    elif tool_name == "call_specialist":
        result = call_specialist(
            tool_input["agent_slug"],
            tool_input["category"],
            tool_input["prepared_task"],
        )
    elif tool_name == "write_file":
        result = write_file(
            tool_input["filename"],
            tool_input["content"],
            tool_input.get("subfolder", ""),
        )
    elif tool_name == "create_agent":
        result = create_agent(
            tool_input["category"],
            tool_input["agent_slug"],
            tool_input["yaml_content"],
        )
    elif tool_name == "create_project":
        result = create_project(
            tool_input["category"],
            tool_input["folder_name"],
            tool_input["claude_md"],
            tool_input.get("description", ""),
            tool_input.get("how_to_run", ""),
        )
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, indent=2)


def run(output_fn=None, input_fn=None, status_fn=None):
    if output_fn is None:
        output_fn = lambda text: print(f"\n[Conductor]\n{text}\n")
    if input_fn is None:
        input_fn = lambda: input("You: ")
    if status_fn is None:
        status_fn = lambda event: print(f"  --> {event}")

    client = anthropic.Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        http_client=httpx.Client(verify=False),
    )

    messages = [{"role": "user", "content": "Hello. I have a task I need help with. Please start."}]

    session_usage = {"input_tokens": 0, "output_tokens": 0,
                     "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

    while True:
        response = client.messages.create(
            model=config.CONDUCTOR_MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )

        u = response.usage
        session_usage["input_tokens"]                += u.input_tokens
        session_usage["output_tokens"]               += u.output_tokens
        session_usage["cache_creation_input_tokens"] += getattr(u, "cache_creation_input_tokens", 0)
        session_usage["cache_read_input_tokens"]     += getattr(u, "cache_read_input_tokens", 0)

        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                output_fn(block.text.strip())

        if response.stop_reason == "tool_use":
            tool_calls   = [b for b in response.content if b.type == "tool_use"]
            tool_results = []

            for tc in tool_calls:
                if tc.name == "list_agents":
                    status_fn({"type": "tool_start", "tool": "list_agents", "label": "Reading AgentLibrary..."})
                    content = _dispatch_tool(tc.name, tc.input)
                    status_fn({"type": "tool_done",  "tool": "list_agents", "label": "Library loaded"})

                elif tc.name == "write_file":
                    fname = tc.input.get("filename", "file")
                    status_fn({"type": "tool_start", "tool": "write_file", "label": f"Saving {fname}..."})
                    content = _dispatch_tool(tc.name, tc.input)
                    status_fn({"type": "tool_done",  "tool": "write_file", "label": f"Saved {fname}"})

                elif tc.name == "call_specialist":
                    slug = tc.input.get("agent_slug", "specialist")
                    status_fn({"type": "specialist_start", "agent": slug, "label": f"Calling {slug}..."})
                    content = _dispatch_tool(tc.name, tc.input)
                    status_fn({"type": "specialist_done", "agent": slug, "label": f"{slug} responded"})

                elif tc.name == "create_agent":
                    slug = tc.input.get("agent_slug", "new-agent")
                    status_fn({"type": "create_agent_start", "agent": slug, "label": f"Creating {slug}..."})
                    content = _dispatch_tool(tc.name, tc.input)
                    result_data = json.loads(content)
                    display = result_data.get("display_name", slug)
                    status_fn({"type": "create_agent_done", "agent": slug, "label": f"{display} created"})

                elif tc.name == "create_project":
                    folder = tc.input.get("folder_name", "project")
                    status_fn({"type": "project_start", "label": f"Creating project {folder}..."})
                    content = _dispatch_tool(tc.name, tc.input)
                    result_data = json.loads(content)
                    status_fn({"type": "project_done", "label": f"{folder} created",
                               "path": result_data.get("project_path", "")})

                else:
                    status_fn({"type": "tool_start", "tool": tc.name, "label": tc.name})
                    content = _dispatch_tool(tc.name, tc.input)
                    status_fn({"type": "tool_done",  "tool": tc.name, "label": "Done"})

                tool_results.append({
                    "type": "tool_result", "tool_use_id": tc.id, "content": content
                })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user",      "content": tool_results})

        elif response.stop_reason in ("end_turn", "max_tokens"):
            if response.stop_reason == "max_tokens":
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": "Please continue."})
            else:
                try:
                    user_input = input_fn().strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if user_input.lower() in ("exit", "quit", "q"):
                    break
                if not user_input:
                    user_input = "(no input)"
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user",      "content": user_input})
        else:
            break

    status_fn({"type": "usage", "usage": session_usage})
