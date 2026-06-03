#!/usr/bin/env python3
"""Secrets-detection hook — blocks Write/Edit content with high-confidence credentials.

PreToolUse hook on Write/Edit/MultiEdit/NotebookEdit. Scans the content
being written for high-confidence secret patterns (AWS access keys,
Anthropic API keys, OpenAI keys, GitHub PATs, Stripe keys, JWT tokens,
PEM private keys). Blocks the write with a structured deny reason.

Threat model: agent honesty, not adversary. The expected failure mode is:
- Agent pastes an example secret from documentation into code.
- Agent commits a test fixture with a real-looking secret string.
- Agent writes a value into .env that should have stayed in the secrets
  manager.

The .env file read is already blocked by `settings.json::permissions.deny`
(`Read(.env*)`), so the agent shouldn't have read a real secret in the
first place — but the WRITE path was unguarded. This closes that gap.

False-positive mitigations:
- Skip test fixtures: paths under `tests/`, `**/__tests__/**`, files
  ending `.test.{ts,tsx,js,jsx,py}` or `.spec.{ts,tsx,js,jsx,py}`.
- Skip documentation: paths under `docs/`.
- Skip placeholder-shaped values: matched-token contains `example`,
  `placeholder`, `your-key-here`, `xxxxx`, `redacted`, `change-me`.
- Skip `.env.example` (canonical placeholder file).
- Skip lines that are comments (`#` Python, `//` JS/TS, `/* */` C-style).

Escape hatch: `DREAMTEAM_ALLOW_INLINE_SECRET=1` overrides the block with
a logged ALLOW_VIA_ESCAPE entry. For the rare operator case (e.g.,
committing a documented public key, intentional ed25519 fingerprint).

OBSOLESCENCE: Remove if Anthropic ships native secrets-detection in the
permission system, or if we move to a managed secrets-scanner like
trufflehog/git-secrets in pre-commit. See Hook Dependency Watchlist in
memory/sync-status.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

ESCAPE_ENV = "DREAMTEAM_ALLOW_INLINE_SECRET"

# Path prefixes / suffixes that should be skipped (legitimate fixture/doc use).
SKIP_PATH_SEGMENTS = (
    "tests/",
    "/tests/",
    "__tests__/",
    "docs/",
    "/docs/",
)
SKIP_PATH_BASENAMES = (
    ".env.example",
)
SKIP_PATH_SUFFIXES = (
    ".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".test.py",
    ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx", ".spec.py",
)

# Placeholder substrings that flip a match from "real secret" to "obviously
# scaffolding". Case-insensitive substring check on the matched token.
PLACEHOLDER_MARKERS = (
    "example",
    "placeholder",
    "your-key",
    "your_key",
    "yourkey",
    "xxxx",
    "redacted",
    "change-me",
    "change_me",
    "changeme",
    "fake",
    "dummy",
    "sample",
)

# Patterns to detect — (name, regex, severity). Each pattern is calibrated
# for high-precision over high-recall: we'd rather miss exotic key formats
# than false-positive on every test fixture. Format choices follow the
# vendor's documented shape.
PATTERNS = [
    ("AWS Access Key ID",       re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Anthropic API Key",       re.compile(r"\bsk-ant-(?:api03|admin01)-[A-Za-z0-9_\-]{80,}\b")),
    ("OpenAI API Key",          re.compile(r"\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}\b")),
    ("GitHub Personal Token",   re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("GitHub Fine-Grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
    ("GitHub OAuth Token",      re.compile(r"\bgho_[A-Za-z0-9]{36}\b")),
    ("Stripe Live Secret Key",  re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b")),
    ("Stripe Test Secret Key",  re.compile(r"\bsk_test_[A-Za-z0-9]{24,}\b")),
    ("Slack Bot Token",         re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google Service Account Private Key", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    ("SSH Private Key",         re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----")),
    # JWT pattern — three base64url segments separated by dots. Length
    # threshold prevents matching trivial-looking placeholder strings.
    ("JWT-shaped Token",        re.compile(r"\beyJ[A-Za-z0-9_\-]{15,}\.[A-Za-z0-9_\-]{15,}\.[A-Za-z0-9_\-]{15,}\b")),
]


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


def _allow():
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }, sys.stdout)


def is_skipped_path(file_path: str) -> bool:
    """Return True for paths where secret-shaped strings are legitimate."""
    normalized = file_path.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    if basename in SKIP_PATH_BASENAMES:
        return True
    for seg in SKIP_PATH_SEGMENTS:
        if normalized.startswith(seg) or seg in normalized:
            return True
    for suf in SKIP_PATH_SUFFIXES:
        if basename.endswith(suf):
            return True
    return False


def looks_like_placeholder(match_text: str) -> bool:
    """Match shows obvious placeholder shape — don't flag."""
    lowered = match_text.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


# Comment-line detection — rough but effective for the common case where a
# documentation comment carries an example secret. We only check the START
# of the line; mid-line comments are accepted as best-effort.
_COMMENT_LINE_RE = re.compile(r"^\s*(?:#|//|/\*|\*)")


def find_secrets(content: str) -> list[tuple[str, str, int]]:
    """Return [(pattern_name, matched_text_excerpt, line_number)] for hits.

    Skips matches on placeholder-shaped tokens + matches on comment lines.
    Returns at most 5 hits to keep the deny reason short.
    """
    if not content:
        return []
    hits: list[tuple[str, str, int]] = []
    # Pre-split lines once for comment-line membership lookup.
    lines = content.splitlines()
    line_starts = [0]
    for line in lines:
        line_starts.append(line_starts[-1] + len(line) + 1)

    def offset_to_line(offset: int) -> tuple[int, str]:
        # Binary search would be faster but linear is fine for hook scale.
        for i in range(len(line_starts) - 1, -1, -1):
            if line_starts[i] <= offset:
                return i + 1, lines[i] if i < len(lines) else ""
        return 1, lines[0] if lines else ""

    for name, regex in PATTERNS:
        for m in regex.finditer(content):
            matched = m.group(0)
            if looks_like_placeholder(matched):
                continue
            lineno, line_text = offset_to_line(m.start())
            if _COMMENT_LINE_RE.match(line_text):
                continue
            # Excerpt: first 8 chars of the match + "..." so the rest doesn't
            # leak into logs or the deny reason. The agent already wrote it
            # client-side but our enforcement surface shouldn't echo it.
            excerpt = matched[:8] + "..." if len(matched) > 8 else matched
            hits.append((name, excerpt, lineno))
            if len(hits) >= 5:
                return hits
    return hits


def _extract_content(tool_name: str, tool_input: dict) -> str:
    """Pull written content from Write/Edit/MultiEdit/NotebookEdit inputs."""
    parts: list[str] = []
    if tool_name == "Write":
        content = tool_input.get("content", "")
        if isinstance(content, str):
            parts.append(content)
    elif tool_name in ("Edit", "MultiEdit"):
        new_string = tool_input.get("new_string", "")
        if isinstance(new_string, str):
            parts.append(new_string)
        # MultiEdit
        edits = tool_input.get("edits", [])
        if isinstance(edits, list):
            for edit in edits:
                if isinstance(edit, dict):
                    ns = edit.get("new_string", "")
                    if isinstance(ns, str):
                        parts.append(ns)
    elif tool_name == "NotebookEdit":
        new_source = tool_input.get("new_source", "")
        if isinstance(new_source, str):
            parts.append(new_source)
    return "\n".join(parts)


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        _allow()
        return

    agent_id = event.get("agent_id", "") or ""
    tool_name = event.get("tool_name", "") or ""
    tool_input = event.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")

    if not file_path:
        _allow()
        return
    if is_skipped_path(file_path):
        _allow()
        return

    content = _extract_content(tool_name, tool_input)
    if not content:
        _allow()
        return

    hits = find_secrets(content)
    if not hits:
        _allow()
        return

    # Escape hatch — operator-authorized override.
    if os.environ.get(ESCAPE_ENV, "").strip() in ("1", "true", "True", "yes"):
        details = ", ".join(f"{name} @ line {line}" for name, _excerpt, line in hits)
        log_hook("secrets-detection", agent_id or "unknown", "ALLOW_VIA_ESCAPE",
                 f"path={file_path} matches=[{details}] env={ESCAPE_ENV}")
        _allow()
        return

    detail_str = "; ".join(f"{name} at line {line} (starts {excerpt!r})" for name, excerpt, line in hits)
    log_hook("secrets-detection", agent_id or "unknown", "DENY",
             f"path={file_path} matches=[{detail_str}]")

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Inline secret detected in write to {file_path}: {detail_str}. "
                f"Move the value to an environment variable (read via os.getenv) "
                f"or a secrets manager. Test fixtures should use clearly-fake "
                f"placeholder strings (containing 'example', 'placeholder', "
                f"'fake', etc.). If this match is a known false-positive, "
                f"set {ESCAPE_ENV}=1 to override after operator review."
            ),
        }
    }, sys.stdout)


if __name__ == "__main__":
    main()
