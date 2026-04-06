#!/usr/bin/env python3
"""Build gate hook — prevents the lead agent from exiting before the build is complete.

Stop hook that checks features.json and qa-report.json before allowing exit.
Uses progress-based stall detection (primary) with block counter fallback.
Supports BUILD_LEAD_SCOPE for two-session hybrid architecture.

Only blocks the lead session (no agent_type). Teammates and subagents exit freely.

OBSOLESCENCE: Remove when Anthropic ships native session exit conditions
or "lead can't exit while teammates running." See Hook Dependency Watchlist
in memory/sync-status.md.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

# --- Fallback safety valve (validated across production runs) ---
MAX_BLOCKS = 20
BLOCK_COUNT_FILE = PROJECT_DIR / ".claude" / "hooks" / ".build-gate-blocks"

# --- Progress-based stall detection ---
STATE_FILE = PROJECT_DIR / "project-state.json"
STALL_THRESHOLD = 5  # consecutive blocks with no progress


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


# --- Fallback block counter (kept as safety net) ---

def get_block_count() -> int:
    try:
        return int(BLOCK_COUNT_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def increment_block_count() -> int:
    count = get_block_count() + 1
    BLOCK_COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    BLOCK_COUNT_FILE.write_text(str(count), encoding="utf-8")
    return count


# --- State read/write for progress tracking ---

def read_state(key: str, default=None):
    """Read a value from project-state.json."""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data.get(key, default)
    except (OSError, json.JSONDecodeError):
        return default


def write_state(key: str, value) -> None:
    """Write a value to project-state.json (atomic read-modify-write)."""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data[key] = value
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


# --- Progress snapshot ---

def get_progress_snapshot() -> dict:
    """Get current feature completion counts from features.json."""
    path = PROJECT_DIR / "features.json"
    if not path.exists():
        return {"completed": 0, "total": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        features = data.get("features", [])
        completed = sum(1 for f in features if f.get("status") == "completed")
        return {"completed": completed, "total": len(features)}
    except (OSError, json.JSONDecodeError):
        return {"completed": 0, "total": 0}


def check_progress_stall() -> tuple[bool, str]:
    """Check if progress has stalled. Returns (stalled, detail).

    Primary gate: compares current progress against last recorded.
    If no progress for STALL_THRESHOLD consecutive checks, session is stalled.
    """
    try:
        current = get_progress_snapshot()
        last = read_state("build_gate_last_progress", {"completed": 0, "total": 0})
        stall_count = read_state("build_gate_stall_count", 0)

        if current["completed"] > last.get("completed", 0):
            # Progress made — reset stall counter
            write_state("build_gate_last_progress", current)
            write_state("build_gate_stall_count", 0)
            return False, f"progress: {current['completed']}/{current['total']}"

        # No progress — increment stall counter
        stall_count += 1
        write_state("build_gate_stall_count", stall_count)
        write_state("build_gate_last_progress", current)

        if stall_count >= STALL_THRESHOLD:
            return True, f"stalled {stall_count} checks at {current['completed']}/{current['total']}"

        return False, f"no progress ({stall_count}/{STALL_THRESHOLD} stalls) at {current['completed']}/{current['total']}"
    except Exception:
        # Progress check failed — fall through to block counter
        return False, "progress check error — using fallback"


# --- Completion criteria checks ---

def check_tests_passing() -> tuple[bool, str]:
    """Check if last test run passed (set by agents via set_state)."""
    result = read_state("last_test_result", "unknown")
    if result == "fail":
        return False, "last test run FAILED — fix before exiting"
    # "pass" or "unknown" (no test run recorded) both allow exit
    return True, f"test result: {result}"


def check_features_complete() -> tuple[bool, str]:
    path = PROJECT_DIR / "features.json"
    if not path.exists():
        return True, "no features.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True, "unreadable features.json"
    features = data.get("features", [])
    if not features:
        return True, "empty features list"
    completed = sum(1 for f in features if f.get("status") == "completed")
    in_progress = sum(1 for f in features if f.get("status") == "in_progress")
    pending = sum(1 for f in features if f.get("status") == "pending")
    total = len(features)
    if completed == total:
        return True, f"{completed}/{total} features complete"
    return False, f"{completed}/{total} complete, {in_progress} in-progress, {pending} pending"


def check_deployment_prep_done() -> tuple[bool, str]:
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
    path = PROJECT_DIR / "qa-report.json"
    if not path.exists():
        return False, "qa-report.json does not exist yet"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "qa-report.json unreadable"
    # Only check critical_issues — the canonical QA gate field
    latest = data.get("latest", {})
    if isinstance(latest, dict):
        summary = latest.get("summary", {})
        if isinstance(summary, dict):
            critical = summary.get("critical_issues", [])
            if isinstance(critical, list) and len(critical) == 0:
                return True, "QA: 0 critical issues"
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


# --- Scope configuration ---

def get_scope() -> str:
    """Get build-lead scope. Determines exit criteria.

    build_only: exit when all features complete (skip QA/deploy checks)
    full: exit when features + QA + deployment-prep all complete
    """
    scope = os.environ.get("BUILD_LEAD_SCOPE", "")
    if not scope:
        scope = read_state("build_lead_scope", "")
    if not scope:
        # Check session_role — qa-lead sets this to "verify"
        role = read_state("session_role", "")
        if role == "verify":
            return "full"
    return scope or "full"  # Default to full for backwards compatibility


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

    scope = get_scope()

    # --- Check completion criteria based on scope ---
    features_ok, features_detail = check_features_complete()

    tests_ok, tests_detail = check_tests_passing()

    if scope == "build_only":
        # Build-only scope: check features + tests
        if features_ok and tests_ok:
            log_hook("build-gate", "lead", "ALLOW", f"scope=build_only | {features_detail} | {tests_detail}")
            json.dump({"decision": "allow"}, sys.stdout)
            return
    else:
        # Full scope: check all three conditions
        qa_ok, qa_detail = check_qa_passed()
        prep_ok, prep_detail = check_deployment_prep_done()

        if features_ok and tests_ok and qa_ok and prep_ok:
            log_hook("build-gate", "lead", "ALLOW", f"scope=full | {features_detail} | {tests_detail} | {qa_detail} | {prep_detail}")
            json.dump({"decision": "allow"}, sys.stdout)
            return

    # --- Not complete — check if we should force-allow via stall/safety valve ---

    # Primary: progress-based stall detection
    stalled, stall_detail = check_progress_stall()
    if stalled:
        log_hook("build-gate", "lead", "ALLOW", f"stalled | {stall_detail}")
        json.dump({"decision": "allow"}, sys.stdout)
        return

    # Fallback: block counter (safety net if progress check fails or is insufficient)
    block_count = get_block_count()
    if block_count >= MAX_BLOCKS:
        log_hook("build-gate", "lead", "ALLOW", f"fallback max blocks ({MAX_BLOCKS})")
        json.dump({"decision": "allow"}, sys.stdout)
        return

    # --- Block the exit ---
    count = increment_block_count()

    reasons = []
    if not features_ok:
        reasons.append(f"Features: {features_detail}")
    if not tests_ok:
        reasons.append(f"Tests: {tests_detail}")
    if scope != "build_only":
        if not qa_ok:
            reasons.append(f"QA: {qa_detail}")
        if not prep_ok:
            reasons.append(f"Deploy: {prep_detail}")
    reason_text = ". ".join(reasons)

    # Tailor directive to what's needed
    if not tests_ok:
        next_step = "Tests are FAILING. Run pytest -v and npm test, fix all failures, then call set_state(key='last_test_result', value='pass')."
    elif not features_ok:
        next_step = "Continue building features. Call get_next_feature() to find remaining work."
    elif scope != "build_only" and not qa_ok:
        next_step = (
            "Run: cat qa-report.json to check QA status. "
            "If QA agent is still running, wait and check again. "
            "After QA passes, spawn the deployment-prep agent."
        )
    elif scope != "build_only" and not prep_ok:
        next_step = (
            "QA has passed but deployment-prep has not run. "
            "Spawn the deployment-prep agent NOW."
        )
    else:
        next_step = "Check get_progress() for current status."

    directive = (
        f"Build not complete (scope={scope}, stall={stall_detail}). {reason_text}. "
        f"Do NOT exit. {next_step}"
    )

    log_hook("build-gate", "lead", "BLOCK", f"block #{count} | scope={scope} | {reason_text}")

    json.dump({
        "decision": "block",
        "reason": directive,
    }, sys.stdout)


if __name__ == "__main__":
    main()
