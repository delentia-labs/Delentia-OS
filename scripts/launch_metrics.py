"""
Round 107: the launch numbers worth looking at, read from public sources, with their limits stated next to them.

    python scripts/launch_metrics.py                 # print today's snapshot
    python scripts/launch_metrics.py --append        # also append it to ~/.delentia/launch_metrics.jsonl so growth can be compared week to week

Why this exists. A launch plan that says "do not use GitHub stars as the success measure" needs a different measure, and the honest one is "how many people got from nothing to a
working first run". The install-report issue form (`.github/ISSUE_TEMPLATE/install_report.yml`) asks exactly that, so this script counts the answers. Everything else here is context:

  * install reports: how many, how many say the first run worked / partly / not, with a Wilson 95% interval (a handful of reports gives a wide one; the script says so);
  * downloads of the Windows installer from the GitHub release (a download is not an install);
  * PyPI downloads of the last day / week / month from pypistats.org (these include mirrors and bots: a rising number is not a count of people);
  * stars, forks, open issues, for orientation only.

What it does NOT do: it never reads a person's data, never writes to any service, and sends no token anywhere but api.github.com (an optional GITHUB_TOKEN raises the rate limit).
A number that could not be fetched is reported as null with the reason, never as zero.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO = "delentia-labs/Delentia-OS"
PACKAGE = "delentia-os"
Fetch = Callable[[str], Any]


def wilson(k: int, n: int, z: float = 1.96) -> Optional[Tuple[float, float]]:
    """95% Wilson interval for k successes in n; None when n is 0."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def http_json(url: str) -> Any:
    headers = {"User-Agent": "delentia-launch-metrics", "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:        # noqa: S310 - fixed public https endpoints
        return json.loads(response.read().decode("utf-8"))


ANSWER = re.compile(r"###\s*Did the first run work\?\s*\n+\s*(.+)", re.I)
MINUTES = re.compile(r"###\s*Roughly how many minutes[^\n]*\n+\s*(\d+)", re.I)


def classify_report(body: str) -> str:
    """'worked' | 'partly' | 'failed' | 'unknown' from the dropdown answer in an install-report issue body."""
    found = ANSWER.search(body or "")
    if not found:
        return "unknown"
    text = found.group(1).strip().lower()
    if text.startswith("yes"):
        return "worked"
    if text.startswith("partly"):
        return "partly"
    if text.startswith("no"):
        return "failed"
    return "unknown"


def install_reports(fetch: Fetch, repo: str = REPO) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    for page in range(1, 6):
        batch = fetch(f"https://api.github.com/repos/{repo}/issues?labels=install-report&state=all&per_page=100&page={page}")
        issues += [i for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            break
    counts = {"worked": 0, "partly": 0, "failed": 0, "unknown": 0}
    minutes: List[int] = []
    for issue in issues:
        counts[classify_report(issue.get("body") or "")] += 1
        m = MINUTES.search(issue.get("body") or "")
        if m:
            minutes.append(int(m.group(1)))
    known = counts["worked"] + counts["partly"] + counts["failed"]
    interval = wilson(counts["worked"], known)
    minutes.sort()
    return {"reports": len(issues), **counts, "worked_share": (counts["worked"] / known) if known else None,
            "worked_share_95ci": [round(interval[0], 3), round(interval[1], 3)] if interval else None,
            "median_minutes_to_first_run": minutes[len(minutes) // 2] if minutes else None,
            "note": "self-reported by people who chose to report; a small n gives a wide interval" + ("" if known >= 20 else " (fewer than 20 usable reports)")}


def installer_downloads(fetch: Fetch, repo: str = REPO) -> Dict[str, Any]:
    releases = fetch(f"https://api.github.com/repos/{repo}/releases?per_page=30")
    rows = []
    for rel in releases:
        for asset in rel.get("assets", []):
            if asset.get("name", "").lower().endswith(".exe"):
                rows.append({"release": rel.get("tag_name"), "asset": asset["name"], "downloads": int(asset.get("download_count", 0))})
    return {"installer_assets": rows, "total_installer_downloads": sum(r["downloads"] for r in rows),
            "note": "a download is not an install; the same person may download twice and the build checks of the project itself count"}


def pypi_recent(fetch: Fetch, package: str = PACKAGE) -> Dict[str, Any]:
    data = fetch(f"https://pypistats.org/api/packages/{package}/recent")
    d = data.get("data", {})
    return {"last_day": d.get("last_day"), "last_week": d.get("last_week"), "last_month": d.get("last_month"),
            "note": "includes mirrors, CI systems and bots; a rising number is not a count of people"}


def repo_context(fetch: Fetch, repo: str = REPO) -> Dict[str, Any]:
    r = fetch(f"https://api.github.com/repos/{repo}")
    return {"stars": r.get("stargazers_count"), "forks": r.get("forks_count"), "open_issues_and_prs": r.get("open_issues_count"),
            "note": "for orientation only; stars do not show that anyone installed or used it"}


def snapshot(fetch: Fetch = http_json, repo: str = REPO, package: str = PACKAGE) -> Dict[str, Any]:
    out: Dict[str, Any] = {"taken_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "repo": repo, "package": package}
    for key, func in (("install_reports", lambda: install_reports(fetch, repo)), ("installer", lambda: installer_downloads(fetch, repo)),
                      ("pypi", lambda: pypi_recent(fetch, package)), ("repo", lambda: repo_context(fetch, repo))):
        try:
            out[key] = func()
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            out[key] = {"value": None, "why_not": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return out


def render(snap: Dict[str, Any]) -> str:
    lines = [f"# Launch metrics, {snap['taken_at']}", ""]
    ir = snap.get("install_reports", {})
    if "reports" in ir:
        share = "n/a" if ir["worked_share"] is None else f"{ir['worked_share']:.0%} (95% interval {ir['worked_share_95ci'][0]:.0%} to {ir['worked_share_95ci'][1]:.0%})"
        lines += [f"- Install reports: {ir['reports']} (worked {ir['worked']}, partly {ir['partly']}, failed {ir['failed']}, unreadable {ir['unknown']}); first run worked: {share}",
                  f"  - median minutes to the first run, as reported: {ir['median_minutes_to_first_run']}", f"  - {ir['note']}"]
    else:
        lines.append(f"- Install reports: not available ({ir.get('why_not')})")
    inst = snap.get("installer", {})
    lines.append(f"- Installer downloads (GitHub releases): {inst.get('total_installer_downloads', 'not available: ' + str(inst.get('why_not')))}")
    py = snap.get("pypi", {})
    lines.append(f"- PyPI downloads (day / week / month): {py.get('last_day')} / {py.get('last_week')} / {py.get('last_month')}" if "last_day" in py else f"- PyPI: not available ({py.get('why_not')})")
    rp = snap.get("repo", {})
    lines.append(f"- Repository (context only): {rp.get('stars')} stars, {rp.get('forks')} forks" if "stars" in rp else f"- Repository: not available ({rp.get('why_not')})")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--append", action="store_true", help="append the snapshot to the history file")
    ap.add_argument("--history", default=str(Path(os.environ.get("DELENTIA_HOME") or Path.home() / ".delentia") / "launch_metrics.jsonl"))
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    snap = snapshot()
    if args.append:
        path = Path(args.history)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snap, ensure_ascii=False) + "\n")
    sys.stdout.write(json.dumps(snap, indent=2, ensure_ascii=False) + "\n" if args.json else render(snap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
