#!/usr/bin/env python3
"""Build gate hook — prevents the lead agent from exiting before the build is complete.

Stop hook that checks features.json and qa-report.json before allowing exit.
If features are incomplete or QA hasn't passed, blocks the exit and tells the
agent to keep working. This survives context compaction because it operates at
the infrastructure level, not the prompt level.

Only blocks the lead session (no agent_type). Teammates and subagents exit freely.

New in Claude Code 2.1.85 (Stop hook with decision: "block").
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# Safety valve — don't block forever if something is truly broken
MAX_BLOCKS = 20
BLOCK_COUNT_FILE = Path(".claude/hooks/.build-gate-blocks")


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


def get_block_count() -> int:
    """Read the current block count from disk."""
    try:
        return int(BLOCK_COUNT_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def increment_block_count() -> int:
    """Increment and return the block count."""
    count = get_block_count() + 1
    BLOCK_COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    BLOCK_COUNT_FILE.write_text(str(count), encoding="utf-8")
    return count


def check_features_complete() -> tuple[bool, str]:
    """Check if all features in features.json are completed.

    Returns (all_complete, detail_string).
    """
    path = Path("features.json")
    if not path.exists():
        return True, "no features.json"  # No features to track — allow exit

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True, "unreadable features.json"  # Don't block on broken file

    features = data.get("features", [])
    if not features:
        return True, "empty features list"

    completed = sum(1 for f in features if f.get("status") == "completed")
    in_progress = sum(1 for f in features if f.get("status") == "in_progress")
    pending = sum(1 for f in features if f.get("status") == "pending")
    total = len(features)

    if completed == total:
        return True, f"{completed}/{total} features complete"

    detail = f"{completed}/{total} complete, {in_progress} in-progress, {pending} pending"
    return False, detail


def check_deployment_prep_done() -> tuple[bool, str]:
    """Check if deployment-prep has run by looking for its commit in git log.

    Returns (prep_done, detail_string).
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-30"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return True, "git log failed — skipping check"

        if "deployment prep" in result.stdout.lower():
            return True, "deployment-prep commit found"

        return False, "deployment-prep has not run yet"
    except (subprocess.TimeoutExpired, OSError):
        return True, "git unavailable — skipping check"


def check_qa_passed() -> tuple[bool, str]:
    """Check if qa-report.json exists and has a passing verdict.

    Returns (qa_passed, detail_string).
    """
    path = Path("qa-report.json")
    if not path.exists():
        return False, "qa-report.json does not exist yet"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "qa-report.json unreadable"

    # Check for passing verdict in multiple formats the QA agent uses
    # Format 1: top-level "verdict" or "overall_result"
    verdict = data.get("verdict", "").lower()
    overall = data.get("overall_result", "").lower()

    if verdict in ("pass", "passed") or overall in ("pass", "passed"):
        return True, f"QA verdict: {verdict or overall}"

    # Format 2: "latest" → "summary" → "critical_issues"
    latest = data.get("latest", {})
    if isinstance(latest, dict):
        summary = latest.get("summary", {})
        if isinstance(summary, dict):
            critical = summary.get("critical_issues", [])
            if isinstance(critical, list) and len(critical) == 0:
                # Zero critical issues = pass
                return True, "QA: 0 critical issues"

    # Format 3: iterations array — check last iteration
    iterations = data.get("iterations", [])
    if iterations:
        last = iterations[-1] if isinstance(iterations, list) else None
        if isinstance(last, dict):
            iter_summary = last.get("summary", {})
            if isinstance(iter_summary, dict):
                critical = iter_summary.get("critical_issues", [])
                if isinstance(critical, list) and len(critical) == 0:
                    return True, "QA: 0 critical issues (last iteration)"

    return False, "QA has not passed yet"


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "") or ""
    agent_type = event.get("agent_type", "") or ""

    # Only gate the lead session — let teammates and subagents exit freely
    if agent_type:
        log_hook("build-gate", agent_id or agent_type, "ALLOW", "not lead session")
        json.dump({"decision": "allow"}, sys.stdout)
        return

    # Safety valve — don't block forever
    block_count = get_block_count()
    if block_count >= MAX_BLOCKS:
        log_hook("build-gate", "lead", "ALLOW", f"max blocks reached ({MAX_BLOCKS})")
        json.dump({"decision": "allow"}, sys.stdout)
        return

    # Check all three completion criteria
    features_ok, features_detail = check_features_complete()
    qa_ok, qa_detail = check_qa_passed()
    prep_ok, prep_detail = check_deployment_prep_done()

    if features_ok and qa_ok and prep_ok:
        log_hook("build-gate", "lead", "ALLOW", f"{features_detail} | {qa_detail} | {prep_detail}")
        json.dump({"decision": "allow"}, sys.stdout)
        return

    # Build is not complete — block the exit
    count = increment_block_count()
    reasons = []
    if not features_ok:
        reasons.append(f"Features: {features_detail}")
    if not qa_ok:
        reasons.append(f"QA: {qa_detail}")
    if not prep_ok:
        reasons.append(f"Deploy: {prep_detail}")

    reason_text = ". ".join(reasons)

    # Tailor the directive to what's still needed
    if not features_ok or not qa_ok:
        next_step = (
            "Run: cat qa-report.json to check QA status. "
            "If QA agent is still running, wait and check again. "
            "After QA passes, spawn the deployment-prep agent."
        )
    else:
        next_step = (
            "QA has passed but deployment-prep has not run. "
            "Spawn the deployment-prep agent NOW. "
            "It verifies deps are declared, imports work, and frontend builds."
        )

    directive = (
        f"Build not complete ({count}/{MAX_BLOCKS}). {reason_text}. "
        f"Do NOT exit. {next_step}"
    )

    log_hook("build-gate", "lead", "BLOCK", f"block #{count} | {reason_text}")

    json.dump({
        "decision": "block",
        "reason": directive,
    }, sys.stdout)


if __name__ == "__main__":
    main()
