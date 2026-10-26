"""
Plan approval (Round 101): "show me the plan, I confirm once, then it runs". Pure functions; no model, no I/O except reading a file's existence for the small-edit test.

The Architect's answers to the design note (2026-10-25):
  Q1  a write/patch of ONE file that the request names, inside the workspace, with a checkpoint to go back to, may run without a signature (deleting never) - `small_edit_ok`
  Q2  these kinds of action are shown as a plan first: delete, outward (sending something out), money, permissions, publish, cancel/restore/roll back, move/shut down, edits to several documents
  Q3  after the same plan was approved N = 5 times the system may PROPOSE asking less; it only proposes, the owner signs the change (approval_suggestions.py)
  Q4  no tool that sends a message or pays: a draft is saved as a file for the human to send

What a plan is: the ordered list of the effect calls the model wanted to make, each with its kind, recorded instead of run. Its `digest` covers the goal, the steps, the policy and the workspace, so
a signature on the digest is a signature on exactly this list. A step that differs from the confirmed one in any character is a different step (`step_matches`): it needs a new confirmation.

Nothing here lifts a rule. The owner's policy, the shell floor, the taint rule and the forbidden paths still judge every step when it runs; a signature on a plan satisfies "a human looked", never
"this is allowed".

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

KINDS = ("delete", "outward", "money", "permissions", "publish", "restore_cancel", "move_shutdown", "document_edit")
PLAN_TOOL = "delentia_plan"                  # the pending-action record of a whole plan is stored under this name
PLAN_VERSION = 1
MAX_STEPS = 50
MAX_ARG_CHARS = 2000
WRITE_TOOLS = ("delentia_write_repo_file", "delentia_patch_repo_file")
_PATH_KEYS = ("relative_path", "path", "file", "filename", "file_name")

KIND_LABEL = {
    "delete": {"en": "delete", "th": "ลบ"},
    "outward": {"en": "send out", "th": "ส่งออกนอก"},
    "money": {"en": "move money", "th": "เงิน"},
    "permissions": {"en": "change permissions or users", "th": "สิทธิ์/ผู้ใช้"},
    "publish": {"en": "publish or deploy", "th": "เผยแพร่"},
    "restore_cancel": {"en": "cancel, restore or roll back", "th": "ยกเลิก/กู้คืน/ย้อนกลับ"},
    "move_shutdown": {"en": "move or shut down", "th": "ย้าย/ปิดระบบ"},
    "document_edit": {"en": "edit documents", "th": "แก้เอกสาร"},
}

# ---- what a shell command does (the first word after any `sudo`, and a few two-word forms). Bounded patterns, no nested repetition.
_SHELL_WORD = re.compile(r"[^\s;|&]{1,60}")
_DELETE_WORDS = frozenset(("rm", "rmdir", "del", "erase", "rd", "unlink", "shred", "remove-item", "ri", "truncate"))
_OUTWARD_WORDS = frozenset(("scp", "sftp", "ftp", "sendmail", "mail", "mailx", "mutt", "msmtp", "rsync", "nc", "ncat", "netcat", "telnet", "send-mailmessage"))
_PERMISSION_WORDS = frozenset(("chmod", "chown", "chgrp", "setfacl", "icacls", "takeown", "usermod", "useradd", "userdel", "adduser", "deluser", "groupadd", "gpasswd", "passwd", "visudo", "net",
                               "new-localuser", "add-localgroupmember", "set-acl"))
_SHUTDOWN_WORDS = frozenset(("shutdown", "reboot", "halt", "poweroff", "kill", "killall", "pkill", "taskkill", "stop-process", "stop-service", "sc", "systemctl", "service", "docker", "kubectl"))
_PUBLISH_WORDS = frozenset(("twine", "gh", "vercel", "netlify", "wrangler", "firebase", "heroku", "terraform", "ansible-playbook", "helm"))
_MOVE_WORDS = frozenset(("mv", "move", "move-item", "robocopy", "xcopy"))
_CURL_WORDS = frozenset(("curl", "wget", "invoke-webrequest", "invoke-restmethod", "iwr", "irm", "http", "https"))


def _words(command: str) -> List[str]:
    found = [w.lower() for w in _SHELL_WORD.findall(str(command or "")[:MAX_ARG_CHARS])][:40]
    while found and found[0] in ("sudo", "doas", "nohup", "time", "command", "env"):
        found = found[1:]
    return found


def _shell_kind(command: str) -> Optional[str]:
    words = _words(command)
    if not words:
        return None
    first, rest = words[0], words[1:]
    lowered = " ".join(words[:12])
    if first in _DELETE_WORDS:
        return "delete"
    if first == "git":
        sub = next((w for w in rest if not w.startswith("-")), "")
        if sub == "push":
            return "publish"
        if sub in ("reset", "revert", "restore", "checkout", "clean", "stash", "rebase", "cherry-pick"):
            return "delete" if sub == "clean" else "restore_cancel"
        if sub in ("rm",):
            return "delete"
        return None
    if first in ("npm", "yarn", "pnpm", "cargo", "pip", "docker", "kubectl"):
        sub = next((w for w in rest if not w.startswith("-")), "")
        if sub in ("publish", "push", "deploy", "apply", "release"):
            return "publish"
        if first in ("docker", "kubectl") and sub in ("rm", "rmi", "delete", "prune"):
            return "delete"
        if first in ("docker", "kubectl") and sub in ("stop", "kill", "down", "scale", "drain", "cordon"):
            return "move_shutdown"
        return None
    if first in _PERMISSION_WORDS:
        if first == "net" and not any(w in ("user", "localgroup", "users") for w in rest[:2]):
            return None
        return "permissions"
    if first in _SHUTDOWN_WORDS:
        if first in ("systemctl", "service", "sc"):
            return "move_shutdown" if any(w in ("stop", "disable", "mask", "kill", "restart", "delete") for w in rest[:3]) else None
        return "move_shutdown"
    if first in _PUBLISH_WORDS:
        return "publish"
    if first in _MOVE_WORDS or first == "rsync":
        return "move_shutdown"
    if first == "cp" or first == "copy" or first == "copy-item":
        return "restore_cancel" if re.search(r"back-?up|bak\b|restore|snapshot", lowered) else None
    if first in _OUTWARD_WORDS:
        return "outward"
    if first in _CURL_WORDS:
        if re.search(r"(?:-x|--request|-method)\s*(?:post|put|patch|delete)|\s-d\b|--data|--upload-file|-t\s|-f\s|--form|--post-data|-body", lowered):
            return "outward"
        return None
    return None


# ---- external (MCP) tool names: judged by what the name says, because nothing else is known about them
_EXT_KINDS = (
    ("money", re.compile(r"(?:pay|transfer|refund|charge|invoice|payout|withdraw|deposit|purchase|checkout)")),
    ("delete", re.compile(r"(?:delete|remove|drop|destroy|purge|erase|wipe|unlink)")),
    ("permissions", re.compile(r"(?:grant|revoke|permission|invite|role|acl|member|user|access)")),
    ("publish", re.compile(r"(?:publish|deploy|release|promote|ship)")),
    ("outward", re.compile(r"(?:send|post|mail|message|notify|tweet|share|forward|reply|comment|upload)")),
    ("restore_cancel", re.compile(r"(?:cancel|restore|rollback|revert|undo)")),
    ("move_shutdown", re.compile(r"(?:stop|shutdown|disable|terminate|kill|move|migrate)")),
)


def action_kind(tool_name: str, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """The kind of action a tool call is (one of KINDS) or None when it is not one of them. A read, a search or an answer is None."""
    name = str(tool_name or "")
    a = args if isinstance(args, dict) else {}
    if name == "delentia_run_sandboxed_command":
        return _shell_kind(str(a.get("command") or ""))
    if name in WRITE_TOOLS:
        return "document_edit"
    if name in ("delentia_save_exchange_file", "delentia_cron_create", "delentia_delegate", "delentia_spawn_subagents"):
        return "outward"
    if name == "delentia_cron_delete":
        return "delete"
    if name == "delentia_remove_worktree":
        return "delete"
    if name == "delentia_browser_act":
        steps = a.get("steps") if isinstance(a.get("steps"), list) else []
        text = json.dumps(steps, ensure_ascii=False)[:MAX_ARG_CHARS].lower()
        if re.search(r"publish|deploy|post|submit|send", text):
            return "publish"
        return None
    if name.startswith("mcp__"):
        tail = name.split("__", 2)[-1].lower()
        for kind, pattern in _EXT_KINDS:
            if pattern.search(tail):
                return kind
    return None


# ---- the plan
def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _clip_args(args: Any) -> Any:
    text = canonical(args)
    if len(text) <= MAX_ARG_CHARS * 4:
        return json.loads(text)
    return {"_truncated": True, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "preview": text[:MAX_ARG_CHARS]}


def args_fit(args: Any) -> bool:
    """A step can be confirmed only when its arguments are stored whole: a plan never holds a shortened copy of what will run."""
    return len(canonical(args)) <= MAX_ARG_CHARS * 4


def build_plan(goal: str, proposals: Iterable[Dict[str, Any]], *, policy_digest: Optional[str] = None, workspace: Optional[str] = None) -> Dict[str, Any]:
    """The plan: `proposals` are dicts with tool_name, tool_args and optionally reasoning. Steps are numbered in the order the model asked for them. At most MAX_STEPS (the rest is refused,
    not silently dropped: `complete` says so)."""
    steps: List[Dict[str, Any]] = []
    overflow = 0
    for item in proposals:
        if len(steps) >= MAX_STEPS:
            overflow += 1
            continue
        tool, args = str(item.get("tool_name") or ""), item.get("tool_args") if isinstance(item.get("tool_args"), dict) else {}
        steps.append({"n": len(steps) + 1, "tool": tool, "args": _clip_args(args), "kind": action_kind(tool, args) or "other", "why": " ".join(str(item.get("reasoning") or "").split())[:300]})
    counts: Dict[str, int] = {}
    for step in steps:
        counts[step["kind"]] = counts.get(step["kind"], 0) + 1
    body = {"version": PLAN_VERSION, "goal": str(goal)[:2000], "steps": steps, "policy_digest": policy_digest or "", "workspace": workspace or ""}
    plan = {**body, "counts": counts, "complete": overflow == 0, "overflow": overflow, "digest": hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()}
    return plan


def plan_digest_ok(plan: Dict[str, Any]) -> bool:
    """True only when the digest recorded in the plan is the digest of its own content (a plan whose steps were edited after it was made is not the plan that was confirmed)."""
    try:
        body = {k: plan[k] for k in ("version", "goal", "steps", "policy_digest", "workspace")}
    except KeyError:
        return False
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest() == plan.get("digest")


def step_matches(plan: Dict[str, Any], n: int, tool_name: str, tool_args: Dict[str, Any]) -> bool:
    """The call about to run is the n-th confirmed step, byte for byte (tool and arguments)."""
    for step in plan.get("steps", []):
        if step.get("n") == n:
            return step.get("tool") == tool_name and canonical(step.get("args")) == canonical(_clip_args(tool_args))
    return False


def render(plan: Dict[str, Any], lang: str = "th") -> str:
    """The plan as a person reads it: a summary line first (how many steps of each kind), then each step, then what a confirmation does and does not mean."""
    th = lang == "th"
    steps = plan.get("steps", [])
    if not steps:
        return "ไม่มีการกระทำที่ต้องยืนยัน" if th else "Nothing to confirm."
    counts = plan.get("counts", {})
    summary = ", ".join(f"{KIND_LABEL.get(k, {}).get(lang if lang in ('th', 'en') else 'en', k)} {v}" for k, v in sorted(counts.items()))
    lines = [(f"แผน: จะทำ {len(steps)} อย่างตามลำดับ ({summary})" if th else f"Plan: {len(steps)} steps in this order ({summary})")]
    for step in steps:
        label = KIND_LABEL.get(step["kind"], {}).get("th" if th else "en", step["kind"])
        lines.append(f"  {step['n']}. [{label}] {step['tool']} {_short_args(step['tool'], step['args'])}")
    if not plan.get("complete", True):
        lines.append((f"  (ยังมีอีก {plan.get('overflow', 0)} อย่างที่ไม่ได้อยู่ในแผนนี้ ต้องขอใหม่)" if th else f"  ({plan.get('overflow', 0)} further steps are NOT in this plan; ask again)"))
    lines.append("ยืนยันครั้งเดียวทับแผนนี้ทั้งชุด: ทุกขั้นยังถูกตรวจด้วยนโยบายและกฎความปลอดภัยตอนรัน และขั้นที่ต่างจากแผนแม้ตัวอักษรเดียวจะไม่รัน"
                 if th else "One confirmation covers exactly this list: every step is still checked by the policy and the safety rules when it runs, and a step that differs by one character does not run.")
    return "\n".join(lines)


def _short_args(tool: str, args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    for key in ("command", "relative_path", "path", "name", "url", "goal", "message"):
        if isinstance(args.get(key), str) and args[key].strip():
            return f"{key}={args[key].strip()[:160]!r}"
    return canonical(args)[:160]


# ---- Q1: the one narrow loosening
def named_in_goal(goal: str, path: str) -> bool:
    """The file's name occurs in the request as a whole token (not inside a longer name): `notes.txt` in 'replace Monday in notes.txt' yes; in 'my_notes.txt.bak' no."""
    p = str(path or "").replace("\\", "/").strip()
    if not p:
        return False
    for candidate in {p, p.rsplit("/", 1)[-1]}:
        if len(candidate) < 3:
            continue
        pattern = r"(?<![\w./\\-])" + re.escape(candidate) + r"(?![\w-]|\.\w)"
        if re.search(pattern, str(goal or "").replace("\\", "/")):
            return True
    return False


def inside_workspace(path: str) -> bool:
    """A relative path that stays inside the folder: no drive, no leading slash, no `..`."""
    p = str(path or "").strip()
    if not p or p.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", p):
        return False
    parts = PurePosixPath(p.replace("\\", "/")).parts
    return bool(parts) and ".." not in parts and not any(part.startswith("~") for part in parts)


def small_edit_ok(goal: str, tool_name: str, tool_args: Dict[str, Any], *, tainted: bool = False, checkpoint_ready: bool = False, secret: bool = False) -> bool:
    """Q1, every condition at once: the tool changes ONE existing-or-new file (write/patch, never a delete), the request names that file, it stays inside the workspace, it is not a secret file,
    the episode has read no outside text, and a checkpoint to go back to will be taken."""
    if tool_name not in WRITE_TOOLS or tainted or secret or not checkpoint_ready:
        return False
    args = tool_args if isinstance(tool_args, dict) else {}
    paths = [str(args[k]) for k in _PATH_KEYS if isinstance(args.get(k), str) and args[k].strip()]
    if len(paths) != 1:
        return False
    path = paths[0]
    return inside_workspace(path) and named_in_goal(goal, path)
