"""
RCT NPC Kernel — Regional Language Adapter (v2.2.0)

Provides language-aware model routing for multi-region deployments:
  - LanguageDetector: auto-detect language from text input
  - RegionalModelRouter: map (language, region, intent) → model_id
  - RegionalModelCache: LRU cache for model selection decisions
  - TenantRegionalConfig: per-tenant regional settings

Implements RFC-001 v2.0 §8-12 (Language-Region Negotiation Extension).

Layer: OS Primitive (depends on syscall, HexaCoreRegistry)
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Language Detection
# ---------------------------------------------------------------------------

class DetectedLanguage:
    """Result of language detection."""
    __slots__ = ("code", "confidence", "script")

    def __init__(self, code: str, confidence: float, script: str = ""):
        self.code = code
        self.confidence = confidence
        self.script = script

    def __repr__(self) -> str:
        return f"DetectedLanguage(code={self.code!r}, confidence={self.confidence:.2f})"


# Unicode block ranges for script detection
_SCRIPT_RANGES: List[Tuple[str, int, int, str]] = [
    # (language_code, codepoint_start, codepoint_end, script_name)
    ("ja", 0x3040, 0x309F, "Hiragana"),
    ("ja", 0x30A0, 0x30FF, "Katakana"),
    ("ja", 0x31F0, 0x31FF, "Katakana Extension"),
    ("zh", 0x4E00, 0x9FFF, "CJK Unified Ideographs"),
    ("zh", 0x3400, 0x4DBF, "CJK Extension A"),
    ("ko", 0xAC00, 0xD7AF, "Hangul Syllables"),
    ("ko", 0x1100, 0x11FF, "Hangul Jamo"),
    ("th", 0x0E00, 0x0E7F, "Thai"),
    ("vi", 0x0300, 0x036F, "Vietnamese Diacriticals"),  # partial — see special handling
    ("id", 0x0000, 0x007F, "Latin"),  # Indonesian uses Latin — needs keyword detection
    ("ar", 0x0600, 0x06FF, "Arabic"),
    ("hi", 0x0900, 0x097F, "Devanagari"),
]

# Vietnamese-specific diacritical chars (common in Vietnamese but rare in other Latin)
_VIETNAMESE_MARKERS = set("àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ")
_VIETNAMESE_MARKERS |= {c.upper() for c in _VIETNAMESE_MARKERS}

# Indonesian common words (for disambiguation from generic Latin)
_INDONESIAN_MARKERS = {
    "dan", "yang", "di", "ini", "itu", "untuk", "dengan", "adalah",
    "pada", "dari", "dalam", "akan", "tidak", "saya", "kami", "mereka",
    "atau", "juga", "ke", "bisa", "sudah", "belum", "ada", "baru",
    "sangat", "hanya", "oleh", "seperti", "antara", "telah", "bahwa",
}


class LanguageDetector:
    """
    Auto-detect language from text input using Unicode script analysis.

    Algorithm:
    1. Count characters per Unicode script range
    2. Apply script-specific heuristics (Japanese = Hiragana+Katakana+CJK, etc.)
    3. Handle CJK disambiguation (Japanese vs Chinese)
    4. Vietnamese detection via diacritical markers
    5. Indonesian detection via keyword frequency
    6. Return language code with confidence score [0.0 .. 1.0]
    """

    def detect(self, text: str) -> DetectedLanguage:
        """Detect primary language of input text."""
        if not text or not text.strip():
            return DetectedLanguage("en", 0.0, "Unknown")

        text = text.strip()
        total_chars = len(text)

        # Count characters per script
        script_counts: Dict[str, int] = {}
        cjk_count = 0
        hiragana_katakana_count = 0
        hangul_count = 0
        thai_count = 0
        vietnamese_count = 0
        latin_count = 0

        for ch in text:
            cp = ord(ch)

            # Skip whitespace/punctuation for script counting
            if ch.isspace() or ch in ".,!?;:()[]{}\"'/-_=+@#$%^&*~`":
                continue

            matched = False
            for lang, start, end, script in _SCRIPT_RANGES:
                if start <= cp <= end:
                    script_counts[lang] = script_counts.get(lang, 0) + 1
                    matched = True
                    if script in ("Hiragana", "Katakana", "Katakana Extension"):
                        hiragana_katakana_count += 1
                    elif script == "CJK Unified Ideographs" or script == "CJK Extension A":
                        cjk_count += 1
                    elif script.startswith("Hangul"):
                        hangul_count += 1
                    elif script == "Thai":
                        thai_count += 1
                    elif script == "Latin":
                        latin_count += 1
                    break

            if not matched:
                # Check Vietnamese diacriticals
                if ch in _VIETNAMESE_MARKERS:
                    vietnamese_count += 1
                    latin_count += 1
                elif 0x0041 <= cp <= 0x007A:  # Basic Latin letters
                    latin_count += 1

        meaningful = max(total_chars - text.count(" "), 1)

        # Decision logic — prioritized
        # 1. Thai script (unambiguous)
        if thai_count > 0 and thai_count / meaningful > 0.3:
            return DetectedLanguage("th", min(thai_count / meaningful + 0.2, 1.0), "Thai")

        # 2. Korean (Hangul is unambiguous)
        if hangul_count > 0 and hangul_count / meaningful > 0.3:
            return DetectedLanguage("ko", min(hangul_count / meaningful + 0.2, 1.0), "Hangul")

        # 3. Japanese vs Chinese disambiguation
        if cjk_count > 0 or hiragana_katakana_count > 0:
            if hiragana_katakana_count > 0:
                # Hiragana/Katakana = definite Japanese
                jp_confidence = min((hiragana_katakana_count + cjk_count) / meaningful + 0.2, 1.0)
                return DetectedLanguage("ja", jp_confidence, "Japanese")
            else:
                # Pure CJK = Chinese (could be Traditional or Simplified)
                zh_confidence = min(cjk_count / meaningful + 0.2, 1.0)
                return DetectedLanguage("zh", zh_confidence, "CJK")

        # 4. Vietnamese (Latin + diacriticals)
        if vietnamese_count > 0 and vietnamese_count / meaningful > 0.1:
            return DetectedLanguage("vi", min(vietnamese_count / meaningful + 0.3, 1.0), "Vietnamese")

        # 5. Indonesian (Latin + keyword frequency)
        if latin_count > 0 and latin_count / meaningful > 0.5:
            words = set(text.lower().split())
            id_matches = len(words & _INDONESIAN_MARKERS)
            if id_matches >= 2:
                return DetectedLanguage("id", min(id_matches / max(len(words), 1) + 0.3, 1.0), "Indonesian")

        # 6. Default to English
        return DetectedLanguage("en", 0.6, "Latin")


# ---------------------------------------------------------------------------
# Regional Model Router
# ---------------------------------------------------------------------------

class RegionalModelNotFound(Exception):
    """Raised when no model can be resolved for a language-region pair."""
    def __init__(self, language: str, region: str):
        self.language = language
        self.region = region
        super().__init__(f"No model found for language={language}, region={region}")


@dataclass
class RegionalModelEntry:
    """One entry in the regional model routing table."""
    language: str           # ISO 639-1 (e.g., "ja")
    region: str             # ISO 3166-1 alpha-2 (e.g., "JP")
    model_id: str           # OpenRouter model ID
    model_name: str         # Human-readable name
    proficiency: float      # Model's proficiency in this language [0.0 .. 1.0]
    cost_input: float       # USD per 1M input tokens
    cost_output: float      # USD per 1M output tokens
    specialties: List[str] = field(default_factory=list)
    compliance_tags: List[str] = field(default_factory=list)  # ["APPI", "PDPA", etc.]


# Default regional model routing table
_REGIONAL_MODELS: List[RegionalModelEntry] = [
    # --- English (US) — default ---
    RegionalModelEntry(
        language="en", region="US",
        model_id="anthropic/claude-opus-4.6",
        model_name="Claude Opus 4.6",
        proficiency=1.0,
        cost_input=5.0, cost_output=25.0,
        specialties=["Architecture", "Complex reasoning"],
    ),
    # --- Thai (TH) ---
    RegionalModelEntry(
        language="th", region="TH",
        model_id="deepseek/deepseek-v3.2",
        model_name="DeepSeek V3.2",
        proficiency=0.92,
        cost_input=0.25, cost_output=0.38,
        specialties=["Thai translation", "Natural language"],
        compliance_tags=["PDPA"],
    ),
    # --- Japanese (JP) ---
    RegionalModelEntry(
        language="ja", region="JP",
        model_id="anthropic/claude-3.5-sonnet",
        model_name="Claude 3.5 Sonnet",
        proficiency=0.95,
        cost_input=3.0, cost_output=15.0,
        specialties=["JLPT-level Japanese", "Technical translation"],
        compliance_tags=["APPI"],
    ),
    # --- Korean (KR) ---
    RegionalModelEntry(
        language="ko", region="KR",
        model_id="openai/gpt-4-turbo",
        model_name="GPT-4 Turbo",
        proficiency=0.88,
        cost_input=10.0, cost_output=30.0,
        specialties=["Hangul optimization", "Korean NLP"],
        compliance_tags=["PIPA"],
    ),
    # --- Chinese Simplified (CN) ---
    RegionalModelEntry(
        language="zh", region="CN",
        model_id="alibaba/qwen-2.5-72b",
        model_name="Qwen 2.5 72B",
        proficiency=0.96,
        cost_input=0.90, cost_output=0.90,
        specialties=["Chinese NLP", "Local deployment"],
        compliance_tags=["PIPL"],
    ),
    # --- Chinese Traditional (TW) ---
    RegionalModelEntry(
        language="zh", region="TW",
        model_id="alibaba/qwen-2.5-72b",
        model_name="Qwen 2.5 72B",
        proficiency=0.93,
        cost_input=0.90, cost_output=0.90,
        specialties=["Traditional Chinese", "Taiwan market"],
    ),
    # --- Vietnamese (VN) ---
    RegionalModelEntry(
        language="vi", region="VN",
        model_id="alibaba/qwen-2.5-7b",
        model_name="Qwen 2.5 7B",
        proficiency=0.82,
        cost_input=0.15, cost_output=0.15,
        specialties=["Vietnamese NLP", "Cost-efficient"],
    ),
    # --- Indonesian (ID) ---
    RegionalModelEntry(
        language="id", region="ID",
        model_id="alibaba/qwen-2.5-7b",
        model_name="Qwen 2.5 7B",
        proficiency=0.80,
        cost_input=0.15, cost_output=0.15,
        specialties=["Bahasa Indonesia", "ASEAN deployment"],
    ),
]


class RegionalModelRouter:
    """
    Maps (language, region, intent) → model_id using the regional routing table.

    Resolution priority:
    1. Exact (language, region) match
    2. Language match (any region)
    3. Preferred model list (from tenant config)
    4. Fallback to English (en/US)
    """

    def __init__(self, models: Optional[List[RegionalModelEntry]] = None):
        self._models = models or list(_REGIONAL_MODELS)
        self._cache = RegionalModelCache(max_size=256)
        self._metrics = RegionalRouterMetrics()

        # Build lookup index: (language, region) → entry
        self._index: Dict[Tuple[str, str], RegionalModelEntry] = {}
        self._lang_index: Dict[str, List[RegionalModelEntry]] = {}
        for entry in self._models:
            self._index[(entry.language, entry.region)] = entry
            if entry.language not in self._lang_index:
                self._lang_index[entry.language] = []
            self._lang_index[entry.language].append(entry)

    def resolve(
        self,
        language: str,
        region: str,
        preferred_models: Optional[List[str]] = None,
        fallback_language: str = "en",
    ) -> RegionalModelEntry:
        """
        Resolve the best model for a language-region pair.

        Args:
            language: ISO 639-1 code (e.g., "ja")
            region: ISO 3166-1 alpha-2 (e.g., "JP")
            preferred_models: Ordered list of model IDs (tenant preference)
            fallback_language: Language to fall back to if no match

        Returns:
            RegionalModelEntry with resolved model

        Raises:
            RegionalModelNotFound if no model can be resolved
        """
        t0 = time.perf_counter_ns()
        self._metrics.total_resolutions += 1

        # Check cache first
        cache_key = f"{language}:{region}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._metrics.cache_hits += 1
            return cached

        # 1. Exact match (language, region)
        entry = self._index.get((language, region))
        if entry:
            self._cache.put(cache_key, entry)
            self._record_latency(t0)
            return entry

        # 2. Language match (any region — pick highest proficiency)
        lang_entries = self._lang_index.get(language, [])
        if lang_entries:
            best = max(lang_entries, key=lambda e: e.proficiency)
            self._cache.put(cache_key, best)
            self._record_latency(t0)
            return best

        # 3. Check preferred models
        if preferred_models:
            for model_id in preferred_models:
                for entry in self._models:
                    if entry.model_id == model_id:
                        self._cache.put(cache_key, entry)
                        self._record_latency(t0)
                        return entry

        # 4. Fallback to fallback_language
        if fallback_language != language:
            fallback_entries = self._lang_index.get(fallback_language, [])
            if fallback_entries:
                best = max(fallback_entries, key=lambda e: e.proficiency)
                self._metrics.fallback_resolutions += 1
                self._cache.put(cache_key, best)
                self._record_latency(t0)
                return best

        self._record_latency(t0)
        raise RegionalModelNotFound(language, region)

    def get_supported_languages(self) -> List[str]:
        """Return list of supported language codes."""
        return sorted(set(e.language for e in self._models))

    def get_supported_regions(self) -> List[str]:
        """Return list of supported region codes."""
        return sorted(set(e.region for e in self._models))

    def get_models_for_language(self, language: str) -> List[RegionalModelEntry]:
        """Get all models supporting a language."""
        return list(self._lang_index.get(language, []))

    def get_compliance_tags(self, region: str) -> List[str]:
        """Get compliance tags required for a region."""
        tags: Set[str] = set()
        for entry in self._models:
            if entry.region == region:
                tags.update(entry.compliance_tags)
        return sorted(tags)

    def add_model(self, entry: RegionalModelEntry) -> None:
        """Register a new regional model."""
        self._models.append(entry)
        self._index[(entry.language, entry.region)] = entry
        if entry.language not in self._lang_index:
            self._lang_index[entry.language] = []
        self._lang_index[entry.language].append(entry)
        self._cache.clear()  # invalidate cache

    def get_metrics(self) -> Dict[str, Any]:
        """Return routing metrics."""
        return {
            "total_resolutions": self._metrics.total_resolutions,
            "cache_hits": self._metrics.cache_hits,
            "fallback_resolutions": self._metrics.fallback_resolutions,
            "cache_hit_rate": (
                self._metrics.cache_hits / max(self._metrics.total_resolutions, 1)
            ),
            "avg_latency_us": (
                self._metrics.total_latency_us / max(self._metrics.total_resolutions, 1)
            ),
            "supported_languages": len(self._lang_index),
            "total_models": len(self._models),
        }

    def _record_latency(self, t0_ns: int) -> None:
        elapsed = (time.perf_counter_ns() - t0_ns) // 1000
        self._metrics.total_latency_us += elapsed


@dataclass
class RegionalRouterMetrics:
    total_resolutions: int = 0
    cache_hits: int = 0
    fallback_resolutions: int = 0
    total_latency_us: int = 0


# ---------------------------------------------------------------------------
# Regional Model Cache (LRU)
# ---------------------------------------------------------------------------

class RegionalModelCache:
    """Simple LRU cache for model resolution results."""

    def __init__(self, max_size: int = 256):
        self._max_size = max_size
        self._cache: OrderedDict[str, RegionalModelEntry] = OrderedDict()

    def get(self, key: str) -> Optional[RegionalModelEntry]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, entry: RegionalModelEntry) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
        self._cache[key] = entry

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# ---------------------------------------------------------------------------
# Tenant Regional Configuration
# ---------------------------------------------------------------------------

@dataclass
class TenantRegionalConfig:
    """
    Per-tenant regional deployment configuration.

    Each tenant (customer deployment) carries regional context that
    influences model selection, compliance requirements, and fallback chains.
    """
    tenant_id: str
    tenant_name: str
    default_language: str = "en"
    default_region: str = "US"
    preferred_models: List[str] = field(default_factory=list)
    fallback_chain: List[str] = field(default_factory=lambda: ["en"])
    data_residency: str = "US"
    compliance_tags: List[str] = field(default_factory=list)
    max_cost_per_1m_tokens: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "default_language": self.default_language,
            "default_region": self.default_region,
            "preferred_models": self.preferred_models,
            "fallback_chain": self.fallback_chain,
            "data_residency": self.data_residency,
            "compliance_tags": self.compliance_tags,
            "max_cost_per_1m_tokens": self.max_cost_per_1m_tokens,
        }


# Pilot customer configurations
PILOT_TENANTS: Dict[str, TenantRegionalConfig] = {
    "jp_techcorp": TenantRegionalConfig(
        tenant_id="jp_techcorp",
        tenant_name="JapaneseTechCorp",
        default_language="ja",
        default_region="JP",
        preferred_models=["anthropic/claude-3.5-sonnet", "openai/gpt-4-turbo"],
        fallback_chain=["ja", "en"],
        data_residency="JP",
        compliance_tags=["APPI"],
        max_cost_per_1m_tokens=20.0,
    ),
    "kr_aicenter": TenantRegionalConfig(
        tenant_id="kr_aicenter",
        tenant_name="KoreanAICenter",
        default_language="ko",
        default_region="KR",
        preferred_models=["openai/gpt-4-turbo"],
        fallback_chain=["ko", "en"],
        data_residency="KR",
        compliance_tags=["PIPA"],
        max_cost_per_1m_tokens=35.0,
    ),
    "cn_enterprise": TenantRegionalConfig(
        tenant_id="cn_enterprise",
        tenant_name="ChinaEnterprise",
        default_language="zh",
        default_region="CN",
        preferred_models=["alibaba/qwen-2.5-72b"],
        fallback_chain=["zh", "en"],
        data_residency="CN",
        compliance_tags=["PIPL"],
        max_cost_per_1m_tokens=5.0,
    ),
    "th_rctlabs": TenantRegionalConfig(
        tenant_id="th_rctlabs",
        tenant_name="RCT Labs Thailand",
        default_language="th",
        default_region="TH",
        preferred_models=["deepseek/deepseek-v3.2"],
        fallback_chain=["th", "en"],
        data_residency="TH",
        compliance_tags=["PDPA"],
        max_cost_per_1m_tokens=10.0,
    ),
    "vn_startup": TenantRegionalConfig(
        tenant_id="vn_startup",
        tenant_name="VietnamStartup",
        default_language="vi",
        default_region="VN",
        preferred_models=["alibaba/qwen-2.5-7b"],
        fallback_chain=["vi", "en"],
        data_residency="VN",
        compliance_tags=[],
        max_cost_per_1m_tokens=2.0,
    ),
    "id_startup": TenantRegionalConfig(
        tenant_id="id_startup",
        tenant_name="IndonesiaAI",
        default_language="id",
        default_region="ID",
        preferred_models=["alibaba/qwen-2.5-7b"],
        fallback_chain=["id", "en"],
        data_residency="ID",
        compliance_tags=[],
        max_cost_per_1m_tokens=2.0,
    ),
}


class TenantRegistry:
    """Registry for managing tenant regional configurations."""

    def __init__(self) -> None:
        self._tenants: Dict[str, TenantRegionalConfig] = dict(PILOT_TENANTS)

    def register(self, config: TenantRegionalConfig) -> None:
        """Register a new tenant."""
        self._tenants[config.tenant_id] = config

    def get(self, tenant_id: str) -> Optional[TenantRegionalConfig]:
        """Get tenant config by ID."""
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> List[TenantRegionalConfig]:
        """List all registered tenants."""
        return list(self._tenants.values())

    def get_tenants_by_region(self, region: str) -> List[TenantRegionalConfig]:
        """Get tenants deployed in a specific region."""
        return [t for t in self._tenants.values() if t.default_region == region]

    def get_tenants_by_language(self, language: str) -> List[TenantRegionalConfig]:
        """Get tenants using a specific default language."""
        return [t for t in self._tenants.values() if t.default_language == language]

    @property
    def size(self) -> int:
        return len(self._tenants)

    def to_summary(self) -> Dict[str, Any]:
        """Summary of all tenants by region."""
        by_region: Dict[str, List[str]] = {}
        for t in self._tenants.values():
            if t.default_region not in by_region:
                by_region[t.default_region] = []
            by_region[t.default_region].append(t.tenant_name)
        return {
            "total_tenants": self.size,
            "by_region": by_region,
        }


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

_DEFAULT_DETECTOR = LanguageDetector()
_DEFAULT_ROUTER = RegionalModelRouter()


def detect_language(text: str) -> DetectedLanguage:
    """Detect language from text using default detector."""
    return _DEFAULT_DETECTOR.detect(text)


def resolve_model_for_text(
    text: str,
    region: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> RegionalModelEntry:
    """
    Convenience: detect language from text and resolve the best model.

    Args:
        text: Input text to analyze
        region: Override region (if None, use default for detected language)
        tenant_id: Tenant ID for preference/compliance overrides
    """
    detected = detect_language(text)
    language = detected.code

    # Get tenant overrides
    preferred_models = []
    if tenant_id:
        tenant = PILOT_TENANTS.get(tenant_id)
        if tenant:
            preferred_models = tenant.preferred_models
            if region is None:
                region = tenant.default_region

    # Default region mapping
    _lang_to_region = {
        "en": "US", "th": "TH", "ja": "JP", "ko": "KR",
        "zh": "CN", "vi": "VN", "id": "ID",
    }
    if region is None:
        region = _lang_to_region.get(language, "US")

    return _DEFAULT_ROUTER.resolve(language, region, preferred_models)


def get_regional_router() -> RegionalModelRouter:
    """Get the default regional model router instance."""
    return _DEFAULT_ROUTER
