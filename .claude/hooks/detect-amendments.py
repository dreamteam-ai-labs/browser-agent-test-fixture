#!/usr/bin/env python3
"""
SessionStart hook: detect spec amendments in features.json.

Writes amendments.json if any completed feature's name, description, or
validation.success_criteria changed since the last-deployed snapshot.

Tracked fields use dotted-path notation to match the features-json-schema
nesting: `name` and `description` live at feature top-level, but
`success_criteria` is nested inside the `validation` block alongside
`test_command`. The dotted-path mechanism also gives us headroom to track
deeper-nested fields (e.g. `metadata.complexity`) in future without a
shape change.

Prior state source: .dreamteam/last-deployed-features.json — a sentinel
the factory writes on successful Coolify deploy-complete (via
f4-local.updateFeatureSet 'deployed' transition). First-ever builds
have no sentinel → hook silent. Correct default: nothing deployed means
nothing to amend against.

Rework takes precedence. If rework.json exists, this hook exits silently
so the rework flow is not disrupted.

Metadata-only classification (v0.6.1). Some tracked fields carry GDPR /
audit metadata that doesn't change behaviour — `pii_fields` is the
canonical example. When a sentinel diff surfaces ONLY metadata-only
field changes (every changed field on every amendment is in
METADATA_ONLY_FIELDS), the hook writes amendments-audit.json instead of
amendments.json. build-gate sees no amendments.json → no Amendment Mode
trigger → no $2-5 rebuild for an annotation-only change. The audit file
preserves the trail for grep-debugging history. Hybrid amendments (one
feature with both `pii_fields` and `description` changes) take the
behaviour path: amendments.json fires, the metadata change rides along.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TRACKED_FIELDS = ("name", "description", "validation.success_criteria", "pii_fields")
# Subset of TRACKED_FIELDS whose changes are pure metadata — record the
# amendment for audit, do NOT trigger a rebuild. Authoritative allowlist.
# Add a field here only when its changes provably never alter runtime behaviour
# or test outcomes (annotations, GDPR traceability, classification labels).
METADATA_ONLY_FIELDS = frozenset({"pii_fields"})
FEATURES_PATH = Path("features.json")
PRIOR_PATH = Path(".dreamteam/last-deployed-features.json")
AMENDMENTS_PATH = Path("amendments.json")
AMENDMENTS_AUDIT_PATH = Path("amendments-audit.json")
REWORK_PATH = Path("rework.json")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _get_nested(data: dict, dotted_path: str) -> Any:
    """Traverse a dict by dotted path. Returns None if any segment is missing
    or hits a non-dict intermediate value. Single-segment paths work unchanged.
    """
    value: Any = data
    for segment in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


def _is_metadata_only(amendment: dict) -> bool:
    """An amendment is metadata-only when EVERY changed field on it is in
    the METADATA_ONLY_FIELDS allowlist. A single behaviour-changing field
    in the same amendment flips it back to behaviour-changing — the
    metadata change rides along for free in the same amendment cycle.
    """
    fields = amendment.get("changed_fields") or []
    if not fields:
        return False
    return all(f in METADATA_ONLY_FIELDS for f in fields)


def detect_amendments(current: dict, prior: dict) -> list[dict]:
    prior_by_id = {
        f["id"]: f for f in prior.get("features", []) if isinstance(f, dict) and "id" in f
    }
    amendments: list[dict] = []
    for feat in current.get("features", []):
        if not isinstance(feat, dict):
            continue
        fid = feat.get("id")
        prior_feat = prior_by_id.get(fid)
        if not prior_feat:
            continue
        # Only flag amendments on features that WERE completed at last deploy.
        # A 'pending' → any-status transition is a normal revision, not an amendment.
        if prior_feat.get("status") != "completed":
            continue
        changed: dict[str, dict] = {}
        for field in TRACKED_FIELDS:
            prior_value = _get_nested(prior_feat, field)
            current_value = _get_nested(feat, field)
            if prior_value != current_value:
                changed[field] = {
                    "prior": prior_value,
                    "current": current_value,
                }
        if changed:
            amendments.append(
                {
                    "feature_id": fid,
                    "feature_name": feat.get("name"),
                    "changed_fields": list(changed.keys()),
                    "diff": changed,
                }
            )
    return amendments


def main() -> int:
    # Rework takes precedence — do not compete with it.
    if REWORK_PATH.exists():
        return 0

    current = read_json(FEATURES_PATH)
    prior = read_json(PRIOR_PATH)
    if not current or not prior:
        return 0

    amendments = detect_amendments(current, prior)
    if not amendments:
        # User reverted their edits — clean up both sentinel files.
        for path in (AMENDMENTS_PATH, AMENDMENTS_AUDIT_PATH):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
        return 0

    # Metadata-only routing: if EVERY amendment in this run is metadata-only
    # (e.g. pii_fields-only), record to amendments-audit.json and skip the
    # rebuild trigger. Hybrid runs (any behaviour-changing amendment present)
    # write the full set to amendments.json — metadata changes ride along.
    all_metadata_only = all(_is_metadata_only(a) for a in amendments)
    target_path = AMENDMENTS_AUDIT_PATH if all_metadata_only else AMENDMENTS_PATH
    other_path = AMENDMENTS_PATH if all_metadata_only else AMENDMENTS_AUDIT_PATH

    # Clean the sibling file if state shifted (e.g. user reverted the
    # behaviour change but kept the pii_fields annotation — was a trigger,
    # now metadata-only; previous amendments.json must go).
    if other_path.exists():
        try:
            other_path.unlink()
        except OSError:
            pass

    try:
        target_path.write_text(
            json.dumps({"amendments": amendments}, indent=2) + "\n"
        )
    except OSError as exc:
        print(
            f"[detect-amendments] failed to write {target_path.name}: {exc}",
            file=sys.stderr,
        )
        return 0

    classification = "metadata-only (no rebuild)" if all_metadata_only else "behaviour-changing"
    print(
        f"[detect-amendments] wrote {len(amendments)} amendment(s) to "
        f"{target_path.name} — {classification}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
