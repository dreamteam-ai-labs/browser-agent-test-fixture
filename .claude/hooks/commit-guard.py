#!/usr/bin/env python3
"""Commit guard — rejects placeholder commit messages and test-only rework commits.

PreToolUse hook on Bash(git commit). Two checks:
1. Placeholder patterns that break factory loop git history parsing.
2. In rework mode: fix: commits must include production code changes,
   not just test files. Run 11 showed a builder writing tests without
   fixing the actual bugs.

OBSOLESCENCE: Remove if Anthropic ships native commit message validation
in agent frontmatter. See Hook Dependency Watchlist.
"""
import json
import os
import re
import subprocess
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
        pass


# Patterns that indicate a placeholder commit message
PLACEHOLDER_PATTERNS = [
    r"<feature[- _]?name>",
    r"<actual[- _]?feature>",
    r"\[feature[- _]?name\]",
    r"\[actual[- _]?name\]",
    r"implement \[",
    r"implement <",
    r"feat: implement$",       # bare "feat: implement" with nothing after
]


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "") or ""
    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only check git commit commands
    if "git commit" not in command:
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    # Extract the commit message from one of: -m "msg", -F file, heredoc
    message = None

    # 1. -m "msg" or -m 'msg' — match opening and closing quotes via backreference
    # so that inner quotes (e.g. heredoc 'EOF' inside "$(cat <<'EOF'...)") don't
    # prematurely close the match. Inner-char class is escape-aware: either
    # `\\.` (backslash + any char = escape sequence) or `(?!\1).` (any char that
    # is NOT the closing quote). This makes `-m "hello \"world\""` parse to
    # `hello \"world\"` instead of terminating at the first inner `\"`.
    msg_match = re.search(r"""-m\s+(["'])((?:\\.|(?!\1).)*)\1""", command, re.DOTALL)
    if msg_match:
        message = msg_match.group(2)

    # 2. -F <file> or --file=<file> — read the message file
    if message is None:
        file_match = re.search(r"(?:-F\s+|--file=)(\S+)", command)
        if file_match:
            msg_path = file_match.group(1).strip('"\'')
            try:
                with open(msg_path, encoding="utf-8") as f:
                    message = f.read()
            except OSError:
                pass  # Can't read file, fall through to heredoc check

    # 3. Heredoc — `git commit <<'EOF' ... EOF` or `<<EOF ... EOF`
    # Capture everything between <<MARKER and MARKER on its own line
    if message is None:
        heredoc_match = re.search(
            r"<<-?\s*['\"]?(\w+)['\"]?\s*\n(.*?)\n\s*\1\s*(?:\n|$)",
            command,
            re.DOTALL,
        )
        if heredoc_match:
            message = heredoc_match.group(2)

    # 4. $(cat <<'EOF' ... EOF) pattern used by some tools — cheap fallback
    if message is None:
        cat_heredoc = re.search(
            r"\$\(cat\s+<<-?\s*['\"]?(\w+)['\"]?\s*\n(.*?)\n\s*\1\s*\)",
            command,
            re.DOTALL,
        )
        if cat_heredoc:
            message = cat_heredoc.group(2)

    if message is None:
        # Can't parse message by any known pattern — allow with log
        log_hook("commit-guard", agent_id or "unknown", "ALLOW_UNPARSED", command[:80])
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }, sys.stdout)
        return

    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            log_hook("commit-guard", agent_id or "unknown", "BLOCK", f"placeholder: {message[:80]}")
            json.dump({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Commit message contains a placeholder: '{message[:80]}'. "
                        "Use the REAL feature name (e.g., 'feat: implement expenses-crud')."
                    ),
                }
            }, sys.stdout)
            return

    # --- Rework mode: fix: commits must touch production code, not just tests ---
    if (
        (PROJECT_DIR / "rework.json").exists()
        and message.strip().lower().startswith("fix:")
    ):
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True, text=True, timeout=5,
                cwd=str(PROJECT_DIR),
            )
            staged = result.stdout.strip().splitlines() if result.stdout.strip() else []
            has_source = any(
                f.startswith("src/") or f.startswith("frontend/src/")
                for f in staged
            )
            if staged and not has_source:
                log_hook("commit-guard", agent_id or "unknown", "BLOCK", f"rework test-only: {staged}")
                json.dump({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            "BLOCKED: This rework fix: commit only contains test files. "
                            "Rework items require production code changes (src/ or frontend/src/). "
                            "Fix the source code first, then commit both the fix and the test together."
                        ),
                    }
                }, sys.stdout)
                return
        except (subprocess.TimeoutExpired, OSError):
            pass  # Can't check staged files — allow and let the build gate catch it

    log_hook("commit-guard", agent_id or "unknown", "ALLOW", f"msg: {message[:80]}")
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }, sys.stdout)


if __name__ == "__main__":
    main()
