#!/usr/bin/env python3
"""Audit deps — detect undeclared Python dependencies (ghost deps).

Scans all .py files in src/ for imports and compares against declared
dependencies in pyproject.toml. Reports any imports that are not in the
standard library AND not declared as dependencies.

Usage:
    python3 .claude/hooks/audit-deps.py          # Scan src/
    python3 .claude/hooks/audit-deps.py --fix     # Print what to add (no auto-edit)
    python3 .claude/hooks/audit-deps.py --json    # JSON output for programmatic use

Exit codes:
    0 = All imports are declared or stdlib
    1 = Undeclared dependencies found
"""
import ast
import json
import re
import sys
from pathlib import Path

# ── Python standard library modules (3.11+) ──────────────────────────
# This list covers the vast majority. Some platform-specific modules omitted.
STDLIB_MODULES = frozenset({
    "__future__", "_thread", "abc", "aifc", "argparse", "array", "ast",
    "asynchat", "asyncio", "asyncore", "atexit", "audioop", "base64",
    "bdb", "binascii", "binhex", "bisect", "builtins", "bz2", "calendar",
    "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs", "codeop",
    "collections", "colorsys", "compileall", "concurrent", "configparser",
    "contextlib", "contextvars", "copy", "copyreg", "cProfile", "crypt",
    "csv", "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
    "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt",
    "getpass", "gettext", "glob", "graphlib", "grp", "gzip", "hashlib",
    "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
    "imp", "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "lib2to3", "linecache", "locale", "logging", "lzma",
    "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap",
    "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev",
    "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
    "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site", "smtpd",
    "smtplib", "sndhdr", "socket", "socketserver", "sqlite3", "ssl",
    "stat", "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
    "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
    "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib",
    "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
    "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
    "zipapp", "zipfile", "zipimport", "zlib",
    # Also common internal/private modules
    "_io", "_collections_abc", "_frozen_importlib", "typing_extensions",
    "annotations",
})

# ── Known package-to-import mappings ──────────────────────────────────
# When the import name differs from the pip package name.
IMPORT_TO_PACKAGE = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "gi": "PyGObject",
    "attr": "attrs",
    "dotenv": "python-dotenv",
    "jose": "python-jose",
    "jwt": "PyJWT",
    "magic": "python-magic",
    "dateutil": "python-dateutil",
    "google": "google-cloud-core",
    "firebase_admin": "firebase-admin",
    "sqlalchemy": "SQLAlchemy",
    "pythonjsonlogger": "python-json-logger",
    "passlib": "passlib",
    "multipart": "python-multipart",
    "uvicorn": "uvicorn",
    "starlette": "starlette",
    "stripe_module": "stripe",
}


def normalize_package(name: str) -> str:
    """Normalize package name for comparison."""
    name = re.sub(r"\[.*?\]", "", name)
    name = re.split(r"[><=!~;@]", name)[0]
    return name.strip().lower().replace("-", "_")


def get_declared_deps(pyproject_path: Path) -> set[str]:
    """Parse pyproject.toml and return normalized dependency names."""
    if not pyproject_path.exists():
        return set()
    deps: set[str] = set()
    in_deps = False
    for line in pyproject_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            match = re.match(r'^\s*"([^"]+)"', stripped)
            if match:
                deps.add(normalize_package(match.group(1)))
    return deps


def scan_imports(src_dir: Path) -> dict[str, set[str]]:
    """Scan all .py files and return {top_level_module: set_of_files_that_import_it}."""
    imports: dict[str, set[str]] = {}

    for py_file in src_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module:
                # Skip explicit relative imports (from .auth import ...)
                if node.level and node.level > 0:
                    continue
                module = node.module.split(".")[0]

            if module:
                # Skip implicit relative imports (from auth import ... where auth.py exists in package)
                if (src_dir / module).exists() or (src_dir / module / "__init__.py").exists() or (src_dir / f"{module}.py").exists():
                    continue
                if module not in imports:
                    imports[module] = set()
                imports[module].add(str(py_file))

    return imports


def find_undeclared(
    imports: dict[str, set[str]],
    declared: set[str],
    project_package: str | None = None,
) -> list[dict]:
    """Find imports that are not stdlib, not declared, and not the project itself."""
    undeclared = []

    for module, files in sorted(imports.items()):
        # Skip stdlib
        if module in STDLIB_MODULES:
            continue

        # Skip the project's own package
        if project_package and module == project_package:
            continue

        # Check if declared (try both the import name and known mappings)
        normalized_import = module.lower().replace("-", "_")
        known_package = IMPORT_TO_PACKAGE.get(module)

        is_declared = (
            normalized_import in declared
            or (known_package and normalize_package(known_package) in declared)
        )

        if not is_declared:
            suggestion = known_package or module
            undeclared.append({
                "import": module,
                "package": suggestion,
                "files": sorted(files),
            })

    return undeclared


def detect_project_package(pyproject_path: Path) -> str | None:
    """Try to detect the project's own package name from pyproject.toml."""
    if not pyproject_path.exists():
        return None
    in_project = False
    for line in pyproject_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("name"):
            match = re.match(r'name\s*=\s*"([^"]+)"', stripped)
            if match:
                return normalize_package(match.group(1))
        if in_project and stripped.startswith("[") and stripped != "[project]":
            break
    return None


def main():
    json_output = "--json" in sys.argv
    fix_mode = "--fix" in sys.argv

    # Find src/ directory
    src_dir = Path("src")
    if not src_dir.exists():
        if not json_output:
            print("No src/ directory found.")
        sys.exit(0)

    pyproject_path = Path("pyproject.toml")
    declared = get_declared_deps(pyproject_path)
    project_package = detect_project_package(pyproject_path)
    imports = scan_imports(src_dir)
    undeclared = find_undeclared(imports, declared, project_package)

    if json_output:
        result = {
            "total_imports": len(imports),
            "declared_deps": len(declared),
            "undeclared": undeclared,
            "status": "fail" if undeclared else "pass",
        }
        print(json.dumps(result, indent=2))
    else:
        if not undeclared:
            print(f"All {len(imports)} imports are declared or stdlib.")
        else:
            print(f"UNDECLARED DEPENDENCIES ({len(undeclared)} found):\n")
            for dep in undeclared:
                files_str = ", ".join(dep["files"][:3])
                if len(dep["files"]) > 3:
                    files_str += f" (+{len(dep['files']) - 3} more)"
                print(f"  {dep['import']} (pip install {dep['package']})")
                print(f"    imported in: {files_str}")
            print(f"\nAdd these to pyproject.toml [project.dependencies]:")
            for dep in undeclared:
                print(f'    "{dep["package"]}",')

    sys.exit(1 if undeclared else 0)


if __name__ == "__main__":
    main()
