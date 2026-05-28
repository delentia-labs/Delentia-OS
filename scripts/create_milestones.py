#!/usr/bin/env python3
"""
Create GitHub Milestones for delentia-os via GitHub REST API.

Usage:
    python scripts/create_milestones.py --token ghp_xxxYOURTOKENxxx

Requires: requests (pip install requests)
"""

import argparse
import json
import sys

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

REPO_OWNER = "rctlabs"
REPO_NAME = "delentia-os"

MILESTONES = [
    {
        "title": "v1.0.3a0 — Playground Release",
        "due_on": "2026-05-31T00:00:00Z",
        "description": (
            "Zero-friction first experience: Colab/Binder/Codespaces quick-launch, "
            "hypothesis property tests, benchmark CLI, GitHub Discussions, "
            "API stability documentation."
        ),
    },
    {
        "title": "v1.0.0 — Stable PyPI Release",
        "due_on": "2026-09-30T00:00:00Z",
        "description": (
            "pip install delentia-os from PyPI with stability guarantee. "
            "Includes type stubs, full API reference, semantic versioning guarantee, "
            "pre-built wheels for Python 3.10/3.11/3.12, and signed GitHub Release."
        ),
    },
    {
        "title": "v1.1.0 — Observability + Integrations",
        "due_on": "2026-12-31T00:00:00Z",
        "description": (
            "Production-ready observability: Prometheus /metrics, Grafana dashboard, "
            "docker-compose.monitoring.yml, OpenTelemetry trace exporter, "
            "n8n adapter, Home Assistant adapter, Obsidian plugin."
        ),
    },
    {
        "title": "v1.2.0 — ASEAN Expansion",
        "due_on": "2027-06-30T00:00:00Z",
        "description": (
            "ASEAN regional expansion: VN/ID/MY language adapters, "
            "PDPA compliance module (Thailand Personal Data Protection Act), "
            "RFC-002 Multi-Region Consensus, Universal Adapter v2 (20+ integrations)."
        ),
    },
]


def create_milestone(session: requests.Session, owner: str, repo: str, milestone: dict) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/milestones"
    response = session.post(url, json=milestone)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Create GitHub milestones for delentia-os")
    parser.add_argument("--token", required=True, help="GitHub Personal Access Token (repo scope)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be created without making API calls"
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {args.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    for ms in MILESTONES:
        if args.dry_run:
            print(f"[DRY RUN] Would create: {ms['title']} (due: {ms['due_on'][:10]})")
            continue
        try:
            result = create_milestone(session, REPO_OWNER, REPO_NAME, ms)
            print(f"✅ Created: {result['title']} → {result['html_url']}")
        except requests.HTTPError as exc:
            body = exc.response.json() if exc.response else {}
            if body.get("errors", [{}])[0].get("code") == "already_exists":
                print(f"⚠️  Already exists: {ms['title']} (skipped)")
            else:
                print(f"❌ Failed: {ms['title']} — {exc}")
                print(f"   Response: {json.dumps(body, indent=2)}")

    print("\nDone. View milestones at:")
    print(f"  https://github.com/{REPO_OWNER}/{REPO_NAME}/milestones")


if __name__ == "__main__":
    main()
