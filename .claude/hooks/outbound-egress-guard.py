#!/usr/bin/env python3
"""Outbound-egress guard — blocks Bash commands targeting non-allowlisted hosts.

PreToolUse hook on Bash. Extracts URLs / host references from the command,
checks each against `.claude/egress-allowlist.json`, blocks the call if any
host is unlisted. Pairs with `sitecustomize.py` (intercepts Python network
libs) for Bash-level coverage of curl/wget/git clone/pip --index-url/npm
install patterns.

Threat model: agent honesty, not adversary. Honest failure modes:
- Agent helpfully `curl`s a URL operator gave in chat that turned out
  to be a typo'd attacker domain.
- Agent runs `pip install` against a typo-squat package name (PyPI itself
  is allowlisted; the package fetch still goes to files.pythonhosted.org
  via pip, which IS allowlisted — but a `--index-url https://attacker/`
  override would target an unlisted host and get blocked).
- Agent runs `git clone https://gitlab.attacker/...` thinking it's
  GitHub — blocked.

Allowlist matches by host SUFFIX so subdomains automatically inherit
(`github.com` covers `api.github.com`, `raw.github.com`, etc.). Hosts
listed in the canonical list are the only ones that pass. Override via
the `DREAMTEAM_ALLOW_UNLISTED_EGRESS=1` env var (matches the pattern from
protect-harness-paths.py + secrets-detection.py).

Allowlist config: `.claude/egress-allowlist.json`. Hot-editable.
Allowlist file itself is harness-protected against agent writes.

MISSING-ALLOWLIST POLICY (v0.8.10+): fail closed.
    Pre-v0.8.10 this hook failed OPEN when the allowlist file was missing
    — every Bash command was allowed with only a log warning. That made
    a render-glitch or filesystem-loss event silently disable the entire
    in-agent egress defense, leaving only the vps-daemon iptables floor.
    Now: missing allowlist → DENY (with the same escape env var honored
    for diagnostic bypass). Paired with `egress-allowlist-check.py`
    SessionStart hook which catches the same condition at session open.

OBSOLESCENCE: Remove if Anthropic ships native outbound-network policy
or if we move to a managed egress proxy. See Hook Dependency Watchlist.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
ALLOWLIST_PATH = PROJECT_DIR / ".claude" / "egress-allowlist.json"
ESCAPE_ENV = "DREAMTEAM_ALLOW_UNLISTED_EGRESS"

# Patterns that surface URLs / hosts in shell commands. We match generously
# and check each candidate against the allowlist; false positives are fine
# (a string that looks like a URL but isn't will simply pass the allowlist
# check or fail loudly). False negatives are the costly direction.
URL_RE = re.compile(r"\bhttps?://([A-Za-z0-9.\-]+)(?::\d+)?(?:/|\b)")
GIT_CLONE_RE = re.compile(r"\bgit\s+clone\s+(?:--[a-z\-]+\s+)*https?://([A-Za-z0-9.\-]+)")
PIP_INDEX_RE = re.compile(r"--index-url[=\s]+https?://([A-Za-z0-9.\-]+)")
PIP_EXTRA_INDEX_RE = re.compile(r"--extra-index-url[=\s]+https?://([A-Za-z0-9.\-]+)")
NPM_REGISTRY_RE = re.compile(r"--registry[=\s]+https?://([A-Za-z0-9.\-]+)")


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


def load_allowlist() -> list[str]:
    """Return the list of allowed host suffixes. Empty on read failure."""
    if not ALLOWLIST_PATH.is_file():
        return []
    try:
        data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    hosts = data.get("allowed_hosts", [])
    return [h for h in hosts if isinstance(h, str)]


def host_is_allowed(host: str, allowlist: list[str]) -> bool:
    """Return True if `host` is an exact match OR a subdomain of any allowlist entry.

    `host` is the parsed hostname (no port, no path). Allowlist entries can be
    bare hostnames (`github.com`); subdomains match by suffix.
    """
    host = host.lower().strip(".")
    for entry in allowlist:
        e = entry.lower().strip(".")
        if host == e or host.endswith("." + e):
            return True
    return False


def extract_hosts(command: str) -> list[str]:
    """Extract every host that the command would contact, deduped + ordered."""
    seen: list[str] = []
    seen_set: set[str] = set()

    def _add(h: str) -> None:
        h = h.lower()
        if h and h not in seen_set:
            seen_set.add(h)
            seen.append(h)

    for m in URL_RE.finditer(command):
        _add(m.group(1))
    # Specific patterns may catch things URL_RE missed (mid-flag URLs etc.)
    for pat in (GIT_CLONE_RE, PIP_INDEX_RE, PIP_EXTRA_INDEX_RE, NPM_REGISTRY_RE):
        for m in pat.finditer(command):
            _add(m.group(1))
    return seen


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
    tool_name = event.get("tool_name", "") or ""
    tool_input = event.get("tool_input", {}) or {}

    if tool_name != "Bash":
        _allow()
        return

    command = tool_input.get("command", "")
    if not command:
        _allow()
        return

    hosts = extract_hosts(command)
    if not hosts:
        _allow()
        return

    escape_set = os.environ.get(ESCAPE_ENV, "").strip() in ("1", "true", "True", "yes")

    allowlist = load_allowlist()
    if not allowlist:
        # No allowlist configured — FAIL CLOSED (v0.8.10+; was fail-open
        # pre-v0.8.10 and caused silent in-agent egress-defense loss
        # whenever the template-rendered allowlist file was missing).
        # Operator escape still honored so diagnostic / off-policy work
        # is not blocked.
        if escape_set:
            log_hook(
                "outbound-egress-guard", agent_id or "unknown",
                "ALLOW_NO_ALLOWLIST_VIA_ESCAPE",
                f"hosts=[{','.join(hosts)}] env={ESCAPE_ENV} — allowlist absent, escape bypass",
            )
            _allow()
            return
        log_hook(
            "outbound-egress-guard", agent_id or "unknown",
            "DENY_NO_ALLOWLIST",
            f"hosts=[{','.join(hosts)}] command={command[:120]} — egress-allowlist.json missing or unreadable",
        )
        _deny(
            f"Outbound egress denied: the egress allowlist file "
            f"(.claude/egress-allowlist.json) is missing or unreadable, "
            f"so no host can be approved. This usually means a template "
            f"render glitch or filesystem loss — restore the file from "
            f"templates (or run drift-apply). If this is intentional for "
            f"the current diagnostic, set {ESCAPE_ENV}=1 to bypass."
        )
        return

    unlisted = [h for h in hosts if not host_is_allowed(h, allowlist)]
    if not unlisted:
        _allow()
        return

    if escape_set:
        log_hook(
            "outbound-egress-guard", agent_id or "unknown", "ALLOW_VIA_ESCAPE",
            f"unlisted=[{','.join(unlisted)}] env={ESCAPE_ENV}",
        )
        _allow()
        return

    log_hook(
        "outbound-egress-guard", agent_id or "unknown", "DENY",
        f"unlisted_hosts=[{','.join(unlisted)}] command={command[:120]}",
    )
    _deny(
        f"Outbound egress to unlisted host(s): {', '.join(unlisted)}. "
        f"The egress allowlist (.claude/egress-allowlist.json) covers "
        f"approved domains (PyPI, npm, GitHub, Anthropic, etc.). "
        f"If this host is needed, edit the allowlist (operator action) "
        f"or set {ESCAPE_ENV}=1 to override after operator review."
    )


if __name__ == "__main__":
    main()
