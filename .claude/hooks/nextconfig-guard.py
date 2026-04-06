#!/usr/bin/env python3
"""Next.config guard — rejects output: "export" in Next.js config.

PostToolUse hook on Edit/Write of next.config files. Static export
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


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "") or ""
    tool_input = event.get("tool_input", {})
    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")

    # Only check next.config files
    normalized = file_path.replace("\\", "/")
    basename = normalized.split("/")[-1] if "/" in normalized else normalized
    if not basename.startswith("next.config"):
        json.dump({"decision": "allow"}, sys.stdout)
        return

    # Read the file AFTER the edit was applied (PostToolUse)
    config_path = Path(file_path)
    if not config_path.exists():
        json.dump({"decision": "allow"}, sys.stdout)
        return

    try:
        content = config_path.read_text(encoding="utf-8")
    except OSError:
        json.dump({"decision": "allow"}, sys.stdout)
        return

    # Check for output: "export" (various JS/TS patterns)
    if re.search(r'output\s*:\s*["\']export["\']', content):
        log_hook("nextconfig-guard", agent_id or "unknown", "WARN", f"output:export in {basename}")
        # PostToolUse can't block — but we can add context telling the agent to fix it
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "WARNING: next.config has output: 'export' which breaks SSR deployment. "
                    "The production pipeline uses `next start` (SSR mode), not static export. "
                    "Remove the output: 'export' line from next.config immediately."
                ),
            }
        }, sys.stdout)
        return

    log_hook("nextconfig-guard", agent_id or "unknown", "ALLOW", basename)
    json.dump({"decision": "allow"}, sys.stdout)


if __name__ == "__main__":
    main()
