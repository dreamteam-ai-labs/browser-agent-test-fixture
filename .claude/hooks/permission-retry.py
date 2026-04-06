#!/usr/bin/env python3
"""Permission retry hook — handles auto-mode classifier denials.

PermissionDenied hook (new in CC 2.1.88). Fires after the auto-mode
classifier blocks a tool call. Returns {retry: true} to let the model
try an alternative approach, or logs the denial for observability.

OBSOLESCENCE: Remove if Anthropic ships native retry behavior for
auto-mode denials. See Hook Dependency Watchlist in memory/sync-status.md.
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

    agent_id = event.get("agent_id", "") or "unknown"
    tool_name = event.get("tool_name", "unknown")
    reason = event.get("reason", "")

    log_hook("permission-retry", agent_id, "DENIED", f"tool={tool_name} | reason={reason[:200]}")

    # Allow the model to retry with an alternative approach
    json.dump({"retry": True}, sys.stdout)


if __name__ == "__main__":
    main()
