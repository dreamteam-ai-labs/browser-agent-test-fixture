"""
Entity Model — Extracts entity relationships from features.json + discovered pages.

TEMPORARY: This is a fuzzy extraction (~70% accurate). It will be replaced by
architecture.json when the Architect Session (Session 0) is implemented.
See: memory/project_architecture_decisions_pending.md

The interface contract is STABLE — consumers (qa-smoke-test.py, validate-browser-crud.py)
use the entity model dict regardless of source. When architecture.json lands, swap
extract_from_features() for load_from_architecture(). No downstream changes needed.

Entity model structure:
{
    "expenses": {
        "page": "/expenses",
        "display_name": "Expenses",
        "crud": ["create", "read", "update", "delete"],
        "depends_on": ["categories"],
        "foreign_keys": {"category_id": "categories"},
        "fields": ["amount", "category_id", "description", "date", "currency"],
        "test_data": {"amount": 25.50, "currency": "GBP", "description": "Test expense"}
    }
}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SKIP_UI_PAGES = {
    "login", "register", "signup", "auth", "callback",
    "settings", "profile", "account", "api",
}

# Pages that are view-only (no CRUD)
VIEW_ONLY_INDICATORS = {
    "dashboard", "analytics", "reports", "summary", "overview", "home",
}

# Default test values by field type pattern
DEFAULT_TEST_VALUES = {
    "amount": 25.50,
    "price": 19.99,
    "cost": 10.00,
    "quantity": 1,
    "limit": 200.00,
    "threshold": 80,
    "name": "Test Item",
    "title": "Test Title",
    "description": "Test description",
    "email": "test@example.com",
    "currency": "GBP",
    "date": "2026-04-01",
    "colour": "#3B82F6",
    "color": "#3B82F6",
}


def toposort_entities(entity_model: dict) -> list[str]:
    """Topological sort: dependencies first."""
    ordered = []
    visited = set()

    def visit(name):
        if name in visited:
            return
        visited.add(name)
        for dep in entity_model.get(name, {}).get("depends_on", []):
            if dep in entity_model:
                visit(dep)
        ordered.append(name)

    for name in entity_model:
        visit(name)
    return ordered


def discover_pages() -> list[str]:
    """Discover UI pages from frontend/src/app/*/page.tsx."""
    app_dir = Path("frontend/src/app")
    if not app_dir.exists():
        return []
    pages = []
    for d in sorted(app_dir.iterdir()):
        if not d.is_dir() or d.name.startswith(("_", ".", "(")):
            continue
        if d.name.lower() in SKIP_UI_PAGES:
            continue
        if any((d / f"page.{ext}").exists() for ext in ("tsx", "jsx", "ts", "js")):
            pages.append(d.name)
    return pages


def _normalise(name: str) -> str:
    """Normalise a name for fuzzy matching: lowercase, strip hyphens/underscores, singularise."""
    n = name.lower().replace("-", "").replace("_", "")
    # Simple singularisation: categories → category, expenses → expense
    if n.endswith("ies") and len(n) > 4:
        n = n[:-3] + "y"
    elif n.endswith("es") and len(n) > 4:
        n = n[:-2]
    elif n.endswith("s") and len(n) > 3:
        n = n[:-1]
    return n


def _extract_endpoints_from_desc(desc: str) -> dict[str, str]:
    """Extract API endpoints from a feature description.

    Returns dict mapping CRUD operation to endpoint:
    {"create": "POST /api/expenses", "list": "GET /api/expenses", ...}
    """
    endpoints = {}
    # Find all HTTP method + path pairs
    for match in re.finditer(r'(GET|POST|PUT|PATCH|DELETE)\s+(/api/[^\s.,;)]+)', desc):
        method = match.group(1)
        path = match.group(2).rstrip('.')

        if method == 'POST' and '{' not in path:
            endpoints["create"] = f"{method} {path}"
        elif method == 'GET' and '{id}' in path:
            endpoints["read_one"] = f"{method} {path}"
        elif method == 'GET' and '{' not in path:
            # Could be list or a specific endpoint
            if 'export' in path:
                endpoints["export"] = f"{method} {path}"
            elif 'summary' in path or 'status' in path or 'alert' in path:
                endpoints["summary"] = f"{method} {path}"
            else:
                endpoints["list"] = f"{method} {path}"
        elif method in ('PUT', 'PATCH') and '{id}' in path:
            endpoints["update"] = f"{method} {path}"
        elif method == 'DELETE' and '{id}' in path:
            endpoints["delete"] = f"{method} {path}"

    return endpoints


def _extract_fields_from_desc(desc: str) -> list[str]:
    """Extract field names from a feature description.

    Looks for patterns like:
    - (amount, category_id, description, date, currency)
    - amount DECIMAL, name TEXT
    - {amount, description}
    """
    fields = set()

    # Pattern 1: parenthesised lists — POST /api/expenses (amount, category_id, ...)
    for match in re.finditer(r'\(([^)]{5,})\)', desc):
        for part in match.group(1).split(','):
            word = part.strip().split()[0].lower()
            if word.isidentifier() and word not in ('id', 'pk', 'fk', 'not', 'null', 'unique', 'default'):
                fields.add(word)

    # Pattern 2: column definitions — amount DECIMAL, name TEXT NOT NULL
    for match in re.finditer(r'(\w+)\s+(?:UUID|TEXT|DECIMAL|INT|INTEGER|BOOLEAN|TIMESTAMP|VARCHAR|DATE)\b', desc, re.IGNORECASE):
        word = match.group(1).lower()
        if word not in ('id', 'returns', 'with', 'the', 'and', 'set'):
            fields.add(word)

    # Remove common non-field words
    noise = {'create', 'read', 'update', 'delete', 'list', 'get', 'post', 'put',
             'returns', 'endpoint', 'api', 'user', 'authenticated', 'paginated',
             'the', 'and', 'with', 'for', 'from', 'each', 'any', 'all', 'large',
             'small', 'new', 'old', 'total', 'by', 'on', 'in', 'of', 'to', 'a',
             'default', 'defaults', 'only', 'custom', 'distinct', 'optional',
             'required', 'returns', 'array', 'object', 'string', 'number', 'boolean'}
    fields -= noise
    # Only keep fields that look like database column names (contain _ or are short common nouns)
    fields = {f for f in fields if '_' in f or (len(f) <= 12 and f.isalpha())}

    return sorted(fields)


def _extract_foreign_keys(fields: list[str], all_entities: set[str]) -> dict[str, str]:
    """Detect foreign key fields — fields ending in _id that reference another entity."""
    fks = {}
    for field in fields:
        if field.endswith("_id"):
            ref_name = field[:-3]  # category_id → category
            ref_norm = _normalise(ref_name)  # category → category
            for entity in all_entities:
                entity_norm = _normalise(entity)  # categories → category
                if ref_norm == entity_norm:
                    fks[field] = entity
                    break
    return fks


def _infer_cardinality(field_name: str) -> str:
    """Infer cardinality from FK field name.

    TEMPORARY: fuzzy inference. FUTURE: architecture.json provides this.

    Returns: "many_to_one" | "many_to_many" | "one_to_one"
    """
    # category_ids (plural) or a join table → many-to-many
    if field_name.endswith("_ids"):
        return "many_to_many"
    # category_id (singular) → many-to-one (most common)
    if field_name.endswith("_id"):
        return "many_to_one"
    return "many_to_one"  # default


def _build_relationships(entity_model: dict) -> list[dict]:
    """Build explicit relationship list from foreign keys across all entities.

    Returns list of:
    {"from": "expenses", "to": "categories", "field": "category_id",
     "cardinality": "many_to_one", "type": "parent_child"}
    """
    relationships = []
    for name, entity in entity_model.items():
        for fk_field, target in entity.get("foreign_keys", {}).items():
            relationships.append({
                "from": name,
                "to": target,
                "field": fk_field,
                "cardinality": _infer_cardinality(fk_field),
                "type": "parent_child",  # target is parent, name is child
            })
    return relationships


def _detect_crud(desc: str, page_name: str, feature_id: str = "") -> list[str]:
    """Detect CRUD capabilities from feature description and feature ID."""
    desc_lower = (desc + " " + feature_id).lower()

    # View-only pages
    if _normalise(page_name) in VIEW_ONLY_INDICATORS:
        return []

    # Explicit CRUD keyword or "managing" pattern
    if "crud" in desc_lower or "managing" in desc_lower or "management" in desc_lower:
        return ["create", "read", "update", "delete"]

    ops = []
    if any(kw in desc_lower for kw in ["create", "post /", "post/", "add ", "new ", "creates "]):
        ops.append("create")
    if any(kw in desc_lower for kw in ["list", "get /", "read", "fetch", "display", "view", "paginated"]):
        ops.append("read")
    if any(kw in desc_lower for kw in ["update", "put /", "edit", "modify", "patch /"]):
        ops.append("update")
    if any(kw in desc_lower for kw in ["delete", "remove"]):
        ops.append("delete")

    # Default: if a page exists and has a backend feature, assume at least read
    if not ops:
        ops.append("read")

    return ops


def _generate_test_data(fields: list[str], foreign_keys: dict[str, str]) -> dict:
    """Generate test data for entity creation based on field names."""
    data = {}
    for field in fields:
        if field in foreign_keys:
            continue  # FK fields filled by dependency, not test data
        if field in DEFAULT_TEST_VALUES:
            data[field] = DEFAULT_TEST_VALUES[field]
        elif "name" in field:
            data[field] = "Test Item"
        elif "date" in field or "time" in field:
            data[field] = "2026-04-01"
        elif "amount" in field or "price" in field or "cost" in field or "limit" in field:
            data[field] = 25.50
    return data


def _make_display_name(page_name: str) -> str:
    """Generate a human-readable display name from a page directory name."""
    return page_name.replace("-", " ").replace("_", " ").title()


def extract_from_features(features_json_path: str = "features.json",
                          pages: list[str] | None = None) -> dict:
    """Extract entity model from features.json + discovered pages.

    TEMPORARY fuzzy extraction. Will be replaced by load_from_architecture().

    Returns entity model dict keyed by page name.
    """
    if pages is None:
        pages = discover_pages()

    # Load features
    features = []
    try:
        with open(features_json_path) as f:
            data = json.load(f)
        features = [f for f in data.get("features", []) if f.get("status") in ("completed", "done")]
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Index features by normalised name for matching
    backend_features = {}
    ui_features = {}
    for feat in features:
        fid = feat.get("id", "")
        tags = feat.get("tags", [])
        if "backend" in tags:
            backend_features[fid] = feat
        if "ui" in tags or "frontend" in tags:
            ui_features[fid] = feat

    all_entity_names = set(pages)
    model = {}

    for page in pages:
        page_norm = _normalise(page)

        # Find matching backend feature
        backend_feat = None
        for fid, feat in backend_features.items():
            if page_norm in _normalise(fid):
                backend_feat = feat
                break

        # Find matching UI feature
        ui_feat = None
        for fid, feat in ui_features.items():
            if page_norm in _normalise(fid):
                ui_feat = feat
                break

        # Use whichever has a description (prefer backend for CRUD info)
        desc = ""
        if backend_feat:
            desc = backend_feat.get("description", "")
        elif ui_feat:
            desc = ui_feat.get("description", "")

        # Extract entity info
        feat_id = (backend_feat or ui_feat or {}).get("id", "")
        crud = _detect_crud(desc, page, feat_id)
        fields = _extract_fields_from_desc(desc)
        foreign_keys = _extract_foreign_keys(fields, all_entity_names)
        test_data = _generate_test_data(fields, foreign_keys)
        endpoints = _extract_endpoints_from_desc(desc)

        # Also check UI feature description for additional endpoints
        if ui_feat and ui_feat != backend_feat:
            ui_desc = ui_feat.get("description", "")
            ui_endpoints = _extract_endpoints_from_desc(ui_desc)
            for k, v in ui_endpoints.items():
                if k not in endpoints:
                    endpoints[k] = v

        # Dependencies from foreign keys
        depends_on = sorted(set(foreign_keys.values()))

        entry = {
            "page": f"/{page}",
            "display_name": _make_display_name(page),
            "crud": crud,
            "depends_on": depends_on,
            "foreign_keys": foreign_keys,
            "fields": fields,
            "test_data": test_data,
            "endpoints": endpoints,
        }

        if not crud:
            entry["type"] = "view_only"

        model[page] = entry

    # Add cardinality info to each FK
    for name, entity in model.items():
        entity["foreign_key_details"] = {
            fk_field: {
                "target": target,
                "cardinality": _infer_cardinality(fk_field),
            }
            for fk_field, target in entity.get("foreign_keys", {}).items()
        }

    return model


def get_relationships(entity_model: dict) -> list[dict]:
    """Get explicit relationship list from an entity model."""
    return _build_relationships(entity_model)


def load_from_architecture(architecture_json_path: str = "architecture.json") -> dict:
    """Load entity model from architecture.json (Architect Session output).

    Reads the services → entities → ui section and produces the same interface
    contract as extract_from_features(). Consumers get identical output regardless
    of source.
    """
    try:
        with open(architecture_json_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    # Navigate services nesting (v1.0 schema)
    services = data.get("services", {})
    if services:
        # Filter to build_new services (skip existing deployed services)
        build_new = {k: v for k, v in services.items() if v.get("source") != "existing"}
        if not build_new:
            return {}
        first_service = next(iter(build_new.values()))
        entities = first_service.get("entities", {})
    else:
        # Fallback: flat "entities" key (pre-v1.0 format)
        entities = data.get("entities", {})

    if not entities:
        return {}

    model = {}
    for entity_name, entity in entities.items():
        ui = entity.get("ui", {})
        page = ui.get("page", "")
        if not page:
            continue

        page_key = page.lstrip("/")
        fields_raw = entity.get("fields", {})
        field_names = [k for k in fields_raw if not fields_raw[k].get("pk")]
        fks = {k: v["fk"].split(".")[0] for k, v in fields_raw.items() if v.get("fk")}

        # Build endpoint strings (e.g., "POST /api/expenses")
        endpoints = {}
        for ep_name, ep in entity.get("endpoints", {}).items():
            method = ep.get("method", "")
            path = ep.get("path", "")
            if method and path:
                endpoints[ep_name] = f"{method} {path}"

        # Generate test data from field definitions
        test_data = {}
        for fname in field_names:
            if fname in fks:
                continue  # FK fields filled by dependency
            field_def = fields_raw.get(fname, {})
            # Check DEFAULT_TEST_VALUES first
            if fname in DEFAULT_TEST_VALUES:
                test_data[fname] = DEFAULT_TEST_VALUES[fname]
            elif field_def.get("enum"):
                test_data[fname] = field_def["enum"][0]
            elif field_def.get("default") is not None:
                test_data[fname] = field_def["default"]
            elif "name" in fname:
                test_data[fname] = "Test Item"
            elif "date" in fname or "time" in fname:
                test_data[fname] = "2026-04-01"
            elif field_def.get("type") in ("decimal", "integer"):
                test_data[fname] = 10
            elif field_def.get("type") == "boolean":
                test_data[fname] = True
            elif field_def.get("type") == "string":
                test_data[fname] = f"Test {fname}"

        entry = {
            "page": page,
            "display_name": ui.get("display_name", _make_display_name(page_key)),
            "crud": ui.get("crud", []),
            "depends_on": sorted(set(fk_target for fk_target in fks.values())),
            "foreign_keys": fks,
            "fields": field_names,
            "test_data": test_data,
            "endpoints": endpoints,
        }

        if not entry["crud"]:
            entry["type"] = "view_only"

        model[page_key] = entry

    # Add cardinality info to each FK (same as extract_from_features output)
    for name, entity_entry in model.items():
        entity_entry["foreign_key_details"] = {
            fk_field: {
                "target": target,
                "cardinality": _infer_cardinality(fk_field),
            }
            for fk_field, target in entity_entry.get("foreign_keys", {}).items()
        }

    return model


def get_entity_model(features_path: str = "features.json",
                     architecture_path: str = "architecture.json",
                     pages: list[str] | None = None) -> dict:
    """Get entity model — prefers architecture.json, falls back to fuzzy extraction.

    This is the primary entry point. Consumers call this and get the same
    interface regardless of source.
    """
    # Prefer architecture.json (deterministic) over fuzzy extraction
    arch_model = load_from_architecture(architecture_path)
    if arch_model:
        return arch_model

    # Fallback: fuzzy extraction from features.json
    return extract_from_features(features_path, pages)


# ── CLI test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    model = get_entity_model()
    print(json.dumps(model, indent=2))

    # Summary
    print(f"\n=== Entity Model Summary ===")
    for name, entity in model.items():
        crud = ", ".join(entity["crud"]) if entity["crud"] else "view-only"
        deps = ", ".join(entity["depends_on"]) if entity["depends_on"] else "none"
        fks = ", ".join(f"{k}→{v}" for k, v in entity["foreign_keys"].items()) if entity["foreign_keys"] else "none"
        eps = ", ".join(entity.get("endpoints", {}).values()) or "none"
        print(f"  {name}: crud=[{crud}] deps=[{deps}] fks=[{fks}] fields={len(entity['fields'])}")
        print(f"    endpoints: {eps}")
