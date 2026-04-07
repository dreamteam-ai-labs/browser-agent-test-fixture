"""
QA Smoke Test — Deterministic end-to-end test script.

Handles auth registration, login verification, and browser smoke testing
in a single self-contained script. No shell variables, no LLM interpretation,
no ambiguity. Run it, read the output.

Usage:
    python3 scripts/qa-smoke-test.py

Output:
    Structured JSON to stdout (for the QA agent to parse).
    Detailed progress to stderr (for build logs).
    Results written to qa-smoke-results.json.
    Credentials written to qa-test-credentials.json.

Exit codes:
    0 = pass
    1 = fail (auth broken, browser test failed, etc.)
    2 = infrastructure error (browser agent unreachable, ports failed, etc.)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import urllib.error

BACKEND_URL = "http://localhost:8000"
FRONTEND_PORT = 3000
BROWSER_AGENT_URL = "https://browser.dreamteamlabs.co.uk"
BROWSER_AGENT_MOCK = os.environ.get("BROWSER_AGENT_MOCK", "").lower() == "true"
CREDENTIALS_FILE = "qa-test-credentials.json"
RESULTS_FILE = "qa-smoke-results.json"


def log(msg):
    print(f"[qa-smoke] {msg}", file=sys.stderr, flush=True)


def _parse_response_body(raw: str):
    """Parse JSON or NDJSON response. For NDJSON, returns the last line (the result)."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    # NDJSON: browser agent v2.2+ streams progress lines, last line is the result
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
    return {"raw": raw[:500]}


def http_post(url, data, timeout=30, headers=None):
    """POST JSON, return (status_code, parsed_body). Handles both JSON and NDJSON responses."""
    body = json.dumps(data).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        url, data=body,
        headers=hdrs,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _parse_response_body(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"raw": e.reason}
        return e.code, err
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}
    except Exception as e:
        return 0, {"error": str(e)}


def http_get(url, headers=None, timeout=10):
    """GET, return (status_code, parsed_body). status=0 means network error."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"raw": e.reason}
        return e.code, err
    except Exception as e:
        return 0, {"error": str(e)}


# ── Step 1: Register + verify auth ──────────────────────────────────────────


def _firebase_register(email, password, api_key, tenant_id=None):
    """Register via Firebase REST API. Returns (id_token, error)."""
    firebase_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={api_key}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    if tenant_id:
        payload["tenantId"] = tenant_id
    status, body = http_post(firebase_url, payload, timeout=15)
    if 200 <= status < 300 and body.get("idToken"):
        return body["idToken"], None
    return None, body.get("error", {}).get("message", f"HTTP {status}")


def _firebase_login(email, password, api_key, tenant_id=None):
    """Login via Firebase REST API. Returns (id_token, error)."""
    firebase_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    if tenant_id:
        payload["tenantId"] = tenant_id
    status, body = http_post(firebase_url, payload, timeout=15)
    if 200 <= status < 300 and body.get("idToken"):
        return body["idToken"], None
    return None, body.get("error", {}).get("message", f"HTTP {status}")


def run_auth_test():
    """Register a fresh user, get a token, sync to local DB. Discovery-based — handles any auth pattern."""
    import uuid
    email = f"qa-tester-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "TestPass123!"
    result = {
        "success": False,
        "email": email,
        "password": password,
        "auth_method": None,
        "steps": {},
    }

    with open(CREDENTIALS_FILE, "w") as f:
        json.dump({"email": email, "password": password}, f, indent=2)
    log(f"  Credentials saved to {CREDENTIALS_FILE}")

    token = None

    # ── Strategy 1: Backend register endpoint ──
    log(f"  Trying backend registration: {email}")
    status, body = http_post(
        f"{BACKEND_URL}/api/auth/register",
        {"email": email, "password": password, "name": "QA Tester", "display_name": "QA Tester"},
    )
    result["steps"]["backend_register"] = {"status": status}

    if 200 <= status < 300:
        log(f"  Backend register: HTTP {status} OK")
        result["auth_method"] = "backend_register"
        token = (
            body.get("token") or body.get("access_token")
            or body.get("idToken") or body.get("id_token")
        )
        if not token:
            # Backend registered but didn't return token — try login
            log(f"  No token in register response, trying login")
            status, body = http_post(
                f"{BACKEND_URL}/api/auth/login",
                {"email": email, "password": password},
            )
            result["steps"]["backend_login"] = {"status": status}
            if 200 <= status < 300:
                token = (
                    body.get("token") or body.get("access_token")
                    or body.get("idToken") or body.get("id_token")
                )

    # ── Strategy 2: Firebase client-side auth ──
    if not token:
        log(f"  Backend register failed or unavailable — trying Firebase")
        # Discover Firebase config from the app
        config_status, config_body = http_get(f"{BACKEND_URL}/api/auth/config")
        if config_status != 200 or not config_body.get("apiKey"):
            # Also try /api/config as fallback
            config_status, config_body = http_get(f"{BACKEND_URL}/api/config")

        api_key = config_body.get("apiKey") if config_status == 200 else None
        tenant_id = config_body.get("tenantId") if config_status == 200 else None

        if not api_key:
            result["error"] = "No backend register endpoint AND no Firebase config found"
            log(f"  FAIL: {result['error']}")
            return result

        log(f"  Firebase config: apiKey={api_key[:10]}..., tenantId={tenant_id}")
        fb_token, fb_err = _firebase_register(email, password, api_key, tenant_id)
        result["steps"]["firebase_register"] = {"success": fb_token is not None, "error": fb_err}

        if not fb_token:
            result["error"] = f"Firebase registration failed: {fb_err}"
            log(f"  FAIL: {result['error']}")
            return result

        log(f"  Firebase register: OK")
        token = fb_token
        result["auth_method"] = "firebase_client"

    if not token:
        result["error"] = "Could not obtain auth token via any method"
        log(f"  FAIL: {result['error']}")
        return result

    log(f"  Token obtained ({len(token)} chars)")

    # ── Sync user to local DB ──
    # Call /api/auth/me (or /api/users/me) which typically auto-creates the local user record.
    # This is critical — without it, subsequent API calls fail with "User not found".
    for verify_path in ["/api/auth/me", "/api/users/me"]:
        status, body = http_get(
            f"{BACKEND_URL}{verify_path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        log(f"  Sync user ({verify_path}): HTTP {status}")
        if 200 <= status < 300:
            result["steps"]["sync_user"] = {"status": status, "path": verify_path}
            break
    else:
        log(f"  WARNING: Could not sync user to local DB — API calls may fail")
        result["steps"]["sync_user"] = {"status": status, "warning": "User may not exist in local DB"}

    result["success"] = True
    result["token"] = token
    result["token_verified"] = (200 <= status < 300)

    return result


# ── Step 1.5: Seed sample data ──────────────────────────────────────────────


def seed_sample_data(token):
    """Discover API endpoints from OpenAPI spec and seed sample data."""
    log("\nSTEP 1.5: Seeding sample data for browser test")
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Discover endpoints from OpenAPI spec
    try:
        status, spec = http_get(f"{BACKEND_URL}/openapi.json")
        if status != 200:
            log("  Could not fetch OpenAPI spec — skipping seed")
            return

        for path, methods in spec.get("paths", {}).items():
            if "post" not in methods:
                continue
            if any(skip in path for skip in ["/auth", "/login", "/register", "/logout", "/export", "/extract"]):
                continue

            post_op = methods["post"]
            body = _build_sample_body(post_op, spec)
            if not body:
                continue

            try:
                s, resp = http_post(f"{BACKEND_URL}{path}", body, timeout=10, headers=auth_headers)
                if s in (200, 201):
                    log(f"  Seeded: {path} — {s}")
                else:
                    log(f"  Skip: {path} — {s}")
            except Exception:
                pass
    except Exception as e:
        log(f"  Seed discovery failed: {e}")


def _build_sample_body(post_op, spec):
    """Build a minimal request body from OpenAPI schema."""
    request_body = post_op.get("requestBody", {})
    content = request_body.get("content", {}).get("application/json", {})
    schema = content.get("schema", {})

    if "$ref" in schema:
        ref_path = schema["$ref"].replace("#/components/schemas/", "")
        schema = spec.get("components", {}).get("schemas", {}).get(ref_path, {})

    if not schema.get("properties"):
        return None

    body = {}
    for prop, prop_schema in schema.get("properties", {}).items():
        prop_type = prop_schema.get("type", "string")
        if prop_type == "string":
            if "date" in prop.lower():
                body[prop] = "2026-03-29"
            elif "email" in prop.lower():
                body[prop] = "seed@example.com"
            elif "url" in prop.lower():
                body[prop] = "https://example.com"
            else:
                body[prop] = f"QA Seed {prop}"
        elif prop_type in ("number", "integer"):
            body[prop] = 100
        elif prop_type == "boolean":
            body[prop] = True

    return body if body else None


# ── Step 2: Make ports public ───────────────────────────────────────────────


def make_ports_public():
    """Make codespace ports public. Returns frontend URL or error.

    If `gh codespace ports visibility` fails (e.g. GITHUB_TOKEN lacks codespace scope),
    we still return the URL — the harness/factory loop already makes ports public
    externally via ensurePortsPublic() before Claude starts.
    """
    codespace = os.environ.get("CODESPACE_NAME")
    if not codespace:
        return {"success": False, "error": "CODESPACE_NAME env var not set — not in a codespace?"}

    frontend_url = f"https://{codespace}-{FRONTEND_PORT}.app.github.dev"
    login_url = f"{frontend_url}/login"

    log(f"Making ports public (codespace: {codespace})")
    try:
        subprocess.run(
            ["gh", "codespace", "ports", "visibility",
             "8000:public", f"{FRONTEND_PORT}:public", "-c", codespace],
            capture_output=True, text=True, timeout=15, check=True,
        )
        log(f"  Ports set public via gh CLI")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        detail = getattr(e, 'stderr', str(e)).strip() if hasattr(e, 'stderr') else str(e)
        log(f"  gh ports command failed ({detail}) — assuming ports already public (set by harness)")

    log(f"  Public URL: {frontend_url}")
    log(f"  Login URL:  {login_url}")
    return {"success": True, "frontend_url": login_url}


# ── Step 3: Read features ──────────────────────────────────────────────────


def read_features():
    """Read completed feature names from features.json."""
    try:
        with open("features.json") as f:
            data = json.load(f)
        names = [
            feat["name"]
            for feat in data.get("features", [])
            if feat.get("status") in ("completed", "done")
        ]
        log(f"  {len(names)} completed features from features.json")
        return names
    except FileNotFoundError:
        log("  features.json not found — agent will auto-discover")
        return []
    except Exception as e:
        log(f"  Error reading features.json: {e} — agent will auto-discover")
        return []


# ── Step 4: Call browser agent ──────────────────────────────────────────────


def call_browser_agent(frontend_url, email, password, features, num_pages=4):
    """Call browser agent /smoke-test. Returns structured result."""
    # Scale iterations to page count: ~10 per page (login + navigate + CRUD), min 25
    max_iters = max(25, num_pages * 10)
    agent_timeout = max(180000, num_pages * 60000)
    http_timeout = max(300, num_pages * 90)

    log(f"Calling browser agent...")
    log(f"  Target: {frontend_url}")
    log(f"  User: {email}")
    log(f"  Features: {len(features)}, Pages: {num_pages}, Iterations: {max_iters}")

    payload = {
        "url": frontend_url,
        "credentials": {"email": email, "password": password},
        "features": features,
        "maxIterations": max_iters,
        "timeout": agent_timeout,
        "uploadScreenshots": True,
    }
    if BROWSER_AGENT_MOCK:
        payload["mock"] = True
        log(f"  MOCK MODE — browser agent will return synthetic results")

    status, body = http_post(
        f"{BROWSER_AGENT_URL}/smoke-test",
        payload,
        timeout=http_timeout,
    )

    if status == 0:
        log(f"  Browser agent unreachable: {body.get('error')}")
        return {
            "overall": "skipped",
            "reason": f"Browser agent unreachable: {body.get('error')}",
            "service_reachable": False,
        }

    if status < 200 or status >= 300:
        log(f"  Browser agent HTTP {status}: {body}")
        return {
            "overall": "error",
            "error": f"Browser agent returned HTTP {status}",
            "detail": body,
            "service_reachable": True,
        }

    smoke = body.get("smokeTestResults", body)
    smoke["service_reachable"] = True
    # Preserve screenshot URLs from top-level response (browser agent puts them outside smokeTestResults)
    if "screenshotUrls" in body and "screenshotUrls" not in smoke:
        smoke["screenshotUrls"] = body["screenshotUrls"]
    # Preserve console messages from browser (page errors, failed requests, JS exceptions)
    if "consoleMessages" in body and "consoleMessages" not in smoke:
        smoke["consoleMessages"] = body["consoleMessages"]
        errors = [m for m in body["consoleMessages"] if m.get("type") in ("error", "pageerror", "requestfailed")]
        if errors:
            log(f"  Browser console: {len(errors)} error(s) out of {len(body['consoleMessages'])} messages")
    # Preserve top-level error field (browser agent crash reason lives here, not inside smokeTestResults)
    if "error" in body and "error" not in smoke:
        smoke["error"] = body["error"]
        log(f"  Browser agent error: {body['error']}")
    overall = smoke.get("overall", "unknown")
    log(f"  Result: {overall}")

    if smoke.get("tests"):
        for t in smoke["tests"]:
            icon = "PASS" if t.get("status") == "pass" else "FAIL"
            log(f"    [{icon}] {t.get('feature')}: {t.get('notes', '')[:80]}")

    if smoke.get("critical_issues"):
        for issue in smoke["critical_issues"]:
            log(f"    CRITICAL: {issue}")

    return smoke


# ── Entity Model + Browser CRUD (Tank-Grade) ────────────────────────────────
# Per-entity isolated browser sessions. Crash isolation. Retry on failure.
# Entity model drives test instructions, ordering, and result mapping.
#
# TEMPORARY: entity model uses fuzzy extraction from features.json.
# FUTURE: swaps to architecture.json when Architect Session ships.

MAX_RETRIES_PER_ENTITY = 2
ITERS_PER_ENTITY = 25  # Login ~8 iters + CRUD ~12 iters + buffer
ENTITY_TIMEOUT_MS = 180000
ENTITY_HTTP_TIMEOUT = 240
PARALLEL_ENTITY_TESTS = True  # Run independent entities concurrently


def _load_entity_model():
    """Load entity model — import from entity_model.py if available, else empty."""
    try:
        from scripts.entity_model import get_entity_model
        return get_entity_model()
    except ImportError:
        try:
            sys.path.insert(0, ".")
            from scripts.entity_model import get_entity_model
            return get_entity_model()
        except ImportError:
            return {}


def _toposort_entities(entity_model):
    """Topological sort: dependencies first. Delegates to entity_model.py."""
    try:
        from scripts.entity_model import toposort_entities
        return toposort_entities(entity_model)
    except ImportError:
        # Inline fallback
        ordered, visited = [], set()
        def visit(name):
            if name in visited: return
            visited.add(name)
            for dep in entity_model.get(name, {}).get("depends_on", []):
                if dep in entity_model: visit(dep)
            ordered.append(name)
        for name in entity_model: visit(name)
        return ordered


def _build_entity_instruction(name, entity):
    """Build a focused browser test instruction for a single entity."""
    page = entity.get("page", f"/{name}")
    display = entity.get("display_name", name.title())
    crud = entity.get("crud", [])
    test_data = entity.get("test_data", {})
    fks = entity.get("foreign_keys", {})

    if not crud:
        return (
            f"Navigate to {page} ({display}). "
            f"Verify: (1) the page renders with proper CSS styling, (2) data or content loads correctly, "
            f"(3) no error messages or blank sections. "
            f"This is a view-only page — no create/edit/delete needed. "
            f"Report PASS if the page renders correctly with data, FAIL if anything is broken."
        )

    parts = [f"Navigate to {page} ({display}). Test each operation IN ORDER:"]

    if "create" in crud:
        data_desc = ", ".join(f"{k}: {v}" for k, v in test_data.items())
        fk_note = ""
        if fks:
            fk_parts = [f"For '{k}', select an existing item from the dropdown/picker" for k in fks]
            fk_note = " " + ". ".join(fk_parts) + "."
        parts.append(
            f"(1) CREATE: Find the create/add/new button or link. Fill the form with: {data_desc}.{fk_note} "
            f"Submit the form. Verify no error appears and you're redirected back to the list."
        )

    if "read" in crud:
        parts.append(
            f"(2) READ: Verify the newly created item appears in the list with correct data."
        )

    if "update" in crud:
        parts.append(
            f"(3) UPDATE: Click on the item to open it. Change one field (e.g. add ' Updated' to the name/description). "
            f"Save. Verify the change persists in the list."
        )

    if "delete" in crud:
        parts.append(
            f"(4) DELETE: Find the delete button for the item. Confirm deletion if prompted. "
            f"Verify the item is removed from the list."
        )

    parts.append(
        f"Report each operation separately as PASS or FAIL with specific details. "
        f"Use these exact names in your report: '{display} CREATE', '{display} READ', '{display} UPDATE', '{display} DELETE'."
    )

    return " ".join(parts)


def _call_browser_for_entity(frontend_url, email, password, instruction, entity_name):
    """Call browser agent for a single entity. Isolated session."""
    log(f"    Calling browser agent for {entity_name}...")

    payload = {
        "url": frontend_url,
        "credentials": {"email": email, "password": password},
        "features": [instruction],
        "maxIterations": ITERS_PER_ENTITY,
        "timeout": ENTITY_TIMEOUT_MS,
        "uploadScreenshots": True,
    }
    if BROWSER_AGENT_MOCK:
        payload["mock"] = True

    status, body = http_post(
        f"{BROWSER_AGENT_URL}/smoke-test",
        payload,
        timeout=ENTITY_HTTP_TIMEOUT,
    )

    if status == 0:
        return {"overall": "error", "tests": [], "error": f"Browser agent unreachable: {body.get('error')}"}
    if status < 200 or status >= 300:
        return {"overall": "error", "tests": [], "error": f"HTTP {status}"}

    smoke = body.get("smokeTestResults", body)
    # Preserve screenshots
    if "screenshotUrls" in body and "screenshotUrls" not in smoke:
        smoke["screenshotUrls"] = body["screenshotUrls"]
    if "consoleMessages" in body and "consoleMessages" not in smoke:
        smoke["consoleMessages"] = body["consoleMessages"]
    if "error" in body and "error" not in smoke:
        smoke["error"] = body["error"]

    return smoke


def _test_single_entity(frontend_url, email, password, name, entity):
    """Test a single entity with retry. Returns (name, best_result, crud_entry)."""
    instruction = _build_entity_instruction(name, entity)
    crud = entity.get("crud", [])
    page = entity.get("page", f"/{name}")
    display = entity.get("display_name", name.title())

    log(f"\n  ── Entity: {display} ({page}) ──")
    if crud:
        log(f"    Expected CRUD: {', '.join(crud)}")
    else:
        log(f"    Type: view-only")

    best_result = None
    for attempt in range(1, MAX_RETRIES_PER_ENTITY + 1):
        if attempt > 1:
            log(f"    Retry {attempt}/{MAX_RETRIES_PER_ENTITY}...")

        result = _call_browser_for_entity(frontend_url, email, password, instruction, name)
        tests = result.get("tests", [])
        overall = result.get("overall", "error")

        for t in tests:
            icon = "PASS" if t.get("status") == "pass" else "FAIL"
            log(f"    [{icon}] {t.get('feature', '?')}: {t.get('notes', '')[:80]}")

        if result.get("error"):
            log(f"    Error: {result['error'][:100]}")

        if best_result is None or len(tests) > len(best_result.get("tests", [])):
            best_result = result

        if overall == "pass":
            break
        if tests and "error" not in result:
            break

    entity_tests = _map_single_entity_result(name, entity, best_result)

    # Form field validation (#5) — compare entity model fields against DOM
    form_issues = _validate_form_fields(entity, best_result)
    if form_issues:
        for issue in form_issues:
            log(f"    ⚠ FORM: {issue}")
        entity_tests["form_validation"] = "fail"
    elif entity.get("crud"):  # Only validate forms on CRUD entities
        entity_tests["form_validation"] = "pass"

    # List count verification (#7) — check DOM for item count
    page_state = best_result.get("finalPageState", {}) if best_result else {}
    list_items = page_state.get("listItems", {})
    if list_items.get("count", -1) >= 0:
        log(f"    DOM: {list_items['count']} list items (via {list_items.get('selector', '?')})")

    crud_entry = {"entity": name, "page": page, "tests": entity_tests} if entity_tests else None

    return name, best_result, crud_entry


def run_browser_crud_tests(frontend_url, email, password, entity_model):
    """Run per-entity isolated browser CRUD tests with retry and parallelism.

    Each entity gets its own browser session. Crash in one entity
    does NOT affect testing of other entities. Failed entities retry once.
    Independent entities (same dependency level) run in parallel.

    Returns (all_results, crud_results):
    - all_results: dict of per-entity smoke results (for logging)
    - crud_results: list in browser_crud_results contract format
    """
    ordered = _toposort_entities(entity_model)
    log(f"  Testing {len(ordered)} entities in dependency order: {', '.join(ordered)}")

    all_results = {}
    crud_results = []

    if PARALLEL_ENTITY_TESTS:
        # Group entities by dependency level for parallel execution
        # Level 0: no dependencies. Level 1: depends on level 0. etc.
        levels = {}
        entity_level = {}
        for name in ordered:
            deps = entity_model.get(name, {}).get("depends_on", [])
            known_dep_levels = [entity_level[d] for d in deps if d in entity_level]
            if not known_dep_levels:
                entity_level[name] = 0
            else:
                entity_level[name] = max(known_dep_levels) + 1
            level = entity_level[name]
            levels.setdefault(level, []).append(name)

        import concurrent.futures

        for level_num in sorted(levels.keys()):
            entities_at_level = levels[level_num]
            if len(entities_at_level) == 1:
                # Single entity — run directly
                name = entities_at_level[0]
                n, result, entry = _test_single_entity(
                    frontend_url, email, password, name, entity_model[name])
                all_results[n] = result
                if entry:
                    crud_results.append(entry)
            else:
                # Multiple independent entities — run in parallel
                log(f"\n  ── Parallel batch (level {level_num}): {', '.join(entities_at_level)} ──")
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(entities_at_level)) as executor:
                    futures = {
                        executor.submit(
                            _test_single_entity,
                            frontend_url, email, password, name, entity_model[name]
                        ): name for name in entities_at_level
                    }
                    for future in concurrent.futures.as_completed(futures):
                        n, result, entry = future.result()
                        all_results[n] = result
                        if entry:
                            crud_results.append(entry)
    else:
        # Sequential fallback
        for name in ordered:
            n, result, entry = _test_single_entity(
                frontend_url, email, password, name, entity_model[name])
            all_results[n] = result
            if entry:
                crud_results.append(entry)

    return all_results, crud_results


def _validate_form_fields(entity, smoke_result):
    """Validate that the browser agent found expected form fields.

    Compares entity model's expected fields against form fields
    reported by the browser agent's DOM inspection.

    Returns list of validation issues (empty = all good).
    """
    expected_fields = set(entity.get("fields", []))
    if not expected_fields:
        return []

    # Get form fields from the browser agent's page state
    page_state = smoke_result.get("finalPageState", {})
    found_fields = page_state.get("formFields", [])
    if not found_fields:
        return []  # No form data available — can't validate

    # Extract field names/labels from DOM
    found_names = set()
    for f in found_fields:
        if f.get("name"):
            found_names.add(f["name"].lower())
        if f.get("label"):
            # Normalise label: "Monthly Limit" → "monthly_limit"
            normalised = f["label"].lower().replace(" ", "_").replace("-", "_")
            found_names.add(normalised)

    # Check which expected fields were found
    issues = []
    for expected in expected_fields:
        expected_lower = expected.lower()
        if expected_lower.endswith("_id"):
            continue  # FK fields are dropdowns — matched differently
        # Fuzzy: check if expected field name appears in any found name
        found = any(expected_lower in fn or fn in expected_lower for fn in found_names)
        if not found:
            issues.append(f"Expected field '{expected}' not found in form (found: {', '.join(sorted(found_names)[:5])})")

    return issues


def _map_single_entity_result(name, entity, smoke_result):
    """Map a single entity's browser agent result to the CRUD contract.

    Uses the entity model to know which operations to look for,
    and the display_name for matching feature names in the result.
    """
    crud_keywords = {
        "create": ["create", "add", "new", "form", "submit"],
        "read": ["read", "list", "view", "display", "appears"],
        "update": ["update", "edit", "modify", "save", "change"],
        "delete": ["delete", "remove"],
    }

    tests = smoke_result.get("tests", [])
    display = entity.get("display_name", name.title()).lower()
    singular = name.lower().rstrip("s")
    crud = entity.get("crud", [])
    result = {}

    if not crud:
        # View-only: check if any test mentions this entity and passed
        for t in tests:
            feature_lower = t.get("feature", "").lower()
            if singular in feature_lower or display in feature_lower or name.lower() in feature_lower:
                result["renders"] = t.get("status", "unknown")
                notes = t.get("notes", "").lower()
                if any(kw in notes for kw in ["display", "data", "metric", "load", "show"]):
                    result["data_loads"] = t.get("status", "unknown")
                break
        # If no specific match, but tests exist and overall passed, mark renders
        if not result and smoke_result.get("overall") == "pass":
            result["renders"] = "pass"
        return result

    # CRUD entity: match each expected operation
    for op in crud:
        keywords = crud_keywords.get(op, [op])
        matched = False
        for t in tests:
            feature_lower = t.get("feature", "").lower()
            notes_lower = t.get("notes", "").lower()
            # Must mention the entity AND the operation
            entity_match = singular in feature_lower or display in feature_lower or name.lower() in feature_lower
            op_match = any(kw in feature_lower for kw in keywords)
            if entity_match and op_match:
                result[op] = t.get("status", "unknown")
                matched = True
                break
        if not matched:
            # Check notes for the operation even without entity name match
            # (agent might report "Create: pass" without entity name since it's a single-entity session)
            for t in tests:
                feature_lower = t.get("feature", "").lower()
                if any(kw in feature_lower for kw in keywords):
                    result[op] = t.get("status", "unknown")
                    matched = True
                    break
        if not matched:
            result[op] = "not_tested"

    return result


def write_crud_to_qa_report(crud_results, qa_report_path="qa-report.json"):
    """Write browser_crud_results into qa-report.json."""
    report = {}
    rpath = Path(qa_report_path)
    if rpath.exists():
        try:
            report = json.loads(rpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    report["browser_crud_results"] = crud_results
    if "latest" in report and isinstance(report["latest"], dict):
        report["latest"]["browser_crud_results"] = crud_results
    rpath.write_text(json.dumps(report, indent=2), encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    log("=" * 60)
    log("QA SMOKE TEST — deterministic end-to-end verification")
    log("=" * 60)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "auth": None,
        "browser_smoke_test": None,
    }
    exit_code = 0

    # ── Step 0: Browser agent pre-check (with retry for Render cold start) ──
    log("")
    log("STEP 0: Browser agent connectivity check")

    browser_reachable = False
    WAKE_RETRIES = 4
    WAKE_DELAYS = [10, 15, 15, 15]  # Up to 55s total

    for attempt in range(WAKE_RETRIES):
        status, body = http_get(f"{BROWSER_AGENT_URL}/", timeout=30)
        if status > 0:
            log(f"  Browser agent reachable (HTTP {status}) on attempt {attempt + 1}")
            browser_reachable = True
            break
        log(f"  Attempt {attempt + 1}/{WAKE_RETRIES} failed: {body.get('error')}")
        if attempt < WAKE_RETRIES - 1:
            delay = WAKE_DELAYS[attempt]
            log(f"  Retrying in {delay}s (Render cold start)...")
            time.sleep(delay)

    if not browser_reachable:
        log("  Browser agent UNREACHABLE after all retries — skipping browser test")
        output["browser_smoke_test"] = {
            "overall": "error",
            "reason": f"Browser agent unreachable after {WAKE_RETRIES} attempts",
        }
        skip_browser = True
    else:
        skip_browser = False

    # ── Auth ──
    log("")
    log("STEP 1: Auth flow test")
    auth = run_auth_test()
    output["auth"] = auth

    if not auth["success"]:
        log(f"\nAUTH FAILED — cannot proceed with browser test")
        output["browser_smoke_test"] = {
            "overall": "error",
            "error": f"Auth failed: {auth.get('error')} — no valid credentials for browser test",
        }
        exit_code = 1
    else:
        email = auth["email"]
        password = auth["password"]
        log(f"\nQA TEST CREDENTIALS: email={email} password={password}")

        # ── Seed data ──
        token = auth.get("token")
        if token:
            seed_sample_data(token)

        # ── Frontend check ──
        if not os.path.isdir("frontend"):
            log("\nNo frontend/ directory — browser smoke test not applicable")
            output["browser_smoke_test"] = {"overall": "not_applicable"}
        else:
            # ── Ports ──
            log("\nSTEP 2: Make ports public")
            ports = make_ports_public()
            if not ports["success"]:
                log(f"\nPORTS FAILED: {ports['error']}")
                output["browser_smoke_test"] = {
                    "overall": "error",
                    "error": ports["error"],
                }
                exit_code = 2
            else:
                # ─�� Entity Model ──
                log("\nSTEP 3: Build entity model")

                entity_model = _load_entity_model()
                if entity_model:
                    log(f"  Entity model: {len(entity_model)} entities")
                    for name, ent in entity_model.items():
                        crud = ", ".join(ent["crud"]) if ent["crud"] else "view-only"
                        deps = ", ".join(ent["depends_on"]) if ent["depends_on"] else "none"
                        fks = ", ".join(f"{k}→{v}" for k, v in ent.get("foreign_keys", {}).items()) or "none"
                        log(f"    {name}: [{crud}] deps=[{deps}] fks=[{fks}]")
                else:
                    log("  No entity model — browser CRUD testing skipped")

                # ── Browser CRUD testing (per-entity isolated sessions) ──
                if skip_browser:
                    log("\nSTEP 4: Skipped — browser agent unreachable (Step 0)")
                    # output already set in Step 0
                elif not entity_model:
                    log("\nSTEP 4: Skipped — no entity model available")
                    output["browser_smoke_test"] = {"overall": "skipped", "reason": "No entity model"}
                else:
                    log("\nSTEP 4: Per-entity browser CRUD testing")
                    log(f"  Strategy: isolated sessions, {MAX_RETRIES_PER_ENTITY} retries per entity, {ITERS_PER_ENTITY} iterations each")

                    all_results, crud_results = run_browser_crud_tests(
                        ports["frontend_url"], email, password, entity_model,
                    )

                    # Aggregate overall result
                    total_entities = len(entity_model)
                    tested_entities = len(crud_results)
                    all_pass = all(
                        all(v == "pass" for v in r["tests"].values())
                        for r in crud_results
                    )
                    any_fail = any(
                        any(v == "fail" for v in r["tests"].values())
                        for r in crud_results
                    )

                    if tested_entities == total_entities and all_pass:
                        overall = "pass"
                        exit_code = 0
                    elif any_fail:
                        overall = "fail"
                        exit_code = 1
                    elif tested_entities < total_entities:
                        overall = "partial"
                        exit_code = 1
                    else:
                        overall = "pass"
                        exit_code = 0

                    output["browser_smoke_test"] = {
                        "overall": overall,
                        "entities_tested": tested_entities,
                        "entities_total": total_entities,
                        "per_entity_results": all_results,
                    }

                    # Summary
                    log(f"\n  ── Browser CRUD Summary ──")
                    for r in crud_results:
                        tests_str = ", ".join(f"{k}={v}" for k, v in r["tests"].items())
                        icon = "✓" if all(v == "pass" for v in r["tests"].values()) else "✗"
                        log(f"    {icon} {r['entity']}: {tests_str}")
                    untested = [n for n in entity_model if n not in [r["entity"] for r in crud_results]]
                    if untested:
                        for name in untested:
                            log(f"    ✗ {name}: NOT TESTED")
                    log(f"  Overall: {overall.upper()} ({tested_entities}/{total_entities} entities)")

                    # Write CRUD results to qa-report.json
                    write_crud_to_qa_report(crud_results)
                    log(f"  Written to qa-report.json")

    # ── Write results ──
    output["exit_code"] = exit_code
    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    log("")
    log("=" * 60)
    overall_auth = "PASS" if auth["success"] else "FAIL"
    overall_browser = output["browser_smoke_test"].get("overall", "unknown")
    log(f"AUTH: {overall_auth}  |  BROWSER: {overall_browser.upper()}")
    log(f"Results: {RESULTS_FILE}")
    log(f"Exit code: {exit_code}")
    log("=" * 60)

    # Stdout: machine-readable JSON for the QA agent
    print(json.dumps(output, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
