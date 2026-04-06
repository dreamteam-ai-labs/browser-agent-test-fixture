#!/usr/bin/env python3
"""Post-compact hook — re-injects feature progress and phase directive after compaction.

When Claude's context is compacted, agents lose track of which features
are done, in-progress, or pending. This hook fires after compaction and
returns a phase-specific directive + progress summary, ensuring agents
stay oriented.

OBSOLESCENCE: Remove when Anthropic ships native compaction-aware context
injection. See Hook Dependency Watchlist in memory/sync-status.md.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

STATE_FILE = PROJECT_DIR / "project-state.json"

# Phase-specific directives — focused, actionable, short
PHASE_DIRECTIVES = {
    "foundations": (
        "You are building FOUNDATIONS (Phase 0+1). "
        "Call get_next_feature(max_phase=1) to find the next feature. "
        "Build it, test it, complete it. Repeat until no more Phase 0+1 features remain. "
        "Then call set_state(key='build_phase', value='builders') to advance."
    ),
    "builders": (
        "BUILDERS are running as teammates. "
        "Monitor progress with get_progress(). Wait for them to finish. "
        "Do NOT build features yourself — the builders handle Phase 2+."
    ),
    "verification": (
        "All features built. Run verification: pytest -v && cd frontend && npm test. "
        "If tests pass, the build phase is complete."
    ),
    "qa": (
        "QA phase. Spawn qa-tester if not already running. "
        "Check qa-report.json for results. If critical issues, fix them and retest."
    ),
    "deploy": (
        "QA passed. Spawn deployment-prep agent if not already running. "
        "Wait for it to commit."
    ),
    "done": (
        "Build complete. All features built, QA passed, deployment-prep done. "
        "You can exit."
    ),
}


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


def read_build_phase() -> str:
    """Read build_phase from project-state.json."""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data.get("build_phase", "")
    except (OSError, json.JSONDecodeError):
        return ""


def get_progress_summary() -> str:
    """Build a compact progress summary from features.json."""
    lines = []

    # Environment features
    env_path = PROJECT_DIR / "environment_features.json"
    if env_path.exists():
        try:
            data = json.loads(env_path.read_text(encoding="utf-8"))
            features = data.get("features", [])
            done = sum(1 for f in features if f.get("status") == "completed")
            total = len(features)
            if done < total:
                lines.append(f"ENV PREREQUISITES: {done}/{total} complete (BLOCKING)")
            else:
                lines.append(f"ENV PREREQUISITES: {done}/{total} complete")
        except (json.JSONDecodeError, OSError):
            pass

    # App features
    app_path = PROJECT_DIR / "features.json"
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

    agent_id = event.get("agent_id", "unknown") or "unknown"

    # Build the recovery message
    parts = []

    # Phase-specific directive (primary — short, actionable)
    build_phase = read_build_phase()
    if build_phase and build_phase in PHASE_DIRECTIVES:
        parts.append(f"[PHASE: {build_phase.upper()}]")
        parts.append(PHASE_DIRECTIVES[build_phase])
        parts.append("")

    # Progress summary (secondary — context)
    summary = get_progress_summary()
    parts.append(summary)

    message = "\n".join(parts)

    log_detail = f"phase={build_phase or 'unset'}"
    try:
        data = json.loads((PROJECT_DIR / "features.json").read_text(encoding="utf-8"))
        features = data.get("features", [])
        done = sum(1 for f in features if f.get("status") == "completed")
        log_detail += f" | {done}/{len(features)} features"
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        pass

    log_hook("post-compact", agent_id, "RECOVER", log_detail)

    json.dump({
        "decision": "allow",
        "message": f"[Post-compaction state recovery]\n{message}",
    }, sys.stdout)


if __name__ == "__main__":
    main()
