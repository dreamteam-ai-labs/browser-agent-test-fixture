"""sitecustomize.py — Python-level outbound-egress allowlist enforcement.

Auto-imported by CPython on startup (before user code runs) when
`.claude/scripts` is on PYTHONPATH. This module monkey-patches the
standard Python network surfaces — `urllib.request.urlopen`,
`http.client.HTTPConnection`, `http.client.HTTPSConnection`,
`socket.create_connection` — to consult `.claude/egress-allowlist.json`
before making any outbound connection.

Why this exists: the Bash-level `outbound-egress-guard.py` hook catches
curl/wget/git clone/pip --index-url/npm --registry patterns, but anything
that goes through Python's network libraries (urllib, httpx, requests,
aiohttp, anthropic SDK, openai SDK, stripe SDK, etc.) bypasses Bash
inspection. This file closes that surface.

Coverage:
  - `urllib.request.urlopen` (stdlib)
  - `http.client.HTTPConnection.request` / `HTTPSConnection.request`
    (low-level — used by urllib + most third-party libs)
  - `socket.create_connection` (catches non-http TCP egress + libs that
    bypass http.client entirely)

The check is the same as the Bash hook: host extracted, suffix-matched
against `allowed_hosts` in egress-allowlist.json. Unlisted host raises
`EgressBlockedError(RuntimeError)` — caller sees a clear traceback
naming the host and the override env var.

Escape hatch: `DREAMTEAM_ALLOW_UNLISTED_EGRESS=1` matches the pattern
from protect-harness-paths.py + secrets-detection.py + outbound-egress-
guard.py — single override turns off ALL of them so an operator carving
out one specific case doesn't have to re-edit configs.

Side-effect cost:
  - Adds ~5-10ms to Python interpreter startup (allowlist file read + 4
    monkey-patches).
  - Allowlist file is read once at import time, cached for the process
    lifetime. Editing the allowlist mid-build does NOT propagate to
    already-running Python processes — they must restart.

Failure modes:
  - If `.claude/egress-allowlist.json` is missing or malformed, this
    module is a NO-OP (no patches applied, no enforcement). Matches the
    Bash hook's fail-open policy. Empty allowlist = no enforcement (an
    operator-installation gap, not an active threat).
  - If monkey-patching fails for any reason (rare — would need a custom
    Python build), the module logs a warning to hook-log.txt and remains
    a no-op rather than crash interpreter startup.

OBSOLESCENCE: Remove if Anthropic ships native Python-process network
policy at the harness layer.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Resolve project dir defensively — sitecustomize runs in arbitrary
# subprocess contexts where CLAUDE_PROJECT_DIR might not be set.
_PROJECT_DIR = Path(
    os.environ.get("CLAUDE_PROJECT_DIR")
    or os.environ.get("REPO_ROOT")
    or os.getcwd()
)
_ALLOWLIST_PATH = _PROJECT_DIR / ".claude" / "egress-allowlist.json"
_HOOK_LOG = _PROJECT_DIR / ".claude" / "hooks" / "hook-log.txt"
_ESCAPE_ENV = "DREAMTEAM_ALLOW_UNLISTED_EGRESS"


class EgressBlockedError(RuntimeError):
    """Raised when Python code attempts to connect to a non-allowlisted host."""


def _log(action: str, detail: str) -> None:
    try:
        _HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().isoformat(timespec="milliseconds")
        with open(_HOOK_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} | sitecustomize-egress | agent=python | {action} | {detail}\n")
    except OSError:
        pass


def _load_allowlist() -> list[str]:
    if not _ALLOWLIST_PATH.is_file():
        return []
    try:
        data = json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    hosts = data.get("allowed_hosts", [])
    return [h.lower().strip(".") for h in hosts if isinstance(h, str)]


_ALLOWLIST: list[str] = _load_allowlist()


def _host_is_allowed(host: str) -> bool:
    if not host:
        return True  # nothing to check (e.g., file:// URLs reach this path)
    host = host.lower().strip(".")
    # Strip any IPv6 brackets / port-like fragments defensively.
    if host.startswith("[") and "]" in host:
        host = host[1:host.index("]")]
    for entry in _ALLOWLIST:
        if host == entry or host.endswith("." + entry):
            return True
    return False


def _escape_active() -> bool:
    return os.environ.get(_ESCAPE_ENV, "").strip() in ("1", "true", "True", "yes")


def _check_host_or_raise(host: str, source: str) -> None:
    if not _ALLOWLIST:
        # No allowlist configured — fail-open (matches Bash hook policy).
        return
    if _host_is_allowed(host):
        return
    if _escape_active():
        _log("ALLOW_VIA_ESCAPE", f"source={source} host={host} env={_ESCAPE_ENV}")
        return
    _log("DENY", f"source={source} host={host}")
    raise EgressBlockedError(
        f"Outbound egress to '{host}' blocked by .claude/egress-allowlist.json "
        f"(source: {source}). If this host is needed, edit the allowlist "
        f"(operator action) or set {_ESCAPE_ENV}=1 to override after operator "
        f"review."
    )


def _install_patches() -> None:
    """Apply monkey-patches to all known Python network surfaces."""
    if not _ALLOWLIST:
        # Nothing to enforce — leave network surfaces unpatched.
        return

    try:
        import http.client
        import socket
        import urllib.parse
        import urllib.request
    except ImportError:
        # Should never happen on CPython — bail without patches.
        _log("PATCH_SKIPPED", "stdlib import failed")
        return

    # 1. http.client.HTTPConnection / HTTPSConnection.request
    _orig_http_request = http.client.HTTPConnection.request

    def _patched_request(self, method, url, body=None, headers=None, *args, **kwargs):
        _check_host_or_raise(self.host, source=f"http.client.{type(self).__name__}.request")
        return _orig_http_request(self, method, url, body, headers or {}, *args, **kwargs)

    http.client.HTTPConnection.request = _patched_request  # type: ignore[method-assign]

    # 2. urllib.request.urlopen — extracts host from the Request/url first.
    _orig_urlopen = urllib.request.urlopen

    def _patched_urlopen(url, *args, **kwargs):
        if isinstance(url, str):
            target = url
        else:
            # urllib.request.Request — has .full_url / .host
            target = getattr(url, "full_url", "") or getattr(url, "host", "")
        try:
            parsed = urllib.parse.urlparse(target)
            host = parsed.hostname or ""
        except Exception:
            host = ""
        _check_host_or_raise(host, source="urllib.request.urlopen")
        return _orig_urlopen(url, *args, **kwargs)

    urllib.request.urlopen = _patched_urlopen  # type: ignore[assignment]

    # 3. socket.create_connection — catches anything that bypasses http.client
    # (e.g., raw socket users, some async libs). Allow localhost-direct
    # connections (the typical case for in-process service calls) — those
    # are covered by allowlist entries localhost/127.0.0.1/::1 anyway.
    _orig_create_connection = socket.create_connection

    def _patched_create_connection(address, *args, **kwargs):
        # address is (host, port) tuple
        host = ""
        try:
            host = address[0] if isinstance(address, tuple) else ""
        except Exception:
            pass
        _check_host_or_raise(str(host), source="socket.create_connection")
        return _orig_create_connection(address, *args, **kwargs)

    socket.create_connection = _patched_create_connection  # type: ignore[assignment]

    _log("PATCHES_INSTALLED", f"allowlist_size={len(_ALLOWLIST)}")


try:
    _install_patches()
except Exception as exc:  # noqa: BLE001 — never crash interpreter startup
    _log("PATCH_FAILED", f"exception={type(exc).__name__}: {exc}")
