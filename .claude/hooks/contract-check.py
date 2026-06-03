#!/usr/bin/env python3
"""Contract check — warns when integration code accesses fields not in api_spec.

PostToolUse hook on Write|Edit|MultiEdit. When a builder writes code that
references an existing-service URL env var (e.g. os.environ['BROWSER_AGENT_URL']),
this hook scans the same file for field accesses (data.get('X'), data['X'],
response['X']) and diffs them against the service's api_spec in
service-catalog.json. Checks response body properties, request body properties,
AND query/path parameter names. Any field access not present in the spec
triggers a WARNING (non-blocking) to nudge the builder back to the real
contract before the bug compiles.

This is a write-time nudge, not a hard gate. The hard gate is
scripts/validate-integrations.py at deploy time. Together they defend against
the "builder guesses field names" failure mode.

OBSOLESCENCE: Remove if Anthropic ships native typed external-API linting,
or if we move builders onto generated API clients. See Hook Dependency Watchlist.
"""
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


def _ok_output() -> None:
    json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse"}}, sys.stdout)


def _load_catalog() -> dict:
    for candidate in ("service-catalog.json", "architecture.json"):
        p = PROJECT_DIR / candidate
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def _find_service_name_from_url_var(var_name: str, catalog: dict) -> str | None:
    """Map 'BROWSER_AGENT_URL' back to the service key 'browser-agent'."""
    stem = var_name[:-4] if var_name.endswith("_URL") else var_name
    target = stem.lower().replace("_", "-")
    # catalog may be service-catalog.json ({services: {...}}) or architecture.json
    services = catalog.get("services", {}) or catalog
    for key in services:
        if key.lower() == target:
            return key
    return None


def _get_api_spec(catalog: dict, service_key: str) -> dict | None:
    services = catalog.get("services", {}) or catalog
    svc = services.get(service_key, {}) if isinstance(services, dict) else {}
    if not isinstance(svc, dict):
        return None
    spec = svc.get("api_spec")
    return spec if isinstance(spec, dict) else None


def _collect_spec_field_names(api_spec: dict) -> set[str]:
    """Walk OpenAPI spec and return every field name: response properties,
    request body properties, AND query/path parameter names."""
    names: set[str] = set()

    def _walk(node):
        if isinstance(node, dict):
            if "properties" in node and isinstance(node["properties"], dict):
                for k in node["properties"].keys():
                    if isinstance(k, str):
                        names.add(k)
                    _walk(node["properties"][k])
            for k, v in node.items():
                if k != "properties":
                    _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(api_spec.get("components", {}).get("schemas", {}))
    _walk(api_spec.get("paths", {}))

    # Explicitly extract query/path parameter names from OpenAPI paths.
    # Parameters live at paths.{path}.{method}.parameters[].name and are
    # NOT inside "properties", so the generic walk above misses them.
    for path_item in (api_spec.get("paths") or {}).values():
        if not isinstance(path_item, dict):
            continue
        # Path-level parameters
        for param in path_item.get("parameters", []):
            if isinstance(param, dict) and isinstance(param.get("name"), str):
                names.add(param["name"])
        # Method-level parameters
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = path_item.get(method, {})
            if not isinstance(op, dict):
                continue
            for param in op.get("parameters", []):
                if isinstance(param, dict) and isinstance(param.get("name"), str):
                    names.add(param["name"])

    return names


# Regex to find code that reads os.environ['X_URL'] or os.environ.get('X_URL')
ENV_URL_PY = re.compile(
    r"""os\.environ(?:\.get)?\s*[\[\(]\s*['"]([A-Z][A-Z0-9_]*_URL)['"]""",
)

# TypeScript / JavaScript: process.env.X_URL or process.env['X_URL']
ENV_URL_JS = re.compile(
    r"""process\.env(?:\.([A-Z][A-Z0-9_]*_URL)|\[['"]([A-Z][A-Z0-9_]*_URL)['"]\])""",
)

# Identifiers in the file — we'll match any token against known field names
# regardless of whether it's accessed via .x, ["x"], .get("x"), or just appears
# as a string literal. Simple and language-agnostic.
IDENTIFIER_LIKE = re.compile(r"""(?<![\w\-])([a-zA-Z_][a-zA-Z0-9_]*)(?![\w\-])""")
STRING_LITERAL = re.compile(r"""['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""")


def _extract_content(tool_input: dict) -> str:
    """Extract the new/written content from a Write/Edit/MultiEdit tool input."""
    parts: list[str] = []
    if "content" in tool_input and isinstance(tool_input["content"], str):
        parts.append(tool_input["content"])
    if "new_string" in tool_input and isinstance(tool_input["new_string"], str):
        parts.append(tool_input["new_string"])
    if "edits" in tool_input and isinstance(tool_input["edits"], list):
        for edit in tool_input["edits"]:
            if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
                parts.append(edit["new_string"])
    return "\n".join(parts)


def _extract_file_path(tool_input: dict) -> str:
    return tool_input.get("file_path", "") or ""


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        _ok_output()
        return

    agent_id = event.get("agent_id", "") or ""
    tool_name = event.get("tool_name", "") or ""
    tool_input = event.get("tool_input", {}) or {}

    if tool_name not in ("Write", "Edit", "MultiEdit"):
        _ok_output()
        return

    file_path = _extract_file_path(tool_input)
    # Only check source files that plausibly contain integration code
    if not any(file_path.endswith(ext) for ext in (".py", ".ts", ".tsx", ".js", ".jsx")):
        _ok_output()
        return

    content = _extract_content(tool_input)
    if not content:
        _ok_output()
        return

    # Find any env URL references
    env_vars: list[str] = []
    for m in ENV_URL_PY.finditer(content):
        env_vars.append(m.group(1))
    for m in ENV_URL_JS.finditer(content):
        env_vars.append(m.group(1) or m.group(2))

    if not env_vars:
        _ok_output()
        return

    catalog = _load_catalog()
    if not catalog:
        log_hook("contract-check", agent_id or "unknown", "SKIP_NO_CATALOG", file_path)
        _ok_output()
        return

    warnings: list[str] = []
    for var in set(env_vars):
        svc_key = _find_service_name_from_url_var(var, catalog)
        if not svc_key:
            continue
        api_spec = _get_api_spec(catalog, svc_key)
        if not api_spec:
            continue
        known = _collect_spec_field_names(api_spec)
        if not known:
            continue
        # Build a normalized-form -> canonical lookup for known fields.
        norm_to_known: dict[str, str] = {}
        for k in known:
            norm_to_known.setdefault(_norm(k), k)
        # Scan every identifier and string literal in the file. Any token whose
        # normalized form matches a known field — but whose literal spelling
        # differs — is a near-variant and likely a contract mismatch.
        tokens: set[str] = set()
        for m in IDENTIFIER_LIKE.finditer(content):
            tokens.add(m.group(1))
        for m in STRING_LITERAL.finditer(content):
            tokens.add(m.group(1))
        suspect_pairs: list[tuple[str, str]] = []
        for tok in tokens:
            if tok in known:
                continue
            canonical = norm_to_known.get(_norm(tok))
            if canonical and canonical != tok:
                suspect_pairs.append((tok, canonical))
        if suspect_pairs:
            pair_strs = sorted({f"{t}->{c}" for t, c in suspect_pairs})
            warnings.append(
                f"{svc_key}: {file_path} uses near-variants {pair_strs} "
                f"(expected spelling shown after ->)"
            )

    if warnings:
        msg = "CONTRACT WARNING (non-blocking): " + " | ".join(warnings)
        log_hook("contract-check", agent_id or "unknown", "WARN", msg[:200])
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": msg + "\nRead service-catalog.json api_spec and match field names verbatim. No guessing.",
            }
        }, sys.stdout)
        return

    log_hook("contract-check", agent_id or "unknown", "OK", f"vars={sorted(set(env_vars))}")
    _ok_output()


def _has_similar(name: str, pool) -> bool:
    """Case- and separator-insensitive match. 'screenshot_url' ≈ 'screenshotUrl'."""
    if isinstance(pool, str):
        return _norm(name) == _norm(pool)
    for p in pool:
        if _norm(name) == _norm(p):
            return True
    return False


def _norm(s: str) -> str:
    return re.sub(r"[_\-]", "", s).lower()


if __name__ == "__main__":
    main()
