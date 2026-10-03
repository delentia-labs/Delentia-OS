"""
Round 56: a smaller tool menu for the model, measured before it is trusted.

Every model call carries the menu of tools. Measured on this runtime's 39 tools: the menu as sent (name, full description and argument schema)
is about 5,200 tokens, which is more than everything else in a typical prompt together, and a small model facing 39 choices picks the wrong one.
The loop already had a keyword filter (J.1.4) that keeps every tool sharing ONE word with the goal, so a common word ("file", "run") leaves most of the menu
and a goal with no shared word gets all of it. This module adds two opt-in things:

  * `rank_tools`: score every tool against the goal (IDF-weighted word overlap on name + description + a short synonym hint, English and Thai) and keep the
    best K. A goal that scores nothing keeps the full menu, so the model is never starved. A tool the ranker cannot know (an external MCP tool) is
    scored from its own name and description like any other.
  * `format_menu(compact=True)`: the arguments as `name(type)*` instead of the full JSON schema (the `*` marks required ones).

Both are OFF by default: `DELENTIA_TOOL_MENU=ranked` and `DELENTIA_TOOL_MENU_FORMAT=compact`. What is measured offline (scripts/measure_tool_menu.py):
whether the tools a goal needs survive the cut, and how many tokens go. What is NOT measured until a real model runs: whether a model chooses better from
the smaller menu (the point of the exercise), which is why they stay off until the paid test's A/B says so.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set

MENU_ENV = "DELENTIA_TOOL_MENU"                 # ranked | (anything else = the loop's existing keyword filter)
FORMAT_ENV = "DELENTIA_TOOL_MENU_FORMAT"        # compact | (anything else = name, description, full schema)
TOP_K_ENV = "DELENTIA_TOOL_MENU_TOP_K"
DEFAULT_TOP_K = 10

_STOP = frozenset("""the and for that this with from into your you are not can will have has had was were been which what when where how who why
 all any each some than then them they their its our out about over under per via use using used get got make made want need please just also very
 one two let tell show give take look find those these there here more most other such only same own too off""".split())

# Short synonym hints per tool, English and Thai: what people say when they want this tool, not what the tool's description says. A tool without a
# hint (an external MCP tool, a tool added later) is ranked from its own name and description alone.
HINTS: Dict[str, str] = {
    "delentia_recall": "remember memory memories know told said previously earlier preference preferences history recollect | จำ ความจำ เคยบอก จำได้ ความทรงจำ เคย",
    "delentia_remember": "remember note save store keep memorise memorize later record fact | จำไว้ บันทึกไว้ เก็บไว้ จดไว้ ความจำ",
    "delentia_read_repo_file": "open read show contents inside file view display text | เปิดไฟล์ อ่านไฟล์ ดูไฟล์ ไฟล์ เนื้อหา",
    "delentia_search_repo_files": "search find grep where mention occurrences locate across code repository | ค้นหา หา ที่ไหน กล่าวถึง ในโค้ด",
    "delentia_write_repo_file": "create write add new file save content draft | สร้างไฟล์ เขียนไฟล์ เพิ่มไฟล์",
    "delentia_patch_repo_file": "change edit replace modify update fix rename substitute line function | แก้ไขไฟล์ แก้ไข เปลี่ยน แทนที่",
    "delentia_run_sandboxed_command": "run execute command shell tests lint build script terminal test pytest | รันคำสั่ง สั่งรัน ทดสอบ คำสั่ง",
    "delentia_crawl_url": "fetch open page website url link http https webpage download read site | เว็บ ลิงก์ หน้าเว็บ เปิดเว็บ ไปที่",
    "delentia_web_search": "search internet web google look up lookup who maintains maintainer author released release version latest current online news find online | ค้นเว็บ ค้นหาเว็บ อินเทอร์เน็ต ล่าสุด ออนไลน์",
    "delentia_schedule_reminder": "remind reminder alert notify later tomorrow tonight friday monday schedule ping | เตือน แจ้งเตือน พรุ่งนี้ ตั้งเตือน",
    "delentia_check_reminders": "reminders due fired alerts pending scheduled check any | เตือนที่ ถึงเวลา การแจ้งเตือน",
    "delentia_spawn_subagents": "split parallel helpers workers subagents delegate divide separate agents several jobs | แบ่งงาน ผู้ช่วย พร้อมกัน หลายตัว",
    "delentia_delegate": "delegate hand over assign profile another agent specialist | มอบหมาย ส่งต่อ ให้ตัวช่วย",
    "delentia_query_audit_log": "audit log history approvals signed actions taken permanent record trail who did | ประวัติ การอนุมัติ บันทึกการทำงาน ตรวจสอบย้อนหลัง",
    "delentia_query_intents": "intents processed requests interpreted kernel earlier today past goals | คำขอ เจตนา ที่ประมวลผล",
    "delentia_list_exchange_files": "list files waiting shared transfer folder handoff exchange directory inbox | ไฟล์ในโฟลเดอร์ โฟลเดอร์แลกเปลี่ยน",
    "delentia_read_exchange_file": "read open exchange transfer handoff dropped file contents | อ่านไฟล์แลกเปลี่ยน",
    "delentia_save_exchange_file": "save put write drop place into transfer folder handoff exchange share other agent | บันทึกลงโฟลเดอร์ ส่งไฟล์ แชร์ไฟล์",
    "delentia_convert_content": "convert transform format csv json html markdown yaml xml turn into | แปลงไฟล์ แปลงรูปแบบ",
    "delentia_check_ground_truth_claim": "verify check true fact claim statement correct accurate false is it true | ตรวจสอบข้อเท็จจริง จริงไหม ถูกต้องไหม",
    "delentia_daemon_status": "daemon scheduler background running alive status tasks last ran | ทำงานอยู่ไหม สถานะ เบื้องหลัง scheduler",
    "delentia_list_worktrees": "list worktrees checkouts working copies open helper branches | รายการ worktree สำเนาทำงาน",
    "delentia_create_worktree": "create isolated worktree checkout branch separate copy experiment safely | สร้าง worktree แยก สำเนาแยก",
    "delentia_remove_worktree": "remove delete clean up worktree checkout finished | ลบ worktree",
    "delentia_list_capabilities": "capabilities features available registered abilities what can you do | ความสามารถ ทำอะไรได้",
    "delentia_generate_image": "draw picture image generate illustration logo art photo render | วาดภาพ สร้างภาพ รูปภาพ",
    "delentia_expand_tool_output": "expand full original compressed shortened output complete text again earlier result | ขยาย ข้อความเต็ม ผลลัพธ์ที่ถูกย่อ",
    "delentia_list_forged_tools": "forged custom tools we wrote created switched on active list our own | เครื่องมือที่สร้างเอง เครื่องมือที่เปิด",
    "delentia_run_forged_tool": "run use forged custom tool we created our own slugify median function | ใช้เครื่องมือที่สร้างเอง",
    "delentia_crystallize_keywords": "keywords key terms extract tag important words entropy phrases | คำสำคัญ สกัดคำ แท็ก",
    "delentia_synthesize_function": "write function code snippet implement generate small program helper validate check string | เขียนฟังก์ชัน ฟังก์ชัน โค้ดสั้น",
    "delentia_process_intent": "process analyse intent understand request classify goal pipeline | วิเคราะห์เจตนา",
    "delentia_compress_intent_delta": "compress shrink delta context summarise history tokens | บีบอัด ย่อ",
    "delentia_export_session_state": "export save session state snapshot container | ส่งออก สถานะ เซสชัน",
    "delentia_import_session_state": "import load restore session state snapshot container | นำเข้า สถานะ เซสชัน",
    "delentia_schedule_self_evolution": "schedule periodic self evolution cycle improve over time | วงจรพัฒนาตนเอง",
    "delentia_verify_intent_conservation": "verify intent preserved fidelity stages pipeline conservation | ตรวจความตรงของเจตนา",
    "delentia_autonomous_loop": "autonomous loop agent run goal episode steps work toward | รันเอเจนต์ ทำงานอัตโนมัติ",
    "delentia_search_sessions": "search past sessions episodes history earlier conversation what did we do before previously discussed decided last week | ค้นประวัติ เคยคุยกัน ครั้งก่อน ที่ผ่านมา เมื่อวาน สัปดาห์ที่แล้ว",
    "delentia_cron_create": "schedule recurring repeat every daily weekly hourly cron job automate regularly unattended report later | ตั้งงาน ตั้งเวลา ทุกวัน ทุกชั่วโมง ทำซ้ำ อัตโนมัติ",
    "delentia_cron_list": "list recurring scheduled jobs cron what is scheduled upcoming | งานที่ตั้งเวลาไว้ รายการงานตามเวลา",
    "delentia_cron_delete": "delete remove stop cancel recurring scheduled job cron | ยกเลิกงานตามเวลา หยุดงาน",
    "delentia_assemble_nodes": "assemble nodes graph workflow compose dag | ประกอบ node กราฟ",
}

_SUFFIXES = ("ing", "ed", "es", "s")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> Set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP}


def thai_trigrams(text: str) -> Set[str]:
    out: Set[str] = set()
    for run in re.findall(r"[฀-๿]+", text):
        run = run.replace("ำ", "ํา")           # SARA AM split by NFKC elsewhere in the runtime: keep one form on both sides
        out.update(run[i:i + 3] for i in range(max(0, len(run) - 2)))
    return out


def _name_parts(name: str) -> Set[str]:
    return {_stem(p) for p in re.split(r"[_\W]+", name.lower()) if len(p) > 2 and p not in ("delentia", "mcp")}


def _doc(tool: Dict[str, Any]) -> Dict[str, Set[str]]:
    name = str(tool.get("name", ""))
    hint = HINTS.get(name, "")
    description = str(tool.get("description") or "")[:400]
    english_hint, _, thai_hint = hint.partition("|")
    return {"name": _name_parts(name), "text": tokens(description) | tokens(english_hint), "thai": thai_trigrams(thai_hint) | thai_trigrams(description)}


def score_tools(goal: str, tools: Sequence[Dict[str, Any]]) -> List[float]:
    """One score per tool (same order). IDF over the tool texts so a word that every tool uses ("real", "file") counts for little."""
    docs = [_doc(t) for t in tools]
    n = max(1, len(docs))
    df: Dict[str, int] = {}
    for d in docs:
        for w in d["name"] | d["text"]:
            df[w] = df.get(w, 0) + 1
    goal_words, goal_thai = tokens(goal), thai_trigrams(goal)
    scores = []
    for d in docs:
        s = 0.0
        for w in goal_words:
            idf = math.log(1.0 + n / df[w]) if w in df else 0.0
            if w in d["name"]:
                s += 2.0 * idf
            if w in d["text"]:
                s += idf
        if goal_thai:
            s += 1.5 * len(goal_thai & d["thai"]) / 3.0
        scores.append(s)
    return scores


# Kept on every menu: once a large tool result has been compressed the model needs this one to read the original back.
ALWAYS = frozenset({"delentia_expand_tool_output"})
# A tool that works on something another tool fetches comes with it: you cannot patch a file you have not read, convert a file you have not opened,
# or run a forged tool you have not looked up. Structural pairs, not goal-specific rules.
COMPANIONS: Dict[str, Sequence[str]] = {
    "delentia_patch_repo_file": ("delentia_read_repo_file",),
    "delentia_convert_content": ("delentia_read_exchange_file",),
    "delentia_run_forged_tool": ("delentia_list_forged_tools",),
}


def rank_tools(goal: str, tools: Sequence[Dict[str, Any]], k: int = DEFAULT_TOP_K) -> List[Dict[str, Any]]:
    """The best `k` tools for the goal, in their original order. Nothing scores -> the full menu (never leave the model with nothing)."""
    scores = score_tools(goal, tools)
    if not any(s > 0 for s in scores):
        return list(tools)
    best = sorted(range(len(tools)), key=lambda i: (-scores[i], i))[: max(1, k)]
    keep = {i for i in best if scores[i] > 0} | {i for i, t in enumerate(tools) if t.get("name") in ALWAYS}
    kept_names = {tools[i].get("name") for i in keep}
    wanted = {c for name in kept_names for c in COMPANIONS.get(str(name), ())}
    keep |= {i for i, t in enumerate(tools) if t.get("name") in wanted}
    return [t for i, t in enumerate(tools) if i in keep]


def _compact_args(schema: Any) -> str:
    if not isinstance(schema, dict):
        return ""
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    parts = []
    for name, spec in props.items():
        kind = spec.get("type", "any") if isinstance(spec, dict) else "any"
        if isinstance(kind, list):
            kind = "|".join(str(x) for x in kind)
        parts.append(f"{name}:{kind}{'*' if name in required else ''}")
    return ", ".join(parts)


def format_menu(tools: Sequence[Dict[str, Any]], compact: bool = False) -> str:
    if not compact:
        return "\n".join(f"- {t['name']}: {t['description']} (args schema: {t.get('input_schema', {})})" for t in tools)
    lines = []
    for t in tools:
        first = " ".join(str(t.get("description") or "").split())
        first = re.split(r"(?<=[.!?])\s", first, maxsplit=1)[0][:200]
        lines.append(f"- {t['name']}({_compact_args(t.get('input_schema'))}): {first}")
    return "\n".join(lines)


def ranked_enabled() -> bool:
    return (os.environ.get(MENU_ENV) or "").strip().lower() == "ranked"


def compact_enabled() -> bool:
    return (os.environ.get(FORMAT_ENV) or "").strip().lower() == "compact"


def top_k() -> int:
    try:
        return max(1, int(os.environ.get(TOP_K_ENV) or DEFAULT_TOP_K))
    except ValueError:
        return DEFAULT_TOP_K


def maybe_ranked(goal: str, tools: Sequence[Optional[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """The ranked menu when DELENTIA_TOOL_MENU=ranked, else None (the caller keeps its own filter)."""
    return rank_tools(goal, [t for t in tools if t], top_k()) if ranked_enabled() else None
