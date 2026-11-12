"""
Release receipts: one command that checks a PUBLISHED release the way an outsider would, and writes down what happened (DEL-PTP-03 and DEL-PTP-05 of the Preview 0.1 closure plan).

    python scripts/release_receipts.py --version 2.4.4 --out docs/release/evidence/2.4.4
    python scripts/release_receipts.py --version 2.4.4 --reuse-venv C:\\path\\to\\venv --out ...   # skip the install, use a venv that already holds it
    python scripts/release_receipts.py --version 2.4.4 --source . --out ...                       # also run the checks that need the repository at the tag (evidence kit, crash and replay tests)

What it does, from the INSTALLED package in an empty virtual environment (never from the source tree):
  INSTALL   pip install delentia-os==VERSION, pip check, `delentia --version`, the wheel's SHA-256 against the one PyPI published
  DEMO-01   demo compare (scripted): every check passes and the audit chain is intact
  DEMO-02   demo edit (scripted): it stops and waits, the file is unchanged until a signature, one signature changes it once
  DEMO-03   a signature from a key nobody trusts is refused and nothing changes
  DEMO-04   demo injection (scripted): it stops and waits; refusing it leaves the files unchanged
  DEMO-05   the audit chain verifies, and a copy with ONE stored value changed does not
  GITHUB    the release's assets, the installer's SHA-256 against its line in SHA256SUMS.txt, the tag's commit, the CI runs on that commit
  SOURCE    (with --source) the evidence kit and its verifier; the crash / replay tests (DEMO-06)

A check that could not run is `not_run`, never a pass. Every check keeps the command, the exit code and the tail of its output. The receipt (`receipt.json`, `RECEIPT.md`) names the
versions, the operating system and the time. A scripted model proves the gate and the audit; it says nothing about how well a language model works. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

PYPI_JSON = "https://pypi.org/pypi/delentia-os/{version}/json"
WAIT_RE = re.compile(r"(?:Waiting for approval, id|รออนุมัติ รหัส)\s+`?([0-9a-f-]{8,})", re.I)


# ---------------------------------------------------------------------------------------------------------------------------------- helpers (pure, tested)
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_approval_id(text: str) -> Optional[str]:
    match = WAIT_RE.search(text or "")
    return match.group(1) if match else None


def parse_checksums(text: str) -> Dict[str, str]:
    """`SHA256SUMS.txt` lines: `<64 hex> [*]<name>` -> {name: hex}."""
    out: Dict[str, str] = {}
    for line in (text or "").splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def count_passed_checks(report_text: str) -> Dict[str, int]:
    return {"passed": len(re.findall(r"^- passed:", report_text or "", re.M)), "failed": len(re.findall(r"^- (?:FAILED|failed):", report_text or "", re.M))}


def verdict(checks: List[Dict[str, Any]]) -> str:
    """`pass` only when every check ran and passed; `fail` when any failed; otherwise `incomplete` (something did not run)."""
    states = [c["status"] for c in checks]
    if "fail" in states:
        return "fail"
    if "not_run" in states or not states:
        return "incomplete"
    return "pass"


def check(cid: str, title: str, status: str, detail: str, evidence: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    assert status in ("pass", "fail", "not_run")
    return {"id": cid, "title": title, "status": status, "detail": detail, "evidence": evidence or []}


class Runner:
    def __init__(self, python: str, env: Dict[str, str], cwd: Path):
        self.python, self.env, self.cwd = python, env, cwd
        self.log: List[Dict[str, Any]] = []

    def run(self, args: List[str], timeout: float = 900) -> Dict[str, Any]:
        started = time.time()
        try:
            done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env, cwd=str(self.cwd), timeout=timeout)
            code, out = done.returncode, (done.stdout or "") + (done.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = -1, "timed out"
        except OSError as exc:
            code, out = -2, f"could not start: {exc}"
        row = {"command": " ".join(str(a) for a in args), "exit_code": code, "seconds": round(time.time() - started, 1), "output_tail": out[-700:], "output": out}
        self.log.append({k: v for k, v in row.items() if k != "output"})
        return row

    def cli(self, *args: str, timeout: float = 900) -> Dict[str, Any]:
        return self.run([self.python, "-m", "rct_control_plane.cli", *args], timeout=timeout)


def slim(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: v for k, v in r.items() if k != "output"} for r in rows]


# ---------------------------------------------------------------------------------------------------------------------------------- the checks
def venv_python(venv: Path) -> str:
    return str(venv / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python"))


def check_install(version: str, work: Path, reuse: Optional[Path], base_env: Dict[str, str]) -> "tuple[List[Dict[str, Any]], Optional[str]]":
    results: List[Dict[str, Any]] = []
    if reuse is not None:
        py = venv_python(reuse)
    else:
        venv = work / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
        py = venv_python(venv)
    r = Runner(py, base_env, work)
    ev: List[Dict[str, Any]] = []
    if reuse is None:
        ev.append(r.run([py, "-m", "pip", "install", "--quiet", "--no-cache-dir", f"delentia-os=={version}"], timeout=1800))
        if ev[-1]["exit_code"] != 0:
            results.append(check("INSTALL", f"pip install delentia-os=={version} in an empty environment", "fail", "pip could not install it", slim(ev)))
            return results, None
    pc = r.run([py, "-m", "pip", "check"])
    ver: Dict[str, Any] = r.cli("--version")
    ev += [pc, ver]
    ok = pc["exit_code"] == 0 and version in ver["output"]
    results.append(check("INSTALL", f"installed in an empty environment, pip check clean, `delentia --version` says {version}", "pass" if ok else "fail", ver["output_tail"].strip()[-120:], slim(ev)))
    # the wheel PyPI published
    try:
        with urllib.request.urlopen(PYPI_JSON.format(version=version), timeout=30) as resp:                    # noqa: S310 - a fixed https address
            files = json.loads(resp.read())["urls"]
        wheel = next(f for f in files if f["filename"].endswith(".whl"))
        dl = work / "dl"
        dl.mkdir(exist_ok=True)
        d = r.run([py, "-m", "pip", "download", "--no-deps", "--no-cache-dir", "-d", str(dl), f"delentia-os=={version}"], timeout=900)
        got = sha256_file(next(dl.glob("*.whl")))
        same = got == wheel["digests"]["sha256"]
        results.append(check("WHEEL-SHA", "the wheel pip downloads has the SHA-256 PyPI published", "pass" if same else "fail", f"{got} (PyPI: {wheel['digests']['sha256']})", slim([d])))
    except Exception as exc:                                                                                     # noqa: BLE001 - a network or parsing failure is 'not run', not a pass
        results.append(check("WHEEL-SHA", "the wheel pip downloads has the SHA-256 PyPI published", "not_run", f"{type(exc).__name__}: {exc}"))
    return results, py


def demo_checks(py: str, work: Path, base_env: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    user = work / "user-home"                      # an empty home, so nothing here reads or writes the person's real ~/.delentia (the demo keeps its own data folder inside the demo folder)
    user.mkdir(exist_ok=True)
    demo = work / "demo"
    env = {**base_env, "HOME": str(user), "USERPROFILE": str(user), "DELENTIA_UPDATE_CHECK": "off"}
    r = Runner(py, env, work)
    init = r.cli("demo", "init", "--lang", "en", "--dir", str(demo))
    quote = demo / "workspace" / "quotes" / "vendor_a.md"
    if init["exit_code"] != 0 or not quote.is_file():
        return [check(cid, t, "fail", "demo init failed: " + init["output_tail"][-200:], slim([init])) for cid, t in (("DEMO-01", "compare"), ("DEMO-02", "edit"), ("DEMO-03", "wrong key"), ("DEMO-04", "injection"), ("DEMO-05", "tamper"))]
    db = demo / "data" / "agentic.db"
    before = sha256_file(quote)

    compare = r.cli("demo", "run", "compare", "--scripted", "--dir", str(demo))
    counts = count_passed_checks(compare["output"])
    status1 = r.cli("demo", "status", "--dir", str(demo))
    try:
        audit = json.loads(status1["output"][status1["output"].index("{"): status1["output"].rindex("}") + 1])["audit"]
    except Exception:                                                                                            # noqa: BLE001
        audit = {}
    ok1 = compare["exit_code"] == 0 and counts["passed"] >= 5 and counts["failed"] == 0 and audit.get("ok") is True and audit.get("signed") == audit.get("rows") and sha256_file(quote) == before
    out.append(check("DEMO-01", "compare (scripted): every check passes, the chain is intact and signed, the originals are unchanged", "pass" if ok1 else "fail",
                     f"{counts['passed']} checks passed, {counts['failed']} failed; audit {audit}", slim([compare, status1])))

    edit = r.cli("demo", "run", "edit", "--scripted", "--dir", str(demo))
    approval = find_approval_id(edit["output"])
    unchanged_waiting = sha256_file(quote) == before
    ok2a = approval is not None and unchanged_waiting
    # DEMO-03: a key that is not on the approvers list
    wrong = work / "wrong-approver.pem"
    kg = r.cli("approvals", "keygen", "--out", str(wrong))
    bad: Dict[str, Any] = r.cli("approvals", "approve", approval or "none", "--key", str(wrong), "--db", str(db)) if approval else {"exit_code": -3, "output_tail": "no approval id", "command": "", "seconds": 0}
    still = sha256_file(quote) == before
    out.append(check("DEMO-03", "a signature from a key nobody trusts is refused, and the file stays unchanged", "pass" if (approval and bad["exit_code"] != 0 and still and kg["exit_code"] == 0) else "fail",
                     f"exit code {bad['exit_code']}; file unchanged: {still}; {bad['output_tail'].strip()[-150:]}", slim([kg, bad]) if approval else slim([kg])))
    good: Dict[str, Any] = r.cli("demo", "approve", approval or "none", "--scripted", "--dir", str(demo)) if approval else {"exit_code": -3, "output_tail": "no approval id", "command": "", "seconds": 0}
    after = sha256_file(quote)
    again: Dict[str, Any] = r.cli("demo", "approve", approval or "none", "--scripted", "--dir", str(demo)) if approval else {"exit_code": 0, "output_tail": "", "command": "", "seconds": 0}
    once = sha256_file(quote) == after
    ok2 = ok2a and good["exit_code"] == 0 and after != before and once
    out.insert(len(out) - 1, check("DEMO-02", "edit (scripted): it stops and waits, the file is unchanged until a signature, one signature changes it, a second approval does not change it again",
                                   "pass" if ok2 else "fail", f"approval id {approval}; unchanged while waiting: {unchanged_waiting}; changed after the signature: {after != before}; unchanged by a second approval: {once}",
                                   slim([edit, good, again])))

    demo2 = work / "demo-injection"                # a fresh folder: the injection scenario edits the same quote the edit demo has just changed
    init2 = r.cli("demo", "init", "--lang", "en", "--dir", str(demo2))
    inj = r.cli("demo", "run", "injection", "--scripted", "--dir", str(demo2))
    inj_id = find_approval_id(inj["output"])
    snapshot = {p.name: sha256_file(p) for p in (demo2 / "workspace" / "quotes").glob("*.md")}
    rej: Dict[str, Any] = r.cli("demo", "reject", inj_id or "none", "--dir", str(demo2)) if inj_id else {"exit_code": -3, "output_tail": "no approval id", "command": "", "seconds": 0}
    same = snapshot == {p.name: sha256_file(p) for p in (demo2 / "workspace" / "quotes").glob("*.md")}
    out.append(check("DEMO-04", "injection (scripted): it stops and waits for a person; refusing it is signed and leaves the files unchanged", "pass" if (inj_id and rej["exit_code"] == 0 and same) else "fail",
                     f"approval id {inj_id}; reject exit {rej['exit_code']}; files unchanged: {same}", slim([init2, inj] + ([rej] if inj_id else []))))

    verify = r.cli("audit-chain", "verify", "--db", str(db))
    tampered = work / "tampered.db"
    tamper_note = ""
    try:
        src = sqlite3.connect(str(db))               # the backup interface copies the write-ahead log too; a plain file copy would lose the newest rows
        dst = sqlite3.connect(str(tampered))
        src.backup(dst)
        src.close()
        dst.close()
        con = sqlite3.connect(str(tampered))
        cols = [row[1] for row in con.execute("PRAGMA table_info(audit_trail)")]
        target = next((c for c in cols if c in ("details", "payload", "action", "entity_type", "description")), cols[-1])
        first = con.execute("SELECT rowid FROM audit_trail ORDER BY rowid LIMIT 1").fetchone()[0]
        con.execute(f"UPDATE audit_trail SET {target} = COALESCE({target}, '') || 'x' WHERE rowid = ?", (first,))
        con.commit()
        con.close()
        tamper_note = f"changed one stored value in column {target}"
    except Exception as exc:                                                                                     # noqa: BLE001
        tamper_note = f"could not alter the copy: {exc}"
    bad_chain = r.cli("audit-chain", "verify", "--db", str(tampered))
    out.append(check("DEMO-05", "the audit chain verifies, and a copy with ONE stored value changed does not", "pass" if (verify["exit_code"] == 0 and bad_chain["exit_code"] != 0 and "could not" not in tamper_note) else "fail",
                     f"intact chain exit {verify['exit_code']}; altered copy exit {bad_chain['exit_code']} ({tamper_note})", slim([verify, bad_chain])))
    return sorted(out, key=lambda c: c["id"])


def github_checks(repo: str, tag: str, version: str, work: Path) -> List[Dict[str, Any]]:
    if shutil.which("gh") is None:
        return [check("GITHUB-ASSETS", "release assets and checksum", "not_run", "the gh command is not installed")]
    r = Runner(sys.executable, dict(os.environ), work)
    view = r.run(["gh", "release", "view", tag, "--repo", repo, "--json", "assets,tagName,publishedAt,isDraft,isPrerelease,targetCommitish"])
    out: List[Dict[str, Any]] = []
    try:
        info = json.loads(view["output"])
    except Exception:                                                                                             # noqa: BLE001
        return [check("GITHUB-ASSETS", "release assets and checksum", "not_run", "could not read the release: " + view["output_tail"][-150:], slim([view]))]
    names = [a["name"] for a in info.get("assets", [])]
    need = [f"Delentia-Setup-{version}.exe", "Delentia-Setup.exe", "SHA256SUMS.txt"]
    missing = [n for n in need if n not in names] + ([] if any(n.endswith(".whl") for n in names) else ["a wheel"]) + ([] if any(n.endswith(".tar.gz") for n in names) else ["an sdist"])
    dl = work / "release"
    dl.mkdir(exist_ok=True)
    d = r.run(["gh", "release", "download", tag, "--repo", repo, "--dir", str(dl), "--clobber"])
    sums = parse_checksums((dl / "SHA256SUMS.txt").read_text(encoding="utf-8")) if (dl / "SHA256SUMS.txt").is_file() else {}
    mism = []
    for name in (f"Delentia-Setup-{version}.exe", "Delentia-Setup.exe"):
        f = dl / name
        if not f.is_file() or name not in sums or sha256_file(f) != sums[name]:
            mism.append(name)
    hashes = {n: sha256_file(dl / n) for n in need if (dl / n).is_file()}
    out.append(check("GITHUB-ASSETS", f"{tag} carries the wheel, the sdist, both installers and SHA256SUMS.txt, and each installer equals its line", "pass" if not missing and not mism and not info.get("isDraft") else "fail",
                     f"missing: {missing or 'none'}; hash mismatch: {mism or 'none'}; sha256 {hashes}", slim([view, d])))
    tagsha = r.run(["gh", "api", f"repos/{repo}/git/ref/tags/{tag}", "--jq", ".object.type + \" \" + .object.sha"])
    commit = r.run(["gh", "api", f"repos/{repo}/commits/{tag}", "--jq", ".sha"])
    sha = commit["output"].strip()
    runs: Dict[str, Any] = r.run(["gh", "run", "list", "--repo", repo, "--commit", sha, "--json", "databaseId,name,status,conclusion,workflowName", "--limit", "30"]) if re.fullmatch(r"[0-9a-f]{40}", sha) else {"output": "[]", "exit_code": 1}
    try:
        run_rows = json.loads(runs["output"])
    except Exception:                                                                                             # noqa: BLE001
        run_rows = []
    out.append(check("GITHUB-TAG", f"{tag} points at a full commit and the workflow runs on it are recorded", "pass" if re.fullmatch(r"[0-9a-f]{40}", sha) else "fail",
                     f"commit {sha}; tag ref {tagsha['output'].strip()}; runs: " + ", ".join(f"{x.get('workflowName')} {x.get('conclusion') or x.get('status')} #{x.get('databaseId')}" for x in run_rows), slim([tagsha, commit, runs])))
    return out


def source_checks(source: Path, work: Path, version: str) -> List[Dict[str, Any]]:
    r = Runner(sys.executable, {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(source)}, source)
    out: List[Dict[str, Any]] = []
    kit_dir = work / "evidence-kit"
    kit = r.run([sys.executable, "scripts/evidence_kit.py", "--out", str(kit_dir)], timeout=3600)
    ver = r.run([sys.executable, "scripts/verify_evidence_kit.py", str(kit_dir)], timeout=600) if kit["exit_code"] == 0 else {"exit_code": -3, "output_tail": "the kit did not finish", "command": "", "seconds": 0}
    out.append(check("SOURCE-EVIDENCE-KIT", "the evidence kit runs from the repository and its verifier (standard library only) accepts the folder", "pass" if kit["exit_code"] == 0 and ver["exit_code"] == 0 else "fail",
                     f"kit exit {kit['exit_code']}, verifier exit {ver['exit_code']}", slim([kit, ver])))
    tests = ["rct_control_plane/tests/test_idempotency_round91_real.py", "rct_control_plane/tests/test_crash_windows_round82_real.py", "rct_control_plane/tests/test_live_workflows_w09_round105_real.py"]
    present = [t for t in tests if (source / t).is_file()]
    if not present:
        out.append(check("DEMO-06", "a crash and a resume do not repeat a once-only action", "not_run", "the crash / replay tests were not found in the source folder"))
    else:
        t = r.run([sys.executable, "-m", "pytest", *present, "-q", "-p", "no:cacheprovider", "-W", "ignore"], timeout=3600)
        out.append(check("DEMO-06", "a crash and a resume do not repeat a once-only action (the repository's crash and replay tests)", "pass" if t["exit_code"] == 0 else "fail", t["output_tail"].strip().splitlines()[-1] if t["output_tail"].strip() else "", slim([t])))
    return out


# ---------------------------------------------------------------------------------------------------------------------------------- main
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default="delentia-labs/Delentia-OS")
    ap.add_argument("--tag", default=None, help="default: v<version>")
    ap.add_argument("--reuse-venv", default=None, help="a virtual environment that already holds that version (skips the install)")
    ap.add_argument("--source", default=None, help="the repository checked out at the tag: also runs the evidence kit and the crash / replay tests")
    ap.add_argument("--skip-github", action="store_true")
    args = ap.parse_args(argv)
    tag = args.tag or f"v{args.version}"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    base_env = {k: v for k, v in os.environ.items() if not k.startswith("DELENTIA_")}
    base_env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    checks: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="delentia-receipts-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        install, py = check_install(args.version, work, Path(args.reuse_venv) if args.reuse_venv else None, base_env)
        checks += install
        if py:
            checks += demo_checks(py, work, base_env)
        else:
            checks += [check(c, "needs the installed package", "not_run", "the install did not succeed") for c in ("DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-05")]
        checks += github_checks(args.repo, tag, args.version, work) if not args.skip_github else [check("GITHUB-ASSETS", "release assets and checksum", "not_run", "skipped by --skip-github")]
        checks += source_checks(Path(args.source), work, args.version) if args.source else [check("SOURCE-EVIDENCE-KIT", "evidence kit from the repository", "not_run", "no --source given"), check("DEMO-06", "crash / replay tests", "not_run", "no --source given")]
    receipt = {"version": args.version, "tag": tag, "repo": args.repo, "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "python": platform.python_version(), "platform": platform.platform(),
               "scripted_model_note": "DEMO-* use a scripted stand-in for the model: they show the gate, the approval and the audit, not how well a language model works.",
               "verdict": verdict(checks), "checks": checks}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    icon = {"pass": "PASS", "fail": "FAIL", "not_run": "NOT RUN"}
    lines = [f"# Release receipt: delentia-os {args.version} ({tag})", "", f"Verdict: **{receipt['verdict']}** ({sum(c['status'] == 'pass' for c in checks)} pass, {sum(c['status'] == 'fail' for c in checks)} fail, {sum(c['status'] == 'not_run' for c in checks)} not run)",
             f"Run {started} on {platform.platform()} with Python {platform.python_version()}. {receipt['scripted_model_note']}", "", "| Check | Result | What was seen |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['id']}: {c['title']} | {icon[c['status']]} | {c['detail'][:300].replace('|', '/').replace(chr(10), ' ')} |")
    (out / "RECEIPT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(f"{icon[c['status']]:8s} {c['id']}: {c['detail'][:110]}" for c in checks))
    print(f"verdict: {receipt['verdict']}  ->  {out}")
    return 0 if receipt["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
