#!/usr/bin/env python3
"""Path guard hook — enforces file path restrictions per agent role.

Reads hook event JSON from stdin. Uses agent_id to determine which
directories the agent is allowed to write to. Returns JSON decision.

Agent rules:
  backend-builder:  allow src/, tests/ — deny frontend/
  frontend-builder: allow frontend/ — deny src/, tests/
  qa-tester:        deny all writes (defense-in-depth)
"""
import json
import sys
from datetime import datetime
from pathlib import Path


def log_hook(hook_name: str, agent_id: str, action: str, detail: str = ""):
    log_path = Path(".claude/hooks/hook-log.txt")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="milliseconds")
    line = f"{timestamp} | {hook_name} | agent={agent_id} | {action}"
    if detail:
        line += f" | {detail}"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Best-effort logging — never break the hook


# Agent path rules: {agent_id_pattern: {"allow": [...], "deny": [...]}}
AGENT_RULES = {
    "backend-builder": {
        "allow": ["src/", "tests/", "pyproject.toml", "alembic/"],
        "deny": ["frontend/"],
    },
    "frontend-builder": {
        "allow": ["frontend/"],
        "deny": ["src/", "tests/", "alembic/"],
    },
    "qa-tester": {
        "allow": ["qa-report.json", "qa-smoke-results.json"],
        "deny": ["src/", "tests/", "frontend/"],
    },
}


def get_file_path(event: dict) -> str | None:
    """Extract the file path from the hook event."""
    tool_input = event.get("tool_input", {})
    # Write/Edit/MultiEdit all use file_path
    return tool_input.get("file_path") or tool_input.get("path")


def match_agent(agent_id: str) -> dict | None:
    """Find matching rules for the agent. Matches by substring."""
    if not agent_id:
        return None
    for pattern, rules in AGENT_RULES.items():
        if pattern in agent_id.lower():
            return rules
    return None


def check_path(file_path: str, rules: dict) -> tuple[bool, str]:
    """Check if the file path is allowed by the rules.

    Returns (allowed, reason).
    """
    # Normalize path separators
    normalized = file_path.replace("\\", "/")

    # Check deny list first
    for denied in rules.get("deny", []):
        if normalized.startswith(denied) or f"/{denied}" in normalized:
            return False, f"Path '{normalized}' is in denied area '{denied}' for this agent"

    # If there's an allow list, path must match at least one entry
    allow_list = rules.get("allow", [])
    if allow_list:
        for allowed in allow_list:
            if normalized.startswith(allowed) or f"/{allowed}" in normalized:
                return True, "Path is in allowed area"
        return False, f"Path '{normalized}' is not in any allowed area for this agent"

    return True, "No restrictions"


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # Can't parse input — allow by default (don't block on hook errors)
        json.dump({"decision": "allow"}, sys.stdout)
        return

    agent_id = event.get("agent_id", "") or ""
    rules = match_agent(agent_id)

    if rules is None:
        # Unknown agent or lead — allow everything
        json.dump({"decision": "allow"}, sys.stdout)
        return

    file_path = get_file_path(event)
    if not file_path:
        # No file path in event — allow (might be a non-file tool)
        json.dump({"decision": "allow"}, sys.stdout)
        return

    allowed, reason = check_path(file_path, rules)
    if allowed:
        log_hook("path-guard", agent_id, "ALLOW", f"path={file_path}")
        json.dump({"decision": "allow"}, sys.stdout)
    else:
        log_hook("path-guard", agent_id, "DENY", f"path={file_path}")
        json.dump({
            "decision": "block",
            "reason": reason,
        }, sys.stdout)


if __name__ == "__main__":
    main()
