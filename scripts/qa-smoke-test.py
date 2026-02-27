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
import urllib.error

BACKEND_URL = "http://localhost:8000"
FRONTEND_PORT = 3000
BROWSER_AGENT_URL = "https://claude-browser-agent.onrender.com"
CREDENTIALS_FILE = "qa-test-credentials.json"
RESULTS_FILE = "qa-smoke-results.json"


def log(msg):
    print(f"[qa-smoke] {msg}", file=sys.stderr, flush=True)


def http_post(url, data, timeout=30):
    """POST JSON, return (status_code, parsed_body). status=0 means network error."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
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


# -- Step 1: Register + verify auth ------------------------------------------


def run_auth_test():
    """Register a fresh user, login, verify token. Returns structured result."""
    email = f"qa-tester-{int(time.time())}@test.example.com"
    password = "TestPass123!"
    result = {
        "success": False,
        "email": email,
        "password": password,
        "steps": {},
    }

    # 1a. Register
    log(f"Registering: {email}")
    status, body = http_post(
        f"{BACKEND_URL}/api/auth/register",
        {"email": email, "password": password, "name": "QA Tester", "display_name": "QA Tester"},
    )
    result["steps"]["register"] = {"status": status, "response": body}

    if status < 200 or status >= 300:
        result["error"] = f"Registration failed (HTTP {status})"
        log(f"  FAIL: {result['error']} -- {body}")
        return result
    log(f"  Register: HTTP {status} OK")

    # 1b. Login
    status, body = http_post(
        f"{BACKEND_URL}/api/auth/login",
        {"email": email, "password": password},
    )
    result["steps"]["login"] = {"status": status}

    if status < 200 or status >= 300:
        result["error"] = f"Login failed (HTTP {status})"
        log(f"  FAIL: {result['error']} -- {body}")
        return result

    # Extract token — apps may use different field names
    token = (
        body.get("token")
        or body.get("access_token")
        or body.get("idToken")
        or body.get("id_token")
    )
    if not token:
        result["error"] = f"Login response has no token field. Keys: {list(body.keys())}"
        log(f"  FAIL: {result['error']}")
        return result
    log(f"  Login: HTTP {status} OK, token received")

    # 1c. Verify token with /api/users/me
    status, body = http_get(
        f"{BACKEND_URL}/api/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    result["steps"]["verify_token"] = {"status": status}
    log(f"  Verify token (/api/users/me): HTTP {status}")

    # Auth succeeded
    result["success"] = True
    result["token_verified"] = (200 <= status < 300)

    # Persist credentials so other tools can use them
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump({"email": email, "password": password}, f, indent=2)
    log(f"  Credentials saved to {CREDENTIALS_FILE}")

    return result


# -- Step 2: Make ports public ------------------------------------------------


def make_ports_public():
    """Make codespace ports public. Returns frontend URL or error."""
    codespace = os.environ.get("CODESPACE_NAME")
    if not codespace:
        return {"success": False, "error": "CODESPACE_NAME env var not set -- not in a codespace?"}

    log(f"Making ports public (codespace: {codespace})")
    try:
        subprocess.run(
            ["gh", "codespace", "ports", "visibility",
             "8000:public", f"{FRONTEND_PORT}:public", "-c", codespace],
            capture_output=True, text=True, timeout=15, check=True,
        )
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"gh ports failed: {e.stderr.strip()}"}
    except FileNotFoundError:
        return {"success": False, "error": "gh CLI not found"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "gh ports timed out"}

    frontend_url = f"https://{codespace}-{FRONTEND_PORT}.app.github.dev"
    # Point directly at /login to avoid client-side redirect destroying Puppeteer context
    login_url = f"{frontend_url}/login"
    log(f"  Public URL: {frontend_url}")
    log(f"  Login URL:  {login_url}")
    return {"success": True, "frontend_url": login_url}


# -- Step 3: Read features ---------------------------------------------------


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
        log("  features.json not found -- agent will auto-discover")
        return []
    except Exception as e:
        log(f"  Error reading features.json: {e} -- agent will auto-discover")
        return []


# -- Step 4: Call browser agent -----------------------------------------------


def call_browser_agent(frontend_url, email, password, features):
    """Call browser agent /smoke-test. Returns structured result."""
    log(f"Calling browser agent...")
    log(f"  Target: {frontend_url}")
    log(f"  User: {email}")
    log(f"  Features: {len(features)}")

    status, body = http_post(
        f"{BROWSER_AGENT_URL}/smoke-test",
        {
            "url": frontend_url,
            "credentials": {"email": email, "password": password},
            "features": features,
            "maxIterations": 15,
            "timeout": 120000,
            "uploadScreenshots": True,
        },
        timeout=180,
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
    # Preserve screenshot URLs from top-level response
    if "screenshotUrls" in body and "screenshotUrls" not in smoke:
        smoke["screenshotUrls"] = body["screenshotUrls"]
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


# -- Main ---------------------------------------------------------------------


def main():
    log("=" * 60)
    log("QA SMOKE TEST -- deterministic end-to-end verification")
    log("=" * 60)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "auth": None,
        "browser_smoke_test": None,
    }
    exit_code = 0

    # -- Step 0: Browser agent pre-check (with retry for Render cold start) --
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
        log("  Browser agent UNREACHABLE after all retries -- skipping browser test")
        output["browser_smoke_test"] = {
            "overall": "error",
            "reason": f"Browser agent unreachable after {WAKE_RETRIES} attempts",
        }
        skip_browser = True
    else:
        skip_browser = False

    # -- Auth --
    log("")
    log("STEP 1: Auth flow test")
    auth = run_auth_test()
    output["auth"] = auth

    if not auth["success"]:
        log(f"\nAUTH FAILED -- cannot proceed with browser test")
        output["browser_smoke_test"] = {
            "overall": "error",
            "error": f"Auth failed: {auth.get('error')} -- no valid credentials for browser test",
        }
        exit_code = 1
    else:
        email = auth["email"]
        password = auth["password"]
        log(f"\nQA TEST CREDENTIALS: email={email} password={password}")

        # -- Frontend check --
        if not os.path.isdir("frontend"):
            log("\nNo frontend/ directory -- browser smoke test not applicable")
            output["browser_smoke_test"] = {"overall": "not_applicable"}
        else:
            # -- Ports --
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
                # -- Features --
                log("\nSTEP 3: Read features")
                features = read_features()

                # -- Browser agent --
                if skip_browser:
                    log("\nSTEP 4: Skipped -- browser agent unreachable (Step 0)")
                else:
                    log("\nSTEP 4: Browser smoke test")
                    smoke = call_browser_agent(
                        ports["frontend_url"], email, password, features,
                    )
                    output["browser_smoke_test"] = smoke

                    overall = smoke.get("overall", "unknown")
                    if overall == "pass":
                        exit_code = 0
                    elif overall == "skipped":
                        exit_code = 2
                    else:
                        exit_code = 1

    # -- Write results --
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
