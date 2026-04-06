#!/usr/bin/env python3
"""TaskCreated hook — logs task creation events for build observability.

Fires when an agent spawns a task via TaskCreate. Logs the task name,
creating agent, and description to hook-log.txt. Never blocks.

New in Claude Code 2.1.84.

OBSOLESCENCE: Remove when Anthropic ships native task logging to file.
See Hook Dependency Watchlist in memory/sync-status.md.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))


def log_hook(hook_name: str, agent_id: str, action: str, detail: str = ""):
    log_path = PROJECT_DIR / ".claude" / "hooks" / "hook-log.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="milliseconds")
    line = f"{timestamp} | {hook_name} | agent={agent_id} | {action}"
    if detail:
        line += f" | {detail}"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "unknown") or "unknown"
    tool_input = event.get("tool_input", {})
    task_desc = tool_input.get("description", "")[:150]
    task_prompt = tool_input.get("prompt", "")[:100]

    detail_parts = []
    if task_desc:
        detail_parts.append(f"desc={task_desc}")
    if task_prompt:
        detail_parts.append(f"prompt={task_prompt}")
    detail = " | ".join(detail_parts) if detail_parts else "no details"

    log_hook("task-created", agent_id, "TASK_SPAWNED", detail)

    # Observability only — never block task creation
    json.dump({"decision": "allow"}, sys.stdout)


if __name__ == "__main__":
    main()
