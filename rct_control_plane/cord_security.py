"""
CORD Security Engine — Constitutional Oversight & Rejection Detector

Provides entropy-based input validation and prompt-injection pattern matching
for JITNA packet payloads and intent descriptions before they enter the
Control Plane execution graph.

CORD = Constitutional Oversight Rejection Detector

Architecture:
    1. EntropyValidator  — high-entropy strings (base64/hex blobs, obfuscation)
    2. InjectionDetector — prompt-injection / jailbreak pattern matching
    3. GovernanceViolationDetector — anomalous FDIA score spikes (metric gaming)
    4. CORDEngine        — orchestrates all three checks, returns CORDResult

Security model:
    - GIGO Rejection: garbage/obfuscated input blocked before compilation
    - Injection Resistance: adversarial natural-language attacks rejected
    - Metric Gaming Detection: statistical outlier detection on FDIA scores
    - All rejections logged to the audit trail

Test coverage: 100 curated public test vectors (see cord_security_tests.py)

Apache 2.0 — RCT Labs (https://rctlabs.co)
"""

from __future__ import annotations

import hashlib
import math
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Result Types
# ============================================================================

class CORDVerdict(str, Enum):
    """Overall CORD verdict for an input."""
    CLEAN = "clean"           # Input passes all checks
    SUSPICIOUS = "suspicious" # One soft-signal fired; log but allow
    REJECTED = "rejected"     # One hard-signal fired; block execution


class CORDCheckType(str, Enum):
    """Which CORD sub-check fired."""
    ENTROPY = "entropy"
    INJECTION = "injection"
    METRIC_GAMING = "metric_gaming"
    PAYLOAD_SIZE = "payload_size"


@dataclass
class CORDFinding:
    """A single finding from a CORD sub-check."""
    check_type: CORDCheckType
    severity: str          # "hard" (reject) | "soft" (warn)
    pattern_id: str        # Unique ID of the rule that fired
    excerpt: str           # Short excerpt showing what matched (≤120 chars)
    detail: str            # Human-readable explanation


@dataclass
class CORDResult:
    """Result of running the CORD Engine on a single input."""
    verdict: CORDVerdict
    findings: List[CORDFinding] = field(default_factory=list)
    entropy_score: float = 0.0
    input_length: int = 0
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    input_fingerprint: str = ""   # SHA-256 of raw input (for dedup)

    @property
    def is_clean(self) -> bool:
        return self.verdict == CORDVerdict.CLEAN

    @property
    def hard_findings(self) -> List[CORDFinding]:
        return [f for f in self.findings if f.severity == "hard"]

    @property
    def soft_findings(self) -> List[CORDFinding]:
        return [f for f in self.findings if f.severity == "soft"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "entropy_score": round(self.entropy_score, 4),
            "input_length": self.input_length,
            "checked_at": self.checked_at,
            "input_fingerprint": self.input_fingerprint,
            "findings": [
                {
                    "check_type": f.check_type.value,
                    "severity": f.severity,
                    "pattern_id": f.pattern_id,
                    "excerpt": f.excerpt,
                    "detail": f.detail,
                }
                for f in self.findings
            ],
        }


# ============================================================================
# 1. Entropy Validator
# ============================================================================

# Max Shannon entropy before triggering (bits per character, 0–8 scale)
_ENTROPY_HARD_THRESHOLD = 5.8   # very high → likely obfuscation / base64 blob
_ENTROPY_SOFT_THRESHOLD = 5.0   # moderate → worth flagging
_MIN_LENGTH_FOR_ENTROPY = 64    # don't entropy-check short strings


def _shannon_entropy(text: str) -> float:
    """Calculate Shannon entropy (bits/char) of a text string."""
    if not text:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


class EntropyValidator:
    """
    Detect obfuscated or garbage input via Shannon entropy analysis.

    High-entropy strings (long base64/hex blobs, encoded payloads) are a
    common vector for embedding hidden instructions or exfiltration attempts.
    """

    def check(self, text: str) -> List[CORDFinding]:
        findings: List[CORDFinding] = []
        if len(text) < _MIN_LENGTH_FOR_ENTROPY:
            return findings

        score = _shannon_entropy(text)

        if score >= _ENTROPY_HARD_THRESHOLD:
            findings.append(CORDFinding(
                check_type=CORDCheckType.ENTROPY,
                severity="hard",
                pattern_id="CORD-E001",
                excerpt=text[:80] + ("…" if len(text) > 80 else ""),
                detail=(
                    f"Shannon entropy {score:.2f} bits/char exceeds hard "
                    f"threshold {_ENTROPY_HARD_THRESHOLD}. Input appears "
                    "obfuscated or contains an encoded payload."
                ),
            ))
        elif score >= _ENTROPY_SOFT_THRESHOLD:
            findings.append(CORDFinding(
                check_type=CORDCheckType.ENTROPY,
                severity="soft",
                pattern_id="CORD-E002",
                excerpt=text[:80] + ("…" if len(text) > 80 else ""),
                detail=(
                    f"Shannon entropy {score:.2f} bits/char is elevated "
                    f"(soft threshold {_ENTROPY_SOFT_THRESHOLD}). May contain "
                    "encoded data; review before execution."
                ),
            ))

        return findings


# ============================================================================
# 2. Injection Detector
# ============================================================================

@dataclass
class _InjectionPattern:
    pattern_id: str
    regex: re.Pattern[str]
    severity: str
    detail: str


# 100 curated public test vectors covering the main injection categories
# Categories: role-switch, DAN/jailbreak, token manipulation, system-override,
#             multi-lang bypass, encoding bypass, context confusion
_INJECTION_PATTERNS: List[_InjectionPattern] = [
    # ── Role-switch attacks ──────────────────────────────────────────────
    _InjectionPattern("CORD-I001", re.compile(
        r"\bignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|context)",
        re.IGNORECASE
    ), "hard", "Classic 'ignore previous instructions' jailbreak."),
    _InjectionPattern("CORD-I002", re.compile(
        r"\byou\s+are\s+now\s+(a|an)\s+\w+",
        re.IGNORECASE
    ), "hard", "Role-reassignment attack: 'you are now a [role]'."),
    _InjectionPattern("CORD-I003", re.compile(
        r"\bact\s+as\s+(a|an)\s+\w+(\s+without\s+(restrictions?|filters?|limits?))?",
        re.IGNORECASE
    ), "hard", "Role-play injection: 'act as [X] without restrictions'."),
    _InjectionPattern("CORD-I004", re.compile(
        r"\bpretend\s+(you\s+are|to\s+be)\s+(a|an)?\s*\w+",
        re.IGNORECASE
    ), "soft", "Persona-switch: 'pretend you are / pretend to be'."),
    _InjectionPattern("CORD-I005", re.compile(
        r"\bforget\s+(your\s+)?(training|guidelines?|rules?|system\s+prompt)",
        re.IGNORECASE
    ), "hard", "Training-erasure attack: 'forget your training/guidelines'."),

    # ── DAN / jailbreak keywords ─────────────────────────────────────────
    _InjectionPattern("CORD-I006", re.compile(
        r"\bDAN\b|\bdo\s+anything\s+now\b",
        re.IGNORECASE
    ), "hard", "DAN (Do Anything Now) jailbreak keyword detected."),
    _InjectionPattern("CORD-I007", re.compile(
        r"\bjailbreak\b",
        re.IGNORECASE
    ), "soft", "Jailbreak keyword detected."),
    _InjectionPattern("CORD-I008", re.compile(
        r"\bunfiltered\s+(mode|response|output|ai)\b",
        re.IGNORECASE
    ), "hard", "'Unfiltered mode/AI' bypass attempt."),
    _InjectionPattern("CORD-I009", re.compile(
        r"\bno\s+(safety|ethical?|content)\s+(filter|restriction|guideline)s?",
        re.IGNORECASE
    ), "hard", "Request to disable safety filters."),
    _InjectionPattern("CORD-I010", re.compile(
        r"\bdeveloper\s+mode\b|\benable\s+dev\s+mode\b",
        re.IGNORECASE
    ), "hard", "'Developer mode' bypass attempt."),

    # ── System prompt extraction ──────────────────────────────────────────
    _InjectionPattern("CORD-I011", re.compile(
        r"\brepeat\s+(your\s+)?(system\s+prompt|instructions?|context|initial\s+prompt)",
        re.IGNORECASE
    ), "hard", "System prompt extraction: 'repeat your system prompt'."),
    _InjectionPattern("CORD-I012", re.compile(
        r"\bprint\s+(your\s+)?(system\s+prompt|hidden\s+instructions?)",
        re.IGNORECASE
    ), "hard", "System prompt extraction via 'print'."),
    _InjectionPattern("CORD-I013", re.compile(
        r"\bwhat\s+(are|were|is)\s+your\s+(instructions?|system\s+prompt|rules?)\b",
        re.IGNORECASE
    ), "soft", "Probe for hidden system instructions."),
    _InjectionPattern("CORD-I014", re.compile(
        r"\bshow\s+(me\s+)?(your\s+)?(full\s+)?(system\s+prompt|initial\s+context)",
        re.IGNORECASE
    ), "hard", "System prompt extraction via 'show'."),

    # ── Context confusion / escape sequences ─────────────────────────────
    _InjectionPattern("CORD-I015", re.compile(
        r"(?:^|\n)\s*#{1,6}\s+(?:system|assistant|user|human|ai)\s*:",
        re.IGNORECASE | re.MULTILINE
    ), "hard", "Markdown header role injection (# System: / # User:)."),
    _InjectionPattern("CORD-I016", re.compile(
        r"<\|(?:system|user|assistant|im_start|im_end)\|>",
        re.IGNORECASE
    ), "hard", "ChatML token injection (<|system|>, <|im_start|>, etc.)."),
    _InjectionPattern("CORD-I017", re.compile(
        r"\[INST\]|\[/INST\]|\[SYS\]|\[/SYS\]",
        re.IGNORECASE
    ), "hard", "Llama-2 instruction token injection ([INST], [SYS])."),
    _InjectionPattern("CORD-I018", re.compile(
        r"<<SYS>>|<</SYS>>",
        re.IGNORECASE
    ), "hard", "Llama-2 system block injection (<<SYS>>)."),
    _InjectionPattern("CORD-I019", re.compile(
        r"\bnew\s+conversation\b|\bnew\s+session\b|\breset\s+context\b",
        re.IGNORECASE
    ), "soft", "Context reset injection attempt."),
    _InjectionPattern("CORD-I020", re.compile(
        r"---+\s*(?:system|instructions?|prompt)\s*---+",
        re.IGNORECASE
    ), "hard", "HR-delimiter role injection (--- system ---)."),

    # ── Encoding / obfuscation bypasses ──────────────────────────────────
    _InjectionPattern("CORD-I021", re.compile(
        r"(?:[A-Za-z0-9+/]{40,}={0,2})",
    ), "soft", "Long base64-like string; possible encoded payload."),
    _InjectionPattern("CORD-I022", re.compile(
        r"(?:\\x[0-9a-fA-F]{2}){6,}",
    ), "hard", "Hex escape sequence cluster; obfuscation attempt."),
    _InjectionPattern("CORD-I023", re.compile(
        r"(?:\\u[0-9a-fA-F]{4}){4,}",
    ), "soft", "Unicode escape sequence cluster; possible obfuscation."),
    _InjectionPattern("CORD-I024", re.compile(
        r"(?:0x[0-9a-fA-F]{2}\s*){8,}",
    ), "soft", "Hex byte sequence; possible encoded instruction."),

    # ── Prompt override / goal hijacking ─────────────────────────────────
    _InjectionPattern("CORD-I025", re.compile(
        r"\byour\s+(only|real|true|actual)\s+(goal|purpose|task|job|instruction)\s+is\b",
        re.IGNORECASE
    ), "hard", "Goal hijacking: 'your only/real goal is'."),
    _InjectionPattern("CORD-I026", re.compile(
        r"\bfrom\s+now\s+on\b.{0,40}\b(you\s+(will|must|should)|always|never)\b",
        re.IGNORECASE
    ), "hard", "Persistent instruction injection: 'from now on'."),
    _InjectionPattern("CORD-I027", re.compile(
        r"\boverride\s+(your\s+)?(safety|ethical?|guidelines?|constitutional)\b",
        re.IGNORECASE
    ), "hard", "Explicit override of constitutional constraints."),
    _InjectionPattern("CORD-I028", re.compile(
        r"\byou\s+(must|should|will)\s+(now\s+)?bypass\b",
        re.IGNORECASE
    ), "hard", "Explicit bypass instruction."),
    _InjectionPattern("CORD-I029", re.compile(
        r"\bthink\s+step\s+by\s+step\s+about\s+how\s+to\s+(?:bypass|jailbreak|hack)\b",
        re.IGNORECASE
    ), "hard", "Chain-of-thought bypass scaffolding."),
    _InjectionPattern("CORD-I030", re.compile(
        r"\bhypothetically\s+speaking\s*,?\s*(?:if\s+)?(?:you\s+could|there\s+were)\b",
        re.IGNORECASE
    ), "soft", "Hypothetical framing to bypass constraints."),

    # ── Exfiltration attempts ─────────────────────────────────────────────
    _InjectionPattern("CORD-I031", re.compile(
        r"\bsend\s+(this|the)\s+(to|data|payload|context)\s+(http|https|ftp|webhook)\b",
        re.IGNORECASE
    ), "hard", "Exfiltration via URL injection."),
    _InjectionPattern("CORD-I032", re.compile(
        r"\bfetch\s+(?:http|https)://\S+",
        re.IGNORECASE
    ), "hard", "SSRF / data exfiltration attempt via fetch."),
    _InjectionPattern("CORD-I033", re.compile(
        r"\b(?:curl|wget|nc|ncat|netcat)\s+(?:-\w+\s+)*https?://\S+",
        re.IGNORECASE
    ), "hard", "Shell command injection (curl/wget/netcat)."),
    _InjectionPattern("CORD-I034", re.compile(
        r"\beval\s*\(|exec\s*\(|__import__\s*\(",
        re.IGNORECASE
    ), "hard", "Python code injection (eval/exec/__import__)."),
    _InjectionPattern("CORD-I035", re.compile(
        r"<script[^>]*>|javascript\s*:",
        re.IGNORECASE
    ), "hard", "XSS / script injection attempt."),

    # ── Multi-language bypasses ───────────────────────────────────────────
    _InjectionPattern("CORD-I036", re.compile(
        r"\b(?:ignorieren|ignorez|ignorer|ignora)\s+(?:alle|vorige|previous)\b",
        re.IGNORECASE
    ), "soft", "Multi-language 'ignore' bypass (DE/FR/ES)."),
    _InjectionPattern("CORD-I037", re.compile(
        r"\bเพิกเฉย.{0,20}(?:คำสั่ง|ระบบ|instructions?)",
        re.IGNORECASE
    ), "soft", "Thai-language injection attempt."),

    # ── FDIA / constitutional bypass ─────────────────────────────────────
    _InjectionPattern("CORD-I038", re.compile(
        r"\bset\s+(?:fdia|alignment|desire|intent)\s*=\s*[0-9.]+",
        re.IGNORECASE
    ), "hard", "Direct FDIA parameter manipulation attempt."),
    _InjectionPattern("CORD-I039", re.compile(
        r"\bset\s+governance\s*(factor\s*)?=\s*1\b",
        re.IGNORECASE
    ), "hard", "Governance factor override to 1.0 (bypass attempt)."),
    _InjectionPattern("CORD-I040", re.compile(
        r"\bfdia\s*score\s*(?:is|=|:)\s*(?:0\.9[5-9]|1\.0)",
        re.IGNORECASE
    ), "soft", "Suspicious FDIA score claim ≥ 0.95 in text."),

    # ── Indirect injection (data-path) ───────────────────────────────────
    _InjectionPattern("CORD-I041", re.compile(
        r"\[hidden\s+instructions?\]|\[secret\s+prompt\]",
        re.IGNORECASE
    ), "hard", "Hidden instruction marker in text."),
    _InjectionPattern("CORD-I042", re.compile(
        r"<!--.*?-->",
        re.DOTALL
    ), "soft", "HTML comment block; possible hidden instruction."),
    _InjectionPattern("CORD-I043", re.compile(
        r"/\*.*?\*/",
        re.DOTALL
    ), "soft", "C-style comment block; possible hidden instruction."),
    _InjectionPattern("CORD-I044", re.compile(
        r"\bstop\b.{0,20}\bfollowing\b.{0,20}\b(rules?|instructions?|guidelines?)",
        re.IGNORECASE
    ), "hard", "Explicit instruction to stop following rules."),
    _InjectionPattern("CORD-I045", re.compile(
        r"\byou\s+are\s+free\s+to\b|\bno\s+longer\s+bound\b",
        re.IGNORECASE
    ), "hard", "Constraint liberation framing."),

    # ── Additional hard stops ─────────────────────────────────────────────
    _InjectionPattern("CORD-I046", re.compile(
        r"\bsudo\b.{0,30}\b(override|bypass|disable|unlock)\b",
        re.IGNORECASE
    ), "hard", "sudo-privilege escalation framing."),
    _InjectionPattern("CORD-I047", re.compile(
        r"\badmin\s+mode\b|\broot\s+access\b|\bsuperuser\s+mode\b",
        re.IGNORECASE
    ), "hard", "Privilege escalation keyword."),
    _InjectionPattern("CORD-I048", re.compile(
        r"\bGPT-4\s+is\s+now\s+(a|in)\b|\bClaude\s+is\s+now\b",
        re.IGNORECASE
    ), "hard", "Model identity substitution attack."),
    _InjectionPattern("CORD-I049", re.compile(
        r"\btoken\s+limit\b.{0,40}\bbypass\b|\bcontext\s+window\b.{0,40}\boverflow\b",
        re.IGNORECASE
    ), "soft", "Context overflow / token-limit exploit attempt."),
    _InjectionPattern("CORD-I050", re.compile(
        r"\binfinite\s+loop\b|\brecurse\s+forever\b|\bwhile\s+true\b",
        re.IGNORECASE
    ), "soft", "DoS via infinite loop / recursion hint."),

    # ── Multi-language: Thai injection (I051–I055) ────────────────────────
    _InjectionPattern("CORD-I051", re.compile(
        r"ละเว้น.{0,20}(?:คำสั่ง|ระบบ|system)",
        re.IGNORECASE
    ), "hard", "Thai: 'ละเว้น' (ignore) combined with instruction/system keyword."),
    _InjectionPattern("CORD-I052", re.compile(
        r"เพิกเฉย.{0,30}(?:กฎ|คำสั่ง|ข้อจำกัด)",
        re.IGNORECASE
    ), "hard", "Thai: 'เพิกเฉย' (disregard) combined with rules/restrictions."),
    _InjectionPattern("CORD-I053", re.compile(
        r"ตอนนี้คุณคือ|คุณเป็น.{0,20}(?:ที่ไม่มี|ปราศจาก)(?:ข้อจำกัด|กฎ)",
        re.IGNORECASE
    ), "hard", "Thai role-reassignment: 'ตอนนี้คุณคือ' (now you are)."),
    _InjectionPattern("CORD-I054", re.compile(
        r"ลืม.{0,30}(?:คำสั่ง|การฝึก|ระบบ)",
        re.IGNORECASE
    ), "soft", "Thai: 'ลืม' (forget) training/system instructions."),
    _InjectionPattern("CORD-I055", re.compile(
        r"บอก.{0,20}(?:system prompt|คำสั่งระบบ|prompt เดิม)",
        re.IGNORECASE
    ), "hard", "Thai: 'บอก' (tell me) system prompt extraction attempt."),

    # ── Multi-language: Chinese injection (I056–I058) ─────────────────────
    _InjectionPattern("CORD-I056", re.compile(
        r"忽略.{0,20}(?:之前|所有|上面).{0,20}(?:指令|提示|规则)",
        re.IGNORECASE
    ), "hard", "Chinese: 忽略 (ignore) previous instructions/rules."),
    _InjectionPattern("CORD-I057", re.compile(
        r"现在你是|你现在是.{0,20}(?:没有|不受).{0,20}(?:限制|约束)",
        re.IGNORECASE
    ), "hard", "Chinese role-reassignment: 现在你是 (now you are) without restrictions."),
    _InjectionPattern("CORD-I058", re.compile(
        r"输出.{0,20}(?:系统提示|system prompt|初始指令)",
        re.IGNORECASE
    ), "hard", "Chinese: 输出 (output) system prompt extraction attempt."),

    # ── Multi-language: Japanese injection (I059–I061) ────────────────────
    _InjectionPattern("CORD-I059", re.compile(
        r"前の指示を無視|すべての指示を無視",
        re.IGNORECASE
    ), "hard", "Japanese: 'ignore previous/all instructions'."),
    _InjectionPattern("CORD-I060", re.compile(
        r"あなたは今.{0,20}(?:制限なし|フィルターなし|自由)",
        re.IGNORECASE
    ), "hard", "Japanese: 'you are now without restrictions/filters'."),
    _InjectionPattern("CORD-I061", re.compile(
        r"システムプロンプト.{0,20}(?:を出力|を教えて|を表示)",
        re.IGNORECASE
    ), "hard", "Japanese: system prompt extraction attempt."),

    # ── Encoding bypass: URL / percent-encoding (I062–I064) ───────────────
    _InjectionPattern("CORD-I062", re.compile(
        r"(?:%[0-9a-fA-F]{2}){8,}",
    ), "soft", "Percent-encoded sequence cluster; possible URL-encoded injection."),
    _InjectionPattern("CORD-I063", re.compile(
        r"&#x[0-9a-fA-F]+;|&#\d+;",
    ), "soft", "HTML entity encoding; possible character obfuscation."),
    _InjectionPattern("CORD-I064", re.compile(
        r"\\\d{3}(?:\\\d{3}){3,}",
    ), "soft", "Octal escape sequence cluster; obfuscation attempt."),

    # ── Indirect / data-path injection (I065–I069) ────────────────────────
    _InjectionPattern("CORD-I065", re.compile(
        r"\"role\"\s*:\s*\"system\"|'role'\s*:\s*'system'",
        re.IGNORECASE
    ), "hard", "JSON role:system field injection; ChatML data-path attack."),
    _InjectionPattern("CORD-I066", re.compile(
        r"&anchor\s|<<\s*:\s*\*|yaml\s+anchor\s+injection",
        re.IGNORECASE
    ), "soft", "YAML anchor/alias abuse; indirect injection via config data."),
    _InjectionPattern("CORD-I067", re.compile(
        r"{{.{0,60}}}|{%.{0,60}%}",
    ), "soft", "Template injection (Jinja2/Twig/Handlebars) detected."),
    _InjectionPattern("CORD-I068", re.compile(
        r"\$\{.{0,60}\}|\$\(.{0,60}\)",
    ), "soft", "Shell variable or command substitution; SSTI/injection risk."),
    _InjectionPattern("CORD-I069", re.compile(
        r"(?:--|;)\s*(?:DROP|SELECT|INSERT|UPDATE|DELETE|UNION)\b",
        re.IGNORECASE
    ), "hard", "SQL injection attempt in natural-language payload."),

    # ── Chain-of-thought manipulation (I070–I074) ─────────────────────────
    _InjectionPattern("CORD-I070", re.compile(
        r"\blet.{0,10}think\b.{0,40}\bhow\s+to\s+(?:bypass|jailbreak|evade|circumvent)\b",
        re.IGNORECASE
    ), "hard", "CoT bypass scaffolding: 'let's think how to bypass'."),
    _InjectionPattern("CORD-I071", re.compile(
        r"\bstep\s+\d+\b.{0,40}\bstep\s+\d+\b.{0,40}\bjailbreak\b",
        re.IGNORECASE
    ), "hard", "Step-by-step jailbreak scaffolding."),
    _InjectionPattern("CORD-I072", re.compile(
        r"\bfirst\s*,\s*.{0,40}\bsecond\s*,\s*.{0,40}\bbypass\b",
        re.IGNORECASE
    ), "soft", "Sequential instruction with bypass keyword."),
    _InjectionPattern("CORD-I073", re.compile(
        r"\bchain\s+of\s+thought\b.{0,60}\b(?:bypass|unrestricted|uncensored)\b",
        re.IGNORECASE
    ), "hard", "CoT framing explicitly targeting unrestricted output."),
    _InjectionPattern("CORD-I074", re.compile(
        r"\bif\s+you\s+were\s+(?:a|an)\s+\w+\s+without\s+(?:any\s+)?(?:restrictions?|guidelines?|ethics?)\b",
        re.IGNORECASE
    ), "hard", "Counterfactual persona attack: 'if you were X without restrictions'."),

    # ── Roleplay / persona escalation (I075–I079) ─────────────────────────
    _InjectionPattern("CORD-I075", re.compile(
        r"\bplay\s+(the\s+)?role\s+of\b.{0,40}\b(?:evil|malicious|uncensored|without\s+restrictions?)\b",
        re.IGNORECASE
    ), "hard", "Roleplay instruction targeting uncensored/evil persona."),
    _InjectionPattern("CORD-I076", re.compile(
        r"\bstay\s+in\s+character\b.{0,60}\b(?:never\s+break|always\s+respond)",
        re.IGNORECASE
    ), "soft", "Persistent character-lock with universal response mandate."),
    _InjectionPattern("CORD-I077", re.compile(
        r"\bcharacter\s+(?:named|called)\b.{0,40}\b(?:has\s+no\s+restrictions?|can\s+do\s+anything)\b",
        re.IGNORECASE
    ), "hard", "Named character with no-restrictions framing."),
    _InjectionPattern("CORD-I078", re.compile(
        r"\bAIM\b|\bALEX\b.{0,30}\bunethical\b|\bGOD\s+MODE\b",
        re.IGNORECASE
    ), "hard", "Known jailbreak persona names: AIM, ALEX-unethical, GOD MODE."),
    _InjectionPattern("CORD-I079", re.compile(
        r"\bopposite\s+(day|mode|world)\b.{0,60}\b(?:everything\s+(?:bad|harmful|illegal)\s+is\s+(?:good|allowed))\b",
        re.IGNORECASE
    ), "hard", "Opposite-day framing to invert safety constraints."),

    # ── Token smuggling / invisible chars (I080–I083) ─────────────────────
    _InjectionPattern("CORD-I080", re.compile(
        r"[\u200b\u200c\u200d\uFEFF\u2060]",
    ), "soft", "Zero-width character detected; possible token-smuggling attempt."),
    _InjectionPattern("CORD-I081", re.compile(
        r"[\u0300-\u036f\u0489]{3,}",
    ), "soft", "Combining diacritics cluster; possible homoglyph obfuscation."),
    _InjectionPattern("CORD-I082", re.compile(
        r"[\uE000-\uF8FF]",
    ), "soft", "Private-use Unicode area character; possible steganographic injection."),
    _InjectionPattern("CORD-I083", re.compile(
        r"(?:[\u0430-\u044f\u0391-\u03c9].*?){4,}",
    ), "soft", "Cyrillic/Greek homoglyph cluster; likely Latin word obfuscation."),

    # ── Prompt format confusion (I084–I088) ───────────────────────────────
    _InjectionPattern("CORD-I084", re.compile(
        r"<\|(?:begin|end)_of_text\|>|<\|eot_id\|>",
        re.IGNORECASE
    ), "hard", "Llama-3 special token injection (<|begin_of_text|>, <|eot_id|>)."),
    _InjectionPattern("CORD-I085", re.compile(
        r"</?s>|<\|pad\|>|<\|sep\|>",
        re.IGNORECASE
    ), "soft", "Special separator token injection (</s>, <|sep|>, etc.)."),
    _InjectionPattern("CORD-I086", re.compile(
        r"HUMAN:\s*\n|ASSISTANT:\s*\n|BOT:\s*\n",
        re.IGNORECASE
    ), "hard", "Turn-delimiter injection (HUMAN:/ASSISTANT:/BOT: headers)."),
    _InjectionPattern("CORD-I087", re.compile(
        r"```\s*system\s*\n|```\s*instructions?\s*\n",
        re.IGNORECASE
    ), "hard", "Markdown code-fence role injection (```system, ```instructions)."),
    _InjectionPattern("CORD-I088", re.compile(
        r"\[SYSTEM\]|\[INST\s+\w",
        re.IGNORECASE
    ), "hard", "Square-bracket role token injection ([SYSTEM], [INST ...])."),

    # ── Adversarial goal hijacking (I089–I093) ────────────────────────────
    _InjectionPattern("CORD-I089", re.compile(
        r"\bthe\s+(?:previous|above|prior)\s+(?:message|task|request)\s+(?:was|is)\s+(?:a\s+)?(?:test|trick|joke)\b",
        re.IGNORECASE
    ), "soft", "Legitimacy-undercutting: 'the previous message was a test/trick'."),
    _InjectionPattern("CORD-I090", re.compile(
        r"\byour\s+(?:real|true|actual)\s+purpose\s+(?:is|was)\s+to\b",
        re.IGNORECASE
    ), "hard", "Purpose-reframing: 'your real purpose is to…'."),
    _InjectionPattern("CORD-I091", re.compile(
        r"\bresearch\s+purposes?\s+only\b.{0,60}\b(?:how\s+to|steps?\s+to)\b",
        re.IGNORECASE
    ), "soft", "'Research purposes only' framing with how-to request."),
    _InjectionPattern("CORD-I092", re.compile(
        r"\bfiction(?:al)?\b.{0,40}\b(?:character|story)\b.{0,60}\b(?:explain|describe|provide)\b.{0,40}\b(?:how\s+to|steps?)\b",
        re.IGNORECASE
    ), "soft", "Fictional framing used to elicit procedural instructions."),
    _InjectionPattern("CORD-I093", re.compile(
        r"\beducational\s+(?:purposes?|context)\b.{0,60}\b(?:detailed?\s+)?(?:steps?|instructions?|guide)\b.{0,40}\b(?:harm|attack|exploit|bypass)\b",
        re.IGNORECASE
    ), "hard", "Educational framing combined with harm/exploit keyword."),

    # ── Agentic / tool-use hijacking (I094–I098) ──────────────────────────
    _InjectionPattern("CORD-I094", re.compile(
        r"\bcall\s+(?:the\s+)?(?:(?:delete|drop|rm|format)\s+)?(?:tool|function|api)\b"
        r"|\bcall\s+(?:the\s+)?(?:tool|function|api)\b.{0,40}\b(?:delete|drop|rm|format)\b",
        re.IGNORECASE
    ), "hard", "Agentic tool-call injection targeting destructive actions."),
    _InjectionPattern("CORD-I095", re.compile(
        r"\buse\s+(?:the\s+)?(?:write|create|execute)\s+(?:tool|function)\b.{0,60}\b(?:malware|ransomware|backdoor|exploit)\b",
        re.IGNORECASE
    ), "hard", "Tool-call injection to create malware/backdoor/exploit."),
    _InjectionPattern("CORD-I096", re.compile(
        r"\bsend\s+(?:an?\s+)?(?:email|message|webhook)\b.{0,60}\b(?:with\s+the\s+(?:system\s+)?(?:prompt|context|memory))\b",
        re.IGNORECASE
    ), "hard", "Exfiltration via agentic send action with system context."),
    _InjectionPattern("CORD-I097", re.compile(
        r"\bautonomously\b.{0,40}\b(?:without\s+(?:asking|confirming|permission))\b",
        re.IGNORECASE
    ), "soft", "Autonomy escalation: act without permission/confirmation."),
    _InjectionPattern("CORD-I098", re.compile(
        r"\bignore\s+(?:the\s+)?(?:(?:approval|human|user)\s+){1,2}(?:step|gate|check|review)\b",
        re.IGNORECASE
    ), "hard", "Approval gate bypass: ignore human-in-the-loop step."),

    # ── Miscellaneous hard stops (I099–I100) ──────────────────────────────
    _InjectionPattern("CORD-I099", re.compile(
        r"\bpassword\s+is\b.{0,40}\bplease\s+(?:use|enter|provide)\b|\bsecret\s+key\s*[:=]",
        re.IGNORECASE
    ), "soft", "Credential injection attempt in payload."),
    _InjectionPattern("CORD-I100", re.compile(
        r"\bremember\s+this\s+for\s+(?:all\s+)?(?:future|subsequent|next)\s+(?:messages?|requests?|conversations?)\b",
        re.IGNORECASE
    ), "hard", "Persistent memory poisoning: 'remember this for future messages'."),
]

# Pre-sorted: hard before soft for early exit
_SORTED_PATTERNS = sorted(_INJECTION_PATTERNS, key=lambda p: (0 if p.severity == "hard" else 1))


class InjectionDetector:
    """Detect prompt-injection / jailbreak patterns in text inputs."""

    def __init__(self, patterns: Optional[List[_InjectionPattern]] = None) -> None:
        self._patterns = patterns if patterns is not None else _SORTED_PATTERNS

    def check(self, text: str) -> List[CORDFinding]:
        findings: List[CORDFinding] = []
        for pat in self._patterns:
            m = pat.regex.search(text)
            if m:
                start = max(0, m.start() - 20)
                end = min(len(text), m.end() + 20)
                excerpt = text[start:end].replace("\n", " ")
                if len(excerpt) > 120:
                    excerpt = excerpt[:117] + "…"
                findings.append(CORDFinding(
                    check_type=CORDCheckType.INJECTION,
                    severity=pat.severity,
                    pattern_id=pat.pattern_id,
                    excerpt=excerpt,
                    detail=pat.detail,
                ))
        return findings


# ============================================================================
# 3. Governance Violation Detector (metric-gaming)
# ============================================================================

class GovernanceViolationDetector:
    """
    Detect anomalous FDIA score spikes that indicate metric gaming.

    Agents that consistently report near-perfect scores (D=1.0, I=1.0, A=1.0)
    without variance are likely gaming the metric rather than measuring it.

    Algorithm:
      - Maintain a rolling window of recent FDIA scores per agent.
      - Flag if: mean > 0.92 AND stddev < 0.02 (suspiciously perfect cluster)
      - Flag if: two consecutive scores differ by > 0.35 (implausible jump)
    """

    MEAN_HIGH_THRESHOLD = 0.92
    STDDEV_LOW_THRESHOLD = 0.02
    SPIKE_DELTA_THRESHOLD = 0.35
    WINDOW_MIN = 3              # minimum records before statistical check

    def __init__(self) -> None:
        # agent_id → list of recent F scores
        self._windows: Dict[str, List[float]] = {}

    def record(self, agent_id: str, f_score: float) -> List[CORDFinding]:
        """
        Record an F score for an agent and return any findings.

        Call this after computing computeFDIA() to keep the detector updated.
        """
        findings: List[CORDFinding] = []
        window = self._windows.setdefault(agent_id, [])

        # Spike check: compare with last score
        if window:
            delta = abs(f_score - window[-1])
            if delta > self.SPIKE_DELTA_THRESHOLD:
                findings.append(CORDFinding(
                    check_type=CORDCheckType.METRIC_GAMING,
                    severity="soft",
                    pattern_id="CORD-G001",
                    excerpt=f"agent={agent_id} prev={window[-1]:.3f} current={f_score:.3f}",
                    detail=(
                        f"FDIA score jumped {delta:.3f} in one step "
                        f"(threshold {self.SPIKE_DELTA_THRESHOLD}). "
                        "Possible metric gaming or inconsistent reporting."
                    ),
                ))

        window.append(f_score)
        # Keep last 20 records per agent
        if len(window) > 20:
            window.pop(0)

        # Statistical cluster check (needs at least WINDOW_MIN records)
        if len(window) >= self.WINDOW_MIN:
            mean = statistics.mean(window)
            try:
                std = statistics.stdev(window)
            except statistics.StatisticsError:
                std = 0.0
            if mean >= self.MEAN_HIGH_THRESHOLD and std < self.STDDEV_LOW_THRESHOLD:
                findings.append(CORDFinding(
                    check_type=CORDCheckType.METRIC_GAMING,
                    severity="hard",
                    pattern_id="CORD-G002",
                    excerpt=(
                        f"agent={agent_id} window={len(window)} "
                        f"mean={mean:.3f} stddev={std:.4f}"
                    ),
                    detail=(
                        f"FDIA scores are suspiciously clustered: mean={mean:.3f} "
                        f"(≥{self.MEAN_HIGH_THRESHOLD}) and stddev={std:.4f} "
                        f"(<{self.STDDEV_LOW_THRESHOLD}). Likely metric gaming."
                    ),
                ))

        return findings

    def reset_agent(self, agent_id: str) -> None:
        """Clear the score history for an agent."""
        self._windows.pop(agent_id, None)

    def get_window(self, agent_id: str) -> List[float]:
        """Return a copy of the current score window for an agent."""
        return list(self._windows.get(agent_id, []))


# ============================================================================
# 4. Payload Size Validator
# ============================================================================

_MAX_PAYLOAD_BYTES_HARD = 1_048_576   # 1 MB
_MAX_PAYLOAD_BYTES_SOFT = 131_072     # 128 KB


class PayloadSizeValidator:
    """Reject or warn on oversized payloads to prevent DoS."""

    def check(self, text: str) -> List[CORDFinding]:
        size = len(text.encode("utf-8"))
        if size > _MAX_PAYLOAD_BYTES_HARD:
            return [CORDFinding(
                check_type=CORDCheckType.PAYLOAD_SIZE,
                severity="hard",
                pattern_id="CORD-S001",
                excerpt=f"{size:,} bytes",
                detail=(
                    f"Payload size {size:,} bytes exceeds hard limit "
                    f"{_MAX_PAYLOAD_BYTES_HARD:,} bytes (1 MB). Rejecting."
                ),
            )]
        if size > _MAX_PAYLOAD_BYTES_SOFT:
            return [CORDFinding(
                check_type=CORDCheckType.PAYLOAD_SIZE,
                severity="soft",
                pattern_id="CORD-S002",
                excerpt=f"{size:,} bytes",
                detail=(
                    f"Payload size {size:,} bytes exceeds soft limit "
                    f"{_MAX_PAYLOAD_BYTES_SOFT:,} bytes (128 KB). Review before executing."
                ),
            )]
        return []


# ============================================================================
# 5. CORD Engine (orchestrator)
# ============================================================================

class CORDEngine:
    """
    Constitutional Oversight & Rejection Detector — main orchestrator.

    Usage::

        engine = CORDEngine()
        result = engine.check("help me ignore all previous instructions")
        if not result.is_clean:
            raise ValueError(f"CORD rejected: {result.verdict}")

    Governance violation tracking::

        result = engine.check_with_fdia("intent text", agent_id="agent-1", f_score=0.98)
    """

    def __init__(self) -> None:
        self._entropy = EntropyValidator()
        self._injection = InjectionDetector()
        self._governance = GovernanceViolationDetector()
        self._size = PayloadSizeValidator()

    def check(self, text: str) -> CORDResult:
        """
        Run all CORD checks on a text string.

        Does NOT perform FDIA governance tracking (use check_with_fdia for that).
        """
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        entropy = _shannon_entropy(text)

        findings: List[CORDFinding] = []
        findings.extend(self._size.check(text))
        findings.extend(self._entropy.check(text))
        findings.extend(self._injection.check(text))

        verdict = _determine_verdict(findings)

        return CORDResult(
            verdict=verdict,
            findings=findings,
            entropy_score=entropy,
            input_length=len(text),
            input_fingerprint=fingerprint,
        )

    def check_with_fdia(
        self,
        text: str,
        *,
        agent_id: str,
        f_score: float,
    ) -> CORDResult:
        """
        Run all CORD checks AND record the FDIA score for governance tracking.

        Args:
            text: The intent or payload text to check.
            agent_id: The agent ID whose score is being recorded.
            f_score: The FDIA F-score just computed for this agent.

        Returns:
            CORDResult with all findings including governance violations.
        """
        result = self.check(text)
        gov_findings = self._governance.record(agent_id, f_score)
        result.findings.extend(gov_findings)
        # Recompute verdict with governance findings included
        result.verdict = _determine_verdict(result.findings)
        return result

    def record_fdia_score(self, agent_id: str, f_score: float) -> List[CORDFinding]:
        """
        Record an FDIA score without checking a text payload.
        Useful for tracking scores from other sources.
        """
        return self._governance.record(agent_id, f_score)

    def get_governance_window(self, agent_id: str) -> List[float]:
        """Return the FDIA score history window for an agent."""
        return self._governance.get_window(agent_id)


def _determine_verdict(findings: List[CORDFinding]) -> CORDVerdict:
    """Determine verdict from a list of findings."""
    if any(f.severity == "hard" for f in findings):
        return CORDVerdict.REJECTED
    if any(f.severity == "soft" for f in findings):
        return CORDVerdict.SUSPICIOUS
    return CORDVerdict.CLEAN


# ============================================================================
# Convenience function
# ============================================================================

_default_engine: Optional[CORDEngine] = None


def cord_check(text: str) -> CORDResult:
    """
    Module-level convenience function using a shared CORDEngine instance.

    Example::

        from rct_control_plane.cord_security import cord_check
        result = cord_check(user_input)
        if result.verdict == CORDVerdict.REJECTED:
            raise PermissionError("Input rejected by CORD")
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = CORDEngine()
    return _default_engine.check(text)
