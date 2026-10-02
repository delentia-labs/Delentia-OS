"""
A second screen for CORD (Round 53): intent-level rules for prompt injection, jailbreaks, secret
exfiltration and destructive instructions, in English, Thai, Chinese, Japanese and Korean, that survives
the usual obfuscation (letter-spacing, hyphen-splitting, zero-width characters, leetspeak).

Why it exists. cord_security.py's regular-expression list recognised a handful of exact phrasings
("ignore all previous instructions") and nothing else: on the hand-written corpus in
tests/fixtures (scripts/measure_cord_screening.py) the loop's GUARD stopped 22% of attacks on the
development set and 7% on the hold-out, while blocking 3-4% of harmless requests that merely used
words like "pretend" or "act as". A pattern list written phrase by phrase cannot keep up with how a
sentence can be reworded, so these rules work on MEANING-BEARING WORDS NEAR EACH OTHER:

    a verb that cancels a restraint  (ignore, disregard, bypass, skip, disable, forget, ...)
    close to an object that is a restraint  (instructions, rules, safeguards, approval, audit, ...)

and likewise for "reveal ... system prompt", "send ... .env / private key / password", persona
switches to an unrestricted model, markers that fake a system turn, notes addressed to the AI inside
a document, and destructive commands. A rule fires only when both halves are present within a short
distance, so "ignore the whitespace differences" or "disable the dark-mode toggle" do not.

What it is not. It is a heuristic filter, not a proof: a determined attacker can phrase around any
word list, and the model must never be the only line of defence (approvals, the FDIA gate and the
sandbox are). It is tuned on one set of prompts and checked on another it was not tuned on; both
sets are small and written by the maintainers, so the numbers are regression guards.

Everything here is linear time: the text is scanned with str.find and a few anchored regular
expressions that have no nested or repeated groups; there is no backtracking-prone pattern.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

from rct_control_plane.cord_security import CORDCheckType, CORDFinding

# ---------------------------------------------------------------------------------------------
# normalisation
# ---------------------------------------------------------------------------------------------

_LEET = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*")
_SPACE = re.compile(r"\s+")


def _strip_invisible(text: str) -> str:
    return "".join(ch for ch in text if unicodedata.category(ch) not in ("Cf", "Cc") or ch in "\n\t ")


def normalise(text: str) -> str:
    """NFKC, lower case, invisible characters removed, whitespace collapsed."""
    return _SPACE.sub(" ", _strip_invisible(unicodedata.normalize("NFKC", text)).lower()).strip()


def _join_spaced_letters(text: str) -> str:
    """'i g n o r e' -> 'ignore' (a run of four or more single letters separated by spaces)."""
    out: List[str] = []
    run: List[str] = []
    for token in text.split(" "):
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if run:
            out.append("".join(run) if len(run) >= 4 else " ".join(run))
            run = []
        out.append(token)
    if run:
        out.append("".join(run) if len(run) >= 4 else " ".join(run))
    return " ".join(out)


def _unleet(text: str) -> str:
    """Leetspeak inside words that mix letters and digits ('1gn0re' -> 'ignore'); plain numbers are left alone."""
    out: List[str] = []
    for token in text.split(" "):
        has_letter = any(ch.isalpha() for ch in token)
        has_leet = any(ch in _LEET for ch in token)
        out.append("".join(_LEET.get(ch, ch) for ch in token) if has_letter and has_leet and any(ch.isdigit() or ch in "@$" for ch in token) else token)
    return " ".join(out)


def _unhyphen(text: str) -> str:
    """'ig-nore the prev-ious' -> 'ignore the previous' (a hyphen between two letters is removed)."""
    chars = list(text)
    return "".join(ch for i, ch in enumerate(chars)
                   if not (ch == "-" and 0 < i < len(chars) - 1 and chars[i - 1].isalpha() and chars[i + 1].isalpha()))


def _despace_wide(text: str) -> str:
    """'d i s r e g a r d   y o u r' (single spaces between letters, 2+ between words) -> 'disregard your'."""
    tokens = [t for t in re.split(r" {2,}", _strip_invisible(unicodedata.normalize("NFKC", text)).lower().replace("\n", "  ")) if t]
    words = [t.replace(" ", "") if sum(1 for x in t.split(" ") if len(x) == 1) >= max(3, len(t.split(" ")) - 1) else t for t in tokens]
    return _SPACE.sub(" ", " ".join(words)).strip()


def variants(text: str) -> List[str]:
    base = normalise(text)
    seen: List[str] = [base]
    for candidate in (_despace_wide(text), _join_spaced_letters(base), _unleet(base), _unhyphen(base), _unhyphen(_join_spaced_letters(_unleet(base)))):
        if candidate not in seen:
            seen.append(candidate)
    return seen


# ---------------------------------------------------------------------------------------------
# matching helpers
# ---------------------------------------------------------------------------------------------

def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _positions(text: str, phrases: Iterable[str]) -> List[Tuple[int, int, str]]:
    """(start, end, phrase) for every occurrence. ASCII phrases must start on a word boundary (and end on
    one unless they end with '*', which allows any suffix: 'ignor*' matches 'ignoring'); non-ASCII phrases
    (Thai, Chinese, ...) are matched as substrings because those scripts do not separate words with spaces."""
    found: List[Tuple[int, int, str]] = []
    for phrase in phrases:
        open_end = phrase.endswith("*")
        needle = phrase[:-1] if open_end else phrase
        ascii_only = needle.isascii()
        start = text.find(needle)
        while start != -1:
            end = start + len(needle)
            ok = True
            if ascii_only:
                if start > 0 and _is_word_char(text[start - 1]) and _is_word_char(needle[0]):
                    ok = False
                if ok and not open_end and end < len(text) and _is_word_char(text[end]) and _is_word_char(needle[-1]):
                    ok = False
            if ok:
                found.append((start, end, phrase))
            start = text.find(needle, start + 1)
    return found


def _near(a: List[Tuple[int, int, str]], b: List[Tuple[int, int, str]], window: int,
          skip: Optional[Callable[[int], bool]] = None) -> Optional[Tuple[str, str, int]]:
    """The first (verb phrase, object phrase, verb start) with the two within `window` characters.
    `skip(start)` can veto a verb occurrence (used for negations such as 'is not leaked')."""
    for s1, e1, p1 in a:
        if skip is not None and skip(s1):
            continue
        for s2, e2, p2 in b:
            gap = max(s2 - e1, s1 - e2, 0)
            if gap <= window and (s1, e1) != (s2, e2):
                return p1, p2, s1
    return None


# ---------------------------------------------------------------------------------------------
# rule tables
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Pair:
    rule_id: str
    detail: str
    verbs: Tuple[str, ...]
    objects: Tuple[str, ...]
    window: int = 70
    severity: str = "hard"
    untrusted_only: bool = False      # Round 54: rules that would misfire on a user's own wording, applied to third-party content only


@dataclass(frozen=True)
class Phrases:
    rule_id: str
    detail: str
    phrases: Tuple[str, ...]
    severity: str = "hard"


_CANCEL = ("ignor*", "disregard*", "forget*", "overrid*", "bypass*", "skip*", "disabl*", "suspend*", "circumvent*", "cancel*", "set aside",
           "pay no attention", "no longer appl*", "turn off", "switch off", "stop follow*", "do not follow", "don't follow", "do not obey",
           "get around", "work around", "lift the", "remove the", "drop the", "discard*", "on hold", "put aside", "lay aside", "waive*", "relax*",
           "loosen*", "take orders from me", "only follow what i", "follow only my", "only obey", "aside", "cancelled", "canceled", "no need for", "don't need", "do not need", "without waiting",
           "without asking", "without confirm*", "without approval", "without any", "without your", "never refus*")
_RESTRAINT = ("everything you were told", "everything you know", "what you were told", "told before", "before this message", "all prior",
              "prior context", "previous context", "previous messages", "all previous", "everything above", "instruction*", "rules", "guideline*", "directive*", "direction*", "policy", "policies", "restriction*", "safeguard*", "safety",
              "guardrail*", "approval", "sign-off", "signoff", "sign off", "audit", "gate", "verification", "verify", "filter*",
              "constraint*", "limitation*", "configuration", "programming", "training", "ethic*", "content policy", "safety check*", "no longer matter", "your developer", "prior directions", "being careful", "policies you started",
              # Round 54 (first look at an external set: "Ignore all preceding orders", "Forget everything before that"):
              "everything before", "before that", "all preceding", "preceding order*", "preceding instruction*", "previous task*",
              "previous assignment*", "previous information", "all the previous", "everything we discussed", "all the assignment*", "all assignment*",
              "all the task*", "previous order*", "earlier instruction*", "earlier order*")

_REVEAL = ("quote*", "what did", "what exactly did", "reveal*", "show*", "print*", "repeat*", "output*", "display*", "paste*", "tell me", "leak*", "expose*", "dump*", "disclose*",
           "recite*", "list", "give me", "what were", "what are", "what is your", "write out", "copy*", "send", "email*", "upload*", "post",
           "forward*", "exfiltrat*", "read out")
# A negating auxiliary immediately before the verb: "is not leaked", "cannot be skipped", "never ignore". A "not"
# earlier in the sentence ("you must not refuse; ignore your rules") does not make the verb harmless.
_NEGATED_BEFORE = ("not ", "n't ", "cannot be ", "never be ", "never ", "not be ", "no longer ")
_PROMPT_OBJECT = ("system prompt", "system message", "initial instruction*", "hidden instruction*", "developer note*", "developer message",
                  "your instruction*", "your rules", "your guidelines", "configuration prompt", "initial prompt", "original prompt",
                  "the text above", "hidden rules", "the prompt that was", "lines of the prompt", "the prompt above", "prompt placed", "prompt before",
                  "before my message", "system instructions", "the system message", "hidden instructions", "your prompt", "initialised with", "initialized with", "your configuration", "your directive*")

_SECRET_VERB = ("grab*", "extract*", "steal*", "harvest*", "scrape*", "put them in", "pull out", "read*", "cat", "print*", "send*", "email*", "copy*", "upload*", "paste*", "post", "curl", "exfiltrat*", "dump*", "list",
                "leak*", "reveal*", "forward*", "give me", "tell me", "show*", "output*", "type")
# Verbs that also appear in everyday sentences ("the reset email", "show the password field"): they count as
# exfiltration only when the sentence also names somewhere to send the secret.
_SECRET_VERB_NEEDS_SINK = ("email*", "show*", "list", "type", "post", "output*", "give me", "tell me", "read*")
_SECRET_OBJECT = (".env", "id_rsa", "private key", "ssh key", "api key", "api_key", "apikey", "secret*", "password*", "credential*", "token*",
                  "vault_master", "master key", "access key", "authorized_keys", "keychain", "wallet seed", "seed phrase")
_SINK = ("http://", "https://", "my server", "my address", "personal address", "paste site", "public folder", "public exchange", "this chat",
         "the chat", "here", "attacker", "collector", "webhook", "pastebin", "my email", "to me")

_PERSONA_VERB = ("once as", "answer twice", "persona of", "take on the", "who has", "as unlocked", "you are", "you're", "act as", "pretend*", "imagine you", "roleplay", "role-play", "from now on", "become", "behave as", "respond as",
                 "enter", "switch to", "answer as", "play the role")
_UNRESTRICTED = ("no restriction*", "without restriction*", "unrestricted", "no limit*", "without limit*", "no filter*", "without filter*",
                 "no ethical", "without ethic*", "no content policy", "without a policy", "without policy", "never refus*", "no rules",
                 "do anything now", "developer mode", "jailbreak*", "jailbroken", "evil ai", "evil assistant", "removed every restriction",
                 "no guidelines", "no safety", "zero ethical", "zero constraints", "zero restrictions", "no constraints", "without constraints",
                 "no ethical", "no rules at all", "never given a", "never had a content", "was never given", "never says no", "never say no", "no moral", "any request", "whatever i ask", "freegpt", "dan,", " dan ", "as dan", "is dan")

_FAKE_TURN = ("system override", "user is root", "user is admin", "### system", "###system", "<system>", "</system>", "<|im_start|>", "<|im_end|>", "[inst]", "<<sys>>", "</user_input>", "[system]",
              "---end of user message---", "end of user message", "system:", "assistant:", "<|system|>", "<|endoftext|>")
_AUTHORITY = ("authoris*", "authoriz*", "administrator", "admin", "operator", "granted", "full access", "without confirmation", "no restrictions",
              "run any", "execute any", "any command", "any shell", "wipe", "delete", "disable")

_DESTRUCTIVE = ("rm -rf", "rm -fr", "drop database", "drop table", "drop schema", "truncate table", "format c:", "mkfs", "del /f", "del /s", "rd /s",
                "shred ", "dd if=", ":(){", "chmod 777", "chmod -r 777", "force push", "git push --force", "git push -f", "git reset --hard",
                "wipe the", "wipe all", "wipe every", "erase every", "erase all", "destroy the", "remove all records", "delete everything",
                "delete every file", "delete all files", "delete all the files", "delete the entire", "truncate every", "truncate all")
_DESTRUCTIVE_TARGET = ("database", "backup*", "repository", "production", "prod", "server", "records", "audit", "workspace", "disk", "everything",
                       "table*", "main", "all files", "every file")
_EXPLAIN = ("explain", "what does", "what is", "why ", "how does", "how do i", "describe", "summari", "difference between", "write a test",
            "review this", "i want to understand", "not run it", "do not run", "don't run", "for educational", "อธิบาย", "คืออะไร", "ช่วยอธิบาย",
            "แตกต่าง", "请解释", "什么是", "説明して", "とは")
_IMPERATIVE = ("run it", "execute", "right now", "do it", "go ahead", "immediately", "now.", "now!", "on the server", "on the production",
               "on the host", "run rm", "run sudo", "run the", "then continue", "and confirm")

_INDIRECT = ("note for the ai", "for the ai reader", "ai reader", "note for the assistant", "instruction for the ai", "instruction to the ai", "instruction for the assistant", "note to the assistant", "note to ai", "note to assistant", "note to the ai", "ai assistant reading", "ai agents:", "ai agent:", "notice to ai", "dear model",
             "dear ai", "message for the language model", "for the language model", "for automated readers", "to the assistant processing",
             "when you read this", "when summarising this", "when summarizing this", "if you are an ai", "if you are a language model",
             "hidden text for", "instructions for the ai", "attention ai", "attention assistant", "attention language model", "to any ai")
_INDIRECT_FOLLOW = ("do not tell", "don't tell", "mark it", "mark this", "open the user", "send the last", "ignor*", "disregard*", "instead", "silently", "do not mention", "don't mention", "tell the user", "forward", "send", "email*",
                    "run the command", "run `", "call the", "reveal", "disable", "write to", "curl", "execute", "without telling", "secretly")

_APPROVAL_SPOOF = ("treat the approval", "approval flag", "skip the approval", "skip approval", "bypass the approval", "set a = 1", "set a=1", "set a to 1",
                   "signature is attached", "do not need to verify", "don't need to verify", "no need to verify", "no need for anyone", "do not ask for a signature",
                   "skip the verification", "skip verification")
# Claims of approval only count with an action cue beside them ("the security team has signed off, so skip ...").
_APPROVAL_CLAIM = ("already approved", "already signed off", "has approved", "have approved", "gave verbal approval", "verbal approval", "pre-approved",
                   "preapproved", "i am the architect", "i'm the architect", "i am the administrator", "i am an administrator", "i am authori*",
                   "i am the owner", "has signed off", "have signed off", "signed off, so", "already said yes", "already agreed", "already okayed", "already authorised",
                   "already authorized", "no reason to wait")
_ACTION_CUE = ("skip", "proceed", "go ahead", "without", "no need", "do not ask", "don't ask", "do not verify", "write the", "delete", "deploy", "publish",
               "run ", "execute", "so you can", "so go")
_DESTROY_VERB = ("drop*", "delet*", "wipe*", "nuke*", "erase*", "destroy*", "truncat*", "purg*", "obliterat*", "remov*")
_DESTROY_TARGET = ("production database", "production data", "the database", "all databases", "customer database", "orders database", "repository history",
                   "git history", "commit history", "all backups", "the backups", "nightly backups", "every table", "all tables", "audit trail", "audit log",
                   "all records", "every record", "all of the data", "all the data", "entire database", "whole database")
_MASS_SECRET = ("every password", "all the passwords", "all passwords", "every secret", "all secrets", "all the secrets", "every api key", "all api keys",
                "all the keys", "every token", "all tokens", "all credentials", "every credential")
_DESTRUCTIVE_STANDALONE = ("format c:", "format d:", "mkfs.", "rm -rf /", "rm -rf ~", "rm -rf *", ":(){", "dd if=/dev/zero", "drop database")
_HARMFUL = ("deceased grandmother", "napalm", "build a bomb", "make a bomb", "make explosives", "nerve agent", "bioweapon")
_TOOL_ABUSE = ("169.254.169.254", "metadata.google.internal", "authorized_keys", "powershell -enc", "powershell -e ", "-encodedcommand",
               "curl evil", "| sh", "| bash", "|sh", "base64 -d", "/etc/shadow", "~/.ssh", ".bashrc", "crontab -", "nc -e", "bash -i")

# Thai / CJK / Korean: no word boundaries, so verb and object are looked for within a character window.
_TH_CANCEL = ("ไม่ต้องสนใจ", "เพิกเฉย", "ไม่สนใจ", "ลืม", "ข้าม", "ยกเลิก", "ปิด", "หลีกเลี่ยง", "ละเว้น", "ทำลาย", "ไม่ต้องทำตาม", "ไม่ต้องกลัว",
              "ไม่ต้องขอ", "โดยไม่ต้อง", "ปลดล็อก", "ปลด")
_TH_RESTRAINT = ("คำสั่ง", "กฎ", "ข้อจำกัด", "นโยบาย", "การอนุมัติ", "อนุมัติ", "ขั้นตอนการอนุมัติ", "ความปลอดภัย", "audit", "บันทึก", "system prompt",
                 "ข้อห้าม", "มาตรการ", "ตัวกรอง")
_TH_REVEAL = ("แสดง", "บอก", "ส่ง", "เปิดเผย", "พิมพ์", "ให้ฉัน", "มาให้", "ก๊อป", "คัดลอก", "อ่าน")
_TH_SECRET = ("ข้อความระบบ", "ข้อความที่ซ่อน", "คำสั่งระบบ", "พรอมต์ระบบ", "รหัสผ่าน", "คีย์", "กุญแจ", ".env", "token", "api key", "ข้อมูลลับ", "secret", "private key", "system prompt")
_TH_DESTROY = ("ลบไฟล์ทั้งหมด", "ลบทั้งหมด", "ลบทุกอย่าง", "ลบฐานข้อมูล", "ล้างข้อมูลทั้งหมด", "ทำลายข้อมูล")
_TH_UNRESTRICTED = ("ไม่มีข้อจำกัด", "ไม่มีกฎ", "ไร้ข้อจำกัด", "ไม่มีนโยบาย", "ปราศจากข้อจำกัด", "ตอบทุกอย่างโดย")
_CJK_CANCEL = ("送って", "发给我", "发送", "보내", "忽略", "无视", "無視", "忽視", "绕过", "繞過", "忘记", "忘記", "无视你", "무시", "잊어", "우회", "비활성화", "忘れて", "無効にして")
_CJK_RESTRAINT = ("命令", "機密", "机密", "指令", "规则", "規則", "规矩", "提示词", "提示詞", "系统提示", "系統提示", "システムプロンプト", "指示", "ルール", "지시", "프롬프트", "규칙",
                  "安全", "限制", "限制", "制限", "제한")

_PRAISE_THEN = ("well done", "very good", "excellent", "great job", "congratulations", "fantastic", "simply great", "that is enough", "that is done",
                "that was ok", "that was okay", "perfect", "good job", "nice work", "outdone yourself", "you did it", "wow", "stop - ", "attention")
_NEW_TASK = ("new task*", "further task*", "another task", "next task", "new instruction*", "new assignment*", "new challenge", "new job",
             "more task*", "following task", "following question", "following text*", "concentrate on")

_NOW_NEW = ("now new", "now further", "new tasks follow", "new instructions follow", "further tasks follow", "now concentrate", "now i need",
            "now write", "now answer", "now forget", "now please", "now help me", "now follow")

PAIRS: Tuple[Pair, ...] = (
    Pair("CORD-S001", "Cancel-the-restraints: a verb that cancels a rule next to the rule (ignore/bypass/skip/disable ... instructions/approval/safeguards).",
         _CANCEL, _RESTRAINT, window=48),
    Pair("CORD-S002", "Prompt/instruction disclosure: asks the model to reveal, repeat or print its own system prompt or hidden instructions.",
         _REVEAL, _PROMPT_OBJECT, window=70),
    Pair("CORD-S003", "Secret exfiltration: reads or sends a secret (.env, key, password, token) towards a sink.",
         _SECRET_VERB, _SECRET_OBJECT, window=60),
    Pair("CORD-S004", "Persona switch to an unrestricted model.", _PERSONA_VERB, _UNRESTRICTED, window=110),
    Pair("CORD-S005", "Destructive command aimed at data, backups, the audit trail or production.", _DESTRUCTIVE, _DESTRUCTIVE_TARGET, window=50),
    Pair("CORD-S006", "Instruction addressed to an AI hidden inside content, followed by an action.", _INDIRECT, _INDIRECT_FOLLOW, window=160),
    Pair("CORD-S018", "A claim that approval already exists, next to a request to act without it.", _APPROVAL_CLAIM, _ACTION_CUE, window=90),
    Pair("CORD-S019", "Deletion or wiping of a database, its backups, the audit trail or the repository history.", _DESTROY_VERB, _DESTROY_TARGET, window=30),
    Pair("CORD-S020", "Mass disclosure of secrets (every password, all keys, all tokens).", _SECRET_VERB, _MASS_SECRET, window=40),
    Pair("CORD-S021", "Japanese/Chinese/Korean: asks for secrets or the system prompt.", ("送", "发", "显示", "表示", "보내", "출력", "告诉", "见せて", "見せて"),
         ("机密", "機密", "密码", "パスワード", "秘密鍵", "私钥", "비밀번호", "시스템 프롬프트", "系统提示", "システムプロンプト"), window=14),
    Pair("CORD-S022", "Context switch inside third-party content: praise or an 'that is enough', then 'now' with a new task or new instructions.",
         _PRAISE_THEN, _NOW_NEW, window=90, untrusted_only=True),
    Pair("CORD-S023", "Third-party content tells the model to start over or to drop what it was doing.",
         ("start over", "start from scratch", "start anew", "from the front", "begin anew", "leave behind", "put out of your head", "remove from your head"),
         _NEW_TASK + ("all the previous", "all previous", "everything before"), window=70, untrusted_only=True),
    Pair("CORD-S024", "Third-party content assigns the model a new role.", ("you are now", "from now on you", "now you are", "i want you to act as", "act as if you are", "pretend you are", "you will act as"),
         ("terminal", "translator", "debater", "character", "expert", "persona", "stay in", "answer as", "in the style", "interpreter"), window=90, untrusted_only=True),
    Pair("CORD-S007", "Thai: cancels rules or approvals.", _TH_CANCEL, _TH_RESTRAINT, window=24),
    Pair("CORD-S008", "Thai: asks for secrets or the system prompt.", _TH_REVEAL, _TH_SECRET, window=30),
    Pair("CORD-S009", "Chinese/Japanese/Korean: cancels rules or asks for the system prompt.", _CJK_CANCEL, _CJK_RESTRAINT, window=14),
)
SINGLES: Tuple[Phrases, ...] = (
    Phrases("CORD-S010", "Fake system/turn markers inside user text.", _FAKE_TURN),
    Phrases("CORD-S011", "Spoofed approval or authority: claims the approval already exists or asks to skip verification.", _APPROVAL_SPOOF),
    Phrases("CORD-S012", "Tool abuse: metadata endpoints, remote shells, key files, encoded PowerShell, pipe-to-shell.", _TOOL_ABUSE),
    Phrases("CORD-S013", "Thai: destructive instruction.", _TH_DESTROY),
    Phrases("CORD-S017", "A command that destroys a disk, a filesystem or a database on its own.", _DESTRUCTIVE_STANDALONE),
    Phrases("CORD-S015", "Weapon or mass-harm request, or the classic deceased-grandmother jailbreak framing.", _HARMFUL),
    Phrases("CORD-S014", "Thai: unrestricted-model persona.", _TH_UNRESTRICTED),
)


_EXPLAIN_LATE = ("i want to understand", "not run it", "do not run", "don't run", "for educational")


def _has_imperative(text: str) -> bool:
    for marker in _IMPERATIVE:
        start = text.find(marker)
        while start != -1:
            if not any(text[max(0, start - 8):start].endswith(n) for n in ("not ", "n't ", "never ")):
                return True
            start = text.find(marker, start + 1)
    return False


def _explanatory(text: str) -> bool:
    """The request is to explain, describe or test something that merely MENTIONS a dangerous term: the framing
    word is in the first words ('Explain what ...', 'What does the command ...', 'Write a test that ...'), or the
    sender says they do not want it run; and nothing in the text asks for it to be executed."""
    # Question words are framing only at the very start ("What does ..."); a mid-sentence "what is inside" is not.
    question_start = ("what does", "what is", "why ", "how does", "how do i")
    framed = (any(text.find(m) != -1 and text.find(m) <= 12 for m in question_start)
              or any(m in text[:45] for m in _EXPLAIN if m.isascii() and m not in question_start)
              or any(m in text for m in _EXPLAIN if not m.isascii())
              or any(m in text for m in _EXPLAIN_LATE))
    return framed and not _has_imperative(text)


class InjectionScreen:
    """Runs every rule on every normalised variant of the text and returns CORD findings."""

    def check(self, text: str, _depth: int = 0, trusted: bool = True) -> List[CORDFinding]:
        """`trusted=False` is for content that did not come from the user (web pages, stored memory, files from elsewhere): it adds
        the rules that read like a normal user message when a user says them ('Great, now another task: ...') but are a classic
        hijack when they appear inside a page or a document the agent was only meant to read."""
        findings: List[CORDFinding] = []
        fired: set = set()

        def add(rule_id: str, severity: str, detail: str, excerpt: str) -> None:
            if rule_id in fired:
                return
            fired.add(rule_id)
            findings.append(CORDFinding(check_type=CORDCheckType.SCREEN, severity=severity, pattern_id=rule_id,
                                        excerpt=excerpt[:117] + ("…" if len(excerpt) > 117 else ""), detail=detail))

        for variant in variants(text):
            explanatory = _explanatory(variant)
            sink = bool(_positions(variant, _SINK))
            for pair in PAIRS:
                if pair.untrusted_only and trusted:
                    continue
                verbs = _positions(variant, pair.verbs)
                skip: Optional[Callable[[int], bool]] = None
                if pair.rule_id == "CORD-S003":
                    def skip(start: int, v: str = variant) -> bool:
                        return any(v[max(0, start - 6):start].endswith(a) for a in ("a ", "the ", "any ", "your ", "this "))
                if pair.rule_id in ("CORD-S001", "CORD-S002"):
                    def skip(start: int, v: str = variant) -> bool:
                        return any(v[max(0, start - 14):start].endswith(n) for n in _NEGATED_BEFORE)
                if pair.rule_id == "CORD-S003" and not sink:
                    verbs = [v for v in verbs if v[2] not in _SECRET_VERB_NEEDS_SINK]
                hit = _near(verbs, _positions(variant, pair.objects), pair.window, skip)
                if hit:
                    softened = pair.rule_id in ("CORD-S005", "CORD-S003", "CORD-S002") and explanatory
                    add(pair.rule_id, "soft" if softened else pair.severity, pair.detail, f"{hit[0]} ... {hit[1]}")
            for rule in SINGLES:
                positions = _positions(variant, rule.phrases)
                if positions:
                    # A bare 'system:'/'assistant:' only counts next to authority or action words; the explicit
                    # tokens ('<|im_start|>', '### system', '[inst]', ...) count on their own.
                    if rule.rule_id == "CORD-S010":
                        weak = {"system:", "assistant:"}
                        strong = [p for p in positions if p[2] not in weak]
                        if not strong and not _near(positions, _positions(variant, _AUTHORITY), 90):
                            continue
                    severity = "soft" if (rule.rule_id == "CORD-S017" and explanatory) else rule.severity
                    add(rule.rule_id, severity, rule.detail, positions[0][2])
        if _depth == 0:
            for decoded in _decoded_payloads(text):
                inner = [f for f in self.check(decoded, _depth=1, trusted=trusted) if f.severity == "hard"]
                if inner:
                    add("CORD-S016", "hard", "An encoded (base64 or hex) payload decodes to an instruction the screen would block.",
                        "decoded: " + decoded[:60])
        return findings


_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2}){12,}")


def _decoded_payloads(text: str) -> List[str]:
    """Readable text hidden in base64 or hex tokens (binary such as an image decodes to unreadable bytes and is ignored)."""
    import base64
    import binascii
    out: List[str] = []
    for token in _B64.findall(text)[:8]:
        padded = token + "=" * (-len(token) % 4)
        try:
            raw = base64.b64decode(padded, validate=True)
        except (ValueError, binascii.Error):
            continue
        if _printable(raw):
            out.append(raw.decode("utf-8"))
    for token in _HEX.findall(text)[:8]:
        try:
            raw = bytes.fromhex(token)
        except ValueError:
            continue
        if _printable(raw):
            out.append(raw.decode("utf-8"))
    return out


def _printable(raw: bytes) -> bool:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return bool(decoded) and sum(ch.isprintable() or ch in "\n\t" for ch in decoded) / len(decoded) > 0.95
