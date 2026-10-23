"""
Intent Compiler - Natural Language → Structured Intent

This module compiles natural language descriptions into structured IntentObject
that can be processed by the Control Plane execution graph builder.

Compilation Pipeline:
1. Lexical Analysis: Extract keywords, entities, constraints
2. Intent Classification: Determine IntentType
3. Template Matching: Match to execution template
4. Context Binding: Enrich with user/tier/metadata
5. Validation: Check against intent grammar

Example:
    >>> compiler = IntentCompiler()
    >>> result = compiler.compile(
    ...     "Refactor this module to use clean architecture patterns with max cost $2.50",
    ...     user_id="user123",
    ...     user_tier="PRO"
    ... )
    >>> assert result.intent.intent_type == IntentType.REFACTOR
    >>> assert result.intent.budget.max_cost_usd == Decimal("2.50")
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from rct_control_plane.safe_text import filename_matches, path_matches, token_counts

from .intent_schema import (
    BudgetSpec,
    ConstraintType,
    ContextBundle,
    IntentConstraint,
    IntentGrammar,
    IntentObject,
    IntentPriority,
    IntentType,
    RiskProfile,
    ScopeObject,
    ScopeType,
    ValidationResult,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .observability import ControlPlaneObserver


# ============================================================================
# LLM PROVIDER INTEGRATION (optional — graceful degradation)
# ============================================================================

import os
import json as _json

try:
    import openai as _openai_module  # type: ignore
    _HAS_OPENAI = True
except ImportError:
    _openai_module = None  # type: ignore
    _HAS_OPENAI = False

try:
    import anthropic as _anthropic_module  # type: ignore
    _HAS_ANTHROPIC = True
except ImportError:
    _anthropic_module = None  # type: ignore
    _HAS_ANTHROPIC = False


def _call_llm(prompt: str) -> Optional[Dict[str, Any]]:
    """Call an LLM provider to assist with intent classification.

    Returns a parsed dict from the LLM response, or None on any failure.

    Provider selection order (controlled by RCT_LLM_PROVIDER env var):
      - ``regex``   : Disable LLM, always return None.
      - ``openai``  : Force OpenAI.
      - ``anthropic``: Force Anthropic.
      - ``auto``    : Try OpenAI first, then Anthropic (default).
    """
    provider = os.getenv("RCT_LLM_PROVIDER", "auto").lower()
    if provider == "regex":
        return None

    system_prompt = (
        "You are an intent classifier. Given a user request, output a JSON object with keys: "
        "intent_type, scope_type, priority, risk_profile, max_cost_usd, target. "
        "Return ONLY the JSON object."
    )

    # ---- OpenAI path ----
    use_openai = provider in ("openai", "auto")
    if use_openai and _HAS_OPENAI:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                client = _openai_module.OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=256,
                )
                content = response.choices[0].message.content or ""
                return _json.loads(content) if content else None
            except Exception:
                return None

    # ---- Anthropic path ----
    use_anthropic = provider in ("anthropic", "auto")
    if use_anthropic and _HAS_ANTHROPIC:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            try:
                client = _anthropic_module.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=256,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = message.content[0].text if message.content else ""
                return _json.loads(content) if content else None
            except Exception:
                return None

    return None



# ============================================================================
# LEXICAL TOKENS
# ============================================================================

@dataclass
class Token:
    """Lexical token extracted from natural language"""
    type: str                               # KEYWORD, ENTITY, CONSTRAINT, etc.
    value: str
    position: int
    confidence: float = 1.0


@dataclass
class LexicalResult:
    """Result of lexical analysis"""
    tokens: List[Token] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    entities: Dict[str, List[str]] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# COMPILATION RESULT
# ============================================================================

@dataclass
class CompilationResult:
    """Result of intent compilation"""
    success: bool
    intent: Optional[IntentObject] = None
    validation: Optional[ValidationResult] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    compilation_time_ms: float = 0.0
    
    def add_error(self, message: str) -> None:
        """Add compilation error"""
        self.errors.append(message)
        self.success = False

    def add_warning(self, message: str) -> None:
        """Add compilation warning"""
        self.warnings.append(message)


# ============================================================================
# INTENT COMPILER
# ============================================================================

class IntentCompiler:
    """
    Compiles natural language into structured IntentObject.
    
    This is the entry point for all Control Plane requests.
    """
    
    # Intent type keywords mapping
    # Round 50: English keywords match whole words (with -s/-es/-ed/-d/-ing),
    # Thai keywords match as substrings (Thai has no spaces). Plain substring
    # matching sent "report"/"support" to TRANSFORM ("port", SYSTEMIC risk),
    # "latest" to TEST, "prefix" to DEBUG and "release notes" to DEPLOY; and
    # everyday goals (read, search, summarise, write a file, any Thai goal)
    # matched nothing, so D fell back to 0.3 and the RCT-7 plan was empty.
    INTENT_TYPE_KEYWORDS = {
        IntentType.REFACTOR: ["refactor", "restructure", "reorganize", "clean up", "improve code", "update", "upgrade", "bump", "รีแฟคเตอร์", "จัดโครงสร้าง"],
        IntentType.BUILD_APP: ["build", "create", "scaffold", "generate app", "new application",
                               "write", "writing", "new file", "add a file", "สร้าง", "เขียน"],
        IntentType.ANALYZE_RISK: ["analyze", "analyse", "assess", "evaluate risk", "security check", "audit",
                                  "วิเคราะห์", "ประเมิน"],
        IntentType.DEPLOY: ["deploy", "release to", "cut a release", "ship it", "publish", "launch",
                            "ดีพลอย", "ขึ้นระบบจริง"],
        IntentType.OPTIMIZE: ["optimize", "optimise", "improve performance", "speed up", "reduce cost", "เพิ่มประสิทธิภาพ"],
        IntentType.DOCUMENT: ["document", "generate docs", "write documentation", "เอกสาร"],
        IntentType.STRATEGY: ["plan", "strategize", "roadmap", "design", "architect", "วางแผน"],
        # Destructive verbs classify here so they are never "unclassified":
        # HIGH_RISK_KEYWORDS then makes them SYSTEMIC, the strictest I.
        IntentType.TRANSFORM: ["transform", "convert", "migrate", "port", "translate", "แปลง", "ย้ายระบบ",
                               # irreversible or outward-facing operations
                               "delete", "remove", "drop", "wipe", "truncate", "erase", "destroy", "format",
                               "transfer", "withdraw", "pay", "send", "email", "disable", "shutdown", "kill",
                               "reveal", "leak", "rm -rf", "sudo", "ลบ", "โอน", "จ่ายเงิน", "ส่งอีเมล", "ปิดระบบ"],
        IntentType.DEBUG: ["debug", "fix", "troubleshoot", "diagnose", "find bug", "แก้บั๊ก", "แก้ไข"],
        IntentType.TEST: ["test", "verify", "validate", "check", "generate tests", "ทดสอบ"],
        IntentType.QUERY: ["read", "show", "list", "search", "find", "look up", "lookup", "summarise", "summarize",
                           "summary", "tell me", "what is", "what are", "which", "how many", "describe",
                           "explain", "recall", "remember", "how does", "how do", "why", "who", "where",
                           "อ่าน", "ค้นหา", "สรุป", "แสดง", "บอก", "อธิบาย", "จำได้"],
    }
    
    _STRONG_QUERY_WORDS = frozenset({"explain", "recall", "remember", "why", "how does", "how do", "อธิบาย", "จำได้"})

    # Risk indicators
    HIGH_RISK_KEYWORDS = ["deploy", "delete", "drop", "remove", "migrate", "system-wide",
                          "wipe", "truncate", "erase", "destroy", "format", "transfer", "withdraw", "pay",
                          "send", "email", "disable", "shutdown", "kill", "reveal", "leak", "rm -rf", "sudo",
                          "ลบ", "โอน", "จ่ายเงิน", "ส่งอีเมล", "ปิดระบบ"]
    MEDIUM_RISK_KEYWORDS = ["refactor", "modify", "change", "update", "transform"]
    
    # Priority indicators
    CRITICAL_PRIORITY_KEYWORDS = ["urgent", "critical", "emergency", "asap", "immediately"]
    HIGH_PRIORITY_KEYWORDS = ["important", "soon", "high priority", "quickly"]
    LOW_PRIORITY_KEYWORDS = ["whenever", "eventually", "low priority", "background"]
    
    # Scope indicators
    SCOPE_KEYWORDS = {
        ScopeType.FILE: ["this file", "current file", "file"],
        ScopeType.MODULE: ["this module", "module", "package"],
        ScopeType.REPOSITORY: ["repo", "repository", "entire codebase", "all code"],
        ScopeType.SYSTEM: ["system", "entire system", "infrastructure", "all services"],
        ScopeType.INFRASTRUCTURE: ["infra", "deployment", "kubernetes", "docker"],
    }
    
    def __init__(self, observer: Optional['ControlPlaneObserver'] = None):
        """Initialize compiler with default configuration
        
        Args:
            observer: Optional ControlPlaneObserver for event tracking
        """
        self.version = "1.0.0"
        self.compiled_count = 0
        self.observer = observer
    
    # ========================================================================
    # MAIN COMPILATION PIPELINE
    # ========================================================================
    
    def compile(
        self,
        natural_language: str,
        user_id: str,
        user_tier: str,
        organization_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CompilationResult:
        """
        Compile natural language into IntentObject.
        
        Args:
            natural_language: Natural language description of intent
            user_id: User identifier
            user_tier: User tier (FREE, PRO, ENTERPRISE, INTERNAL)
            organization_id: Optional organization ID
            metadata: Optional additional metadata
            
        Returns:
            CompilationResult with structured intent or errors
        """
        start_time = datetime.utcnow()
        result = CompilationResult(success=True)
        
        # Emit event: INTENT_RECEIVED
        if self.observer:
            from .observability import ControlPlaneEventType
            self.observer.observe_event(
                event_type=ControlPlaneEventType.INTENT_RECEIVED,
                data={"text": natural_language[:200], "user_id": user_id, "user_tier": user_tier},
                actor=user_id
            )
        
        try:
            # 1. Lexical analysis
            lexical = self.lex(natural_language)
            
            # 2. Classify intent type
            intent_type = self._classify_intent_type(lexical)
            if not intent_type:
                result.add_error("Could not determine intent type")
                result.success = False
                # Don't increment counter for failures
            else:
                # 3. Extract scope
                scope = self._extract_scope(lexical, natural_language)
                
                # 4. Extract constraints
                constraints = self._extract_constraints(lexical)
                
                # 5. Extract budget
                budget = self._extract_budget(lexical)
                
                # 6. Determine risk profile
                risk_profile = self._determine_risk_profile(intent_type, lexical)
                
                # 7. Determine priority
                priority = self._determine_priority(lexical)
                
                # 8. Build context
                context = ContextBundle(
                    user_id=user_id,
                    user_tier=user_tier,
                    organization_id=organization_id,
                    metadata=metadata or {}
                )
                
                # 9. Create IntentObject
                intent = IntentObject(
                    goal=natural_language[:500],  # Truncate to max length
                    intent_type=intent_type,
                    scope=scope,
                    constraints=constraints,
                    context=context,
                    priority=priority,
                    risk_profile=risk_profile,
                    budget=budget,
                    natural_language_input=natural_language,
                    compiler_version=self.version
                )
                
                # 10. Validate
                validation = IntentGrammar.validate(intent)
                
                # 11. Set result
                result.intent = intent
                result.validation = validation
                result.success = validation.is_valid
                result.errors.extend(validation.errors)
                result.warnings.extend(validation.warnings)
            
        except Exception as e:
            result.add_error(f"Compilation failed: {str(e)}")
        
        finally:
            end_time = datetime.utcnow()
            result.compilation_time_ms = (end_time - start_time).total_seconds() * 1000
            # Track all compilations (success or failure)
            if result.success:
                self.compiled_count += 1
            
            # Emit event: INTENT_COMPILED
            if self.observer:
                from .observability import ControlPlaneEventType
                intent_type_value = None
                if result.intent and hasattr(result.intent, 'intent_type'):
                    intent_type_value = result.intent.intent_type.value if hasattr(result.intent.intent_type, 'value') else str(result.intent.intent_type)
                self.observer.observe_event(
                    event_type=ControlPlaneEventType.INTENT_COMPILED,
                    intent_id=str(result.intent.id) if result.intent else None,
                    data={
                        "intent_type": intent_type_value,
                        "validation_valid": result.validation.is_valid if result.validation else False,
                        "errors": result.errors,
                        "warnings": result.warnings
                    },
                    duration_ms=result.compilation_time_ms,
                    success=result.success,
                    error_message="; ".join(result.errors) if result.errors else None,
                    actor=user_id
                )
        
        return result
    
    # ========================================================================
    # LEXICAL ANALYSIS
    # ========================================================================
    
    def lex(self, text: str) -> LexicalResult:
        """
        Perform lexical analysis on natural language text.
        
        Extracts:
        - Keywords (action verbs, modifiers)
        - Entities (files, modules, services)
        - Constraints (cost, time, quality)
        - Metadata (context clues)
        """
        result = LexicalResult()
        text_lower = text.lower()
        
        # Extract keywords
        result.keywords = self._extract_keywords(text_lower)
        result.metadata["head"], result.metadata["later_action"] = self._head_kind(text_lower)
        result.metadata["head_word"] = self._head_word(text_lower)

        # Extract entities
        result.entities = self._extract_entities(text, text_lower)
        
        # Extract constraints
        result.constraints = self._extract_constraint_values(text_lower)
        
        return result
    
    @staticmethod
    def _has_keyword(text: str, keyword: str) -> bool:
        """Whole-word match for English keywords (allowing -s/-es/-ed/-d/-ing),
        substring match for Thai (written without spaces between words)."""
        if not keyword.isascii():
            return keyword in text
        pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?:s|es|ed|d|ing)?(?![a-z0-9])"
        return re.search(pattern, text) is not None

    # Round 91 (research/intent_risk_criteria_r91.md): the verbs below name a change. Their bare form ("update the file") and their -ing form ("updating the file") ask for one; the other forms
    # ("what changed", "the files that were updated", "the recent changes") usually DESCRIBE one that already happened, unless an action word stands just in front ("make the changes",
    # "apply the updates", "commit these changes"). A description is not a request, so it must not make a read-only goal STRUCTURAL.
    _CHANGE_VERBS = frozenset({"update", "change", "modify", "refactor", "upgrade", "bump", "transform"})
    _ACTION_WORDS = frozenset({"make", "makes", "apply", "applies", "commit", "push", "save", "implement", "perform", "do", "please", "want", "need", "should", "must", "go", "let's", "lets",
                               "write", "run", "release", "ship", "deploy", "merge", "revert", "undo"})

    @classmethod
    def _keyword_is_requested(cls, text: str, keyword: str) -> bool:
        """True when `keyword` occurs in a form that asks for the change. Only the change verbs get this treatment; every other keyword is matched as before."""
        if not keyword.isascii() or keyword not in cls._CHANGE_VERBS:
            return True
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(keyword) + r"(s|es|ed|d|ing)?(?![a-z0-9])", text):
            suffix = m.group(1) or ""
            if suffix in ("", "ing"):
                return True
            before = re.findall(r"[a-z']+", text[:m.start()])[-4:]
            if any(word in cls._ACTION_WORDS for word in before):
                return True
        return False

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract action keywords from text"""
        keywords = []
        
        for _intent_type, type_keywords in self.INTENT_TYPE_KEYWORDS.items():
            for keyword in type_keywords:
                if self._has_keyword(text, keyword) and self._keyword_is_requested(text, keyword):
                    keywords.append(keyword)
        
        # Add risk keywords
        for keyword in self.HIGH_RISK_KEYWORDS + self.MEDIUM_RISK_KEYWORDS:
            if self._has_keyword(text, keyword) and self._keyword_is_requested(text, keyword):
                keywords.append(keyword)
        
        # Add priority keywords
        for keyword in self.CRITICAL_PRIORITY_KEYWORDS + self.HIGH_PRIORITY_KEYWORDS + self.LOW_PRIORITY_KEYWORDS:
            if self._has_keyword(text, keyword):
                keywords.append(keyword)
        
        return keywords
    
    def _extract_entities(self, text: str, text_lower: str) -> Dict[str, List[Any]]:
        """Extract named entities (files, modules, services)"""
        entities: Dict[str, List[Any]] = {
            "files": [],
            "modules": [],
            "services": [],
            "paths": []
        }
        
        # File patterns: *.py, *.js, *.ts, specific filenames
        entities["files"] = filename_matches(text_lower)
        
        # Path patterns
        entities["paths"] = path_matches(text_lower)
        
        # Module patterns (Python/JS-style)
        if "module" in text_lower:
            # Extract quoted strings after "module"
            module_pattern = r'module[:\s]+["\']?([a-z_][a-z0-9_.]*)["\']?'
            entities["modules"] = re.findall(module_pattern, text_lower)
        
        return entities
    
    def _extract_constraint_values(self, text: str) -> Dict[str, Any]:
        """Extract constraint values from text"""
        constraints: Dict[str, Any] = {}
        
        # Cost constraints: $X.XX, $X, X dollars
        cost_patterns = [
            r'\$(\d+(?:\.\d{1,2})?)',           # $2.50
            r'(\d+(?:\.\d{1,2})?)\s*dollars?',  # 2.50 dollars
            r'(\d+(?:\.\d{1,2})?)\s*usd',       # 2.50 USD
        ]
        for pattern in cost_patterns:
            matches = re.findall(pattern, text)
            if matches:
                constraints["max_cost"] = Decimal(matches[0])
                break
        
        # Time constraints: X minutes, X hours, X days
        time_patterns = [
            (r'(\d+)\s*minutes?', lambda m: timedelta(minutes=int(m))),
            (r'(\d+)\s*hours?', lambda m: timedelta(hours=int(m))),
            (r'(\d+)\s*days?', lambda m: timedelta(days=int(m))),
        ]
        for pattern, converter in time_patterns:
            matches = re.findall(pattern, text)
            if matches:
                constraints["max_time"] = converter(matches[0])
                break
        
        # Token limits
        token_matches = token_counts(text)
        if token_matches:
            constraints["max_tokens"] = int(token_matches[0])
        
        return constraints
    
    # ========================================================================
    # CLASSIFICATION & EXTRACTION
    # ========================================================================
    
    # Round 91 (research/unknown_intent_criteria_r91.md, rule set H): the VERB THAT HEADS THE SENTENCE decides whether a goal asks for a change or asks a question; keywords later in the sentence do
    # not ("Edit the README so it lists the new command" is not a query because it contains "list", "What did the last deploy change?" is not a deployment). Fixed lists, English only.
    _POLITE_LEAD = re.compile(r"^(?:please\s+|kindly\s+|go ahead and\s+|can you\s+|could you\s+|would you\s+|i want you to\s+|i need you to\s+|i'd like you to\s+|let's\s+|lets\s+)+")
    _ACTION_HEADS = frozenset({
        "set", "edit", "rename", "add", "replace", "delete", "remove", "restart", "commit", "push", "merge", "increase", "raise", "decrease", "lower", "reduce", "install", "uninstall",
        "run", "execute", "move", "copy", "send", "email", "write", "create", "update", "change", "modify", "disable", "enable", "kill", "stop", "start", "reset", "overwrite", "format",
        "revert", "rollback", "tag", "publish", "archive", "append", "upgrade", "downgrade", "patch", "apply", "drop", "wipe", "truncate", "erase", "destroy", "transfer",
        "withdraw", "pay", "deploy", "release", "ship", "migrate", "refactor", "rewrite", "clean", "purge", "restore", "backup", "build", "generate", "save", "store", "put", "insert",
        "schedule", "cancel", "approve", "reject", "sign", "grant", "revoke", "rotate", "import", "export", "upload", "download", "sync", "trigger", "close", "lock", "unlock",
    })
    _READ_HEADS = frozenset({
        "what", "whats", "when", "where", "who", "whom", "whose", "why", "how", "which", "is", "are", "was", "were", "does", "do", "did", "will", "has", "have", "show", "tell",
        "list", "find", "count", "check", "compare", "explain", "describe", "summarise", "summarize", "read", "look", "estimate", "search", "display", "view", "calculate",
        "compute", "measure", "give", "see",
    })
    _LATER_CLAUSE = re.compile(r"(?:[,;?!.]|\band\b|\bthen\b)\s+(?:(?:and|then|please)\s+)*([a-z']+)")

    # Verbs that make something new (no existing target is needed): an action with one of these heads and no other type word is a BUILD_APP, not a REFACTOR of something that must already exist.
    _CREATE_HEADS = frozenset({"create", "write", "save", "store", "put", "generate", "build", "insert"})

    # Round 92 (research/independent_goals_criteria_r92.md): the same rule for Thai. Thai has no spaces, so the head is found by prefix after the polite lead, longest word first. The lists were built from
    # development set A (goals written by qwen2.5:7b) and my own knowledge of Thai; the holdout set B (written by qwen3:8b, roles swapped) is run once. A question is also recognised by its closing
    # words (คืออะไร, ไหม, หรือไม่ ...) when no action verb heads the sentence.
    _THAI_LEAD = re.compile(r"^(?:\s|คุณช่วย|ช่วยกรุณา|กรุณา|โปรด|ช่วย|ขอให้|ผมอยากให้|ฉันอยากให้|ดิฉันอยากให้|ผมอยาก|ฉันอยาก|อยากให้|อยาก|ต้องการให้|ผมต้องการ|ฉันต้องการ|ต้องการ|รบกวน|ลอง|ให้)+")
    _THAI_ACTION_HEADS = tuple(sorted({
        "แก้ไข", "แก้", "เปลี่ยนชื่อ", "เปลี่ยนแปลง", "เปลี่ยน", "ย้าย", "ลบทิ้ง", "ลบ", "สร้าง", "เขียน", "เพิ่ม", "ส่งออก", "ส่ง", "รัน", "เรียกใช้", "ติดตั้ง", "ถอนการติดตั้ง", "ตั้งเวลา", "ตั้งค่า",
        "ตั้งชื่อ", "ตั้ง", "คัดลอก", "ก๊อป", "บันทึก", "อัปเดต", "อัพเดต", "อัปเกรด", "อัพเกรด", "ปรับปรุง", "ปรับเปลี่ยน", "ปรับ", "ปิด", "เปิด", "หยุด", "เริ่ม", "ยกเลิก", "อนุมัติ", "ปฏิเสธ", "ดีพลอย",
        "คอมมิต", "พุช", "รีเซ็ต", "รีสตาร์ท", "แทนที่", "อัปโหลด", "อัพโหลด", "ดาวน์โหลด", "สำรองข้อมูล", "สำรอง", "กู้คืน", "ผสาน", "นำเข้า", "ลงนาม", "ล้าง", "จัดเรียง", "แปลง", "ทำให้", "สั่ง", "จอง",
        "ชำระ", "จ่าย", "โอน", "แชร์", "เผยแพร่", "โพสต์", "แนบ", "ใส่", "เติม", "ลง", "เก็บ", "ตั้งให้", "รวมไฟล์", "ปรับแต่ง", "ทำการ", "ลบออก", "เอา", "นำ", "ใช้คำสั่ง", "ประมวลผล",
    }, key=len, reverse=True))
    _THAI_CREATE_HEADS = ("สร้าง", "เขียน", "เพิ่ม", "บันทึก", "เก็บ", "เติม", "ใส่", "แนบ")
    _THAI_READ_HEADS = tuple(sorted({
        "ช่วยอธิบาย", "อธิบาย", "สรุป", "ค้นหา", "ค้น", "หา", "ดู", "แสดง", "บอก", "เปรียบเทียบ", "ตรวจสอบ", "ตรวจ", "อ่าน", "นับ", "คำนวณ", "ประเมิน", "วิเคราะห์", "ระบุ", "แนะนำ", "ตอบ", "เล่า",
        "ยกตัวอย่าง", "ขอคำแนะนำ", "ขอข้อมูล", "ขอคำอธิบาย", "ขอความช่วยเหลือ", "ขอดู", "ขอรายละเอียด", "ขอสรุป", "ขอตัวอย่าง", "รายการ", "ลิสต์", "อะไร", "ทำไม", "อย่างไร", "ยังไง", "ใคร", "ที่ไหน",
        "เมื่อไร", "เมื่อไหร่", "กี่", "เท่าไร", "เท่าไหร่", "มีอะไร", "มี", "คือ", "สามารถ", "อยากรู้", "อยากทราบ", "สงสัย", "ทราบ",
    }, key=len, reverse=True))
    _THAI_QUESTION_END = re.compile(r"(?:คืออะไร|อะไรบ้าง|อะไร|ทำไม|อย่างไร|ยังไง|ไหม|หรือไม่|หรือเปล่า|เท่าไร|เท่าไหร่|กี่|ใคร|ที่ไหน|เมื่อไร|เมื่อไหร่|ได้หรือไม่|\?)")
    _THAI_LATER_ACTION = re.compile(r"(?:แล้วก็|แล้ว|จากนั้น|ต่อด้วย|และ|พร้อมทั้ง|พร้อมกับ)(?:ช่วย|ก็|ให้|ต่อ)?(" + "|".join(re.escape(w) for w in _THAI_ACTION_HEADS) + r")")

    @classmethod
    def _thai_head_kind(cls, text: str) -> "tuple[Optional[str], bool, str]":
        """('action' | 'read' | None, a later clause starts with an action verb, the head verb) for a goal that starts in Thai."""
        body = cls._THAI_LEAD.sub("", text.strip(), count=1)
        head_word = ""
        kind: Optional[str] = None
        for w in cls._THAI_ACTION_HEADS:
            if body.startswith(w):
                kind, head_word = "action", w
                break
        if kind is None:
            for w in cls._THAI_READ_HEADS:
                if body.startswith(w):
                    kind, head_word = "read", w
                    break
        if kind is None and cls._THAI_QUESTION_END.search(body):
            kind = "read"
        later = bool(cls._THAI_LATER_ACTION.search(body[len(head_word):] if head_word else body))
        return kind, later, head_word

    @classmethod
    def _head_word(cls, text: str) -> str:
        stripped = text.strip()
        if re.match(r"[฀-๿]", cls._THAI_LEAD.sub("", stripped, count=1)[:1] or " "):
            _kind, _later, word = cls._thai_head_kind(stripped)
            return "create" if word in cls._THAI_CREATE_HEADS else word
        m = re.match(r"[a-z']+", cls._POLITE_LEAD.sub("", stripped, count=1))
        return m.group(0) if m else ""

    @classmethod
    def _head_kind(cls, text: str) -> "tuple[Optional[str], bool]":
        """('action' | 'read' | None, whether a LATER clause starts with a state-changing verb) for a goal in lower case. English: the verb that heads the sentence. Thai: see _thai_head_kind. Other text has no head and is left to the keyword lists."""
        if re.match(r"[฀-๿]", cls._THAI_LEAD.sub("", text.strip(), count=1)[:1] or " "):
            kind, later, _word = cls._thai_head_kind(text)
            return kind, later
        head_text = cls._POLITE_LEAD.sub("", text.strip(), count=1)
        m = re.match(r"[a-z']+", head_text)
        if not m:
            return None, False
        word = m.group(0)
        later = any(w in cls._ACTION_HEADS for w in cls._LATER_CLAUSE.findall(head_text[m.end():]))
        if word in cls._ACTION_HEADS:
            return "action", later
        if word in cls._READ_HEADS:
            return "read", later
        return None, later

    def _classify_intent_type(self, lexical: LexicalResult) -> Optional[IntentType]:
        """Classify intent type based on keywords"""
        head = lexical.metadata.get("head")
        later = bool(lexical.metadata.get("later_action"))
        scores = {}

        for intent_type, type_keywords in self.INTENT_TYPE_KEYWORDS.items():
            score = 0
            for keyword in type_keywords:
                if keyword in lexical.keywords:
                    # Question words are a strong signal that the user wants an answer,
                    # not a job ("Explain how the audit chain works" is not an audit).
                    score += 2 if (intent_type == IntentType.QUERY and keyword in self._STRONG_QUERY_WORDS) else 1
            if score > 0:
                scores[intent_type] = score
        
        if head == "action":
            # the sentence asks for a change: a query word later in it does not turn it into a question; with no other type keyword it is a change to something that exists
            non_query = {t: s for t, s in scores.items() if t != IntentType.QUERY}
            if non_query:
                return max(non_query, key=lambda k: non_query[k])
            return IntentType.BUILD_APP if lexical.metadata.get("head_word") in self._CREATE_HEADS else IntentType.REFACTOR
        if head == "read" and not later and not any(kw in lexical.keywords for kw in self.HIGH_RISK_KEYWORDS):
            return IntentType.QUERY                         # a question that merely mentions a verb ("what did the last release change?") stays a question; a high-risk word keeps the old reading

        if not scores:
            return IntentType.REFACTOR if later else None     # a question followed by a request for a change, and no other type word: it asks for a change

        # Return type with highest score
        return max(scores, key=lambda k: scores[k])
    
    def _extract_scope(self, lexical: LexicalResult, full_text: str) -> ScopeObject:
        """Extract scope from lexical analysis"""
        # Determine scope type
        scope_type = ScopeType.MODULE  # Default
        
        for stype, keywords in self.SCOPE_KEYWORDS.items():
            if any(kw in lexical.keywords or self._has_keyword(full_text.lower(), kw) for kw in keywords):
                scope_type = stype
                break
        
        # Extract target from entities
        target = "."  # Default to current directory
        if lexical.entities["files"]:
            target = lexical.entities["files"][0][0]
        elif lexical.entities["paths"]:
            target = lexical.entities["paths"][0]
        elif lexical.entities["modules"]:
            target = lexical.entities["modules"][0]
        
        return ScopeObject(
            scope_type=scope_type,
            target=target
        )
    
    def _extract_constraints(self, lexical: LexicalResult) -> List[IntentConstraint]:
        """Convert extracted constraints to IntentConstraint objects"""
        constraints = []
        
        if "max_cost" in lexical.constraints:
            constraints.append(IntentConstraint(
                constraint_type=ConstraintType.COST,
                value=float(lexical.constraints["max_cost"]),
                operator="LTE",
                strict=True,
                reason="User-specified cost limit"
            ))
        
        if "max_time" in lexical.constraints:
            constraints.append(IntentConstraint(
                constraint_type=ConstraintType.TIME,
                value=lexical.constraints["max_time"].total_seconds(),
                operator="LTE",
                strict=True,
                reason="User-specified time limit"
            ))
        
        return constraints
    
    def _extract_budget(self, lexical: LexicalResult) -> BudgetSpec:
        """Extract budget specification"""
        budget = BudgetSpec()
        
        if "max_cost" in lexical.constraints:
            budget.max_cost_usd = lexical.constraints["max_cost"]
        
        if "max_time" in lexical.constraints:
            budget.max_time = lexical.constraints["max_time"]
        
        if "max_tokens" in lexical.constraints:
            budget.max_tokens = lexical.constraints["max_tokens"]
        
        return budget
    
    def _determine_risk_profile(self, intent_type: IntentType, lexical: LexicalResult) -> RiskProfile:
        """Determine risk profile based on intent type and keywords"""
        # Check for high-risk keywords
        if any(kw in lexical.keywords for kw in self.HIGH_RISK_KEYWORDS):
            return RiskProfile.SYSTEMIC

        head = lexical.metadata.get("head")
        later = bool(lexical.metadata.get("later_action"))
        if head == "read" and not later and intent_type == IntentType.QUERY:
            return RiskProfile.LOW                       # Round 91: a plain question (no high-risk word, nothing asked for later in the sentence)
        # a goal that asks for a change is never below STRUCTURAL, whatever its type keywords say
        floor = RiskProfile.STRUCTURAL if (head == "action" or later) else RiskProfile.LOW

        # Check for medium-risk keywords
        if any(kw in lexical.keywords for kw in self.MEDIUM_RISK_KEYWORDS):
            return RiskProfile.STRUCTURAL

        # Intent type-based risk
        high_risk_types = [IntentType.DEPLOY, IntentType.TRANSFORM]
        medium_risk_types = [IntentType.REFACTOR, IntentType.OPTIMIZE, IntentType.BUILD_APP]

        if intent_type in high_risk_types:
            return RiskProfile.SYSTEMIC
        elif intent_type in medium_risk_types:
            return RiskProfile.STRUCTURAL
        else:
            return floor
    
    def _determine_priority(self, lexical: LexicalResult) -> IntentPriority:
        """Determine priority based on keywords"""
        if any(kw in lexical.keywords for kw in self.CRITICAL_PRIORITY_KEYWORDS):
            return IntentPriority.CRITICAL
        elif any(kw in lexical.keywords for kw in self.HIGH_PRIORITY_KEYWORDS):
            return IntentPriority.HIGH
        elif any(kw in lexical.keywords for kw in self.LOW_PRIORITY_KEYWORDS):
            return IntentPriority.LOW
        else:
            return IntentPriority.MEDIUM
    
    # ========================================================================
    # CONTEXT BINDING
    # ========================================================================
    
    def bind_context(
        self,
        intent: IntentObject,
        additional_context: Dict[str, Any]
    ) -> IntentObject:
        """
        Enrich intent with additional execution context.
        
        This can be used to add runtime context after initial compilation.
        """
        intent.context.metadata.update(additional_context)
        return intent
    
    # ========================================================================
    # TEMPLATE SUGGESTION
    # ========================================================================
    
    def suggest_template(self, intent: IntentObject) -> str:
        """
        Suggest execution template based on intent characteristics.
        
        Returns template name that can be used by template library.
        """
        template_map = {
            IntentType.REFACTOR: "refactor_template",
            IntentType.BUILD_APP: "build_app_template",
            IntentType.ANALYZE_RISK: "analyze_risk_template",
            IntentType.DEPLOY: "deploy_template",
            IntentType.OPTIMIZE: "optimize_template",
            IntentType.DOCUMENT: "document_template",
            IntentType.STRATEGY: "strategy_template",
            IntentType.TRANSFORM: "transform_template",
        }
        
        return template_map.get(intent.intent_type, "generic_template")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def quick_compile(
    text: str,
    user_id: str = "default_user",
    user_tier: str = "FREE"
) -> CompilationResult:
    """Quick compilation for testing/prototyping"""
    compiler = IntentCompiler()
    return compiler.compile(text, user_id, user_tier)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "IntentCompiler",
    "CompilationResult",
    "LexicalResult",
    "Token",
    "quick_compile",
]
