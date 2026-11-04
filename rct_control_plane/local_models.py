"""
Round 109: a person with no coding skill can get a local model from inside the Desk: see what this computer can hold, start or find Ollama, and download a model with a progress bar.

Until now the setup page told a new user to "type `ollama pull qwen3:8b` in a terminal" and offered one model to every computer. This module is the backend of the replacement:

  * `hardware_facts()`    how much memory this computer has (read from the operating system; the number of CPU threads); nothing is guessed about a graphics card.
  * `CATALOG`             a short, curated list of local models with only facts that were read from the model's own Ollama page on 2026-11-03 (download size, tools support, licence) and, where this
                          project measured the model, what it measured. Models this project has NOT measured say so. Nothing here ranks quality.
  * `recommend(ram)`      which of them probably fit, by a stated rule (an ESTIMATE, not a measurement). No model is recommended over another: the few results this project has
                          are small and unstable (see the note of qwen3:8b), and every local model here is for trying Delentia; the measured results are in docs/KNOWN_LIMITATIONS.md.
  * `ollama_status()`, `start_ollama()`   is Ollama installed, is it running, start it. Installing Ollama stays the person's own click on the official download page: Delentia does not download or run an
                          installer by itself.
  * `PullManager`         downloads a model through Ollama's own HTTP API with progress, one at a time, cancellable, after a disk-space check, and only a model from the catalog.

Owner-only (the Desk routes are not on the person allowlist). Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
CATALOG_DATE = "2026-11-03"
# Estimated memory a model needs = its download size x FIT_FACTOR + FIT_EXTRA_GB (the model's working memory and the context), and it must fit in FIT_SHARE of the computer's memory (the rest is for
# the operating system, the browser and Delentia itself). This is a planning rule taken from public guidance (about 0.6 GB per billion parameters at 4 bits, plus a couple of GB), NOT measured here.
FIT_FACTOR = 1.25
FIT_EXTRA_GB = 1.5
FIT_SHARE = 0.70
MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,60}:[a-z0-9][a-z0-9._-]{0,30}$")


@dataclass(frozen=True)
class LocalModel:
    tag: str                       # the Ollama tag
    label: str
    size_gb: float                 # download size, read from the model's Ollama page on CATALOG_DATE
    tools: bool                    # the page lists tool calling
    licence: str
    note_en: str
    note_th: str
    measured_en: str = ""          # what THIS project measured, in words; empty = not measured here
    measured_th: str = ""
    vendor_claim: bool = False     # the note repeats a claim of the model's maker that this project has not checked


CATALOG: List[LocalModel] = [
    LocalModel("qwen3:1.7b", "Qwen3 1.7B", 1.4, True, "see the model page",
               "Very small. For computers with little memory.", "เล็กมาก สำหรับเครื่องที่แรมน้อย"),
    LocalModel("qwen3:4b", "Qwen3 4B", 2.5, True, "see the model page",
               "Small, for computers with about 8 GB of memory.", "ขนาดเล็ก สำหรับเครื่องแรมราว 8 GB"),
    LocalModel("qwen3:8b", "Qwen3 8B", 5.2, True, "see the model page",
               "The one this project has tried most.", "ตัวที่โครงการนี้ลองมากที่สุด",
               "On the same 5 simple goals it completed 4 in one run and 2 in another run on a later day (one machine: the result moves a lot between runs); on the harder fixed task set it completed 0 of 4 in every arm; about 13 tokens a second on a CPU.",
               "ใน 5 เป้าหมายง่ายชุดเดิม ทำสำเร็จ 4 ในรอบหนึ่งและ 2 ในอีกรอบหนึ่งวันถัดมา (เครื่องเดียว ผลแกว่งมากระหว่างรอบ) ในชุดงานฐานที่ยากกว่าทำสำเร็จ 0 จาก 4 ทุกแขน ความเร็วราว 13 โทเคนต่อวินาทีบน CPU"),
    LocalModel("qwen3:14b", "Qwen3 14B", 9.3, True, "see the model page",
               "Bigger. Needs a computer with plenty of memory.", "ใหญ่กว่า ต้องใช้เครื่องที่มีแรมมาก"),
    LocalModel("bonsai-2:4b", "Bonsai-2 4B (ternary weights)", 1.6, True, "Apache 2.0",
               "About half the download of a normal 4-bit model; supports tools, thinking and images. The maker says its quality is close to full precision.",
               "ดาวน์โหลดเล็กกว่าโมเดล 4 บิตทั่วไปราวครึ่งหนึ่ง ใช้เครื่องมือ คิด และรับภาพได้ ผู้ผลิตระบุว่าคุณภาพใกล้ความละเอียดเต็ม", vendor_claim=True),
    LocalModel("bonsai-2:9b", "Bonsai-2 9B (ternary weights)", 3.2, True, "Apache 2.0",
               "A 9B model in a 3.2 GB download. The maker says its quality is close to full precision. This project has not measured it.",
               "โมเดล 9B ในไฟล์ 3.2 GB ผู้ผลิตระบุว่าคุณภาพใกล้ความละเอียดเต็ม โครงการนี้ยังไม่ได้วัด", vendor_claim=True),
    LocalModel("lfm3:1.7b", "LFM3 1.7B", 1.1, True, "LFM Open License v1.0",
               "Very small and built for local agents; its own page says it is not meant for complex multi-step work. Read its licence before using it commercially.",
               "เล็กมากและทำมาสำหรับเอเจนต์ในเครื่อง หน้าของมันเองบอกว่าไม่เหมาะกับงานหลายขั้นที่ซับซ้อน อ่านสัญญาอนุญาตก่อนใช้เชิงพาณิชย์", vendor_claim=True),
]
BY_TAG: Dict[str, LocalModel] = {m.tag: m for m in CATALOG}


def estimated_memory_gb(model: LocalModel) -> float:
    return round(model.size_gb * FIT_FACTOR + FIT_EXTRA_GB, 1)


def fits(model: LocalModel, ram_gb: Optional[float]) -> Optional[bool]:
    """True/False by the stated estimate; None when the memory of this computer is not known."""
    if not ram_gb:
        return None
    return estimated_memory_gb(model) <= ram_gb * FIT_SHARE


def hardware_facts() -> Dict[str, Any]:
    """Memory and CPU threads, read from the operating system. A graphics card is not looked at: nothing is claimed about it."""
    ram: Optional[float] = None
    try:
        if sys.platform == "win32":
            class _Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = _Mem()
            status.dwLength = ctypes.sizeof(_Mem)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):         # type: ignore[attr-defined]
                ram = status.ullTotalPhys / 1024 ** 3
        elif sys.platform == "darwin":
            ram = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout.strip()) / 1024 ** 3
        else:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    ram = int(line.split()[1]) / 1024 ** 2
                    break
    except Exception:                                                                       # noqa: BLE001 - unknown memory is reported as unknown, never as a number
        ram = None
    return {"ram_gb": round(ram, 1) if ram else None, "cpu_threads": os.cpu_count(), "platform": sys.platform}


def recommend(ram_gb: Optional[float], installed: Optional[List[str]] = None) -> Dict[str, Any]:
    """The catalog with, for this computer's memory, whether each model probably fits. Nothing is ranked by quality."""
    have = set(installed or [])
    rows = []
    for m in CATALOG:
        f = fits(m, ram_gb)
        rows.append({**asdict(m), "estimated_memory_gb": estimated_memory_gb(m), "fits": f, "installed": m.tag in have or f"{m.tag}:latest" in have,
                     "measured_here": bool(m.measured_en)})
    return {"catalog_date": CATALOG_DATE, "rule": {"factor": FIT_FACTOR, "extra_gb": FIT_EXTRA_GB, "share": FIT_SHARE, "kind": "estimate, not measured"}, "models": rows}


# ---------------------------------------------------------------- Ollama: is it there, start it

def ollama_url() -> str:
    from rct_control_plane.llm_provider import DEFAULT_OLLAMA_URL
    return (os.getenv("DELENTIA_OLLAMA_URL") or DEFAULT_OLLAMA_URL).rstrip("/")


def find_ollama() -> Optional[str]:
    found = shutil.which("ollama")
    if found:
        return found
    candidates = []
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            candidates.append(Path(base) / "Programs" / "Ollama" / "ollama.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Ollama.app/Contents/Resources/ollama"))
    else:
        candidates.append(Path("/usr/local/bin/ollama"))
    return next((str(p) for p in candidates if p.is_file()), None)


def installed_models(url: Optional[str] = None, timeout: float = 3.0) -> Optional[List[str]]:
    """The models Ollama lists, or None when it can not be reached."""
    try:
        reply = httpx.get((url or ollama_url()) + "/api/tags", timeout=timeout)
        reply.raise_for_status()
        return sorted({str(m.get("name")) for m in reply.json().get("models", []) if isinstance(m, dict) and m.get("name")})
    except (httpx.HTTPError, ValueError, OSError):
        return None


def ollama_status(url: Optional[str] = None) -> Dict[str, Any]:
    models = installed_models(url)
    path = find_ollama()
    state = "running" if models is not None else ("installed_not_running" if path else "not_installed")
    return {"state": state, "installed": bool(path) or models is not None, "running": models is not None, "path": path, "models": models or [], "url": url or ollama_url(),
            "download_url": OLLAMA_DOWNLOAD_URL}


def start_ollama(wait_seconds: float = 10.0, popen: Any = None) -> Dict[str, Any]:
    """Start `ollama serve` in the background and wait until it answers. Never installs anything."""
    status = ollama_status()
    if status["running"]:
        return {**status, "started": False, "message": "already running"}
    if not status["path"]:
        return {**status, "started": False, "message": "Ollama is not installed on this computer"}
    kwargs: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000       # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    try:
        (popen or subprocess.Popen)([status["path"], "serve"], **kwargs)
    except OSError as exc:
        return {**status, "started": False, "message": f"could not start it: {str(exc)[:120]}"}
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if installed_models() is not None:
            return {**ollama_status(), "started": True, "message": "started"}
        time.sleep(0.5)
    return {**ollama_status(), "started": False, "message": "it was started but did not answer in time; try again in a moment"}


# ---------------------------------------------------------------- downloading a model with progress

class PullError(ValueError):
    pass


@dataclass
class PullState:
    name: str = ""
    status: str = "idle"           # idle | downloading | done | failed | cancelled
    completed: int = 0
    total: int = 0
    message: str = ""
    started_at: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def view(self) -> Dict[str, Any]:
        percent = round(100.0 * self.completed / self.total, 1) if self.total else None
        return {**asdict(self), "percent": percent}


class PullManager:
    """One download at a time. The model name must be one of the catalog's tags."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = PullState()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return self._state.view()

    def start(self, name: str, free_bytes: Optional[int] = None, url: Optional[str] = None) -> Dict[str, Any]:
        name = (name or "").strip()
        model = BY_TAG.get(name)
        if model is None or not MODEL_NAME.match(name):
            raise PullError("this model is not in Delentia's list")
        if free_bytes is None:
            free_bytes = shutil.disk_usage(Path.home()).free
        need = int(model.size_gb * 1024 ** 3 * 1.5) + 1024 ** 3                  # the file, room to unpack, one GB spare
        if free_bytes < need:
            raise PullError(f"not enough free disk space: about {need / 1024 ** 3:.1f} GB are needed and {free_bytes / 1024 ** 3:.1f} GB are free")
        if installed_models(url) is None:
            raise PullError("Ollama is not running; start it first")
        with self._lock:
            if self._state.status == "downloading":
                raise PullError("a download is already running")
            self._cancel.clear()
            self._state = PullState(name=name, status="downloading", started_at=time.time(), message="starting")
            self._thread = threading.Thread(target=self._run, args=(name, url or ollama_url()), daemon=True)
            self._thread.start()
        return self.state()

    def cancel(self) -> Dict[str, Any]:
        self._cancel.set()
        return self.state()

    def wait(self, timeout: float = 30.0) -> None:
        thread = self._thread
        if thread:
            thread.join(timeout)

    def _set(self, **fields: Any) -> None:
        with self._lock:
            for k, v in fields.items():
                setattr(self._state, k, v)
            self._state.updated_at = time.time()

    def _run(self, name: str, url: str) -> None:
        try:
            with httpx.stream("POST", url + "/api/pull", json={"name": name, "stream": True}, timeout=httpx.Timeout(30.0, read=120.0)) as reply:
                reply.raise_for_status()
                for line in reply.iter_lines():
                    if self._cancel.is_set():
                        self._set(status="cancelled", message="cancelled")
                        return
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("error"):
                        self._set(status="failed", message=str(event["error"])[:200])
                        return
                    status = str(event.get("status", ""))
                    fields: Dict[str, Any] = {"message": status[:120]}
                    if event.get("total"):
                        fields.update(total=int(event["total"]), completed=int(event.get("completed", 0)))
                    self._set(**fields)
                    if status == "success":
                        self._set(status="done", message="done", completed=self._state.total or self._state.completed)
                        return
            self._set(status="failed", message="the download ended without a success message")
        except (httpx.HTTPError, OSError) as exc:
            self._set(status="failed", message=f"the download stopped: {str(exc)[:160]}")


PULLS = PullManager()
