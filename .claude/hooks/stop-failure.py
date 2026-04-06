#!/usr/bin/env python3
"""StopFailure hook — logs API errors (rate limits, auth failures, etc.).

Fires when a turn ends due to an API error rather than normal completion.
Logs the error to hook-log.txt for observability and returns allow (never blocks).

New in Claude Code 2.1.78.

OBSOLESCENCE: Remove when Anthropic ships native error telemetry to file.
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
        pass  # Best-effort logging — never break the hook


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "unknown") or "unknown"
    error = event.get("error", "unknown error")
    stop_reason = event.get("stop_reason", "")

    # Build a concise detail string
    detail_parts = []
    if stop_reason:
        detail_parts.append(f"reason={stop_reason}")
    if isinstance(error, str):
        detail_parts.append(error[:200])
    elif isinstance(error, dict):
        detail_parts.append(json.dumps(error)[:200])
    detail = " | ".join(detail_parts) if detail_parts else "no details"

    log_hook("stop-failure", agent_id, "API_ERROR", detail)

    # Always allow — this hook is observability only, never blocks
    json.dump({"decision": "allow"}, sys.stdout)


if __name__ == "__main__":
    main()
