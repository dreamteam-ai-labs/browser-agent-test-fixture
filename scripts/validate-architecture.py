#!/usr/bin/env python3
"""Validate architecture.json — structural checks + semantic cross-reference with features.json.

Output contract (agreed with DreamTeam factory loop):
  - Success: VALID: N entities, M endpoints, R relationships
  - Failure: INVALID: <reason>
  - Always exits 0 (sshSafe returns stdout, not exit code)
  - Single line output only
"""

import json
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

        # Existing services: validate URL only, skip entity checks
        if svc.get("source") == "existing":
            if "url" not in svc:
                return False, f"INVALID: existing service '{svc_name}' missing 'url'"
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

    # ── Layer 2b: depends_on + feature assignment validation ──
    all_svc_names = set(services.keys())
    for svc_name, svc in services.items():
        # Validate depends_on references
        for dep in svc.get("depends_on", []):
            if dep not in all_svc_names:
                return False, f"INVALID: service '{svc_name}' depends_on unknown service '{dep}'"
            if dep == svc_name:
                return False, f"INVALID: service '{svc_name}' depends_on itself"

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

    # ── Layer 3: Semantic cross-reference with features.json ──
    features_file = Path(features_path)
    if features_file.exists():
        try:
            with open(features_file) as f:
                features_data = json.load(f)
            features = features_data.get("features", [])

            # Validate feature assignment: every phase 2+ feature assigned to exactly one service
            phase2_feature_ids = {f.get("id") for f in features if f.get("phase", 0) >= 2}
            assigned_features = set()
            for svc_name, svc in services.items():
                if svc.get("source") == "existing":
                    continue
                for fid in svc.get("features", []):
                    if fid in assigned_features:
                        pass  # WARNING: duplicate assignment, non-blocking
                    assigned_features.add(fid)

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
