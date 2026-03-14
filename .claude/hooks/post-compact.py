#!/usr/bin/env python3
"""Post-compact hook — re-injects feature progress after context compaction.

When Claude's context is compacted, agents lose track of which features
are done, in-progress, or pending. This hook fires after compaction and
returns a progress summary as a message, ensuring agents stay oriented.
"""
import json
import sys
from pathlib import Path


def get_progress_summary() -> str:
    """Build a compact progress summary from features.json."""
    lines = []

    # Environment features
    env_path = Path("environment_features.json")
    if env_path.exists():
        try:
            data = json.loads(env_path.read_text(encoding="utf-8"))
            features = data.get("features", [])
            done = sum(1 for f in features if f.get("status") == "completed")
            total = len(features)
            if done < total:
                lines.append(f"ENV PREREQUISITES: {done}/{total} complete (BLOCKING)")
            else:
                lines.append(f"ENV PREREQUISITES: {done}/{total} complete ✓")
        except (json.JSONDecodeError, OSError):
            pass

    # App features
    app_path = Path("features.json")
    if not app_path.exists():
        return "No features.json found."

    try:
        data = json.loads(app_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "Could not read features.json."

    features = data.get("features", [])
    completed = [f for f in features if f.get("status") == "completed"]
    in_progress = [f for f in features if f.get("status") == "in_progress"]
    pending = [f for f in features if f.get("status") == "pending"]

    lines.append(f"PROGRESS: {len(completed)}/{len(features)} features complete")

    if in_progress:
        lines.append("IN PROGRESS:")
        for f in in_progress:
            lines.append(f"  - {f['id']}: {f['name']}")

    if pending:
        lines.append(f"PENDING: {len(pending)} features remaining")
        # Show next few pending
        for f in pending[:3]:
            lines.append(f"  - {f['id']}: {f['name']}")
        if len(pending) > 3:
            lines.append(f"  ... and {len(pending) - 3} more")

    lines.append("")
    lines.append("Call get_progress() for full details, or get_next_feature() to continue.")

    return "\n".join(lines)


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    summary = get_progress_summary()
    json.dump({
        "decision": "allow",
        "message": f"[Post-compaction state recovery]\n{summary}",
    }, sys.stdout)


if __name__ == "__main__":
    main()
