#!/usr/bin/env python3
"""Package guard — prevents agents from creating rogue packages in src/.

PreToolUse hook on Write/Edit. All Python code must live in the declared
package (src/fixture/). Agents sometimes create a second package
with a cleaner name, which breaks the Dockerfile and start.sh since they're
hardcoded to the template package name.

OBSOLESCENCE: Remove when F4 generates sensible package names AND agents
stop creating sibling packages. See Hook Dependency Watchlist.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

# Baked in at template render time — the only allowed package under src/
DECLARED_PACKAGE = "fixture"


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

    normalized = file_path.replace("\\", "/")

    # Only check files under src/
    if not (normalized.startswith("src/") or "/src/" in normalized):
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    # Extract the package directory (first component after src/)
    # e.g., src/expense_tracker/models.py → expense_tracker
    parts = normalized.split("/")
    try:
        src_idx = parts.index("src")
        if src_idx + 1 < len(parts):
            package_dir = parts[src_idx + 1]
        else:
            package_dir = ""
    except ValueError:
        package_dir = ""

    # Allow: files directly in src/ (e.g., src/__init__.py)
    if not package_dir or package_dir.startswith("__"):
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    # Allow: the declared package
    if package_dir == DECLARED_PACKAGE:
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    # Block: any other package directory under src/
    log_hook("package-guard", agent_id or "unknown", "BLOCK", f"rogue package={package_dir}, declared={DECLARED_PACKAGE}")
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"All code must be in src/{DECLARED_PACKAGE}/, not src/{package_dir}/. "
                f"The Dockerfile, pyproject.toml, and start.sh are configured for the "
                f"'{DECLARED_PACKAGE}' package. Creating a separate package will break deployment."
            ),
        }
    }, sys.stdout)


if __name__ == "__main__":
    main()
