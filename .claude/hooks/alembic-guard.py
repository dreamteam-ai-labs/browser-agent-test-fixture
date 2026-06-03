#!/usr/bin/env python3
"""Alembic guard — blocks non-additive migrations.

PostToolUse hook on Bash(alembic *). After `alembic revision --autogenerate`,
reads the generated migration file and rejects DROP TABLE, DROP COLUMN,
or NOT NULL without DEFAULT — operations that break rollback safety.

v1 code must always work against v2 schema (additive-only migrations).
This is the load-bearing rule for revision recovery.

OBSOLESCENCE: Remove if Anthropic ships native Alembic migration validation
or if we move to a managed migration system. See Hook Dependency Watchlist.
"""
import glob
import json
import os
import re
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


# Simple destructive patterns — these must never appear in an additive migration.
# Two pattern classes:
#   - Direct op.<verb>() calls (Alembic's canonical destructive ops).
#   - Raw SQL DROP keywords anywhere in the file. Catches op.execute("DROP TABLE ..."),
#     op.execute(text("DROP TABLE ...")), connection.execute("DROP ..."), and any other
#     pattern that smuggles destructive DDL through a raw-SQL path. Alembic migrations
#     should never need raw destructive SQL — the op.<verb>() API covers every case.
#     False-positive rate is accepted (a comment containing "DROP TABLE" would trigger
#     a warning); false-negatives in destructive migrations are far costlier (silent
#     prod data loss). Case-insensitive (`(?i)`) because SQL is case-insensitive even
#     though convention is uppercase.
DESTRUCTIVE_PATTERNS = [
    (r"op\.drop_table\(", "DROP TABLE"),
    (r"op\.drop_column\(", "DROP COLUMN"),
    (r"op\.drop_index\(", "DROP INDEX"),
    (r"op\.drop_constraint\(", "DROP CONSTRAINT"),
    (r"(?i)\bDROP\s+TABLE\b", "raw SQL DROP TABLE (op.execute or similar)"),
    (r"(?i)\bDROP\s+COLUMN\b", "raw SQL DROP COLUMN (op.execute or similar)"),
    (r"(?i)\bDROP\s+INDEX\b", "raw SQL DROP INDEX (op.execute or similar)"),
    (r"(?i)\bDROP\s+CONSTRAINT\b", "raw SQL DROP CONSTRAINT (op.execute or similar)"),
]


def _find_balanced_call(content: str, start: int) -> str:
    """Return the text from `start` to the matching closing paren.

    Used to extract a full Column(...) or add_column(...) expression
    including arguments split across multiple lines.
    """
    depth = 0
    i = start
    n = len(content)
    # Advance to the opening paren
    while i < n and content[i] != "(":
        i += 1
    if i >= n:
        return ""
    start_paren = i
    depth = 1
    i += 1
    while i < n and depth > 0:
        ch = content[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    return content[start_paren:i]


def _check_nullable_without_default(content: str) -> int:
    """Count Column() calls that have nullable=False without server_default.

    Scans balanced parentheses across multi-line Column() expressions so that
    Black-formatted migrations don't produce false positives. Alembic
    autogenerate always wraps column definitions in Column(...), so matching
    that one pattern covers add_column, create_table, and alter_column cases.
    """
    violations = 0
    # Match Column( or sa.Column( — but use word boundary to avoid matching
    # substrings like "add_column" that happen to contain "Column"
    pattern = re.compile(r"(?<![\w.])(?:sa\.)?Column(?=\()")
    for match in pattern.finditer(content):
        call_text = _find_balanced_call(content, match.end())
        if not call_text:
            continue
        has_not_null = re.search(r"nullable\s*=\s*False", call_text) is not None
        has_default = (
            re.search(r"server_default\s*=", call_text) is not None
            or re.search(r"default\s*=", call_text) is not None
        )
        if has_not_null and not has_default:
            violations += 1
    return violations


def find_latest_migration() -> Path | None:
    """Find the most recently created Alembic migration file."""
    versions_dir = PROJECT_DIR / "alembic" / "versions"
    if not versions_dir.exists():
        return None
    migrations = sorted(
        versions_dir.glob("*.py"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return migrations[0] if migrations else None


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        event = {}

    agent_id = event.get("agent_id", "") or ""
    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only check after alembic revision commands
    if "alembic revision" not in command:
        return  # PostToolUse — no output needed for non-matching commands

    migration = find_latest_migration()
    if migration is None:
        log_hook("alembic-guard", agent_id or "unknown", "SKIP", "no migration file found")
        return

    content = migration.read_text(encoding="utf-8")
    violations = []

    for pattern, description in DESTRUCTIVE_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            violations.append(f"{description} ({len(matches)} occurrence(s))")

    # Multi-line-aware check for NOT NULL without server_default
    # Scans balanced Column() / add_column() expressions — handles Black formatting
    nullable_violations = _check_nullable_without_default(content)
    if nullable_violations:
        violations.append(f"NOT NULL without DEFAULT ({nullable_violations} occurrence(s))")

    if violations:
        detail = "; ".join(violations)
        log_hook("alembic-guard", agent_id or "unknown", "BLOCK", f"{migration.name}: {detail}")
        # PostToolUse can add context but can't block (only PreToolUse can deny).
        # Output a strong warning as additionalContext so the model sees it.
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"MIGRATION SAFETY VIOLATION in {migration.name}: {detail}. "
                    "Migrations MUST be additive only — no DROP TABLE, DROP COLUMN, "
                    "or NOT NULL without server_default. This breaks rollback safety "
                    "(v1 code must work against v2 schema). "
                    "Delete this migration and regenerate without destructive operations. "
                    "If you need to remove a column, leave it in the schema and stop using it."
                ),
            }
        }, sys.stdout)
        return

    log_hook("alembic-guard", agent_id or "unknown", "ALLOW", f"{migration.name}: additive only")


if __name__ == "__main__":
    main()
