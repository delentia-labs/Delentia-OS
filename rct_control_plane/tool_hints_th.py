"""
Thai hints for external tools (Round 115, candidate A1; criteria: research/THAI_TOOL_MENU_AMENDMENT_3_R115.md, written before any hint was generated).

The ranked tool menu scores a tool by words it shares with the request. A tool of an external MCP server is described in English, so a Thai request shares nothing with it and the tool never reaches the menu.
The built-in tools carry hints in both languages (`tool_menu.HINTS`). This module gives an external tool its own Thai hint, kept in a plain JSON file the owner can read and edit:

    {"mcp__notes__read_note": {"hint": "<thai words>", "for": "<sha256 of name + description>", "source": "model" | "owner"}}

A hint is used only while its `for` still equals the hash of the tool's CURRENT name and description (a tool that changed is ignored until regenerated or re-approved), only with
DELENTIA_TOOL_MENU_THAI_HINTS=on (default off), and only through the Thai-trigram score a built-in tool's Thai hint already gets. Nothing here is called per request except a dictionary lookup.
`generate()` asks a LOCAL model once per tool, from the tool's name and description only; the model never sees a request. If the model does not answer, no hint is written.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

PATH_ENV = "DELENTIA_TOOL_HINTS_TH"
SWITCH_ENV = "DELENTIA_TOOL_MENU_THAI_HINTS"
DEFAULT_MODEL = "qwen3:8b"
THAI = re.compile(r"[฀-๿]")

# Prompt v2 (Amendment 3, note 1: the one allowed change, made on the development sentences). v1 was frozen before the first hint was generated; it produced padded hints (combinations of the same
# words) that shared generic trigrams across many tools. It never mentions a request, a dataset or the owner.
PROMPT = ("You help Thai speakers find software tools by name in everyday conversation.\n"
          "Tool name: {name}\nTool description: {description}\n\n"
          "Write the Thai words a Thai speaker would use to ask for this tool: the action it performs and the thing it works on. Give 5 to 8 DIFFERENT items. "
          "Each item is one word or a short phrase of at most three words, at least three Thai letters long. Do not combine the same word with many others, "
          "and do not use a generic word (data, message, information) alone. Separate the items with single spaces. Output only the Thai words, nothing else.")


def enabled() -> bool:
    return (os.environ.get(SWITCH_ENV) or "").strip().lower() == "on"


def default_path() -> Path:
    override = os.environ.get(PATH_ENV)
    if override:
        return Path(override)
    from rct_control_plane.data_home import data_home
    return (data_home() or Path.home() / ".delentia") / "tool_hints_th.json"


def fingerprint(tool: Dict[str, Any]) -> str:
    return hashlib.sha256((str(tool.get("name", "")) + "\n" + str(tool.get("description") or "")).encode("utf-8")).hexdigest()


_cache: Dict[str, Any] = {"path": None, "mtime": None, "data": {}}


def load(path: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """The hints file as a dictionary; a missing, unreadable or malformed file is an empty dictionary (the menu is then today's menu)."""
    p = Path(path) if path else default_path()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {}
    if _cache["path"] == str(p) and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data = {str(k): v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get("hint"), str)} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    _cache.update(path=str(p), mtime=mtime, data=data)
    return data


def hint_for(tool: Dict[str, Any]) -> str:
    """The Thai hint of this tool, or '' (off, no file, no entry, or the entry was made for a different name or description)."""
    if not enabled():
        return ""
    entry = load().get(str(tool.get("name", "")))
    if not entry or entry.get("for") != fingerprint(tool):
        return ""
    return str(entry.get("hint") or "")


def clean(text: str) -> str:
    """Keeps the Thai words of a model's answer: drops thinking blocks, numbering, punctuation and anything that is not Thai or a space."""
    text = re.sub(r"<think>.*?</think>", " ", text or "", flags=re.S)
    words = [w for w in re.split(r"[\s,;/|\n]+", re.sub(r"[0-9.()\"'\-*•]+", " ", text)) if THAI.search(w)]
    return " ".join(dict.fromkeys(w for w in words if sum(1 for ch in w if THAI.match(ch)) >= 3))


def ask_ollama(prompt: str, model: str = DEFAULT_MODEL, timeout: float = 120.0) -> Optional[str]:
    url = (os.environ.get("DELENTIA_OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False, "options": {"temperature": 0, "num_predict": 400}}      # a hint is at most 14 short phrases; one tool's answer ran past 60 s three times without a cap (Amendment 3 rule 6)
    try:
        request = urllib.request.Request(url + "/api/chat", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
        return str(json.loads(urllib.request.urlopen(request, timeout=timeout).read())["message"]["content"])
    except Exception:                                                        # noqa: BLE001 - no model, no hint: the menu stays today's
        return None


def generate(tools: Iterable[Dict[str, Any]], ask=ask_ollama, model: str = DEFAULT_MODEL) -> Dict[str, Dict[str, str]]:
    """One hint per tool from its name and description only. A tool whose answer holds no Thai word gets no entry."""
    out: Dict[str, Dict[str, str]] = {}
    for tool in tools:
        text = ask(PROMPT.format(name=tool.get("name", ""), description=str(tool.get("description") or "")[:400]), model)
        hint = clean(text or "")
        if hint:
            out[str(tool["name"])] = {"hint": hint, "for": fingerprint(tool), "source": "model"}
    return out


def write(entries: Dict[str, Dict[str, str]], path: Optional[Path] = None) -> Path:
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return p
