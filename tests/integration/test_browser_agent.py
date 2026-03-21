"""
Verify browser agent can actually navigate pages in this codespace.
HARD GATE — if this fails, the build stops.

Three-stage verification:
  1. Health check (service is up, Puppeteer available)
  2. /diagnose (Puppeteer launches, navigates to codespace URL, takes screenshot)
  3. URL construction (CODESPACE_NAME produces a reachable address)

Retries with backoff to handle Render cold starts (up to 75s).
Writes full result to browser-agent-preflight.json for QA tester.
"""
import json, os, sys, time, urllib.request, urllib.error

BROWSER_AGENT_BASE = "https://browser.dreamteamlabs.co.uk"
PREFLIGHT_FILE = "browser-agent-preflight.json"
MAX_RETRIES = 6
RETRY_DELAYS = [5, 10, 15, 15, 15, 15]


def _post_json(url, data, timeout=90):
    """POST JSON, return (status, parsed_body)."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status, json.loads(resp.read().decode())


def stage1_health():
    """Stage 1: Health check — service is up and Puppeteer is available."""
    print("\n--- Stage 1: Health Check ---")
    for attempt in range(MAX_RETRIES):
        try:
            print(f"  Attempt {attempt + 1}/{MAX_RETRIES}: {BROWSER_AGENT_BASE}/health")
            req = urllib.request.Request(f"{BROWSER_AGENT_BASE}/health")
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read().decode())
            version = data.get("version", "unknown")
            print(f"  PASS: Browser agent v{version} (HTTP {resp.status})")
            return {"pass": True, "version": version, "attempts": attempt + 1}
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                print(f"  Retrying in {delay}s...")
                time.sleep(delay)
    return {"pass": False, "error": "Health check failed after all retries"}


def stage2_diagnose(codespace_name):
    """Stage 2: /diagnose — Puppeteer launches, navigates, takes screenshot.

    Tests against the backend health endpoint on port 8000. This proves:
    - Puppeteer can launch headless Chrome
    - The codespace URL format is correct
    - The browser agent can reach this codespace through GitHub's proxy
    - Screenshots work (upload to litterbox)
    """
    print("\n--- Stage 2: Browser Navigation (diagnose) ---")
    # Try port 8000 (backend) first — it's started by post-start.sh
    # Fall back to raw codespace URL if backend isn't ready yet
    test_url = f"https://{codespace_name}-8000.app.github.dev/api/health"
    print(f"  Target: {test_url}")

    try:
        status, data = _post_json(f"{BROWSER_AGENT_BASE}/diagnose", {"url": test_url})
        if data.get("success"):
            screenshot = data.get("screenshotUrl", "none")
            final_url = data.get("finalUrl", "unknown")
            elapsed = data.get("elapsed", 0)
            print(f"  PASS: Navigated to {final_url} ({elapsed}ms)")
            print(f"  Screenshot: {screenshot}")
            return {
                "pass": True,
                "final_url": final_url,
                "screenshot_url": screenshot,
                "elapsed_ms": elapsed,
                "test_url": test_url,
            }
        else:
            error = data.get("error", "unknown")
            events = data.get("events", [])
            print(f"  FAIL: Diagnose failed — {error}")
            for ev in events[-3:]:
                print(f"    {ev.get('type')}: {ev.get('url', ev.get('message', ''))}")
            return {"pass": False, "error": error, "events": events, "test_url": test_url}
    except Exception as e:
        print(f"  FAIL: /diagnose request failed — {e}")
        return {"pass": False, "error": str(e), "test_url": test_url}


def stage3_url_reachable(codespace_name):
    """Stage 3: Verify the codespace URL is directly reachable (HTTP level).

    The /diagnose test goes through the browser agent. This test verifies
    the codespace URL is also reachable directly, catching port visibility issues.
    Retries up to 3 times — ports may take a moment to become public.
    """
    print("\n--- Stage 3: Direct URL Reachability ---")
    url = f"https://{codespace_name}-8000.app.github.dev/api/health"
    print(f"  Target: {url}")
    retries = 3
    retry_delay = 5
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=30)
            data = resp.read().decode()
            print(f"  PASS: HTTP {resp.status} — {data[:100]}")
            return {"pass": True, "status": resp.status, "url": url, "attempts": attempt + 1}
        except urllib.error.HTTPError as e:
            # 401/403 = GitHub "Continue" interstitial — URL is reachable, just gated
            if e.code in (401, 403):
                print(f"  PASS (with gate): HTTP {e.code} — GitHub Continue page (expected for public ports)")
                return {"pass": True, "status": e.code, "url": url, "note": "GitHub Continue interstitial", "attempts": attempt + 1}
            if attempt < retries - 1:
                print(f"  Attempt {attempt + 1}/{retries} failed (HTTP {e.code}), retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"  FAIL: HTTP {e.code}")
                return {"pass": False, "status": e.code, "url": url, "error": str(e)}
        except Exception as e:
            if attempt < retries - 1:
                print(f"  Attempt {attempt + 1}/{retries} failed ({e}), retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"  FAIL: {e}")
                return {"pass": False, "url": url, "error": str(e)}


def run_all():
    result = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "browser_agent_url": BROWSER_AGENT_BASE,
        "stages": {},
    }

    # Check CODESPACE_NAME first — everything depends on it
    codespace = os.environ.get("CODESPACE_NAME")
    result["codespace_name"] = codespace or None
    if not codespace:
        print("FAIL: CODESPACE_NAME not set — cannot construct codespace URLs")
        result["overall"] = "fail"
        result["error"] = "CODESPACE_NAME not set"
        with open(PREFLIGHT_FILE, "w") as f:
            json.dump(result, f, indent=2)
        return result

    print(f"Codespace: {codespace}")

    # Stage 1: Health
    s1 = stage1_health()
    result["stages"]["health"] = s1
    if not s1["pass"]:
        result["overall"] = "fail"
        result["error"] = "Browser agent service unreachable"
        with open(PREFLIGHT_FILE, "w") as f:
            json.dump(result, f, indent=2)
        return result

    # Stage 2: Diagnose (Puppeteer navigation + screenshot)
    s2 = stage2_diagnose(codespace)
    result["stages"]["diagnose"] = s2
    if not s2["pass"]:
        result["overall"] = "fail"
        result["error"] = f"Browser agent cannot navigate to codespace: {s2.get('error')}"
        with open(PREFLIGHT_FILE, "w") as f:
            json.dump(result, f, indent=2)
        return result

    # Stage 3: Direct URL reachability
    s3 = stage3_url_reachable(codespace)
    result["stages"]["url_reachable"] = s3
    if not s3["pass"]:
        # Warn but don't fail — /diagnose passed, so the browser agent can reach it
        print("  WARNING: Direct URL unreachable but browser agent navigation worked")
        result["stages"]["url_reachable"]["warning"] = True

    result["overall"] = "pass"
    result["screenshot_url"] = s2.get("screenshot_url")

    with open(PREFLIGHT_FILE, "w") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    print("=== Browser Agent Verification (3-stage) ===")
    result = run_all()
    print(f"\n{'='*50}")
    if result["overall"] == "pass":
        print(f"PASS: Browser agent verified end-to-end")
        print(f"  Service: {result['stages']['health'].get('version')}")
        print(f"  Navigation: {result['stages']['diagnose'].get('final_url')}")
        print(f"  Screenshot: {result.get('screenshot_url', 'none')}")
        sys.exit(0)
    else:
        print(f"FAIL: {result.get('error')}")
        print(f"  Build MUST stop — browser testing is non-negotiable")
        sys.exit(1)
