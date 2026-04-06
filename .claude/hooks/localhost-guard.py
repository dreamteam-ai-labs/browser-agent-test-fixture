#!/usr/bin/env python3
"""Localhost guard — rejects hardcoded localhost URLs in frontend code.

PreToolUse hook on Write/Edit in frontend/. Checks for hardcoded
localhost:8000 which breaks Coolify deployment (frontend runs in a
separate container with NEXT_PUBLIC_API_URL pointing to the backend).

OBSOLESCENCE: Remove if Anthropic ships native content validation
hooks. See Hook Dependency Watchlist.
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

    agent_id = event.get("agent_id", "") or ""
    tool_input = event.get("tool_input", {})
    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
    new_content = tool_input.get("content", "") or tool_input.get("new_string", "")

    # Only check frontend files
    normalized = file_path.replace("\\", "/")
    if "/frontend/" not in normalized and not normalized.startswith("frontend/"):
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    # Skip config files that legitimately reference localhost as a fallback
    basename = normalized.split("/")[-1] if "/" in normalized else normalized
    if basename in ("next.config.js", "next.config.mjs", "next.config.ts", ".env.local", ".env"):
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    # Check for hardcoded localhost URLs in the content being written
    if "localhost:8000" in new_content or "127.0.0.1:8000" in new_content:
        log_hook("localhost-guard", agent_id or "unknown", "BLOCK", f"file={normalized}")
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Hardcoded localhost:8000 detected in {basename}. "
                    "This breaks deployment — the frontend runs in a separate container. "
                    "Use an empty string as axios baseURL or process.env.NEXT_PUBLIC_API_URL. "
                    "Configure Next.js rewrites in next.config to proxy /api/* to the backend."
                ),
            }
        }, sys.stdout)
        return

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }, sys.stdout)


if __name__ == "__main__":
    main()
