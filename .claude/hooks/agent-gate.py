#!/usr/bin/env python3
"""Agent gate hook — blocks Agent tool during foundations phase.

PreToolUse hook with matcher "Agent". Reads build_phase from
project-state.json. During "foundations" phase (or when not set),
blocks the Agent tool to prevent premature teammate spawning.

OBSOLESCENCE: Remove when Anthropic ships native phase-aware
tool permissions in agent frontmatter. See Hook Dependency Watchlist
in memory/sync-status.md.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

STATE_FILE = Path("project-state.json")


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
        pass


def read_build_phase() -> str:
    """Read build_phase from project-state.json."""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data.get("build_phase", "")
    except (OSError, json.JSONDecodeError):
        return ""


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "") or ""
    agent_type = event.get("agent_type", "") or ""

    # Only gate the lead session — teammates and subagents always allowed
    if agent_type:
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    build_phase = read_build_phase()

    # Block during foundations or when phase not yet set
    if build_phase in ("foundations", ""):
        log_hook("agent-gate", agent_id or "lead", "BLOCK", f"phase={build_phase or 'unset'}")
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "Agent tool blocked during foundations phase. "
                    "Complete Phase 0+1 features first using get_next_feature(max_phase=1). "
                    "Call set_state(key='build_phase', value='builders') when foundations are done."
                ),
            }
        }, sys.stdout)
        return

    log_hook("agent-gate", agent_id or "lead", "ALLOW", f"phase={build_phase}")
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }, sys.stdout)


if __name__ == "__main__":
    main()
