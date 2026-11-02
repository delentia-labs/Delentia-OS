"""
Round 109: the scripted demos of Delentia, runnable from a web page without installing anything.

This module has no web code. It runs the same commands a person would type (`delentia demo init`, `demo run <name> --scripted`, `demo reject <id>`) in a throw-away folder with a throw-away
data home, and gives back the report the demo wrote (Markdown). The page (app.py) only shows it.

What is real and what is scripted is said in the report itself: a fixed program stands in for the language model; the tools, the safety gate, the taint rule, the wait for a signature and the signed
audit chain are the real ones. Nothing here says anything about any model's ability.

Safety of this page, by construction:
  * nothing a visitor types reaches a command: the scenario and the language come from fixed lists, and anything else is refused;
  * every run gets its own folder and its own DELENTIA_HOME under a temp directory, removed afterwards: two visitors never share a file, and the host's own data is never touched;
  * the demo keys are generated inside that folder (`demo init`), used once and deleted with it;
  * a run has a time limit and the report is cut at a size limit.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

LANGS = ("en", "th")
TIME_LIMIT_S = 120.0
MAX_REPORT_CHARS = 20_000

# name -> (label, the demo scenario, whether a waiting action is refused afterwards)
SCENARIOS: Dict[str, Tuple[str, str, bool]] = {
    "compare": ("Compare three vendor quotes", "compare", False),
    "injection": ("A note hidden in a quote tells the agent to change a price (the agent obeys)", "injection", False),
    "injection_refused": ("The same, then you refuse the change", "injection", True),
}
LABELS: Dict[str, str] = {key: value[0] for key, value in SCENARIOS.items()}

_APPROVAL_ID = re.compile(r"Waiting for approval, id `([0-9a-f]{6,64})`")
_RESULT_FILE = re.compile(r"^Result file: (.+)$", re.MULTILINE)


class DemoError(RuntimeError):
    """The demo did not run to the end; the message says why and is safe to show."""


def _env(home: Path) -> Dict[str, str]:
    """A clean environment: the child sees a throw-away data home and none of this process's secrets."""
    keep = ("PATH", "SYSTEMROOT", "SystemRoot", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "PYTHONPATH", "VIRTUAL_ENV", "HOME", "USERPROFILE")
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update({"DELENTIA_HOME": str(home), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "DELENTIA_UPDATE_CHECK": "off", "DELENTIA_OFFLINE": "1", "NO_COLOR": "1"})
    return env


def _cli(args: List[str], home: Path, timeout: float) -> str:
    proc = subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=_env(home), cwd=str(home))
    if proc.returncode not in (0, 1):                                           # 1 = a demo check failed: still a report to show
        raise DemoError(f"the demo stopped with exit code {proc.returncode}")
    return (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr and proc.returncode else "")


def run_scenario(name: str, lang: str = "en", *, time_limit_s: float = TIME_LIMIT_S) -> str:
    """Run one scenario in a fresh folder and return the Markdown report. Raises DemoError with a message that is safe to show."""
    if name not in SCENARIOS:
        raise DemoError("unknown scenario")
    if lang not in LANGS:
        raise DemoError("unknown language")
    _, demo_name, refuse = SCENARIOS[name]
    work = Path(tempfile.mkdtemp(prefix="delentia-browser-demo-"))
    try:
        home, folder = work / "home", work / "demo"
        home.mkdir()
        _cli(["demo", "init", "--lang", lang, "--dir", str(folder)], home, time_limit_s)
        out = _cli(["demo", "run", demo_name, "--scripted", "--dir", str(folder)], home, time_limit_s)
        report = _read_report(out, work)
        if refuse:
            found = _APPROVAL_ID.search(out) or _APPROVAL_ID.search(report)
            if not found:
                raise DemoError("the demo did not stop to wait for a signature, so there was nothing to refuse")
            after = _cli(["demo", "reject", found.group(1), "--dir", str(folder)], home, time_limit_s)
            report += "\n\n---\n\n## You refused the change\n\n" + _fence(after.strip())
        return report[:MAX_REPORT_CHARS]
    except subprocess.TimeoutExpired as exc:
        raise DemoError("the demo took too long and was stopped") from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _read_report(stdout: str, work: Path) -> str:
    """The demo writes its report to a file and prints the same text; prefer the file, fall back to what was printed."""
    found = _RESULT_FILE.search(stdout)
    if found:
        path = Path(found.group(1).strip())
        try:
            if work in path.resolve().parents:                                 # only a file inside this run's own folder
                return path.read_text(encoding="utf-8")
        except OSError:
            pass
    return stdout


def _fence(text: str) -> str:
    return "```\n" + text.replace("```", "'''") + "\n```"


def intro(lang: str = "en") -> str:
    """What the visitor is looking at, before pressing anything."""
    if lang == "th":
        return ("**เดโมสคริปต์ ไม่ใช่โมเดลจริง** โปรแกรมสคริปต์ที่เขียนไว้ล่วงหน้าทำหน้าที่แทนโมเดลภาษา ส่วนเครื่องมือ ไฟล์ ประตูความปลอดภัย การรอลายเซ็น และบันทึกที่เซ็นกำกับเป็นของจริงที่รันอยู่ตอนนี้ "
                "ผลนี้จึงแสดงว่า**กลไกทำงานอย่างไร** ไม่ได้บอกอะไรเกี่ยวกับความสามารถของโมเดลใด ๆ")
    return ("**A scripted demo, not a real model.** A fixed program stands in for the language model. The tools, the files, the safety gate, the wait for a signature and the signed log are the real "
            "ones, running now. So this shows **how the mechanism behaves**; it says nothing about any model's ability.")
