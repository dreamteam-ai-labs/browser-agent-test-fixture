#!/usr/bin/env python3
"""Protect harness paths hook — blocks agent writes to harness infrastructure.

CC 2.1.126 broadened `--dangerously-skip-permissions` to bypass prompts for
writes to `.claude/`, `.git/`, `.vscode/`, and shell config files. The DT
factory uses that flag for headless builds. Without this hook, an agent can
silently mutate harness state mid-build (settings.json, hooks, agents,
.mcp.json) with no prompt and no audit trail.

This hook denies PreToolUse on Write/Edit/MultiEdit/NotebookEdit when the
target file lives under any protected path. Carve-out: `.claude/state/**`
is allowed for ephemeral runtime state. Escape hatch: set
`DREAMTEAM_ALLOW_HARNESS_MUTATION=1` for the rare legitimate operator case.

OUTPUT FORMAT — PreToolUse contract (see code.claude.com/docs/en/hooks):
    PreToolUse hooks MUST emit `hookSpecificOutput.permissionDecision`
    (allow/deny/ask/defer), NOT the top-level `decision` key used by
    PostToolUse/Stop/UserPromptSubmit. Pre-v0.8.10 versions of this file
    emitted top-level `decision` and were silently inoperative — Claude
    Code parsed the JSON, found no recognised key, and treated the call
    as "no decision" (= permit). The harness backstop was off. DO NOT
    regress.

OBSOLESCENCE: Remove when CC reverts the 2.1.126 default-permission scope
shift, OR when CC ships native protected-path policy that can be configured
to deny without an interactive prompt.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

# Protected path prefixes (matched against normalized forward-slash paths).
# Order is informational only — first match wins for the deny reason.
PROTECTED_PREFIXES = (
    ".claude/",
    ".git/",
    ".vscode/",
)

# Carve-outs inside protected prefixes — legitimate ephemeral writes.
CARVE_OUTS = (
    ".claude/state/",
)

# Shell config files (matched against basename or trailing-segment).
PROTECTED_SHELL_FILES = (
    ".bashrc",
    ".bash_profile",
    ".bash_logout",
    ".zshrc",
    ".zprofile",
    ".profile",
)

ESCAPE_ENV = "DREAMTEAM_ALLOW_HARNESS_MUTATION"


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


def get_file_path(event: dict) -> str | None:
    tool_input = event.get("tool_input", {})
    return tool_input.get("file_path") or tool_input.get("path")


def normalize(file_path: str) -> str:
    """Normalize to forward slashes and strip leading ./ for prefix matching.

    Absolute paths are made project-relative when possible so the same prefix
    rules catch both `Edit('.claude/settings.json')` and
    `Edit('/workspaces/proj/.claude/settings.json')`.
    """
    p = file_path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    try:
        project_root = str(PROJECT_DIR.resolve()).replace("\\", "/").rstrip("/") + "/"
        if p.startswith(project_root):
            p = p[len(project_root):]
    except OSError:
        pass
    return p


def is_protected(file_path: str) -> tuple[bool, str]:
    """Return (protected, matched_prefix_or_file)."""
    norm = normalize(file_path)

    for carve in CARVE_OUTS:
        if norm.startswith(carve) or f"/{carve}" in norm:
            return False, ""

    for prefix in PROTECTED_PREFIXES:
        if norm.startswith(prefix) or f"/{prefix}" in norm:
            return True, prefix

    basename = norm.rsplit("/", 1)[-1]
    if basename in PROTECTED_SHELL_FILES:
        return True, basename

    return False, ""


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
        _allow()
        return

    agent_id = event.get("agent_id", "") or ""
    file_path = get_file_path(event)
    if not file_path:
        _allow()
        return

    protected, matched = is_protected(file_path)
    if not protected:
        _allow()
        return

    if os.environ.get(ESCAPE_ENV, "").strip() in ("1", "true", "True", "yes"):
        log_hook(
            "protect-harness-paths",
            agent_id,
            "ALLOW_VIA_ESCAPE",
            f"path={file_path} matched={matched} env={ESCAPE_ENV}",
        )
        _allow()
        return

    log_hook("protect-harness-paths", agent_id, "DENY", f"path={file_path} matched={matched}")
    reason = (
        f"Protected harness path: '{file_path}' (matched '{matched}'). "
        f"Agents must not mutate harness/build infrastructure mid-run. "
        f"If this write is intentional, escalate to operator — "
        f"set {ESCAPE_ENV}=1 to override."
    )
    _deny(reason)


if __name__ == "__main__":
    main()
