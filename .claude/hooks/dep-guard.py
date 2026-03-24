#!/usr/bin/env python3
"""Dep guard hook — ensures installed packages are declared in the project manifest.

PostToolUse hook on Bash commands. Detects `pip install` and `npm install` commands,
checks whether the installed package is declared in the project manifest
(pyproject.toml for Python, package.json for Node.js). Blocks if not declared.

Language-aware: add new package managers by adding a case to PACKAGE_MANAGERS.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def log_hook(hook_name: str, agent_id: str, action: str, detail: str = ""):
    log_path = Path(".claude/hooks/hook-log.txt")
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


def normalize_python_package(name: str) -> str:
    """Normalize Python package name: lowercase, hyphens → underscores, strip extras."""
    # Strip extras: package[extra] → package
    name = re.sub(r"\[.*?\]", "", name)
    # Strip version specifiers: package>=1.0 → package
    name = re.split(r"[><=!~;@]", name)[0]
    return name.strip().lower().replace("-", "_")


def normalize_npm_package(name: str) -> str:
    """Normalize npm package name: strip version specifier."""
    # Strip version: package@1.0.0 → package (but keep scoped: @scope/package)
    if name.startswith("@"):
        # Scoped package: @scope/package@version
        parts = name.split("@")
        # parts = ['', 'scope/package', 'version'] or ['', 'scope/package']
        return f"@{parts[1]}" if len(parts) >= 2 else name
    return name.split("@")[0].strip()


def get_declared_python_deps(manifest_path: Path) -> set[str]:
    """Read declared dependencies from pyproject.toml."""
    if not manifest_path.exists():
        return set()
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError:
        return set()

    deps: set[str] = set()
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            # Parse: "package>=1.0", or "package",
            match = re.match(r'^\s*"([^"]+)"', stripped)
            if match:
                deps.add(normalize_python_package(match.group(1)))
    return deps


def get_declared_npm_deps(manifest_path: Path) -> set[str]:
    """Read declared dependencies from package.json."""
    if not manifest_path.exists():
        return set()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()

    deps: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(data.get(section, {}).keys())
    return deps


# ── Package manager definitions ──────────────────────────────────────
# To add a new language: add an entry here with the regex, manifest, and normalizer.

PACKAGE_MANAGERS = [
    {
        "name": "pip",
        # Matches: pip install pkg, pip3 install pkg, python -m pip install pkg
        # Captures the packages after "install" (space-separated)
        # Ignores flags like -r, -e, -q, --upgrade, etc.
        "pattern": re.compile(
            r"(?:pip3?|python3?\s+-m\s+pip)\s+install\s+(.*)", re.IGNORECASE
        ),
        "manifest": "pyproject.toml",
        "normalizer": normalize_python_package,
        "get_declared": get_declared_python_deps,
        "skip_args": {"-r", "--requirement", "-e", "--editable", "-q", "--quiet",
                      "--upgrade", "-U", "--no-deps", "--user", "--force-reinstall",
                      "--pre", "--break-system-packages"},
        "skip_packages": {".", "./", "..", "-e", ".[dev]", ".[mcp]", ".[agent-sdk]",
                          ".[mcp,agent-sdk]"},
    },
    {
        "name": "npm",
        # Matches: npm install pkg, npm i pkg, npm add pkg
        "pattern": re.compile(
            r"npm\s+(?:install|i|add)\s+(.*)", re.IGNORECASE
        ),
        "manifest": "frontend/package.json",
        "normalizer": normalize_npm_package,
        "get_declared": get_declared_npm_deps,
        "skip_args": {"--save-dev", "-D", "--save-optional", "-O", "--save-exact",
                      "-E", "--global", "-g", "--legacy-peer-deps"},
        "skip_packages": set(),
    },
]


def extract_packages(args_str: str, pm: dict) -> list[str]:
    """Extract package names from the argument string, skipping flags and special args."""
    tokens = args_str.split()
    packages = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        # Skip flags
        if token.startswith("-"):
            if token in pm["skip_args"]:
                # Some flags take a value (like -r requirements.txt)
                if token in ("-r", "--requirement"):
                    skip_next = True
                continue
            # Unknown flag — skip it
            continue
        # Skip special packages (self-install, editable)
        if token in pm["skip_packages"]:
            continue
        packages.append(token)
    return packages


def check_command(command: str) -> tuple[str | None, list[str], dict | None]:
    """Check if a command is a package install. Returns (pm_name, undeclared_packages, pm_config)."""
    for pm in PACKAGE_MANAGERS:
        match = pm["pattern"].search(command)
        if not match:
            continue

        args_str = match.group(1).strip()
        if not args_str:
            return None, [], None

        packages = extract_packages(args_str, pm)
        if not packages:
            return None, [], None

        # Check which packages are declared
        manifest_path = Path(pm["manifest"])
        declared = pm["get_declared"](manifest_path)

        undeclared = []
        for pkg in packages:
            normalized = pm["normalizer"](pkg)
            if normalized and normalized not in declared:
                undeclared.append(pkg)

        return pm["name"], undeclared, pm

    return None, [], None


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        json.dump({"decision": "allow"}, sys.stdout)
        return

    agent_id = event.get("agent_id", "unknown") or "unknown"

    # Get the Bash command that was executed
    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "")
    if not command:
        json.dump({"decision": "allow"}, sys.stdout)
        return

    pm_name, undeclared, pm_config = check_command(command)

    if pm_name is None or not undeclared:
        # Not a package install, or all packages are declared
        json.dump({"decision": "allow"}, sys.stdout)
        return

    # Packages installed but not declared — block
    manifest = pm_config["manifest"] if pm_config else "manifest"
    pkg_list = ", ".join(undeclared)

    log_hook("dep-guard", agent_id, "BLOCK",
             f"pm={pm_name} undeclared=[{pkg_list}] manifest={manifest}")

    json.dump({
        "decision": "block",
        "reason": (
            f"You installed {pkg_list} via {pm_name} but "
            f"{'it is' if len(undeclared) == 1 else 'they are'} not declared in {manifest}. "
            f"Add {'it' if len(undeclared) == 1 else 'them'} to {manifest} before continuing. "
            f"For pyproject.toml: add to [project.dependencies]. "
            f"For package.json: add to dependencies or devDependencies."
        ),
    }, sys.stdout)


if __name__ == "__main__":
    main()
