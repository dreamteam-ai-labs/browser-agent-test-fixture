#!/usr/bin/env python3
"""Egress allowlist startup check — fails session-start visibly if the
allowlist file is missing, unparseable, or empty.

WHY THIS HOOK EXISTS
--------------------
`outbound-egress-guard.py` is the per-Bash-command PreToolUse hook that
denies outbound traffic to non-allowlisted hosts. It reads its allowlist
from `.claude/egress-allowlist.json`. Pre-v0.8.10, when the allowlist
file was missing, the guard failed open — every Bash command was allowed
with only a log warning, because the guard treated "no allowlist" as
"no policy" and permitted everything.

That failure mode was silent (no error, no prompt, no visible failure),
so any partially-scaffolded project where the template render glitched
or where the allowlist file was lost would lose its primary in-agent
egress defense without anyone noticing. The harness-protection hook
also protects `.claude/`, so an agent could not repair the file even
if it tried.

WHAT THIS HOOK DOES
-------------------
At every SessionStart, verify the allowlist file:
  1. exists and is readable
  2. parses as JSON
  3. has a non-empty `allowed_hosts` list

If any check fails, exit non-zero with a clear stderr message so the
operator sees the failure immediately rather than discovering it
post-incident via journald.

Escape hatch — `DREAMTEAM_ALLOW_UNLISTED_EGRESS=1` (same env var the
guard honors) — bypasses the check entirely. If the operator has
intentionally disabled the egress policy for diagnostic purposes, the
SessionStart check should not fight that decision.

LAYERS OF DEFENCE
-----------------
This hook is layer 1: visible startup failure. The matching layer 2 is
inside `outbound-egress-guard.py`'s `main()` — same missing-allowlist
condition there now DENIES instead of ALLOWS (was ALLOW pre-v0.8.10).
Either layer alone is sufficient; both together catch the case where
the SessionStart hook itself fails silently (e.g. crashed before this
file existed in a partially-upgraded project).

OBSOLESCENCE: Remove if Anthropic ships native outbound-network policy
or if we move to a managed egress proxy. See Hook Dependency Watchlist.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
ALLOWLIST_PATH = PROJECT_DIR / ".claude" / "egress-allowlist.json"
ESCAPE_ENV = "DREAMTEAM_ALLOW_UNLISTED_EGRESS"


def _print_error(msg: str) -> None:
    print(f"[egress-allowlist-check] {msg}", file=sys.stderr)


def main() -> int:
    if os.environ.get(ESCAPE_ENV, "").strip() in ("1", "true", "True", "yes"):
        _print_error(
            f"egress policy bypassed via {ESCAPE_ENV} — startup check skipped"
        )
        return 0

    if not ALLOWLIST_PATH.is_file():
        _print_error(
            f"FAIL: egress allowlist file missing at {ALLOWLIST_PATH}. "
            f"This file is a template-rendered artifact and is required "
            f"by outbound-egress-guard.py. Without it, outbound network "
            f"enforcement is OFF in this project. Restore the file from "
            f"templates (or run drift-apply), then re-open the session."
        )
        return 1

    try:
        data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _print_error(
            f"FAIL: egress allowlist at {ALLOWLIST_PATH} could not be "
            f"parsed: {exc}. Fix the file or restore from templates."
        )
        return 1

    hosts = data.get("allowed_hosts", [])
    if not isinstance(hosts, list) or not any(isinstance(h, str) and h for h in hosts):
        _print_error(
            f"FAIL: egress allowlist at {ALLOWLIST_PATH} has no "
            f"`allowed_hosts` entries. An empty allowlist would deny "
            f"every outbound call. If this is intentional for the "
            f"current project, set {ESCAPE_ENV}=1 to bypass enforcement."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
