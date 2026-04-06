"""
API CRUD Tester — Entity-model-driven API testing.

Uses entity_model.py to determine what entities exist, their CRUD operations,
endpoints, fields, dependencies, and test data. Runs curl-based tests against
each entity in dependency order.

TEMPORARY: Uses fuzzy entity model from features.json.
FUTURE: Swaps to architecture.json when Architect Session ships.

The API CRUD results use the same contract as browser CRUD results:
{"entity": "expenses", "page": "/expenses", "tests": {"create": "pass", ...}}

This allows the quality gate to compare API vs UI test results side-by-side.

Usage:
    python3 scripts/api_crud_tester.py [--backend-url http://localhost:8000]

Requires: auth token (registers a test user automatically).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error

BACKEND_URL = "http://localhost:8000"


def log(msg):
    print(f"[api-crud] {msg}", file=sys.stderr, flush=True)


def _extract_id(body):
    """Extract item ID from any API response format.

    Handles:
    - {"id": "..."} — direct
    - {"expense": {"id": "..."}} — nested under entity name
    - {"data": {"id": "..."}} — nested under data
    - {"uuid": "..."} — alternative key
    """
    if not isinstance(body, dict):
        return None
    # Direct
    for key in ("id", "uuid", "_id"):
        if key in body and body[key]:
            return str(body[key])
    # Nested: look one level deep for any dict with an id
    for key, value in body.items():
        if isinstance(value, dict):
            for id_key in ("id", "uuid", "_id"):
                if id_key in value and value[id_key]:
                    return str(value[id_key])
    return None


def http(method, url, data=None, token=None, timeout=15):
    """Make an HTTP request. Returns (status_code, parsed_body)."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return e.code, {"error": raw[:200]}
    except Exception as e:
        return 0, {"error": str(e)}


def register_and_login(backend_url):
    """Register a test user and return auth token."""
    import uuid
    email = f"api-crud-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "TestPass123!"

    log(f"Registering test user: {email}")
    status, body = http("POST", f"{backend_url}/api/auth/register", {
        "email": email, "password": password, "display_name": "API CRUD Tester",
    })

    if status not in (200, 201):
        log(f"  Registration failed: HTTP {status} — {body}")
        return None, None, None

    # Login
    status, body = http("POST", f"{backend_url}/api/auth/login", {
        "email": email, "password": password,
    })

    if status != 200:
        log(f"  Login failed: HTTP {status} — {body}")
        return None, None, None

    token = body.get("access_token") or body.get("token") or body.get("idToken") or body.get("id_token")
    if not token:
        log(f"  No token in login response: {list(body.keys())}")
        return None, None, None

    log(f"  Auth OK — token obtained")
    return email, password, token


def _run_entity_crud(name, entity, backend_url, token, created_ids, skip_delete=False):
    """Run create/read/update (and optionally delete) for a single entity.

    Returns (entity_results dict, created_item_id or None).
    """
    endpoints = entity.get("endpoints", {})
    crud = entity.get("crud", [])
    test_data = dict(entity.get("test_data", {}))
    fks = entity.get("foreign_keys", {})
    display = entity.get("display_name", name.title())

    log(f"\n── {display} ──")
    entity_results = {}
    item_id = None

    if not crud and not endpoints:
        if "summary" in endpoints or "list" in endpoints:
            ep = endpoints.get("summary") or endpoints.get("list")
            method, path = ep.split(" ", 1)
            path = path.split("?")[0]
            status, body = http(method, f"{backend_url}{path}", token=token)
            entity_results["read"] = "pass" if 200 <= status < 300 else "fail"
            log(f"  READ ({ep}): {'PASS' if entity_results['read'] == 'pass' else 'FAIL'} — HTTP {status}")
        else:
            entity_results["renders"] = "skip"
            log(f"  No API endpoints — skip")
        return entity_results, None

    # Resolve foreign keys from previously created entities
    for fk_field, fk_entity in fks.items():
        if fk_entity in created_ids:
            test_data[fk_field] = created_ids[fk_entity]
            log(f"  FK: {fk_field} = {created_ids[fk_entity]} (from {fk_entity})")

    # ── CREATE ──
    if "create" in crud and "create" in endpoints:
        ep = endpoints["create"]
        method, path = ep.split(" ", 1)
        status, body = http(method, f"{backend_url}{path}", data=test_data, token=token)
        if 200 <= status < 300:
            entity_results["create"] = "pass"
            item_id = _extract_id(body)
            log(f"  CREATE ({ep}): PASS — HTTP {status}, id={item_id}")
        else:
            entity_results["create"] = "fail"
            log(f"  CREATE ({ep}): FAIL — HTTP {status} — {json.dumps(body)[:100]}")

    # ── READ (list) ──
    if "read" in crud and "list" in endpoints:
        ep = endpoints["list"]
        method, path = ep.split(" ", 1)
        path = path.split("?")[0]
        status, body = http(method, f"{backend_url}{path}", token=token)
        if 200 <= status < 300:
            items = body if isinstance(body, list) else body.get("items", body.get("data", []))
            if isinstance(items, list) and item_id:
                found = any(str(i.get("id")) == str(item_id) for i in items)
                entity_results["read"] = "pass" if found else "fail"
                log(f"  READ ({ep}): {'PASS' if found else 'FAIL — item not in list'} — HTTP {status}, {len(items)} items")
            else:
                entity_results["read"] = "pass"
                log(f"  READ ({ep}): PASS — HTTP {status}")
        else:
            entity_results["read"] = "fail"
            log(f"  READ ({ep}): FAIL — HTTP {status}")

    # ── READ (single) ──
    if "read_one" in endpoints and item_id:
        ep = endpoints["read_one"]
        method, path = ep.split(" ", 1)
        path = path.replace("{id}", str(item_id))
        status, body = http(method, f"{backend_url}{path}", token=token)
        if 200 <= status < 300:
            log(f"  READ ONE ({ep}): PASS — HTTP {status}")
        else:
            log(f"  READ ONE ({ep}): FAIL — HTTP {status}")
            if entity_results.get("read") != "pass":
                entity_results["read"] = "fail"

    # ── UPDATE ──
    if "update" in crud and "update" in endpoints and item_id:
        ep = endpoints["update"]
        method, path = ep.split(" ", 1)
        path = path.replace("{id}", str(item_id))
        # Send all non-FK fields with one field modified
        # This avoids 422 from missing required fields
        # Skip fields that look like constrained formats (hex colours, emails, dates, UUIDs)
        FORMAT_FIELDS = {"colour", "color", "email", "date", "uuid", "id", "url", "uri", "phone"}
        update_data = dict(test_data)
        modified = False
        for field, value in update_data.items():
            if field in fks or field in FORMAT_FIELDS:
                continue
            if isinstance(value, str) and not value.startswith("#") and "@" not in value:
                update_data[field] = value + " Updated"
                modified = True
                break
            elif isinstance(value, (int, float)):
                update_data[field] = round(value * 1.5, 2)
                modified = True
                break
        if not modified:
            # No modifiable field found — send as-is (idempotent update)
            pass
        status, body = http(method, f"{backend_url}{path}", data=update_data, token=token)
        entity_results["update"] = "pass" if 200 <= status < 300 else "fail"
        log(f"  UPDATE ({ep}): {'PASS' if entity_results['update'] == 'pass' else 'FAIL'} — HTTP {status}")
        if entity_results["update"] == "fail":
            log(f"    Detail: {json.dumps(body)[:150]}")

    # ── DELETE (only if not deferred) ──
    if not skip_delete and "delete" in crud and "delete" in endpoints and item_id:
        ep = endpoints["delete"]
        method, path = ep.split(" ", 1)
        path = path.replace("{id}", str(item_id))
        status, body = http(method, f"{backend_url}{path}", token=token)
        entity_results["delete"] = "pass" if 200 <= status < 300 else "fail"
        log(f"  DELETE ({ep}): {'PASS' if entity_results['delete'] == 'pass' else 'FAIL'} — HTTP {status}")
        if entity_results["delete"] == "pass" and "read_one" in endpoints:
            verify_ep = endpoints["read_one"]
            _, verify_path = verify_ep.split(" ", 1)
            verify_path = verify_path.replace("{id}", str(item_id))
            v_status, _ = http("GET", f"{backend_url}{verify_path}", token=token)
            log(f"  DELETE VERIFY: {'PASS — item gone (404)' if v_status == 404 else f'WARN — HTTP {v_status}'}")

    # ── SUMMARY/EXPORT endpoints ──
    for ep_type in ("summary", "export"):
        if ep_type in endpoints:
            ep = endpoints[ep_type]
            method, path = ep.split(" ", 1)
            path = path.split("|")[0].split("?")[0]
            status, body = http(method, f"{backend_url}{path}", token=token)
            entity_results[ep_type] = "pass" if 200 <= status < 300 else "fail"
            log(f"  {ep_type.upper()} ({ep}): {'PASS' if entity_results[ep_type] == 'pass' else 'FAIL'} — HTTP {status}")

    # Mark untested operations
    for op in crud:
        if op not in entity_results:
            entity_results[op] = "not_tested"

    return entity_results, item_id


def run_api_crud_tests(entity_model, backend_url, token):
    """Run API CRUD tests in two passes:

    Pass 1: Create/Read/Update for all entities (dependency order).
    Pass 2: Delete for all entities (reverse dependency order — children first).

    This ensures parent entities exist while children are being tested.
    """
    try:
        from scripts.entity_model import toposort_entities
    except ImportError:
        sys.path.insert(0, ".")
        from scripts.entity_model import toposort_entities
    ordered = toposort_entities(entity_model)

    log(f"\nTesting {len(ordered)} entities in dependency order: {', '.join(ordered)}")

    results = {}
    created_ids = {}

    # ── Pass 1: Create/Read/Update (skip delete) ──
    log(f"\n{'='*40}")
    log(f"Pass 1: Create / Read / Update")
    log(f"{'='*40}")
    for name in ordered:
        entity_results, item_id = _run_entity_crud(
            name, entity_model[name], backend_url, token, created_ids, skip_delete=True)
        results[name] = entity_results
        if item_id:
            created_ids[name] = item_id

    # ── Pass 2: Delete (reverse order — children before parents) ──
    log(f"\n{'='*40}")
    log(f"Pass 2: Delete (reverse dependency order)")
    log(f"{'='*40}")
    for name in reversed(ordered):
        entity = entity_model[name]
        crud = entity.get("crud", [])
        endpoints = entity.get("endpoints", {})
        display = entity.get("display_name", name.title())

        if "delete" not in crud or "delete" not in endpoints or name not in created_ids:
            continue

        ep = endpoints["delete"]
        method, path = ep.split(" ", 1)
        path = path.replace("{id}", str(created_ids[name]))
        log(f"\n── {display}: DELETE ──")
        status, body = http(method, f"{backend_url}{path}", token=token)
        results[name]["delete"] = "pass" if 200 <= status < 300 else "fail"
        log(f"  DELETE ({ep}): {'PASS' if results[name]['delete'] == 'pass' else 'FAIL'} — HTTP {status}")

        # Verify deletion
        if results[name]["delete"] == "pass" and "read_one" in endpoints:
            verify_ep = endpoints["read_one"]
            _, verify_path = verify_ep.split(" ", 1)
            verify_path = verify_path.replace("{id}", str(created_ids[name]))
            v_status, _ = http("GET", f"{backend_url}{verify_path}", token=token)
            log(f"  DELETE VERIFY: {'PASS — item gone (404)' if v_status == 404 else f'WARN — HTTP {v_status}'}")

    return results, created_ids


def build_crud_contract(results, entity_model):
    """Convert API test results to browser_crud_results contract format."""
    crud_results = []
    for name, tests in results.items():
        if tests:
            entity = entity_model.get(name, {})
            crud_results.append({
                "entity": name,
                "page": entity.get("page", f"/{name}"),
                "tests": tests,
            })
    return crud_results


def write_to_qa_report(api_results, qa_report_path="qa-report.json"):
    """Write api_crud_results into qa-report.json."""
    from pathlib import Path
    report = {}
    rpath = Path(qa_report_path)
    if rpath.exists():
        try:
            report = json.loads(rpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    report["api_crud_results"] = api_results
    if "latest" in report and isinstance(report["latest"], dict):
        report["latest"]["api_crud_results"] = api_results
    rpath.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Entity-model-driven API CRUD tester")
    parser.add_argument("--backend-url", default=BACKEND_URL)
    args = parser.parse_args()

    log("=" * 60)
    log("API CRUD TESTER — entity-model-driven")
    log("=" * 60)

    # Load entity model
    sys.path.insert(0, ".")
    try:
        from scripts.entity_model import get_entity_model
    except ImportError:
        from entity_model import get_entity_model

    model = get_entity_model()
    if not model:
        log("ERROR: No entity model available")
        sys.exit(1)

    log(f"\nEntity model: {len(model)} entities")
    for name, ent in model.items():
        crud = ", ".join(ent["crud"]) if ent["crud"] else "view-only"
        eps = len(ent.get("endpoints", {}))
        log(f"  {name}: [{crud}] {eps} endpoints")

    # Auth
    email, password, token = register_and_login(args.backend_url)
    if not token:
        log("ERROR: Auth failed — cannot run API tests")
        sys.exit(1)

    # Run tests
    results, created_ids = run_api_crud_tests(model, args.backend_url, token)

    # Build contract
    crud_contract = build_crud_contract(results, model)

    # Summary
    log(f"\n{'=' * 60}")
    log("API CRUD Summary")
    log(f"{'=' * 60}")
    total_pass = 0
    total_fail = 0
    total_skip = 0
    for entry in crud_contract:
        tests = entry["tests"]
        tests_str = ", ".join(f"{k}={v}" for k, v in tests.items())
        passes = sum(1 for v in tests.values() if v == "pass")
        fails = sum(1 for v in tests.values() if v == "fail")
        total_pass += passes
        total_fail += fails
        total_skip += sum(1 for v in tests.values() if v not in ("pass", "fail"))
        icon = "✓" if fails == 0 else "✗"
        log(f"  {icon} {entry['entity']}: {tests_str}")

    log(f"\nTotal: {total_pass} pass, {total_fail} fail, {total_skip} skip")
    log(f"{'=' * 60}")

    # Write results
    write_to_qa_report(crud_contract)
    log(f"Written to qa-report.json (api_crud_results)")

    # Stdout: machine-readable
    print(json.dumps({"api_crud_results": crud_contract}, indent=2))

    sys.exit(1 if total_fail > 0 else 0)


if __name__ == "__main__":
    main()
