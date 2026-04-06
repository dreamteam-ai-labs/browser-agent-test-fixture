#!/usr/bin/env python3
"""Commit guard — rejects placeholder commit messages.

PreToolUse hook on Bash(git commit). Checks the commit message for
placeholder patterns that break factory loop git history parsing.

OBSOLESCENCE: Remove if Anthropic ships native commit message validation
in agent frontmatter. See Hook Dependency Watchlist.
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


# Patterns that indicate a placeholder commit message
PLACEHOLDER_PATTERNS = [
    r"<feature[- _]?name>",
    r"<actual[- _]?feature>",
    r"\[feature[- _]?name\]",
    r"\[actual[- _]?name\]",
    r"implement \[",
    r"implement <",
    r"feat: implement$",       # bare "feat: implement" with nothing after
]


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "") or ""
    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only check git commit commands
    if "git commit" not in command:
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    # Extract the commit message (after -m)
    msg_match = re.search(r'-m\s+["\'](.+?)["\']', command)
    if not msg_match:
        # Can't parse message — allow (might be using heredoc or other format)
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    message = msg_match.group(1)

    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            log_hook("commit-guard", agent_id or "unknown", "BLOCK", f"placeholder: {message[:80]}")
            json.dump({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Commit message contains a placeholder: '{message[:80]}'. "
                        "Use the REAL feature name (e.g., 'feat: implement expenses-crud')."
                    ),
                }
            }, sys.stdout)
            return

    log_hook("commit-guard", agent_id or "unknown", "ALLOW", f"msg: {message[:80]}")
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }, sys.stdout)


if __name__ == "__main__":
    main()
