"""
Build Report Generator for browser-agent-test-fixture.

Captures structured outcome data after Claude Code builds the product.
This data feeds back to the DreamTeam factory's self-improvement loop.

Usage:
    python scripts/build-report.py [--output json|text] [--submit]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def count_features(features_path: str = "features.json") -> dict:
    """Count features by status."""
    path = Path(features_path)
    if not path.exists():
        return {"total": 0, "completed": 0, "blocked": 0, "pending": 0, "in_progress": 0}

    with open(path) as f:
        data = json.load(f)

    features = data.get("features", [])
    counts = {"total": len(features), "completed": 0, "blocked": 0, "pending": 0, "in_progress": 0}
    for feat in features:
        status = feat.get("status", "pending")
        if status in counts:
            counts[status] += 1
    return counts


def count_env_features(env_path: str = "environment_features.json") -> dict:
    """Count environment feature validation results."""
    path = Path(env_path)
    if not path.exists():
        return {"total": 0, "passed": 0, "failed": 0}

    with open(path) as f:
        data = json.load(f)

    features = data.get("features", [])
    result = {"total": len(features), "passed": 0, "failed": 0}
    for feat in features:
        if feat.get("status") == "completed" and feat.get("tests_pass"):
            result["passed"] += 1
        elif feat.get("status") != "pending":
            result["failed"] += 1
    return result


def get_github_issues() -> list[dict]:
    """Fetch GitHub issues created by the issue-detector hook."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--label", "claude-detected", "--json",
             "number,title,labels,createdAt,body", "--limit", "100"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def categorise_issues(issues: list[dict]) -> dict:
    """Count issues by category label."""
    categories = {}
    for issue in issues:
        labels = [l.get("name", "") for l in issue.get("labels", [])]
        for label in labels:
            if label != "claude-detected":
                categories[label] = categories.get(label, 0) + 1
    return categories


def get_feature_details(features_path: str = "features.json") -> list[dict]:
    """Get per-feature outcome details."""
    path = Path(features_path)
    if not path.exists():
        return []

    with open(path) as f:
        data = json.load(f)

    results = []
    for feat in data.get("features", []):
        results.append({
            "feature_id": feat.get("id"),
            "feature_name": feat.get("name"),
            "phase": feat.get("phase"),
            "status": feat.get("status", "pending"),
            "tests_pass": feat.get("tests_pass", False),
            "description_length": len(feat.get("description", "")),
            "has_files": len(feat.get("files", [])) > 0,
            "has_dependencies": len(feat.get("dependencies", [])) > 0,
        })
    return results


def calculate_buildability_score(feature_counts: dict) -> int:
    """Calculate buildability score (0-100)."""
    total = feature_counts["total"]
    if total == 0:
        return 0
    completed = feature_counts["completed"]
    return round((completed / total) * 100)


def generate_report(output_format: str = "text") -> dict:
    """Generate the complete build report."""
    feature_counts = count_features()
    env_counts = count_env_features()
    issues = get_github_issues()
    issue_categories = categorise_issues(issues)
    feature_details = get_feature_details()
    buildability = calculate_buildability_score(feature_counts)

    report = {
        "project": "browser-agent-test-fixture",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "features": feature_counts,
        "environment": env_counts,
        "buildability_score": buildability,
        "github_issues": {
            "total": len(issues),
            "by_category": issue_categories,
        },
        "feature_details": feature_details,
    }

    if output_format == "text":
        print_text_report(report)
    else:
        print(json.dumps(report, indent=2))

    return report


def print_text_report(report: dict) -> None:
    """Print human-readable build report."""
    fc = report["features"]
    ec = report["environment"]
    gi = report["github_issues"]

    print("=" * 60)
    print(f"BUILD REPORT: {report['project']}")
    print(f"Generated: {report['timestamp']}")
    print("=" * 60)

    print(f"\nBuildability Score: {report['buildability_score']}%")

    print(f"\nFeatures: {fc['completed']}/{fc['total']} completed "
          f"({fc['blocked']} blocked, {fc['pending']} pending)")

    print(f"Environment: {ec['passed']}/{ec['total']} tests passed")

    print(f"\nGitHub Issues (claude-detected): {gi['total']}")
    for cat, count in gi.get("by_category", {}).items():
        print(f"  - {cat}: {count}")

    print("\nFeature Details:")
    for fd in report["feature_details"]:
        status_icon = {
            "completed": "+",
            "blocked": "X",
            "in_progress": "~",
            "pending": " ",
        }.get(fd["status"], "?")
        print(f"  [{status_icon}] {fd['feature_name']} (phase {fd['phase']})")

    print("=" * 60)


if __name__ == "__main__":
    output = "text"
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    generate_report(output)
