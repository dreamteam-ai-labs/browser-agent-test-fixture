#!/usr/bin/env python3
"""Auto-assign hook — suggests next feature for idle agents.

Reads TeammateIdle hook event JSON from stdin. Reads features.json to
find the next pending feature and returns it as a message for the idle agent.

OBSOLESCENCE: Remove when Anthropic ships native TeammateIdle with MCP
integration or native task queue auto-claim. See Hook Dependency Watchlist.
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


def get_next_pending() -> dict | None:
    """Find the next pending feature from features.json."""
    path = PROJECT_DIR / "features.json"
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    for feature in data.get("features", []):
        if feature.get("status") == "pending":
            return feature

    return None


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "unknown")
    next_feature = get_next_pending()

    # Also check if any features are still in_progress
    has_in_progress = False
    try:
        data = json.loads((PROJECT_DIR / "features.json").read_text(encoding="utf-8"))
        has_in_progress = any(
            f.get("status") == "in_progress" for f in data.get("features", [])
        )
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        pass

    if next_feature:
        log_hook("auto-assign", agent_id, "SUGGEST", f"feature={next_feature['id']}")
        message = (
            f"Next pending feature: {next_feature['name']} (id: {next_feature['id']}). "
            f"Description: {next_feature.get('description', 'N/A')}. "
            f"Call get_next_feature() to claim it, then start_feature(id=\"{next_feature['id']}\")."
        )
        json.dump({"decision": "allow", "message": message}, sys.stdout)
    elif has_in_progress:
        # Other agents still working — stay alive in case more work unlocks
        log_hook("auto-assign", agent_id, "WAIT", "features still in progress")
        json.dump({
            "decision": "allow",
            "message": "No pending features, but some are still in progress. "
            "Wait for dependencies to complete, then check get_next_feature() again.",
        }, sys.stdout)
    else:
        # All features done — stop the idle agent to save cost
        log_hook("auto-assign", agent_id, "STOP", "all features completed")
        json.dump({
            "decision": "allow",
            "continue": False,
            "stopReason": "All features completed. No more work to assign.",
        }, sys.stdout)


if __name__ == "__main__":
    main()
