#!/usr/bin/env python3
"""Next.config guard — blocks output: "export" in Next.js config.

PreToolUse hook on Write/Edit of next.config files. Static export
breaks the SSR deployment pipeline (Coolify uses `next start`).

OBSOLESCENCE: Remove if Anthropic ships native file content validation.
See Hook Dependency Watchlist.
"""
import json
import os
import re
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


EXPORT_PATTERN = re.compile(r'output\s*:\s*["\']export["\']')


def _allow():
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }, sys.stdout)


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        _allow()
        return

    agent_id = event.get("agent_id", "") or ""
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")

    # Only check next.config files
    normalized = file_path.replace("\\", "/")
    basename = normalized.split("/")[-1] if "/" in normalized else normalized
    if not basename.startswith("next.config"):
        _allow()
        return

    # Inspect the content about to be written (PreToolUse — before it lands)
    content_to_check = ""
    if tool_name == "Write":
        content_to_check = tool_input.get("content", "")
    elif tool_name in ("Edit", "MultiEdit"):
        content_to_check = tool_input.get("new_string", "")

    if content_to_check and EXPORT_PATTERN.search(content_to_check):
        log_hook("nextconfig-guard", agent_id or "unknown", "BLOCK", f"output:export in {basename}")
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "BLOCKED: output: 'export' breaks SSR deployment. "
                    "The production pipeline uses `next start` (SSR mode), not static export. "
                    "Remove output: 'export' from next.config."
                ),
            }
        }, sys.stdout)
        return

    log_hook("nextconfig-guard", agent_id or "unknown", "ALLOW", basename)
    _allow()


if __name__ == "__main__":
    main()
