#!/usr/bin/env python3
"""Path guard hook — enforces file path restrictions per agent role.

Reads hook event JSON from stdin. Uses agent_id to determine which
directories the agent is allowed to write to. Returns JSON decision.

OUTPUT FORMAT — PreToolUse contract (see code.claude.com/docs/en/hooks):
    PreToolUse hooks MUST emit `hookSpecificOutput.permissionDecision`
    (allow/deny/ask/defer), NOT the top-level `decision` key used by
    PostToolUse/Stop/UserPromptSubmit. Pre-v0.8.10 versions of this file
    emitted top-level `decision` and were silently inoperative — Claude
    Code parsed the JSON, found no recognised key, and treated the call
    as "no decision" (= permit). DO NOT regress.

OBSOLESCENCE: Remove when Anthropic ships native allowedPaths in
agent frontmatter. See Hook Dependency Watchlist in memory/sync-status.md.

Agent rules:
  backend-builder:  allow src/, tests/ — deny frontend/
  frontend-builder: allow frontend/ — deny src/, tests/
  qa-tester:        deny all writes (defense-in-depth)
  doctor:           allow src/, tests/, pyproject.toml — deny lifecycle-owned
                    paths (features.json, .dreamteam/, .claude/, Dockerfile,
                    start.sh, frontend/). v1 rules; denied_touches.ALLOWLIST
                    integration deferred until first concrete entry surfaces.

LEAD SESSION (no matching AGENT_RULES entry — e.g. empty agent_id, build-lead,
qa-lead, architect, or any custom role): match_agent() returns None →
allow-everything fallback. This is INTENTIONAL: the lead session is the
operator-supervised orchestrator, not a delegated teammate. Restricting lead
would break legitimate workflow steps (cross-file refactors, deployment-prep
edits spanning many paths, architecture changes touching configs). The
defense-in-depth backstop for lead is `protect-harness-paths.py`, which runs
FIRST in the same PreToolUse chain and gates `.claude/`, `.git/`, `.vscode/`,
shell-config writes regardless of agent_id. So lead can edit src/, tests/,
frontend/, pyproject.toml, etc. freely, but cannot mutate harness state.

Trust model: gates enforce agent honesty (forcing function so honest agents
don't take shortcuts), not adversarial defense. The protect-harness-paths
hook is the only adversarial-grade gate.
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


# Agent path rules: {agent_id_pattern: {"allow": [...], "deny": [...]}}
AGENT_RULES = {
    "backend-builder": {
        "allow": ["src/", "tests/", "pyproject.toml", "alembic/"],
        "deny": ["frontend/", "src/fixture/db_models.py"],
    },
    "frontend-builder": {
        "allow": ["frontend/"],
        "deny": ["src/", "tests/", "alembic/"],
    },
    "qa-tester": {
        "allow": ["qa-report.json", "qa-smoke-results.json"],
        "deny": ["src/", "tests/", "frontend/"],
    },
    "architect": {
        # architect emits architecture.json only; lane-separation from
        # features.json (owned by features-json-dev / canonicaliser CI gate)
        # is enforced here so it doesn't depend solely on the prose rule
        # at architect.md.mustache:195. Sibling concern: a future
        # architecture-schema-guard.py PostToolUse hook would catch
        # non-schema EXTRA fields in architecture.json (co-design with
        # features-json-dev — separate addition, not blocking this rule).
        "allow": ["architecture.json"],
        "deny": ["features.json", "src/", "tests/", "frontend/", ".dreamteam/"],
    },
    "deployment-prep": {
        "allow": [
            "pyproject.toml",
            "frontend/next.config.mjs",
            "frontend/next.config.js",
            "frontend/src/app/page.tsx",
            "README.md",
            ".gitignore",
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
        ],
        "deny": ["src/", "tests/", "frontend/src/components/", "frontend/src/lib/",
                 "frontend/src/app/api/", "alembic/"],
    },
    "doctor": {
        # Doctor mode: autonomous fix path for failed drift-apply quality gates.
        # Per dreamteam/memory/project_doctor_mode_design.md §2 path-guard scope.
        # v1 rules: src/, tests/, pyproject.toml allowed; lifecycle-owned paths
        # denied. denied_touches.ALLOWLIST/DENYLIST dynamic integration deferred
        # until first concrete entry surfaces.
        "allow": ["src/", "tests/", "pyproject.toml"],
        "deny": [
            "features.json",       # lifecycle invariant — only mutable via amendment
            ".dreamteam/",         # scaffold metadata
            ".claude/",            # agent prompts, RA's lane
            "Dockerfile",          # template-rendered, drift-apply's job
            "start.sh",            # template-rendered, drift-apply's job
            "frontend/",           # different lane
        ],
    },
}


def get_file_path(event: dict) -> str | None:
    """Extract the file path from the hook event."""
    tool_input = event.get("tool_input", {})
    # Write/Edit/MultiEdit all use file_path
    return tool_input.get("file_path") or tool_input.get("path")


def match_agent(agent_id: str) -> dict | None:
    """Find matching rules for the agent. Matches by substring."""
    if not agent_id:
        return None
    for pattern, rules in AGENT_RULES.items():
        if pattern in agent_id.lower():
            return rules
    return None


def check_path(file_path: str, rules: dict) -> tuple[bool, str]:
    """Check if the file path is allowed by the rules.

    Returns (allowed, reason).
    """
    # Normalize path separators
    normalized = file_path.replace("\\", "/")

    # Check deny list first
    for denied in rules.get("deny", []):
        if normalized.startswith(denied) or f"/{denied}" in normalized:
            return False, f"Path '{normalized}' is in denied area '{denied}' for this agent"

    # If there's an allow list, path must match at least one entry
    allow_list = rules.get("allow", [])
    if allow_list:
        for allowed in allow_list:
            if normalized.startswith(allowed) or f"/{allowed}" in normalized:
                return True, "Path is in allowed area"
        return False, f"Path '{normalized}' is not in any allowed area for this agent"

    return True, "No restrictions"


def _allow():
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }, sys.stdout)


def _deny(reason: str):
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # Can't parse input — allow by default (don't block on hook errors)
        _allow()
        return

    agent_id = event.get("agent_id", "") or ""
    rules = match_agent(agent_id)

    if rules is None:
        # Unknown agent or lead — allow everything
        _allow()
        return

    file_path = get_file_path(event)
    if not file_path:
        # No file path in event — allow (might be a non-file tool)
        _allow()
        return

    allowed, reason = check_path(file_path, rules)
    if allowed:
        log_hook("path-guard", agent_id, "ALLOW", f"path={file_path}")
        _allow()
    else:
        log_hook("path-guard", agent_id, "DENY", f"path={file_path}")
        _deny(reason)


if __name__ == "__main__":
    main()
