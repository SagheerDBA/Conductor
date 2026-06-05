"""
Orchestrator -- library_reader.py

Two tools the Orchestrator calls during task execution:
  list_agents      -- reads all Production agents from AgentLibrary
  call_specialist  -- invokes a specialist agent (Sonnet 4.6) and returns its response
"""

import os

import anthropic
import httpx
import yaml

import config


def create_project(
    category: str,
    folder_name: str,
    claude_md: str,
    description: str = "",
    how_to_run: str = "",
    skill_name: str = "",
    skill_content: str = "",
) -> dict:
    """
    Creates a new project workspace following workspace standards.

    category     : 'Personal', 'Apps', 'AI-Infra', 'DBA-Tools', 'SQL-Brain'
    folder_name  : project folder name, e.g., 'ReligionStudy'
    claude_md    : complete CLAUDE.md content
    description  : one-line description for WORKSPACE-FEATURES.md
    how_to_run   : optional HOW_TO_RUN.md content (for apps/tools only)
    skill_name   : optional skill command name, e.g., 'religion' -> /religion
    skill_content: optional skill file content (required if skill_name is set)
    """
    import re as _re
    from datetime import date
    TODAY = date.today().strftime("%Y-%m-%d")

    valid = ("Personal", "Apps", "AI-Infra", "DBA-Tools", "SQL-Brain")
    if category not in valid:
        return {"error": f"Invalid category '{category}'. Must be one of: {valid}"}

    project_path = os.path.join(config.WORKSPACE_ROOT, category, folder_name)
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

    skill_path = None
    if skill_name.strip() and skill_content.strip():
        safe = _re.sub(r"[^a-z0-9\-]", "", skill_name.lower())
        skill_path = os.path.join(r"C:\Users\saghe\.claude\commands", f"{safe}.md")
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(skill_content)
        created_files.append(skill_path)

    # Update WORKSPACE-FEATURES.md ACTIVE PROJECTS table
    ws_path = os.path.join(config.WORKSPACE_ROOT, "_Shared", "WORKSPACE-FEATURES.md")
    if os.path.exists(ws_path) and description.strip():
        try:
            with open(ws_path, "r", encoding="utf-8") as f:
                content = f.read()

            new_row = (
                f"| {folder_name} | `{category}\\{folder_name}` "
                f"| Active | {description} |\n"
            )
            ap_pos   = content.find("## ACTIVE PROJECTS")
            next_sep = content.find("\n---", ap_pos + 18)
            table    = content[ap_pos:next_sep]
            last_nl  = table.rfind("\n")
            ins_pos  = ap_pos + last_nl + 1

            new_content = content[:ins_pos] + new_row + content[ins_pos:]
            new_content = _re.sub(
                r"# Last Updated: \d{4}-\d{2}-\d{2}",
                f"# Last Updated: {TODAY}",
                new_content,
            )
            with open(ws_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception:
            pass  # WORKSPACE-FEATURES update is best-effort

    return {
        "created":      True,
        "project_path": project_path,
        "files":        created_files,
        "skill":        skill_path,
    }


def _update_index_files(category: str, agent_name: str, agent_slug: str,
                        domain: str, version: str):
    """Updates category and master INDEX.md to register a newly created agent."""
    import re
    from datetime import date
    TODAY = date.today().strftime("%Y-%m-%d")

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

    patch(
        os.path.join(config.AGENT_LIBRARY_PATH, category, "INDEX.md"),
        "agents/",
    )
    patch(
        os.path.join(config.AGENT_LIBRARY_PATH, "INDEX.md"),
        f"{category}/agents/",
    )


SAFECOMMS_SCRIPT = config.SAFECOMMS_SCRIPT


def run_safecomms(file_path: str, strict: bool = False) -> dict:
    """
    Runs Test-DraftSafety.ps1 headlessly on a file.

    exit 0 -> CLEAN (safe to publish)
    exit 1 -> HIGH findings present -- do NOT publish

    file_path : full path to the file to scan
    strict    : if True, MEDIUM findings also block (exit 1)
    """
    import subprocess

    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    if not SAFECOMMS_SCRIPT:
        return {"clean": True, "note": "SafeComms not configured -- set SAFECOMMS_SCRIPT in config.py to enable."}
    if not os.path.exists(SAFECOMMS_SCRIPT):
        return {"error": f"SafeComms script not found: {SAFECOMMS_SCRIPT}"}

    cmd = [
        "powershell",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-File", SAFECOMMS_SCRIPT,
        "-Path", file_path,
    ]
    if strict:
        cmd.append("-Strict")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "clean":     result.returncode == 0,
            "exit_code": result.returncode,
            "output":    (result.stdout + result.stderr).strip(),
            "file":      file_path,
        }
    except subprocess.TimeoutExpired:
        return {"error": "SafeComms scan timed out after 60 seconds."}
    except Exception as e:
        return {"error": str(e)}


def create_agent(category: str, agent_slug: str, yaml_content: str) -> dict:
    """
    Creates a new specialist agent and saves it permanently to the AgentLibrary.

    Parses yaml_content to extract display_name, domain, and version.
    Saves definition.yaml and updates both INDEX.md files.
    The agent is immediately available to list_agents and call_specialist.
    """
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


def list_agents() -> dict:
    """
    Reads all Production agent definitions from AgentLibrary.
    Returns a list of agents with key fields needed for routing decisions.
    """
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
                # Include Production and Development agents -- many are ready
                # but were never formally promoted in their definition.yaml
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


def write_file(filename: str, content: str, subfolder: str = "") -> dict:
    """
    Saves content to C:\\Temp\\<subfolder>-<datetime>\\<filename>.

    Always writes under C:\\Temp. Creates the subfolder automatically.
    subfolder: short task description (e.g. 'add-db-to-ag'). Datetime appended automatically.
    """
    import re
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_sub  = re.sub(r'[^A-Za-z0-9._\-]', '-', subfolder).strip('-') if subfolder else "orchestrator-output"
    folder    = os.path.join(config.OUTPUT_DIR, f"{safe_sub}-{timestamp}")
    os.makedirs(folder, exist_ok=True)

    safe_name = re.sub(r'[^A-Za-z0-9._\-]', '_', os.path.basename(filename))
    path      = os.path.join(folder, safe_name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        home = os.path.expanduser("~")
        display = path.replace(home, "~") if path.startswith(home) else path
        return {"saved": True, "path": display, "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"error": str(e)}


def call_specialist(agent_slug: str, category: str, prepared_task: str,
                    prior_outputs: list = None, token_callback=None) -> dict:
    """
    Invokes a specialist agent via the Anthropic API (single-turn).

    agent_slug     : kebab-case slug matching the agent folder
    category       : 'Work' or 'Personal'
    prepared_task  : rich, self-contained task prepared by the Orchestrator
    prior_outputs  : optional list of {agent: display_name, response: text} from
                     prior specialists -- prepended as structured context
    token_callback : optional callable(token_str) for streaming; when provided,
                     tokens are streamed in real time instead of returned at the end
    """
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
        return {"error": f"Agent '{agent_slug}' has no system_prompt defined."}

    display_name = data.get("display_name", agent_slug)

    # Build user message -- prepend prior specialist outputs as structured context
    if prior_outputs:
        context_lines = ["CONTEXT FROM PRIOR SPECIALISTS", "=" * 40]
        for po in prior_outputs:
            context_lines.append(f"[{po.get('agent', 'Unknown Agent')}]")
            context_lines.append(po.get("response", ""))
            context_lines.append("=" * 40)
        context_lines.append("")
        context_lines.append("YOUR TASK")
        context_lines.append("-" * 40)
        user_message = "\n".join(context_lines) + "\n" + prepared_task
    else:
        user_message = prepared_task

    try:
        client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY,
            http_client=httpx.Client(verify=False),
        )

        if token_callback is not None:
            chunks = []
            with client.messages.stream(
                model=config.SPECIALIST_MODEL,
                max_tokens=8192,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    chunks.append(text)
                    token_callback(text)
            full_response = "".join(chunks)
            final = stream.get_final_message()
            return {
                "agent":         display_name,
                "response":      full_response,
                "input_tokens":  final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            }
        else:
            response = client.messages.create(
                model=config.SPECIALIST_MODEL,
                max_tokens=8192,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_message}],
            )
            return {
                "agent":         display_name,
                "response":      response.content[0].text,
                "input_tokens":  response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
    except Exception as e:
        return {"error": f"Specialist call failed: {e}"}
