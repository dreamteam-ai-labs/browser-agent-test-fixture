#!/usr/bin/env python3
"""Auto-assign hook — suggests next feature for idle agents.

Reads TeammateIdle hook event JSON from stdin. Reads features.json to
find the next pending feature and returns it as a message for the idle agent.
"""
import json
import sys
from pathlib import Path


def get_next_pending(features_path: str = "features.json") -> dict | None:
    """Find the next pending feature from features.json."""
    path = Path(features_path)
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

    if next_feature:
        message = (
            f"Next pending feature: {next_feature['name']} (id: {next_feature['id']}). "
            f"Description: {next_feature.get('description', 'N/A')}. "
            f"Call get_next_feature() to claim it, then start_feature(id=\"{next_feature['id']}\")."
        )
        json.dump({"decision": "allow", "message": message}, sys.stdout)
    else:
        json.dump({
            "decision": "allow",
            "message": "No pending features remaining. Check get_progress() for status.",
        }, sys.stdout)


if __name__ == "__main__":
    main()
