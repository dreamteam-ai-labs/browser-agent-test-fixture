#!/usr/bin/env python3
"""Lane-tracking v0 hooks — the blackboard's guaranteed floor (A5, RA+DT 2026-07-03).

Lane-tracking is a durable, async blackboard of per-product build FACTS
(design: customer-dev-squads-2026-06-11.md §7; wire contract: BRIEF-FOR-FJ §3).
Build lanes register on start, publish status at phase end, and re-read after
compaction. Rich facts (endpoints, contracts, docs) are the AGENT's job via
the dreamteam-lane-tracking MCP tools — these hooks are the floor, not the
ceiling.

Three modes (operator-locked v0 hook set — SessionStart + Stop + PostCompact):
    session-start   register lane (fact_type: registration — idempotent by
                    the LWW key) + pull the sibling snapshot to stdout
                    (SessionStart stdout is added to the session's context).
    stop            publish this phase's status fact. WRITE ONLY — never
                    blocks, never emits a decision (Stop-block injection is
                    a force-continue lever, not a publisher).
    post-compact    re-pull the sibling snapshot (compaction loses it).

FAIL-OPEN BY CONTRACT: lane-tracking is build-time assistance — the
blackboard being down/unborn/unconfigured must NEVER fail a build. Every
network/env problem logs to stderr + hook-log and exits 0. The hook is also
a silent no-op when the lane env contract is absent (legacy / un-laned
builds: no FEATURE_SET_KEY or no DREAMTEAM_LANE).

Env contract (mirrors dreamteam-lane-tracking-mcp — keep aligned):
    LANE_TRACKING_SERVICE_URL   service base URL
      (fallback DREAMTEAM_LANE_TRACKING_SERVICE_URL, then the fleet default)
    DREAMTEAM_SERVICE_API_KEY   bearer token (fallback CODESPACE_DREAMTEAM_SERVICE_API_KEY)
    FEATURE_SET_KEY             product scope — REQUIRED, no-op without it
    DREAMTEAM_LANE              lane identity — REQUIRED, NO silent default;
                                "default" is RESERVED (dispatch sentinel) and
                                never published under.

Stdlib only ON PURPOSE: hooks can fire before the factory's post-provision
`pip install .[dev,services,buildtools]`, so httpx / the MCP package may not
exist yet.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

DEFAULT_SERVICE_URL = "https://lane-tracking-service.dreamteamlabs.co.uk"
RESERVED_LANE = "default"
HTTP_TIMEOUT_S = 5
# Injection budget — LWW state is naturally small, but never flood context.
SNAPSHOT_MAX_LINES = 60
SNAPSHOT_MAX_CHARS = 8000
PAYLOAD_HINT_MAX_CHARS = 160


def log_hook(action: str, detail: str = "") -> None:
    log_path = PROJECT_DIR / ".claude" / "hooks" / "hook-log.txt"
    timestamp = datetime.now().isoformat(timespec="milliseconds")
    line = f"{timestamp} | lane-tracking | {action}"
    if detail:
        line += f" | {detail}"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def service_url() -> str:
    return (
        _first_env("LANE_TRACKING_SERVICE_URL", "DREAMTEAM_LANE_TRACKING_SERVICE_URL")
        or DEFAULT_SERVICE_URL
    ).rstrip("/")


def _headers(feature_set_key: str) -> dict[str, str]:
    # Stable header contract across AUTH_LEVEL transitions (empty at Level 0).
    api_key = _first_env("DREAMTEAM_SERVICE_API_KEY", "CODESPACE_DREAMTEAM_SERVICE_API_KEY")
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Dreamteam-Product-ID": feature_set_key,
        "Content-Type": "application/json",
    }


def publish_fact(feature_set_key: str, lane: str, fact_type: str, subject: str, payload: dict) -> bool:
    """POST one fact. Returns success; NEVER raises (fail-open)."""
    body = json.dumps(
        {
            "feature_set_key": feature_set_key,
            "lane": lane,
            "fact_type": fact_type,
            "subject": subject,
            "payload": payload,
            "seq": int(time.time() * 1000),  # LWW authority — epoch-ms per contract
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{service_url()}/api/facts",
        data=body,
        headers=_headers(feature_set_key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            result = json.loads(response.read().decode("utf-8") or "{}")
        superseded = " (superseded — stale write, LWW kept newer)" if result.get("superseded") else ""
        log_hook("PUBLISH", f"{fact_type}/{subject} lane={lane}{superseded}")
        return True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Fail-open: blackboard down ≠ build fails. Loud in the log, silent to the gate.
        log_hook("PUBLISH-FAILED", f"{fact_type}/{subject}: {exc}")
        print(f"[lane-tracking] publish {fact_type} failed (fail-open, build continues): {exc}", file=sys.stderr)
        return False


def read_facts(feature_set_key: str) -> list | None:
    """GET current LWW state for the product. None on failure; NEVER raises."""
    params = urllib.parse.urlencode({"feature_set_key": feature_set_key})
    request = urllib.request.Request(
        f"{service_url()}/api/facts?{params}",
        headers=_headers(feature_set_key),
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            data = json.loads(response.read().decode("utf-8") or "[]")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log_hook("READ-FAILED", str(exc))
        print(f"[lane-tracking] read failed (fail-open, build continues): {exc}", file=sys.stderr)
        return None
    if isinstance(data, dict):  # tolerate {facts: [...]} envelope
        data = data.get("facts", [])
    return data if isinstance(data, list) else []


def _payload_hint(payload) -> str:
    if not isinstance(payload, dict) or not payload:
        return "-"
    try:
        text = json.dumps(payload, sort_keys=True)
    except (TypeError, ValueError):
        return "-"
    if len(text) > PAYLOAD_HINT_MAX_CHARS:
        text = text[: PAYLOAD_HINT_MAX_CHARS - 1] + "…"
    return text


def format_snapshot(feature_set_key: str, lane: str, facts: list) -> str:
    """Compact, capped sibling-facts snapshot for context injection."""
    lanes = sorted({f.get("lane", "?") for f in facts if isinstance(f, dict)})
    lines = [
        f"[lane-tracking] Blackboard snapshot for {feature_set_key} "
        f"({len(facts)} fact(s), lanes: {', '.join(lanes) if lanes else 'none yet'}; you are lane '{lane}'):"
    ]
    for fact in facts[:SNAPSHOT_MAX_LINES]:
        if not isinstance(fact, dict):
            continue
        lines.append(
            f"  {fact.get('lane', '?')} · {fact.get('fact_type', '?')} · "
            f"{fact.get('subject', '?')} · {_payload_hint(fact.get('payload'))}"
        )
    if len(facts) > SNAPSHOT_MAX_LINES:
        lines.append(f"  … {len(facts) - SNAPSHOT_MAX_LINES} more (read_lane_facts for the rest)")
    lines.append(
        "Publish realized endpoints/contracts with the dreamteam-lane-tracking MCP tool "
        "publish_lane_fact; re-read siblings with read_lane_facts BEFORE building against "
        "another lane's surface (pull-first — facts may have changed since this snapshot)."
    )
    text = "\n".join(lines)
    if len(text) > SNAPSHOT_MAX_CHARS:
        text = text[: SNAPSHOT_MAX_CHARS - 15] + "\n… (truncated)"
    return text


def derive_phase_status() -> dict:
    """This phase's status payload, derived from features.json (best effort)."""
    payload: dict = {"status": "in_progress"}
    state_file = PROJECT_DIR / "project-state.json"
    try:
        payload["phase"] = json.loads(state_file.read_text(encoding="utf-8")).get("build_phase", "")
    except (OSError, json.JSONDecodeError):
        pass
    try:
        features = json.loads((PROJECT_DIR / "features.json").read_text(encoding="utf-8")).get("features", [])
    except (OSError, json.JSONDecodeError):
        return payload
    statuses = [f.get("status") for f in features if isinstance(f, dict)]
    completed = sum(1 for s in statuses if s == "completed")
    payload["features_complete"] = completed
    payload["features_total"] = len(statuses)
    if statuses and completed == len(statuses):
        payload["status"] = "realized"
    elif any(s == "blocked" for s in statuses):
        payload["status"] = "blocked"
    elif any(s == "in_progress" for s in statuses):
        payload["status"] = "in_progress"
    else:
        payload["status"] = "pending"
    return payload


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("session-start", "stop", "post-compact"):
        print(f"[lane-tracking] unknown mode {mode!r} — no-op", file=sys.stderr)
        return 0

    # Gate: no lane env contract → legacy / un-laned build → silent no-op.
    feature_set_key = os.environ.get("FEATURE_SET_KEY", "")
    lane = os.environ.get("DREAMTEAM_LANE", "")  # NO silent default, by contract
    if not feature_set_key or not lane:
        return 0
    if lane == RESERVED_LANE:
        # Dispatch sentinel, never a producer identity — refuse to publish under it.
        log_hook("SKIP", f"lane '{RESERVED_LANE}' is reserved (dispatch sentinel) — no-op")
        print(f"[lane-tracking] DREAMTEAM_LANE='{RESERVED_LANE}' is reserved — hook no-op", file=sys.stderr)
        return 0

    if mode == "session-start":
        payload = {"registered_by": "session-start-hook"}
        phase = derive_phase_status().get("phase", "")
        if phase:
            payload["phase"] = phase
        publish_fact(feature_set_key, lane, "registration", "lane", payload)
        facts = read_facts(feature_set_key)
        if facts is not None:
            # SessionStart stdout is added to the session's context.
            print(format_snapshot(feature_set_key, lane, facts))
        return 0

    if mode == "stop":
        # WRITE ONLY — no decision output, never blocks the stop.
        publish_fact(feature_set_key, lane, "status", "lane", derive_phase_status())
        return 0

    # post-compact: the snapshot did not survive compaction — re-pull.
    facts = read_facts(feature_set_key)
    if facts is not None:
        json.dump(
            {
                "decision": "allow",
                "message": "[Post-compaction lane-tracking recovery]\n"
                + format_snapshot(feature_set_key, lane, facts),
            },
            sys.stdout,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — fail-open is the hook's contract
        print(f"[lane-tracking] unexpected error (fail-open, build continues): {exc}", file=sys.stderr)
        sys.exit(0)
