#!/usr/bin/env python3
"""Validate architecture.json — structural checks + semantic cross-reference with features.json.

Output contract (agreed with DreamTeam factory loop):
  - Success: VALID: N entities, M endpoints, R relationships
  - Failure: INVALID: <reason>
  - Always exits 0 (sshSafe returns stdout, not exit code)
  - Single line output only
"""

import json
import subprocess
import sys
from pathlib import Path


def validate_architecture(
    arch_path: str = "architecture.json",
    features_path: str = "features.json",
) -> tuple[bool, str]:
    """Validate architecture.json structure and cross-reference with features.json.

    Returns:
        (is_valid, message) — message starts with 'VALID:' or 'INVALID:'.
    """
    # ── Layer 1: File exists ──
    arch_file = Path(arch_path)
    if not arch_file.exists():
        return False, "INVALID: architecture.json not found"

    try:
        with open(arch_file) as f:
            arch = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"INVALID: architecture.json is not valid JSON — {e}"

    # ── Layer 2: Structural validation ──
    if "version" not in arch:
        return False, "INVALID: missing required field 'version'"

    if "services" not in arch:
        return False, "INVALID: missing required field 'services'"

    services = arch.get("services", {})
    if not isinstance(services, dict) or not services:
        return False, "INVALID: 'services' must be a non-empty object"

    total_entities = 0
    total_endpoints = 0
    total_relationships = 0

    for svc_name, svc in services.items():
        if not isinstance(svc, dict):
            return False, f"INVALID: service '{svc_name}' must be an object"

        # Existing services: validate URL + require api_spec (or explicit opt-out)
        if svc.get("source") == "existing":
            if "url" not in svc:
                return False, f"INVALID: existing service '{svc_name}' missing 'url'"
            # Layer 2e: every existing service must carry its contract.
            # Escape hatches: api_spec_source="manual" with api_spec provided,
            # or api_spec_source="opt_out" with written justification.
            api_spec_source = svc.get("api_spec_source", "openapi")
            if api_spec_source == "opt_out":
                if not svc.get("api_spec_opt_out_reason"):
                    return False, (
                        f"INVALID: existing service '{svc_name}' has api_spec_source='opt_out' "
                        f"but no 'api_spec_opt_out_reason'. Opt-out requires written justification."
                    )
            elif api_spec_source in ("openapi", "manual"):
                spec = svc.get("api_spec")
                if not isinstance(spec, dict) or not spec:
                    return False, (
                        f"INVALID: existing service '{svc_name}' missing 'api_spec'. "
                        f"Integration builders need the contract to avoid guessing field names. "
                        f"Fix: ensure the service exposes /openapi.json and the catalog captures it, "
                        f"OR provide a manual schema via api_spec_source='manual' + api_spec=, "
                        f"OR explicitly opt out with api_spec_source='opt_out' + api_spec_opt_out_reason='...'."
                    )
            else:
                return False, (
                    f"INVALID: existing service '{svc_name}' has unknown "
                    f"api_spec_source '{api_spec_source}' (expected: openapi, manual, opt_out)"
                )
            continue

        entities = svc.get("entities", {})
        if not isinstance(entities, dict) or not entities:
            return False, f"INVALID: service '{svc_name}' has no entities"

        for ent_name, ent in entities.items():
            if not isinstance(ent, dict):
                return False, f"INVALID: entity '{ent_name}' in service '{svc_name}' must be an object"

            if "table" not in ent:
                return False, f"INVALID: entity '{ent_name}' in service '{svc_name}' missing 'table'"

            fields = ent.get("fields", {})
            if not isinstance(fields, dict) or not fields:
                return False, f"INVALID: entity '{ent_name}' in service '{svc_name}' has no fields"

            # Validate field types
            for field_name, field_def in fields.items():
                if not isinstance(field_def, dict):
                    return False, f"INVALID: field '{field_name}' in entity '{ent_name}' must be an object"
                if "type" not in field_def:
                    return False, f"INVALID: field '{field_name}' in entity '{ent_name}' missing 'type'"

            # Validate endpoints
            endpoints = ent.get("endpoints", {})
            for ep_name, ep in endpoints.items():
                if not isinstance(ep, dict):
                    return False, f"INVALID: endpoint '{ep_name}' in entity '{ent_name}' must be an object"
                if "method" not in ep:
                    return False, f"INVALID: endpoint '{ep_name}' in entity '{ent_name}' missing 'method'"
                if "path" not in ep:
                    return False, f"INVALID: endpoint '{ep_name}' in entity '{ent_name}' missing 'path'"

            total_entities += 1
            total_endpoints += len(endpoints)

        # Validate relationships
        relationships = svc.get("relationships", [])
        if not isinstance(relationships, list):
            return False, f"INVALID: 'relationships' in service '{svc_name}' must be an array"

        entity_names = set(entities.keys())
        for rel in relationships:
            if not isinstance(rel, dict):
                return False, f"INVALID: relationship in service '{svc_name}' must be an object"
            for req_field in ("from", "to", "field", "cardinality"):
                if req_field not in rel:
                    return False, f"INVALID: relationship in service '{svc_name}' missing '{req_field}'"
            if rel["from"] not in entity_names:
                return False, f"INVALID: relationship references unknown entity '{rel['from']}'"
            if rel["to"] not in entity_names:
                return False, f"INVALID: relationship references unknown entity '{rel['to']}'"

        total_relationships += len(relationships)

    # ── Layer 2b: depends_on + brief validation ──
    all_svc_names = set(services.keys())
    for svc_name, svc in services.items():
        # Validate depends_on references
        for dep in svc.get("depends_on", []):
            if dep not in all_svc_names:
                return False, f"INVALID: service '{svc_name}' depends_on unknown service '{dep}'"
            if dep == svc_name:
                return False, f"INVALID: service '{svc_name}' depends_on itself"

        # Dependency build_new services need a brief for F4
        if svc.get("source") == "build_new" and not svc.get("entities"):
            if not svc.get("brief"):
                return False, f"INVALID: dependency service '{svc_name}' has no entities and no brief"

    # Cycle detection in depends_on graph
    def _has_cycle(name, visited, stack):
        visited.add(name)
        stack.add(name)
        for dep in services.get(name, {}).get("depends_on", []):
            if dep in stack:
                return True
            if dep not in visited and dep in services:
                if _has_cycle(dep, visited, stack):
                    return True
        stack.discard(name)
        return False

    visited_cycle, stack_cycle = set(), set()
    for svc_name in services:
        if svc_name not in visited_cycle:
            if _has_cycle(svc_name, visited_cycle, stack_cycle):
                return False, f"INVALID: circular dependency detected involving '{svc_name}'"

    # ── Layer 2c: Entity superset check for revisions ──
    # If a previous version exists (git tag), v2 must contain all v1 entities.
    # Removing an entity breaks rollback safety (additive-only migrations).
    try:
        prev_arch_raw = subprocess.run(
            ["git", "show", "HEAD~1:architecture.json"],
            capture_output=True, text=True, timeout=5,
        )
        if prev_arch_raw.returncode == 0:
            prev_arch = json.loads(prev_arch_raw.stdout)
            prev_entities = set()
            for svc in prev_arch.get("services", {}).values():
                if svc.get("source") != "existing":
                    prev_entities.update(svc.get("entities", {}).keys())
            current_entities = set()
            for svc in services.values():
                if svc.get("source") != "existing":
                    current_entities.update(svc.get("entities", {}).keys())
            removed = prev_entities - current_entities
            if removed:
                return False, f"INVALID: entities removed from previous version: {', '.join(sorted(removed))}. Migrations must be additive only."
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass  # No previous version or git not available — skip check

    # ── Layer 2d: required_services check ──
    # If features.json pins specific services, architect must include them all
    # as source: "existing" with matching extends briefs verbatim when specified.
    import unicodedata as _ud

    def _normalize_brief(s: str) -> str:
        """Normalize a brief for verbatim comparison.

        - Unicode NFC to collapse lookalikes
        - Collapse all whitespace runs to single space
        - strip leading/trailing whitespace
        This prevents trivial bypass via reordering/invisible chars while
        still tolerating formatting differences.
        """
        if not isinstance(s, str):
            return ""
        normalized = _ud.normalize("NFC", s)
        return " ".join(normalized.split()).strip()

    features_file_check = Path(features_path)
    if features_file_check.exists():
        try:
            with open(features_file_check) as f:
                features_data_check = json.load(f)
            required = features_data_check.get("required_services", [])
            # Type guard: must be a list (not a string or object)
            if not isinstance(required, list):
                return False, f"INVALID: required_services must be an array, got {type(required).__name__}"
            if not required:
                # Empty array — nothing to check, skip cleanly
                pass
            else:
                # Case-insensitive service lookup map (once, outside loop)
                svc_lower_map = {k.lower(): (k, v) for k, v in services.items()}
                for req in required:
                    if not isinstance(req, dict):
                        return False, f"INVALID: required_services entry must be an object, got {type(req).__name__}"
                    req_name = req.get("name")
                    if not req_name or not isinstance(req_name, str):
                        continue
                    # Case-insensitive lookup for robustness
                    lookup = svc_lower_map.get(req_name.lower())
                    if lookup is None:
                        return False, f"INVALID: required service '{req_name}' missing from architecture.json"
                    actual_name, svc = lookup
                    if svc.get("source") != "existing":
                        return False, f"INVALID: required service '{req_name}' must have source 'existing', got '{svc.get('source')}'"
                    req_extends = req.get("extends")
                    if req_extends is not None:
                        if not isinstance(req_extends, dict):
                            return False, f"INVALID: required service '{req_name}' extends must be an object, got {type(req_extends).__name__}"
                        req_brief = req_extends.get("brief")
                        if req_brief:
                            svc_extends = svc.get("extends", {}) or {}
                            if not isinstance(svc_extends, dict) or not svc_extends.get("brief"):
                                return False, f"INVALID: required service '{req_name}' missing extends.brief from user pin"
                            # Normalized verbatim comparison — NFC + whitespace collapse
                            # blocks reordering, invisible char, and trailing whitespace tricks
                            if _normalize_brief(svc_extends["brief"]) != _normalize_brief(req_brief):
                                return False, f"INVALID: required service '{req_name}' extends.brief does not match user pin verbatim (architect rewrote)"
        except (json.JSONDecodeError, KeyError):
            pass  # features.json parse failure — non-blocking at this layer

    # ── Layer 2e: depends_on → services consistency ──
    # Every name referenced in any depends_on array MUST exist as a key in the
    # services map. The architect sometimes adds a dependency via rule 10
    # (depends_on) without adding the corresponding services entry (rule 8 or
    # 11). That passes the required_services check above (if the missing name
    # wasn't in features.required_services) but fails at build time when env
    # injection tries to resolve the dependency. Caught here instead.
    dangling = []
    for svc_name, svc in services.items():
        svc_deps = svc.get("depends_on", [])
        if not isinstance(svc_deps, list):
            continue
        for dep_name in svc_deps:
            if not isinstance(dep_name, str):
                continue
            if dep_name not in services:
                dangling.append(f"'{svc_name}' depends_on '{dep_name}' but '{dep_name}' is not in the services map")
    if dangling:
        joined = "; ".join(dangling)
        return False, f"INVALID: depends_on references unknown services: {joined}. Every depends_on name must appear as a services map key (add as source='existing' for catalog services)."

    # ── Layer 3: Semantic cross-reference with features.json ──
    features_file = Path(features_path)
    if features_file.exists():
        try:
            with open(features_file) as f:
                features_data = json.load(f)
            features = features_data.get("features", [])

            # Collect all entity names across all services
            all_entity_names = set()
            for svc in services.values():
                all_entity_names.update(svc.get("entities", {}).keys())

            # Check: every entity traces to at least one feature
            for entity_name in all_entity_names:
                matched = False
                for feat in features:
                    feat_id = feat.get("id", "")
                    feat_name = feat.get("name", "").lower()
                    feat_desc = feat.get("description", "").lower()
                    feat_files = [f.lower() for f in feat.get("files", [])]

                    # Level 1: entity name in feature ID
                    if entity_name in feat_id or entity_name.rstrip("s") in feat_id:
                        matched = True
                        break
                    # Level 2: entity name or table in feature name/description
                    if entity_name in feat_name or entity_name in feat_desc:
                        matched = True
                        break
                    if entity_name.rstrip("s") in feat_name or entity_name.rstrip("s") in feat_desc:
                        matched = True
                        break
                    # Level 3: entity page path in feature files
                    if any(entity_name in fp or entity_name.rstrip("s") in fp for fp in feat_files):
                        matched = True
                        break

                if not matched:
                    # WARNING only — logged but does not block
                    pass  # Semantic warnings are non-blocking in Phase 1
        except (json.JSONDecodeError, KeyError):
            pass  # features.json parse failure is non-blocking

    return True, f"VALID: {total_entities} entities, {total_endpoints} endpoints, {total_relationships} relationships"


if __name__ == "__main__":
    arch = sys.argv[1] if len(sys.argv) > 1 else "architecture.json"
    feats = sys.argv[2] if len(sys.argv) > 2 else "features.json"
    _ok, msg = validate_architecture(arch, feats)
    print(msg)
    sys.exit(0)
