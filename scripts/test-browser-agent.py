"""
Test harness — validate the browser agent against the test fixture.

Usage:
    python scripts/test-browser-agent.py
    python scripts/test-browser-agent.py --fixture-url https://browser-agent-test-fixture.onrender.com
    python scripts/test-browser-agent.py --browser-agent-url https://claude-browser-agent.onrender.com

Exit codes:
    0 = pass
    1 = fail
    2 = infrastructure error (fixture or browser agent unreachable)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

DEFAULT_FIXTURE_URL = "https://browser-agent-test-fixture.onrender.com"
DEFAULT_BROWSER_AGENT_URL = "https://claude-browser-agent.onrender.com"

SEED_EMAIL = "test@fixture.example.com"
SEED_PASSWORD = "TestFixture123!"


def log(msg):
    print(f"[test-harness] {msg}", file=sys.stderr, flush=True)


def http_post(url, data, timeout=30):
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
    except Exception as e:
        return 0, {"error": str(e)}


def http_get(url, timeout=10):
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return 0, {"error": str(e)}


def wake_fixture(fixture_url, max_wait=90):
    """Wake the fixture (Render cold start). Returns True if healthy."""
    log(f"Waking fixture: {fixture_url}")
    start = time.time()
    while time.time() - start < max_wait:
        status, body = http_get(f"{fixture_url}/api/health", timeout=10)
        if status == 200:
            log(f"  Fixture healthy (took {time.time() - start:.0f}s)")
            return True
        log(f"  Waiting... (status={status})")
        time.sleep(5)
    log(f"  Fixture did not wake after {max_wait}s")
    return False


def reset_fixture(fixture_url):
    """Reset fixture state for test isolation."""
    log("Resetting fixture state...")
    status, body = http_post(f"{fixture_url}/api/admin/reset", {})
    if status == 200:
        log(f"  Reset OK — seed user: {body.get('seed_user')}")
        return True
    log(f"  Reset failed: HTTP {status} — {body}")
    return False


def run_smoke_test(fixture_url, browser_agent_url):
    """Run the browser agent smoke test against the fixture."""
    features = [
        "User Authentication",
        "Project Management",
        "Task Management",
        "Dashboard",
        "Navigation",
    ]

    log(f"Calling browser agent: {browser_agent_url}/smoke-test")
    log(f"  Target: {fixture_url}")
    log(f"  Credentials: {SEED_EMAIL}")
    log(f"  Features: {len(features)}")

    status, body = http_post(
        f"{browser_agent_url}/smoke-test",
        {
            "url": fixture_url,
            "credentials": {"email": SEED_EMAIL, "password": SEED_PASSWORD},
            "features": features,
            "maxIterations": 15,
            "timeout": 120000,
        },
        timeout=180,
    )

    if status == 0:
        log(f"  Browser agent unreachable: {body.get('error')}")
        return {"overall": "error", "error": f"Browser agent unreachable: {body.get('error')}"}

    if status < 200 or status >= 300:
        log(f"  Browser agent HTTP {status}: {body}")
        return {"overall": "error", "error": f"HTTP {status}", "detail": body}

    smoke = body.get("smokeTestResults", body)
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


def main():
    parser = argparse.ArgumentParser(description="Test browser agent against fixture")
    parser.add_argument("--fixture-url", default=DEFAULT_FIXTURE_URL)
    parser.add_argument("--browser-agent-url", default=DEFAULT_BROWSER_AGENT_URL)
    args = parser.parse_args()

    log("=" * 60)
    log("BROWSER AGENT TEST HARNESS")
    log("=" * 60)

    # Step 1: Wake fixture
    if not wake_fixture(args.fixture_url):
        print(json.dumps({"overall": "error", "error": "Fixture unreachable"}, indent=2))
        return 2

    # Step 2: Reset state
    if not reset_fixture(args.fixture_url):
        print(json.dumps({"overall": "error", "error": "Fixture reset failed"}, indent=2))
        return 2

    # Step 3: Run smoke test
    result = run_smoke_test(args.fixture_url, args.browser_agent_url)

    log("")
    log("=" * 60)
    overall = result.get("overall", "unknown")
    log(f"RESULT: {overall.upper()}")
    log("=" * 60)

    print(json.dumps(result, indent=2))

    if overall == "pass":
        return 0
    elif overall == "error":
        return 2
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
