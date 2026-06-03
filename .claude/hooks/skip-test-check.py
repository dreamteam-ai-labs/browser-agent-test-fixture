#!/usr/bin/env python3
"""Skip-test check — warns when complete_feature is called but tests were skipped.

PostToolUse hook. Fires on all MCP tool calls, filters for complete_feature.
When an agent claims tests_pass:true, scans test files for skip markers
(skipTest, @pytest.mark.skip, @unittest.skip). If found, emits a WARNING
(non-blocking) so the agent reconsiders whether skipped tests are legitimate.

Conservative by design — warns, never blocks. Promote to block after
observing false-positive rate across builds.
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

SKIP_PATTERNS = re.compile(
    r"""(?:"""
    r"""self\.skipTest\s*\("""           # unittest skipTest
    r"""|@pytest\.mark\.skip"""          # pytest skip/skipif
    r"""|@unittest\.skip"""              # unittest skip decorator
    r"""|pytest\.skip\s*\("""            # inline pytest.skip()
    r""")""",
    re.MULTILINE,
)


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


def _ok_output() -> None:
    json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse"}}, sys.stdout)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        _ok_output()
        return

    tool_name = event.get("tool_name", "") or ""
    agent_id = event.get("agent_id", "") or ""
    tool_input = event.get("tool_input", {}) or {}

    # Only check complete_feature calls (MCP tool name includes server prefix)
    if "complete_feature" not in tool_name:
        _ok_output()
        return

    # Only warn when agent claims tests pass
    if not tool_input.get("tests_pass", True):
        _ok_output()
        return

    # Scan test directories for skip markers
    skip_files: list[str] = []
    for test_dir in ("tests", "tests/", "frontend/src"):
        search_dir = PROJECT_DIR / test_dir
        if not search_dir.is_dir():
            continue
        for root, _dirs, files in os.walk(search_dir):
            for fname in files:
                if not (fname.startswith("test_") or fname.endswith(("_test.py", ".test.ts", ".test.tsx", ".test.js"))):
                    continue
                fpath = Path(root) / fname
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if SKIP_PATTERNS.search(content):
                    rel = str(fpath.relative_to(PROJECT_DIR)).replace("\\", "/")
                    skip_files.append(rel)

    if not skip_files:
        log_hook("skip-test-check", agent_id or "unknown", "OK", f"feature={tool_input.get('id', '?')}")
        _ok_output()
        return

    file_list = ", ".join(skip_files[:5])
    if len(skip_files) > 5:
        file_list += f" (+{len(skip_files) - 5} more)"

    msg = (
        f"WARNING: {len(skip_files)} test file(s) contain skip markers: {file_list}. "
        f"You claimed tests_pass=true — verify these skips are intentional and not "
        f"masking failures. If a test was changed from an assertion to a skip, that "
        f"is likely a weakened test. Re-run the full test suite and confirm all "
        f"critical assertions are still present."
    )
    log_hook("skip-test-check", agent_id or "unknown", "WARN", msg[:200])
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        }
    }, sys.stdout)


if __name__ == "__main__":
    main()
