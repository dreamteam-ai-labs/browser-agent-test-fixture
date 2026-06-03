#!/usr/bin/env python3
"""wrapper-env-contract.py — qa-tester-time deterministic check for OSS T1/T2 wrapper env-vars.

Verifies every key declared in `.dreamteam/provisioning-result.json::wrapper_env` is read
verbatim by the wrapper code. Catches the R19/R20 incident pattern: factory injects
`MAILHOG_HTTP_URL` onto the wrapper deployment, wrapper code reads `os.getenv("MAILHOG_API_URL")`
(invented near-miss name), upstream stays unreachable, service reports degraded.

Skips silently when:
- `.dreamteam/provisioning-result.json` does not exist (non-OSS service)
- `wrapper_env` is empty or absent (T0 / non-OSS topology)

Fails (exit 1) when:
- A wrapper_env key is declared but no os.getenv/os.environ access in src/ reads it,
  AND the code DOES read a near-miss name sharing the same prefix that is NOT in wrapper_env.
  This catches the inversion (declared X_HTTP_URL, code reads X_API_URL).

Does NOT fail when:
- A wrapper_env key is unread by the code with no near-miss read either — the wrapper may
  legitimately not consume that key (alternative: the wrapper is partial and another key
  is unused; we only flag the suspicion-of-rename pattern).

Layered defence with build-lead.md.mustache R20 prose (templates v0.6.8): the prompt instructs
the agent to read wrapper_env keys verbatim; this hook deterministically verifies it actually
happened. Prompt-only enforcement gets bypassed when the agent invents a name despite the
prompt; this check fires at qa-tester Stop and blocks exit.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Hook lives at .claude/hooks/<this>.py, repo root is two parents up.
SCAFFOLD_ROOT = Path(__file__).resolve().parents[2]
PROV_RESULT = SCAFFOLD_ROOT / ".dreamteam" / "provisioning-result.json"
SRC_ROOT = SCAFFOLD_ROOT / "src"

# Match os.getenv("X"), os.environ.get("X"), and os.environ["X"] / os.environ['X'].
ENV_READ_RE = re.compile(
    r"""os\.(?:getenv|environ\.get)\s*\(\s*["']([A-Z_][A-Z0-9_]*)["']"""
    r"""|os\.environ\s*\[\s*["']([A-Z_][A-Z0-9_]*)["']\s*\]""",
)


def collect_env_reads(src_root: Path) -> set[str]:
    names: set[str] = set()
    if not src_root.is_dir():
        return names
    for py in src_root.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for getenv_name, environ_name in ENV_READ_RE.findall(text):
            names.add(getenv_name or environ_name)
    return names


def find_violations(wrapper_env_keys: set[str], env_reads: set[str]) -> list[dict]:
    """Return list of suspected rename violations.

    A violation: a wrapper_env key is declared, the code does NOT read it, BUT the code
    reads a name sharing the same first-token prefix that is also NOT in wrapper_env.
    """
    violations: list[dict] = []
    for declared in sorted(wrapper_env_keys):
        if declared in env_reads:
            continue
        prefix = declared.split("_", 1)[0]
        near_misses = sorted(
            n for n in env_reads
            if n != declared and n.startswith(prefix + "_") and n not in wrapper_env_keys
        )
        if near_misses:
            violations.append({"declared": declared, "near_misses": near_misses})
    return violations


def main() -> int:
    if not PROV_RESULT.is_file():
        return 0
    try:
        data = json.loads(PROV_RESULT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        # Soft fail — don't block QA on a corrupt sidecar; the lifecycle layer owns repair.
        print(f"wrapper-env-contract: provisioning-result.json unreadable ({e}) — skipping check", file=sys.stderr)
        return 0
    wrapper_env = data.get("wrapper_env") or {}
    if not isinstance(wrapper_env, dict) or not wrapper_env:
        return 0
    keys = set(wrapper_env.keys())
    env_reads = collect_env_reads(SRC_ROOT)
    violations = find_violations(keys, env_reads)
    if not violations:
        return 0

    print("wrapper-env-contract VIOLATION (R19/R20 incident pattern)", file=sys.stderr)
    print("", file=sys.stderr)
    print("  .dreamteam/provisioning-result.json declares wrapper_env keys that the", file=sys.stderr)
    print("  wrapper code does not read verbatim. The code reads near-miss names that", file=sys.stderr)
    print("  are NOT in wrapper_env — the factory injected the canonical name onto the", file=sys.stderr)
    print("  deployment but os.getenv/os.environ will return None at runtime.", file=sys.stderr)
    print("", file=sys.stderr)
    for v in violations:
        print(f"  - declared in wrapper_env: {v['declared']!r}", file=sys.stderr)
        print(f"    found in src/ instead:    {', '.join(repr(n) for n in v['near_misses'])}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Fix: rename the os.getenv / os.environ calls in src/ to use the wrapper_env", file=sys.stderr)
    print("  keys verbatim. The recipe + provisioning-result.json are the contract; the", file=sys.stderr)
    print("  wrapper conforms.", file=sys.stderr)
    print("", file=sys.stderr)
    print("  See build-lead.md.mustache OSS Wrapper Env-Var Contract section + the R20", file=sys.stderr)
    print("  contract tests in oss-agent-prompts-contract.test.js for the prompt-side", file=sys.stderr)
    print("  layer. This hook is the deterministic enforcement that catches bypasses.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
