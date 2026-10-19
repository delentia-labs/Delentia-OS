"""
Round 90: ONE readiness snapshot, generated from facts, instead of status sentences edited by hand in five documents.

    python scripts/readiness_snapshot.py            # writes docs/release/READINESS_SNAPSHOT.md and .json (uses `gh` for the latest CI run when it is available)
    python scripts/readiness_snapshot.py --offline  # no network, no gh: only what the repository itself says
    python scripts/readiness_snapshot.py --check    # exit 1 when the committed snapshot disagrees with the repository (used by a test)

What it records, each with where it came from: the commit; the latest completed CI run on main and whether TESTING_CANONICAL.md quotes that run; the number of agent tools and how each is
classified; the gates of docs/release/RELEASE_LEVELS.md and their status words; the master workflows' evidence counts; whether anything has a LIVE result with a capable model. A reader
who finds a number in the README can check it against this file, and this file against the command that made it. It never claims a gate is met: it copies the gate table's own words and
counts them.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT_MD = ROOT / "docs" / "release" / "READINESS_SNAPSHOT.md"
OUT_JSON = ROOT / "docs" / "release" / "READINESS_SNAPSHOT.json"
LEVELS = ROOT / "docs" / "release" / "RELEASE_LEVELS.md"
CANON = ROOT / "docs" / "testing" / "TESTING_CANONICAL.md"


def _run(cmd: List[str], timeout: float = 60.0) -> Optional[str]:
    try:
        done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return done.stdout.strip() if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_facts() -> Dict[str, Any]:
    sha = _run(["git", "rev-parse", "HEAD"])
    return {"sha": sha, "short": sha[:7] if sha else None, "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]), "dirty": bool(_run(["git", "status", "--porcelain"]))}


def canonical_facts() -> Dict[str, Any]:
    text = CANON.read_text(encoding="utf-8")
    m = re.search(r"\*\*Authoritative checkpoint:\*\* \*\*(?P<passed>[\d,]+) passed(?: · (?P<skipped>[\d,]+) skipped)?(?: · (?P<failed>[\d,]+) failed)?(?: · (?P<cov>[\d.]+)% coverage)?", text)
    run = re.search(r"run (\d{9,})", text)
    sha = re.search(r"commit ([0-9a-f]{7,40})", text)
    updated = re.search(r"\*\*Last Updated:\*\* (\d{4}-\d{2}-\d{2})", text)
    return {"passed": m["passed"] if m else None, "skipped": m["skipped"] if m else None, "coverage": m["cov"] if m else None,
            "ci_run": run.group(1) if run else None, "commit": sha.group(1) if sha else None, "last_updated": updated.group(1) if updated else None}


def latest_ci() -> Optional[Dict[str, Any]]:
    out = _run(["gh", "run", "list", "--branch", "main", "--workflow", "ci.yml", "--status", "completed", "--limit", "1", "--json", "databaseId,conclusion,headSha,createdAt"])
    if not out:
        return None
    try:
        row = json.loads(out)[0]
    except (ValueError, IndexError):
        return None
    return {"run": str(row["databaseId"]), "conclusion": row["conclusion"], "sha": row["headSha"][:7], "created_at": row["createdAt"]}


def tool_facts() -> Dict[str, Any]:
    from rct_control_plane.governed_autonomous_loop import OWNER_ONLY_TOOLS, PERSON_NEUTRAL_TOOLS, TAINT_GATED_TOOLS, TAINT_INERT_TOOLS, TAINT_SOURCE_TOOLS
    from rct_control_plane.mcp_server import mcp
    names = sorted(t.name for t in asyncio.run(mcp.list_tools()))
    return {"count": len(names), "taint_source": sum(n in TAINT_SOURCE_TOOLS for n in names), "taint_gated": sum(n in TAINT_GATED_TOOLS for n in names),
            "taint_inert": sum(n in TAINT_INERT_TOOLS for n in names), "owner_only": sum(n in OWNER_ONLY_TOOLS for n in names), "person_neutral": sum(n in PERSON_NEUTRAL_TOOLS for n in names),
            "unclassified_for_taint": [n for n in names if n not in TAINT_SOURCE_TOOLS | TAINT_GATED_TOOLS | TAINT_INERT_TOOLS]}


def gate_facts() -> Dict[str, Any]:
    gates = []
    for line in LEVELS.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("G-"):
            status = cells[3]
            word = "met" if status.lower().startswith("met") else "not met" if "not met" in status.lower()[:12] or status.lower().startswith("**not met") else "partly / see text"
            gates.append({"gate": cells[0], "needed_for": cells[1], "status_word": word, "status_text": status})
    return {"gates": gates, "met": sum(g["status_word"] == "met" for g in gates), "not_met": sum(g["status_word"] == "not met" for g in gates), "partly": sum(g["status_word"] == "partly / see text" for g in gates)}


def workflow_facts() -> Dict[str, Any]:
    from research import master_workflows as mw
    counts = mw.readiness_counts()
    return {"workflows": counts.get("workflows"), "scripted_whole_job": counts.get("scripted_end_to_end"), "live_runner": counts.get("live_runner_exists"), "live_result_with_a_capable_model": counts.get("live_result")}


def build(offline: bool) -> Dict[str, Any]:
    ci = None if offline else latest_ci()
    canon = canonical_facts()
    snap: Dict[str, Any] = {"generated_by": "scripts/readiness_snapshot.py", "generated_at": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()), "offline": offline,
                            "git": git_facts(), "canonical_checkpoint": canon, "latest_completed_ci_on_main": ci, "tools": tool_facts(), "gates": gate_facts(), "master_workflows": workflow_facts()}
    snap["canonical_matches_latest_ci"] = None if ci is None else (ci["run"] == canon["ci_run"])
    return snap


def render(s: Dict[str, Any]) -> str:
    g, t, w, c = s["git"], s["tools"], s["master_workflows"], s["canonical_checkpoint"]
    ci = s["latest_completed_ci_on_main"]
    lines = [
        "# Readiness snapshot", "",
        f"> Generated by `scripts/readiness_snapshot.py` at {s['generated_at']} from commit `{g['short']}` ({g['branch']}{', with uncommitted changes' if g['dirty'] else ''}). **Do not edit by hand**: change the sources and run the script again. "
        "Nothing here is a claim of safety or capability; it lists what exists and what each gate currently says.", "",
        "## Tests", "",
        f"* Checkpoint quoted in `docs/testing/TESTING_CANONICAL.md`: **{c['passed']} passed, {c['skipped']} skipped, coverage {c['coverage']}%** (CI run {c['ci_run']}, commit {c['commit']}, updated {c['last_updated']}).",
        (f"* Latest completed CI run on main: run {ci['run']} at `{ci['sha']}`, **{ci['conclusion']}** ({ci['created_at']}). "
         + ("The canonical checkpoint IS this run." if s["canonical_matches_latest_ci"] else "**The canonical checkpoint is an OLDER run than the latest one: refresh it with `scripts/update_test_checkpoint.py`.**"))
        if ci else "* Latest CI run: not looked up (offline, or `gh` not available).", "",
        "## The agent's tools", "",
        f"* {t['count']} tools: {t['taint_source']} return text from outside, {t['taint_gated']} need a signature once an episode has read outside text, {t['taint_inert']} are reviewed as unable to cause a side effect; "
        f"{t['owner_only']} are owner-only and {t['person_neutral']} are person-neutral. Unclassified for the taint gate: {t['unclassified_for_taint'] or 'none'}.", "",
        "## Master workflows (the owner's end-to-end jobs)", "",
        f"* {w['workflows']} workflows; {w['scripted_whole_job']} have a scripted whole-job run; {w['live_runner']} have a live runner; **{w['live_result_with_a_capable_model']} have a live result with a capable model.**", "",
        "## Release gates (copied from `docs/release/RELEASE_LEVELS.md`)", "",
        f"{s['gates']['met']} met · {s['gates']['not_met']} not met · {s['gates']['partly']} partly or to be read in full.", "",
        "| Gate | Needed for | Status word | Status text |", "|---|---|---|---|",
    ]
    for gate in s["gates"]["gates"]:
        lines.append(f"| {gate['gate']} | {gate['needed_for']} | {gate['status_word']} | {gate['status_text'][:150]} |")
    lines += ["", "The machine-readable copy is `READINESS_SNAPSHOT.json` in this folder.", ""]
    return "\n".join(lines)


def check() -> int:
    if not OUT_JSON.exists():
        print("no committed snapshot: run scripts/readiness_snapshot.py")
        return 1
    committed = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    problems = []
    if committed["canonical_checkpoint"] != canonical_facts():
        problems.append("the snapshot's test checkpoint differs from TESTING_CANONICAL.md")
    if committed["gates"] != gate_facts():
        problems.append("the snapshot's gate table differs from RELEASE_LEVELS.md")
    if committed["tools"]["count"] != tool_facts()["count"]:
        problems.append("the number of agent tools changed since the snapshot")
    for p in problems:
        print("STALE:", p)
    print("snapshot is consistent with the repository" if not problems else "run: python scripts/readiness_snapshot.py --offline")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check()
    snap = build(a.offline)
    OUT_JSON.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    OUT_MD.write_text(render(snap), encoding="utf-8", newline="\n")
    print(f"wrote {OUT_MD.relative_to(ROOT)} and {OUT_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
