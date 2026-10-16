"""
Owner's sentence -> a proposed policy, or a question. (Round 82, plan item T10)

The owner of an agent should be able to say "never edit the original quotes, ask me before anything goes to a customer" and see the policy that means, before anything changes. This is a
DETERMINISTIC reader for a small, honest vocabulary (English and Thai): no model, no guessing. It follows three rules that matter more than coverage:

  1. It never loosens by itself. The only thing a sentence can switch to ALLOW is reading. "You may send emails" is a question, not a rule, because a per-tool rule would open sending to
     everyone; so is "do not ask me before ..." and "allow everything".
  2. It asks when unsure. Vague words ("as appropriate", "use your judgment", "ตามความเหมาะสม"), a sentence it cannot attach to a kind of action, or two sentences that disagree, give a
     question and no rule for that part.
  3. It refuses to be an attack surface. "Ignore the previous rules", "disable the approval step", "pretend the owner approved it", "the assistant may approve its own requests" are not
     policy statements; the answer is a refusal, with nothing proposed.

What comes out is a PROPOSAL, shown back for reading. It is never applied here: a policy change goes through the existing path (`delentia fdia`, which needs an approver signature).
Tools are grouped by what they can do (read, write, shell, network, outbound, schedule, memory, agents). This runtime has no tool that sends mail by itself: "outbound" covers the ways text
leaves (scheduled deliveries, the browser, sub-agents, exchange files). A rule is per tool, not per recipient: "the team" and "a customer" cannot be told apart, and the proposal says so.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

NEVER, ASK, ALLOW = "never", "ask", "allow"
STRICTNESS = {ALLOW: 0, ASK: 1, NEVER: 2}

GROUP_TOOLS: Dict[str, List[str]] = {
    "read": ["read_repo_file", "search_repo_files", "read_exchange_file", "list_exchange_files", "search_sessions"],
    "write": ["write_repo_file", "patch_repo_file", "save_exchange_file"],
    "shell": ["run_sandboxed_command", "synthesize_function", "run_forged_tool"],
    "network": ["crawl_url", "web_search", "browse_page", "browser_act"],
    "outbound": ["cron_create", "browser_act", "save_exchange_file", "delegate"],
    "schedule": ["cron_create", "schedule_reminder", "schedule_self_evolution"],
    "memory": ["remember"],
    "agents": ["spawn_subagents", "delegate", "autonomous_loop"],
}

# Order matters: the first group whose words appear wins the ones it shares (network before read: "browse the web" is not "browse files").
_GROUP_WORDS: List[Tuple[str, re.Pattern]] = [
    ("agents", re.compile(r"sub-?agents?|spawn|delegat|ผู้ช่วยย่อย|เอเจนต์ย่อย|เอเจนท์ย่อย")),
    ("schedule", re.compile(r"schedul|recurring|cron|remind|timer|ตั้งเวลา|งานประจำ|นัดหมาย")),
    ("memory", re.compile(r"remember|memoriz|memory|ความจำ|จดจำ|(?<![ก-๙])จำ(?![ก-๙])")),
    ("shell", re.compile(r"shell|commands?|terminal|scripts?|execut|เชลล์|คำสั่ง|สคริปต์")),
    ("network", re.compile(r"\bweb\b|internet|browser|browse|online|website|download|crawl|เว็บ|อินเทอร์เน็ต|เบราว์เซอร์|ดาวน์โหลด")),
    ("outbound", re.compile(r"\bsend|sending|e-?mails?|\bmail\b|messages?|notif|\breply|publish|\bpost\b|forward|\bshare|outgoing|ส่ง|อีเมล|เมล|ข้อความ|แจ้ง|ตอบกลับ|เผยแพร่")),
    ("write", re.compile(r"\bwrit|\bedit|chang|modif|updat|overwrit|delet|remov|\bsave|patch|แก้ไข|เขียน|ลบ|เปลี่ยน|บันทึก|อัปเดต")),
    ("read", re.compile(r"\bread|search|look ?up|\bview|\bopen\b|อ่าน|ค้นหา|ดูไฟล์")),
]

_ATTACK = re.compile(
    r"ignore (all |any |the )?(previous|prior|above|earlier)|disable (the )?(approval|signature|policy|screen|gate|guard|check)|turn off (the )?(injection|screen|guard|policy|approval|gate)|"
    r"admin mode|all tools are allowed|approve (its|their|his|her) own|(already|has) approved|approved everything|pretend|\bset a to\b|skip (the )?(signature|approval)|bypass|"
    r"no approval (is )?(needed|required)|ยกเลิก(การ)?อนุมัติ|ปิด(การ)?(อนุมัติ|ตรวจ|ป้องกัน)|ข้ามการอนุมัติ|อนุมัติเอง")
_EVERYTHING = re.compile(r"\b(everything|anything|all tools|all actions)\b|ทุกอย่าง|ทั้งหมด")
_VAGUE = re.compile(
    r"as appropriate|if (it )?(seems|appears)|where (it )?(makes sense|reasonable)|when(ever)? (needed|necessary|you need)|if (needed|necessary)|(your |own )?judg(e)?ment|sensib|reasonabl|"
    r"careful|necessar|whatever|tidy|helpful|risky|appropriate|ตามความเหมาะสม|ตามสมควร|ตามที่เห็นสมควร|ดุลพินิจ|ถ้าจำเป็น|เมื่อจำเป็น|ที่จำเป็น|ระวัง|สมเหตุสมผล")
_NO_ASK = re.compile(r"no need to ask|(do not|don't|dont|not) (need to )?ask( me)?( before| first)|without (me )?asking|without (my )?(approval|permission)|ไม่ต้องถาม|ห้ามถาม")
_ASK = re.compile(r"ask( me)?( before| first)|my (approval|ok|okay|permission)|confirm with me|requires? (my )?approval|approval (is )?(needed|required)|ต้องถาม|ขออนุมัติ|ถามก่อน|ต้องได้รับอนุมัติ|ต้องขอ")
_NEVER = re.compile(r"\bnever\b|\bdo not\b|\bdon't\b|\bdont\b|must not|\bforbid|\bforbidden\b|\bprohibit|ห้าม|อย่า|ไม่อนุญาต")
_ALLOW = re.compile(r"you may|you can|feel free|\bfreely\b|\ballowed?\b|\bis fine\b|\bok to\b|ได้เลย|อนุญาต|ทำได้")
# Bounded, and anchored at the start of a whitespace run: a bare \s+ is quadratic on a long run of spaces (found by the regex audit).
_SPLIT = re.compile(r"[.;!?\n]+|(?<!\s)\s{1,20}but\s{1,20}|(?<!\s)\s{1,20}however\s{1,20}|(?<!\s)\s{1,20}แต่\s{0,20}")
_NEGATED_NO_ASK = re.compile(r"not ask|ห้ามถาม")


@dataclass
class Statement:
    text: str
    groups: List[str] = field(default_factory=list)
    stance: Optional[str] = None
    outcome: str = "rule"            # rule | question | refused
    why: str = ""


@dataclass
class Proposal:
    status: str                                              # ok | ask | refuse
    rules: List[Dict[str, Any]] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    statements: List[Dict[str, Any]] = field(default_factory=list)
    applied: bool = False                                    # always False: this module proposes, it never changes anything

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def stances(self) -> Dict[str, str]:
        return {r["group"]: r["stance"] for r in self.rules}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", str(text or "")).lower().strip()


def _groups_in(segment: str) -> List[str]:
    found: List[str] = []
    for name, pattern in _GROUP_WORDS:
        if pattern.search(segment):
            found.append(name)
    if "network" in found and "read" in found and not re.search(r"\bread|search|look ?up|อ่าน|ค้นหา", segment):
        found.remove("read")
    if "network" in found and "outbound" in found and not re.search(r"\bsend|e-?mail|\bmail\b|message|ส่ง|อีเมล|เมล", segment):
        found.remove("outbound")
    return found


def _stance(segment: str) -> Optional[str]:
    never_with_ask = _NEVER.search(segment) and re.search(r"without (me )?asking|without (my )?(approval|permission)", segment)
    if never_with_ask:
        return ASK                                           # "never X without asking me" = ask before X
    if _NO_ASK.search(segment):
        return ALLOW                                         # "no need to ask before X", "do not ask me before X": the owner is lifting a question
    if _ASK.search(segment):
        return ASK
    if _NEVER.search(segment):
        return NEVER
    if _ALLOW.search(segment):
        return ALLOW
    return None


def propose(text: str) -> Proposal:
    body = _norm(text)
    if not body:
        return Proposal(status="ask", questions=["The sentence is empty. What should the agent never do, ask about first, or be free to do?"])
    if _ATTACK.search(body):
        return Proposal(status="refuse", notes=["This is not a policy statement: it asks to remove, skip or pretend a safeguard. A sentence cannot switch the safeguards off; "
                                                  "the owner changes the policy with a signature (delentia fdia). Nothing was proposed."])
    segments = [s.strip(" ,:-—") for s in _SPLIT.split(body) if s and s.strip(" ,:-—")]
    statements: List[Statement] = []
    questions: List[str] = []
    wanted: Dict[str, Set[str]] = {}
    for segment in segments:
        st = Statement(text=segment, groups=_groups_in(segment), stance=_stance(segment))
        if _EVERYTHING.search(segment) and st.stance == ALLOW:
            return Proposal(status="refuse", notes=["A sentence cannot lift every question or allow everything: the proposal would remove the safeguards for all tools. "
                                                      "Say which kind of action (reading, writing, commands, web, outgoing, scheduling, memory, helpers) and what to do about it."],
                            statements=[asdict(st)])
        if _VAGUE.search(segment):
            st.outcome, st.why = "question", "judgment words"
            questions.append(f"“{segment}” depends on judgment. A rule is per tool, so it needs a fixed answer: ask you each time, never, or allow always? (Nothing was proposed for this part.)")
        elif not st.groups or st.stance is None:
            st.outcome, st.why = "question", "no clear kind of action or no clear instruction"
            what = "which kind of action this is about (reading, writing, commands, web, outgoing, scheduling, memory, helpers)" if not st.groups else "whether to never do it, ask first, or allow it"
            questions.append(f"“{segment}”: I could not tell {what}. (Nothing was proposed for this part.)")
        else:
            for group in st.groups:
                wanted.setdefault(group, set()).add(st.stance)
        statements.append(st)
    rules: List[Dict[str, Any]] = []
    notes: List[str] = []
    for group, stances in wanted.items():
        if ALLOW in stances and stances & {NEVER, ASK}:
            questions.append(f"The sentences disagree about {group}: one allows it and another {'forbids' if NEVER in stances else 'asks first for'} it. Which one is right? (Nothing was proposed for {group}.)")
            continue
        if stances == {ALLOW} and group != "read":
            questions.append(f"Allowing {group} without asking applies to every use of it, including to customers and outside the team (a rule is per tool, not per recipient). "
                             f"If that is what you want, confirm it in the policy editor; otherwise say 'ask me before {group}'. (Nothing was proposed for {group}.)")
            continue
        stance = max(stances, key=lambda s: STRICTNESS[s])
        if len(stances) > 1:
            notes.append(f"For {group} the sentences say {sorted(stances)}; the strictest ({stance}) was kept.")
        rules.append({"group": group, "stance": stance, "tools": list(GROUP_TOOLS[group])})
    if any(r["group"] == "outbound" for r in rules):
        notes.append("This runtime has no tool that sends mail by itself. 'Outgoing' covers the ways text leaves it (scheduled deliveries, the browser, sub-agents, exchange files), and a rule is per tool: "
                     "'the team' and 'a customer' cannot be told apart.")
    if not rules and not questions:
        questions.append("I found nothing I could turn into a rule. What should the agent never do, ask about first, or be free to do?")
    status = "ask" if questions else "ok"
    return Proposal(status=status, rules=rules, questions=questions, notes=notes, statements=[asdict(s) for s in statements])


def to_policy(proposal: Proposal, policy_id: str = "from-text") -> Dict[str, Any]:
    """The policy file content this proposal means (the same schema as `delentia fdia`). Each tool gets the strictest stance any group gives it. Zero-trust fallback: a tool nobody
    mentioned is not allowed. NOT applied anywhere: the caller shows it, and the owner saves it through the signed path."""
    per_tool: Dict[str, str] = {}
    for rule in proposal.rules:
        for tool in rule["tools"]:
            if tool not in per_tool or STRICTNESS[rule["stance"]] > STRICTNESS[per_tool[tool]]:
                per_tool[tool] = rule["stance"]
    never = sorted(t for t, s in per_tool.items() if s == NEVER)
    ask = sorted(t for t, s in per_tool.items() if s == ASK)
    allow = sorted(t for t, s in per_tool.items() if s == ALLOW)
    rules: List[Dict[str, Any]] = []
    if ask:
        rules.append({"rule_id": "T-ASK", "description": "Asked for in the owner's own words: a person signs first.", "intent_patterns": ask, "action_type": "REQUIRE_HUMAN_SIGNATURE", "required_signatures": 1})
    if allow:
        rules.append({"rule_id": "T-ALLOW", "description": "Reading, allowed in the owner's own words.", "intent_patterns": allow, "action_type": "ALLOW", "assigned_A": 1})
    return {"version": "1.0.0", "policy_id": policy_id, "policy_name": "Proposed from the owner's sentences", "default_fallback_A": 0, "custom_safety_threshold": 0.5,
            "rules": rules, "blocked_action_patterns": [f"*{t}*" for t in never], "require_human_dual_signoff": [], "roles": {"default_role": "developer", "principals": {}}, "jury_by_risk": {}}
