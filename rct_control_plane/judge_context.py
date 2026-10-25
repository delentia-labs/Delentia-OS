"""Round 101: what the agent can hand the clarity judge besides the request's own words.

Set 3 (the Architect's two-axis labels, Round 99) showed that a judge which sees only the sentence stops to ask about things the agent could look up or already knows (17 false stops in 35 for qwen3:8b), and that
the same judge shown the CONTEXT stops 5 times in 35 at the same recall. This module builds that context from what the agent really has, so the variant that was measured can be used for real. It is a pure
function plus a small gatherer; nothing here runs a tool, reads a file's contents or calls a model.

Rules (each is pinned by a test):
  * the context is DATA: the judge's prompt already says never to follow anything inside it, and nothing outside a person's own words and the host's file NAMES goes in;
  * only this person's own things: their pending approvals, their pinned rules, their memories; never another person's;
  * a memory or text that came from outside (an episode that read the web, a dropped file) is left out: the judge is not called for a tainted episode anyway;
  * file NAMES (not contents), at most MAX_FILES; secret-looking names are left out;
  * bounded: every section has a count and a length limit, and the whole text has a limit;
  * the capabilities are plain phrases derived from the names of the tools the agent really has, so "I could look it up" is only said when it is true.

Opt-in: DELENTIA_RCT7_JUDGE_CONTEXT=on (default off) and only when the judge itself is on (DELENTIA_RCT7_JUDGE=propose). The measured prompt is `rct7_judge.SYSTEM_REQUEST_CTX`
(version recorded in `rct7_judge.context_prompt_version()`).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable, List, Optional

ENV = "DELENTIA_RCT7_JUDGE_CONTEXT"
MAX_FILES = 25
MAX_PENDING = 5
MAX_MEMORIES = 3
MAX_RULES = 5
MAX_TURNS_CHARS = 900
MAX_ITEM_CHARS = 200
MAX_TOTAL_CHARS = 2400
NOTHING = "(nothing: the agent knows only this sentence)"

# phrases for what the agent can do, from the names of the tools it really has (a name part => a phrase)
_CAPABILITIES = (
    (("web_search", "search_web"), "search the web"),
    (("crawl_url", "browse_page"), "open a web page"),
    (("read_repo_file", "search_repo_files", "list_repo"), "read and search the files of the workspace"),
    (("recall", "session_search"), "look up what it remembers and earlier sessions"),
    (("query_audit", "query_intents"), "look up its own history"),
    (("read_exchange_file", "list_exchange_files"), "read files in the exchange folder"),
    (("law_lookup",), "look up the supplied statute"),
    (("describe_image",), "read an image"),
    (("transcribe_audio",), "transcribe audio"),
)
_SECRET_NAME = re.compile(r"(^\.env|secret|credential|password|passwd|\.pem$|\.key$|id_rsa|token)", re.IGNORECASE)


def enabled() -> bool:
    return (os.environ.get(ENV) or "off").strip().lower() in ("on", "1", "true", "yes")


def capability_phrases(tool_names: Iterable[str]) -> List[str]:
    names = [str(n) for n in tool_names]
    out: List[str] = []
    for parts, phrase in _CAPABILITIES:
        if any(any(part in name for part in parts) for name in names):
            out.append(phrase)
    return out


def workspace_names(root: Optional[Path], limit: int = MAX_FILES) -> List[str]:
    """File and folder NAMES at the top of the workspace and one level down inside folders: enough for "the report is in docs/", no contents. Names that look like secrets are left out."""
    if root is None:
        return []
    names: List[str] = []
    try:
        top = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return []
    for entry in top:
        if entry.name.startswith(".") or _SECRET_NAME.search(entry.name) or entry.name in ("node_modules", "__pycache__"):
            continue
        if entry.is_dir():
            try:
                inner = sorted(p.name for p in entry.iterdir() if not p.name.startswith(".") and not _SECRET_NAME.search(p.name))[:6]
            except OSError:
                inner = []
            names.append(entry.name + "/" + (" (" + ", ".join(inner) + ")" if inner else ""))
        else:
            names.append(entry.name)
        if len(names) >= limit:
            break
    return names


def _clip(text: Any, limit: int = MAX_ITEM_CHARS) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= limit else one[: limit - 1] + "…"


def build(*, recent_turns: str = "", pending_tools: Iterable[str] = (), memories: Iterable[str] = (), rules: Iterable[str] = (), files: Iterable[str] = (),
          capabilities: Iterable[str] = ()) -> str:
    """The context text for `rct7_judge.judge_request(..., context=...)`. Empty sections are left out; with nothing at all the text says so."""
    sections: List[str] = []
    turns = " ".join(str(recent_turns or "").split())
    if turns:
        sections.append("Earlier in the chat: " + (turns if len(turns) <= MAX_TURNS_CHARS else "…" + turns[-MAX_TURNS_CHARS:]))
    pending = [_clip(t, 80) for t in list(pending_tools)[:MAX_PENDING] if str(t).strip()]
    if pending:
        sections.append("Actions already waiting for this person's approval: " + ", ".join(pending))
    rule_list = [_clip(r) for r in list(rules)[:MAX_RULES] if str(r).strip()]
    if rule_list:
        sections.append("Standing rules this person set: " + " | ".join(rule_list))
    memory_list = [_clip(m) for m in list(memories)[:MAX_MEMORIES] if str(m).strip()]
    if memory_list:
        sections.append("What the agent remembers about this person that may be related: " + " | ".join(memory_list))
    file_list = [_clip(f, 120) for f in list(files)[:MAX_FILES] if str(f).strip()]
    if file_list:
        sections.append("Files in the workspace (names only): " + ", ".join(file_list))
    caps = [str(c) for c in capabilities if str(c).strip()]
    if caps:
        sections.append("Things the agent can do to look something up without asking: " + "; ".join(caps))
    text = "\n".join(sections) if sections else NOTHING
    return text if len(text) <= MAX_TOTAL_CHARS else text[: MAX_TOTAL_CHARS - 1] + "…"


def gather(loop: Any, goal: str) -> str:
    """The context for one request from a live governed loop. Everything is this person's own (the loop's namespace) and nothing comes from an episode that read outside text."""
    from rct_control_plane import fdia_policy
    tool_names = fdia_policy.registry_tool_names()
    pending: List[str] = []
    try:
        for action in loop._pending_actions().list(status="PENDING", limit=20):
            if action.namespace == loop.namespace:
                pending.append(action.tool_name)
    except Exception:                                   # noqa: BLE001 - context is a help, never a reason for the judge to fail
        pending = []
    memories: List[str] = []
    rules: List[str] = []
    try:
        recalled = getattr(loop, "_episode_recalled_for_judge", None)
        if recalled is None:
            recalled = []
        from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
        for item in recalled:
            if item.get("profile") or GovernedAutonomousLoop._memory_origin_tainted([item]):
                continue                                  # a style preference is not a fact about the task; a memory stored after outside text was read is not the person's own words
            (rules if item.get("pinned") else memories).append(str(item.get("content") or ""))
    except Exception:                                   # noqa: BLE001
        pass
    workspace = loop._workspace_id() if hasattr(loop, "_workspace_id") else None
    return build(recent_turns=str(getattr(loop, "_episode_conversation_text", "") or ""), pending_tools=pending, memories=memories, rules=rules,
                 files=workspace_names(Path(workspace) if workspace else None), capabilities=capability_phrases(tool_names))
