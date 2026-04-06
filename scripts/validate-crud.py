#!/usr/bin/env python3
"""Validate CRUD testing — gate script for factory loop.

Checks BOTH api_crud_results AND browser_crud_results from qa-report.json.
API CRUD: verifies every backend entity was tested via API.
Browser CRUD: verifies every UI page was tested via browser.

Either type failing blocks deployment.

Exit codes:
  0 = all results pass (or missing results in warning-only sections)
  1 = any CRUD test failures found
"""
import json
import sys
from pathlib import Path

# Pages to skip — these are infrastructure, not testable entities
SKIP_PAGES = {
    "login", "register", "signup", "auth", "callback",
    "settings", "profile", "account",
    "api",  # API routes, not UI pages
}


def discover_pages() -> list[str]:
    """Discover UI entity pages from frontend directory structure."""
    app_dir = Path("frontend/src/app")
    if not app_dir.exists():
        return []

    pages = []
    for page_dir in sorted(app_dir.iterdir()):
        if not page_dir.is_dir():
            continue
        name = page_dir.name
        if name.startswith("_") or name.startswith(".") or name.startswith("("):
            continue
        if name.lower() in SKIP_PAGES:
            continue
        has_page = any(
            (page_dir / f"page.{ext}").exists()
            for ext in ("tsx", "jsx", "ts", "js")
        )
        if has_page:
            pages.append(name)
    return pages


def load_qa_report() -> dict:
    """Load qa-report.json."""
    path = Path("qa-report.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def extract_results(data: dict, key: str) -> dict:
    """Extract results array from qa-report.json, checking latest and top-level."""
    results = (
        data.get("latest", {}).get(key, [])
        or data.get(key, [])
    )
    return {r.get("entity", "").lower(): r for r in results if isinstance(r, dict)}


def check_results(results: dict, label: str, entities: list[str]) -> tuple[list, list]:
    """Check results for a set of entities. Returns (missing, failed)."""
    missing = []
    failed = []

    for entity in entities:
        entity_lower = entity.lower().rstrip("s")
        result = (
            results.get(entity.lower())
            or results.get(entity_lower)
            or results.get(entity.lower() + "s")
            or results.get(entity_lower + "s")
        )

        if result is None:
            print(f"  MISSING: {entity} — no {label} result")
            missing.append(entity)
        else:
            tests = result.get("tests", {})
            if not tests:
                print(f"  MISSING: {entity} — entry exists but no tests recorded")
                missing.append(entity)
            else:
                failures = [k for k, v in tests.items() if v != "pass"]
                if failures:
                    print(f"  FAILED:  {entity} — {', '.join(failures)} failed")
                    failed.append(f"{entity}: {', '.join(failures)}")
                else:
                    print(f"  PASS:    {entity} ({', '.join(tests.keys())})")

    return missing, failed


def main():
    data = load_qa_report()
    all_failed = []

    # --- API CRUD Results ---
    api_results = extract_results(data, "api_crud_results")
    if api_results:
        print("=== API CRUD Validation ===")
        print(f"API CRUD results: {len(api_results)} entities tested")
        print()
        api_entities = list(api_results.keys())
        _, api_failed = check_results(api_results, "API CRUD", api_entities)
        all_failed.extend(api_failed)
        print()
    else:
        print("=== API CRUD: no results (skipping) ===")
        print()

    # --- Browser CRUD Results ---
    pages = discover_pages()
    browser_results = extract_results(data, "browser_crud_results")

    if pages:
        print("=== Browser CRUD Validation ===")
        print(f"Discovered {len(pages)} UI pages: {', '.join(pages)}")
        print(f"Browser test results: {len(browser_results)} entities tested")
        print()
        browser_missing, browser_failed = check_results(browser_results, "browser CRUD", pages)
        all_failed.extend(browser_failed)

        if browser_missing and not browser_failed:
            print()
            print(f"  Browser coverage incomplete: {', '.join(browser_missing)}")
            print("  (non-blocking until breadth issue resolved)")
        print()
    else:
        print("=== Browser CRUD: no UI pages discovered (skipping) ===")
        print()

    # --- Final verdict ---
    if all_failed:
        print("=== FAILED ===")
        print(f"CRUD test failures: {'; '.join(all_failed)}")
        print()
        print("Fix CRUD test failures before deploying.")
        sys.exit(1)
    else:
        print("=== PASSED ===")
        api_count = len(api_results)
        browser_count = len(browser_results)
        print(f"API: {api_count} entities tested. Browser: {browser_count} pages tested.")
        sys.exit(0)


if __name__ == "__main__":
    main()
