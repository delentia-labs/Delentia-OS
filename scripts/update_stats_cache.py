#!/usr/bin/env python3
"""
update_stats_cache.py
Script for CI/CD to update .stats_cache.json after test runs.

Usage:
    python scripts/update_stats_cache.py [--test-count N]

CI/CD Integration:
    Add this step AFTER pytest run in your CI workflow:
    
    - name: Update stats cache
      run: python scripts/update_stats_cache.py
"""

import json
import os
import subprocess
import time
import argparse


CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".stats_cache.json")


def count_tests_from_pytest() -> int:
    """Run pytest --collect-only to count tests."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--co", "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        for line in result.stdout.splitlines():
            if "selected" in line and "test" in line:
                import re
                m = re.search(r"(\d+) selected", line)
                if m:
                    return int(m.group(1))
    except Exception as e:
        print(f"Warning: Could not count tests via pytest: {e}")
    return None


def count_microservices() -> int:
    """Count microservice directories."""
    microservices_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "microservices"
    )
    if not os.path.isdir(microservices_dir):
        return 62  # baseline
    return len([
        d for d in os.listdir(microservices_dir)
        if os.path.isdir(os.path.join(microservices_dir, d))
        and not d.startswith(".")
    ])


def main():
    parser = argparse.ArgumentParser(description="Update RCT stats cache")
    parser.add_argument("--test-count", type=int, help="Override test count")
    parser.add_argument("--skip-pytest", action="store_true", help="Skip pytest collection")
    args = parser.parse_args()

    print("=== RCT Stats Cache Updater ===")

    # Load existing cache
    existing = {}
    if os.path.isfile(CACHE_PATH):
        with open(CACHE_PATH) as f:
            existing = json.load(f)
        print(f"[*] Existing cache: {existing}")

    # Compute new stats
    if args.test_count:
        test_count = args.test_count
        print(f"[+] Using provided test count: {test_count}")
    elif args.skip_pytest:
        test_count = existing.get("testCount", 4849)
        print(f"[*] Skipping pytest, keeping: {test_count}")
    else:
        print("[*] Counting tests via pytest (this may take a moment)...")
        test_count = count_tests_from_pytest()
        if test_count is None:
            test_count = existing.get("testCount", 4849)
            print(f"[!] Fallback to existing: {test_count}")
        else:
            print(f"[+] Pytest count: {test_count}")

    microservice_count = count_microservices()
    print(f"[+] Microservice count: {microservice_count}")

    cache = {
        "testCount": test_count,
        "microserviceCount": microservice_count,
        "algorithmCount": 41,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"[+] Cache written to {CACHE_PATH}")
    print(f"    {json.dumps(cache, indent=2)}")


if __name__ == "__main__":
    main()
