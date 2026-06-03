"""
Conductor -- library_reader.py

Three tools available to the Conductor agent:
  list_agents      -- reads all agents from AgentLibrary
  call_specialist  -- invokes a specialist agent (single-turn)
  write_file       -- saves artifacts to the output folder
  create_agent     -- creates a new specialist and saves it to AgentLibrary
  create_project   -- scaffolds a new project workspace
"""

import json
import os
import re

import anthropic
import httpx
import yaml

import config


# ---------------------------------------------------------------------------
# list_agents
# ---------------------------------------------------------------------------

def list_agents() -> dict:
    """Returns all agents from AgentLibrary (Production and Development status)."""
    agents = []
    for category in ("Work", "Personal"):
        agents_dir = os.path.join(config.AGENT_LIBRARY_PATH, category, "agents")
        if not os.path.exists(agents_dir):
            continue
        for slug in sorted(os.listdir(agents_dir)):
            definition_path = os.path.join(agents_dir, slug, "definition.yaml")
            if not os.path.exists(definition_path):
                continue
            try:
                with open(definition_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not data:
                    continue
                status = data.get("status", "").lower()
                if status not in ("production", "development"):
                    continue
                boundaries = data.get("boundaries") or {}
                agents.append({
                    "slug":              slug,
                    "category":          category,
                    "display_name":      data.get("display_name", slug),
                    "domain":            str(data.get("domain", "")).strip(),
                    "description":       str(data.get("description", "")).strip(),
                    "does":              boundaries.get("does", []),
                    "does_not":          boundaries.get("does_not", []),
                    "example_use_cases": data.get("example_use_cases", []),
                    "tags":              data.get("tags", []),
                })
            except Exception:
                pass
    return {"agents": agents, "count": len(agents)}


# ---------------------------------------------------------------------------
# call_specialist
# ---------------------------------------------------------------------------

def call_specialist(agent_slug: str, category: str, prepared_task: str) -> dict:
    """Invokes a specialist agent (single-turn) and returns its full response."""
    definition_path = os.path.join(
        config.AGENT_LIBRARY_PATH, category, "agents", agent_slug, "definition.yaml"
    )
    if not os.path.exists(definition_path):
        return {"error": f"Agent '{agent_slug}' not found in category '{category}'."}

    try:
        with open(definition_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return {"error": f"Could not parse definition.yaml: {e}"}

    system_prompt = data.get("system_prompt", "")
    if not system_prompt:
        return {"error": f"Agent '{agent_slug}' has no system_prompt."}

    try:
        client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY,
            http_client=httpx.Client(verify=False),
        )
        response = client.messages.create(
            model=config.SPECIALIST_MODEL,
            max_tokens=8192,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prepared_task}],
        )
        return {
            "agent":         data.get("display_name", agent_slug),
            "response":      response.content[0].text,
            "input_tokens":  response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    except Exception as e:
        return {"error": f"Specialist call failed: {e}"}


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

def write_file(filename: str, content: str, subfolder: str = "") -> dict:
    """
    Saves content to output/<subfolder>-<datetime>/<filename>.
    Creates the subfolder automatically.
    """
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_sub  = re.sub(r"[^A-Za-z0-9._\-]", "-", subfolder).strip("-") if subfolder else "conductor-output"
    folder    = os.path.join(config.OUTPUT_DIR, f"{safe_sub}-{timestamp}")
    os.makedirs(folder, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", os.path.basename(filename))
    path      = os.path.join(folder, safe_name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"saved": True, "path": path, "folder": folder}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# create_agent
# ---------------------------------------------------------------------------

def create_agent(category: str, agent_slug: str, yaml_content: str) -> dict:
    """Creates a new specialist agent and saves it permanently to AgentLibrary."""
    if category not in ("Work", "Personal"):
        return {"error": f"Invalid category '{category}'."}

    try:
        data = yaml.safe_load(yaml_content)
    except Exception as e:
        return {"error": f"Invalid YAML: {e}"}

    if not data:
        return {"error": "YAML parsed to empty document."}

    display_name = data.get("display_name", agent_slug)
    domain       = str(data.get("domain", "")).strip()
    version      = data.get("version", "v1.0")

    agent_dir       = os.path.join(config.AGENT_LIBRARY_PATH, category, "agents", agent_slug)
    os.makedirs(agent_dir, exist_ok=True)
    definition_path = os.path.join(agent_dir, "definition.yaml")

    with open(definition_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    _update_index_files(category, display_name, agent_slug, domain, version)

    return {
        "created":      True,
        "path":         definition_path,
        "display_name": display_name,
        "slug":         agent_slug,
        "category":     category,
    }


def _update_index_files(category, agent_name, agent_slug, domain, version):
    from datetime import date
    TODAY = re.sub(r"\D", "-", date.today().isoformat())

    def patch(filepath, link_prefix):
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_row = (
            f"| [{agent_name}]({link_prefix}{agent_slug}/definition.yaml) "
            f"| {domain} | Production | {version} |\n"
        )
        found  = False
        result = []
        for line in lines:
            if re.match(rf"\|\s*{re.escape(agent_name)}\s*\|", line) and "Planned" in line:
                result.append(new_row)
                found = True
            elif "Last Updated:" in line:
                result.append(f"Last Updated: {TODAY}\n")
            else:
                result.append(line)
        if not found:
            last_table = max(
                (i for i, ln in enumerate(result) if ln.strip().startswith("|")),
                default=len(result) - 1,
            )
            result.insert(last_table + 1, new_row)
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(result)

    patch(os.path.join(config.AGENT_LIBRARY_PATH, category, "INDEX.md"), "agents/")
    patch(os.path.join(config.AGENT_LIBRARY_PATH, "INDEX.md"), f"{category}/agents/")


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------

def create_project(
    category: str,
    folder_name: str,
    claude_md: str,
    description: str = "",
    how_to_run: str = "",
    skill_name: str = "",
    skill_content: str = "",
) -> dict:
    """Scaffolds a new project workspace under WORKSPACE_ROOT/<category>/<folder_name>."""
    workspace = config.WORKSPACE_ROOT
    project_path = os.path.join(workspace, category, folder_name)
    os.makedirs(project_path, exist_ok=True)

    created_files = []

    with open(os.path.join(project_path, "CLAUDE.md"), "w", encoding="utf-8") as f:
        f.write(claude_md)
    created_files.append(os.path.join(project_path, "CLAUDE.md"))

    if how_to_run.strip():
        path = os.path.join(project_path, "HOW_TO_RUN.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(how_to_run)
        created_files.append(path)

    return {
        "created":      True,
        "project_path": project_path,
        "files":        created_files,
    }
