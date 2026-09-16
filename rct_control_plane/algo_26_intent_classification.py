"""
ALGO-26: Intent Classification (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/intent-classification/
app/ on 2026-09-16, following the same strip-the-FastAPI-keep-the-engine
pattern used for ALGO-13/ALGO-18/ALGO-30 (see those modules' own
docstrings). ALGO-26 = Intent Classification (the docstring already in
algorithm_kernel_41.py and the real microservice on disk — not "Intent
Conservation" from the master architecture doc, which nothing implements;
this naming was confirmed by the Architect before this port started).

Real dependency chain merged into one file (6 source files, all
self-contained real logic — no external services, no LLM calls):
    - app/core/intent_classifier.py  -> IntentClassifier (main entry point)
    - app/models/intents.py          -> IntentCategory, IntentDefinition,
                                         BUILTIN_INTENTS + catalog helpers
    - app/models/schemas.py          -> Entity, IntentScore,
                                         ClassificationResponse (Pydantic)
    - app/nlp/preprocessor.py        -> TextPreprocessor
    - app/nlp/pattern_matcher.py     -> PatternMatcher
    - app/core/entity_extractor.py   -> EntityExtractor
    - app/core/context_manager.py    -> ContextManager, SessionContext

No FastAPI/HTTP route code lived in any of these six files (routes.py /
main.py / api/integration.py were separate and are not ported). Relative
imports (`from ..models.intents import ...` etc.) are dropped entirely —
everything now lives in one module, so cross-references are direct
in-file references instead.

Schemas ported (app/models/schemas.py): Entity, IntentScore,
ClassificationResponse — the three Pydantic models actually consumed by
IntentClassifier. schemas.py is genuinely built on `pydantic.BaseModel`
(not dataclasses) for these — e.g. `IntentScore.confidence` uses
`Field(..., ge=0.0, le=1.0)` for real range validation — so they are kept
as Pydantic BaseModel here, matching ALGO-30's precedent of keeping real
internal-validation Pydantic models. HTTP-only request/response wrapper
schemas from the source (ClassificationRequest, EntityExtractionRequest/
Response, BatchClassificationRequest/Response, Context, ContextSetRequest/
Response, ContextGetResponse, IntentDefinitionRequest/Response,
IntentAddResponse, IntentListResponse, IntentStatistics,
StatisticsResponse, HealthResponse, ServiceInfoResponse) were dropped as
out of scope for a non-HTTP port — IntentClassifier.classify_batch()
itself returns `List[ClassificationResponse]` in the source, not a
BatchClassificationResponse wrapper, so nothing engine-relevant is lost.
IntentDefinition (app/models/intents.py) is a plain `@dataclass` in the
source, not a Pydantic model, and is kept as a dataclass here. Likewise
SessionContext (app/core/context_manager.py) is kept as a dataclass.

Real logic ported as-is:
    - PatternMatcher: real compiled-regex matching per intent (any-pattern
      -> 1.0, multi-language patterns e.g. English + Thai per intent) plus
      real keyword-overlap scoring and real sentence-structure feature
      detection (is_question / starts_with_wh / has_imperative / has_modal
      / has_negation) via regex.
    - TextPreprocessor: real contraction expansion, tokenization (keeps
      alphanumeric + Thai Unicode range \\u0E00-\\u0E7F), stop-word removal,
      n-gram generation, phrase extraction.
    - EntityExtractor: real regex-based entity extraction (email, phone,
      url, number, money, date, time) plus heuristic location/person/
      object extraction from capitalization + keyword proximity, plus a
      real keyword-count sentiment classifier (extract_sentiment).
    - ContextManager: real session-based conversation context with TTL
      expiry (checked and pruned on every get_context() call) and
      cleanup_expired().
    - IntentClassifier._score_intent(): the real weighted-combination
      scoring formula — pattern matching 40%, keyword matching 30%,
      context relevance 20% (0.5 if the previous intent in this session is
      in the candidate intent's related_intents), sentence-structure 10%
      (question structures favor question/help intents, imperatives favor
      ACTION-category intents, modals favor QUERY-category intents).
    - IntentClassifier.get_statistics(): `accuracy_rate` is honestly
      "Simplified" (== rounded avg_confidence, per the source's own
      comment — not a real accuracy metric, since there is no ground
      truth to compare against at runtime) and `avg_processing_time` is a
      real measured running average in milliseconds
      (total_processing_time / total_classifications * 1000), the fix the
      source's own comment documents as having replaced an earlier
      hardcoded "45ms" placeholder on 2026-09-14 — preserved here as a
      real measurement, not reintroduced as a placeholder.

Entry point: ``IntentClassifier.classify(text: str, context:
Optional[Dict] = None, min_confidence: float = 0.5) ->
ClassificationResponse`` (see bottom of this file for a real smoke test
that exercises it end to end with distinct question/command/statement
inputs).

Usage::

    from rct_control_plane.algo_26_intent_classification import IntentClassifier

    clf = IntentClassifier()
    result = clf.classify("What time does the museum open?")
    print(result.primary_intent, result.intents[0].confidence)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ============================================================================
# Schemas (ported from app/models/schemas.py — engine-relevant subset only)
# ============================================================================

class Entity(BaseModel):
    """Extracted entity"""
    entity: str = Field(..., description="Entity text")
    type: str = Field(..., description="Entity type")
    value: Any = Field(..., description="Entity value")
    start: Optional[int] = Field(None, description="Start position in text")
    end: Optional[int] = Field(None, description="End position in text")
    confidence: Optional[float] = Field(None, description="Extraction confidence")


class IntentScore(BaseModel):
    """Intent with confidence score"""
    intent: str = Field(..., description="Intent name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    category: str = Field(..., description="Intent category")


class ClassificationResponse(BaseModel):
    """Response from intent classification"""
    text: str
    primary_intent: str = Field(..., description="Primary intent detected")
    intents: List[IntentScore] = Field(..., description="All detected intents with scores")
    entities: List[Entity] = Field(default_factory=list, description="Extracted entities")
    context_used: bool = Field(False, description="Whether context was used")
    clarification_needed: bool = Field(False, description="Whether clarification is needed")
    suggested_prompts: Optional[List[str]] = Field(
        None,
        description="Suggested clarifying prompts (from ALGO-18)"
    )
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")


# ============================================================================
# Intent catalog (ported from app/models/intents.py)
# ============================================================================

class IntentCategory(str, Enum):
    """Intent categories"""
    QUERY = "query"
    ACTION = "action"
    INFORMATION = "information"
    TRANSACTION = "transaction"
    SOCIAL = "social"


@dataclass
class IntentDefinition:
    """Intent definition with examples and patterns"""
    intent: str
    category: IntentCategory
    description: str
    examples: List[str]
    patterns: List[str]  # Regex patterns
    keywords: List[str]
    related_intents: List[str]
    entities: List[str]  # Expected entity types


# Built-in intent catalog
BUILTIN_INTENTS: Dict[str, IntentDefinition] = {
    # Social intents
    "greeting": IntentDefinition(
        intent="greeting",
        category=IntentCategory.SOCIAL,
        description="User greeting or saying hello",
        examples=["Hello", "Hi there", "Good morning", "Hey", "สวัสดี"],
        patterns=[
            r"\b(hello|hi|hey|greetings?|good\s+(morning|afternoon|evening))\b",
            r"\bสวัสดี\b"
        ],
        keywords=["hello", "hi", "hey", "greetings", "morning", "สวัสดี"],
        related_intents=["help"],
        entities=[]
    ),

    "farewell": IntentDefinition(
        intent="farewell",
        category=IntentCategory.SOCIAL,
        description="User saying goodbye",
        examples=["Goodbye", "See you later", "Bye", "Take care", "ลาก่อน"],
        patterns=[
            r"\b(goodbye|bye|see\s+you|farewell|take\s+care)\b",
            r"\bลาก่อน\b"
        ],
        keywords=["goodbye", "bye", "see you", "farewell", "ลาก่อน"],
        related_intents=["thanks"],
        entities=[]
    ),

    "thanks": IntentDefinition(
        intent="thanks",
        category=IntentCategory.SOCIAL,
        description="User expressing gratitude",
        examples=["Thank you", "Thanks", "Appreciate it", "Thanks a lot", "ขอบคุณ"],
        patterns=[
            r"\b(thank(s| you)?|appreciate)\b",
            r"\bขอบคุณ\b"
        ],
        keywords=["thank", "thanks", "appreciate", "ขอบคุณ"],
        related_intents=["farewell"],
        entities=[]
    ),

    "help": IntentDefinition(
        intent="help",
        category=IntentCategory.SOCIAL,
        description="User requesting help or assistance",
        examples=["I need help", "Can you assist me", "Help me with this", "I don't understand", "ช่วยหน่อย"],
        patterns=[
            r"\b(help|assist|support|don't\s+understand)\b",
            r"\bช่วย\b"
        ],
        keywords=["help", "assist", "support", "ช่วย"],
        related_intents=["question"],
        entities=[]
    ),

    # Query intents
    "search": IntentDefinition(
        intent="search",
        category=IntentCategory.QUERY,
        description="User wants to find or search for something",
        examples=["Find a restaurant", "Search for hotels", "Look for nearby parks", "Show me Italian restaurants", "หาร้านอาหาร"],
        patterns=[
            r"\b(find|search|look\s+for|show\s+me|locate)\b",
            r"\bหา\b"
        ],
        keywords=["find", "search", "look", "show", "locate", "หา"],
        related_intents=["recommendation", "question"],
        entities=["location", "object", "criteria"]
    ),

    "question": IntentDefinition(
        intent="question",
        category=IntentCategory.QUERY,
        description="User asking a question",
        examples=["What is this?", "Why did that happen?", "How does it work?", "When will it be ready?", "Where is the station?"],
        patterns=[
            r"\b(what|why|how|when|where|who|which)\b.*\?",
            r"^(what|why|how|when|where|who|which)\b"
        ],
        keywords=["what", "why", "how", "when", "where", "who", "which"],
        related_intents=["help", "search"],
        entities=["object", "location", "time", "person"]
    ),

    "recommendation": IntentDefinition(
        intent="recommendation",
        category=IntentCategory.QUERY,
        description="User asking for recommendations or suggestions",
        examples=["Can you recommend a good hotel?", "What do you suggest?", "Any recommendations?", "What's the best option?", "แนะนำหน่อย"],
        patterns=[
            r"\b(recommend|suggest|advise|best|good)\b",
            r"\bแนะนำ\b"
        ],
        keywords=["recommend", "suggest", "advise", "best", "แนะนำ"],
        related_intents=["search", "comparison"],
        entities=["object", "criteria"]
    ),

    "comparison": IntentDefinition(
        intent="comparison",
        category=IntentCategory.QUERY,
        description="User comparing options",
        examples=["What's the difference between A and B?", "Compare these two options", "Which one is better?", "A vs B", "เปรียบเทียบ"],
        patterns=[
            r"\b(compare|comparison|difference|vs|versus|better|worse)\b",
            r"\bเปรียบเทียบ\b"
        ],
        keywords=["compare", "difference", "vs", "versus", "better", "เปรียบเทียบ"],
        related_intents=["recommendation", "question"],
        entities=["object"]
    ),

    # Action intents
    "create": IntentDefinition(
        intent="create",
        category=IntentCategory.ACTION,
        description="User wants to create something",
        examples=["Create a new account", "Make a reservation", "Build a report", "Generate a document", "สร้าง"],
        patterns=[
            r"\b(create|make|build|generate|new)\b",
            r"\bสร้าง\b"
        ],
        keywords=["create", "make", "build", "generate", "new", "สร้าง"],
        related_intents=["booking"],
        entities=["object"]
    ),

    "update": IntentDefinition(
        intent="update",
        category=IntentCategory.ACTION,
        description="User wants to modify or update something",
        examples=["Update my profile", "Modify the settings", "Change my password", "Edit the document", "แก้ไข"],
        patterns=[
            r"\b(update|modify|change|edit|alter)\b",
            r"\bแก้ไข\b"
        ],
        keywords=["update", "modify", "change", "edit", "แก้ไข"],
        related_intents=["create"],
        entities=["object"]
    ),

    "delete": IntentDefinition(
        intent="delete",
        category=IntentCategory.ACTION,
        description="User wants to remove or delete something",
        examples=["Delete my account", "Remove this item", "Erase the data", "Cancel the order", "ลบ"],
        patterns=[
            r"\b(delete|remove|erase|cancel)\b",
            r"\bลบ\b"
        ],
        keywords=["delete", "remove", "erase", "cancel", "ลบ"],
        related_intents=["cancellation"],
        entities=["object"]
    ),

    "read": IntentDefinition(
        intent="read",
        category=IntentCategory.ACTION,
        description="User wants to view or get information",
        examples=["Show me the details", "Display the results", "View my orders", "Get the report", "ดู"],
        patterns=[
            r"\b(show|display|view|get|see)\b",
            r"\bดู\b"
        ],
        keywords=["show", "display", "view", "get", "see", "ดู"],
        related_intents=["search", "question"],
        entities=["object"]
    ),

    # Information intents
    "weather": IntentDefinition(
        intent="weather",
        category=IntentCategory.INFORMATION,
        description="User asking about weather",
        examples=["What's the weather like?", "Will it rain today?", "Temperature forecast", "Weather in Bangkok", "อากาศวันนี้"],
        patterns=[
            r"\b(weather|temperature|forecast|rain|sunny|cloud)\b",
            r"\bอากาศ\b"
        ],
        keywords=["weather", "temperature", "forecast", "rain", "อากาศ"],
        related_intents=["question"],
        entities=["location", "time", "date"]
    ),

    "time": IntentDefinition(
        intent="time",
        category=IntentCategory.INFORMATION,
        description="User asking about time or date",
        examples=["What time is it?", "What's the date today?", "When is the meeting?", "Schedule for tomorrow", "เวลา"],
        patterns=[
            r"\b(time|date|clock|schedule|when)\b",
            r"\bเวลา\b"
        ],
        keywords=["time", "date", "clock", "schedule", "when", "เวลา"],
        related_intents=["question"],
        entities=["time", "date"]
    ),

    "location": IntentDefinition(
        intent="location",
        category=IntentCategory.INFORMATION,
        description="User asking about location or directions",
        examples=["Where is the station?", "How do I get to the mall?", "Location of the office", "Address of the restaurant", "ที่ไหน"],
        patterns=[
            r"\b(where|location|address|direction|map)\b",
            r"\bที่ไหน\b"
        ],
        keywords=["where", "location", "address", "direction", "ที่ไหน"],
        related_intents=["question", "search"],
        entities=["location", "place"]
    ),

    "definition": IntentDefinition(
        intent="definition",
        category=IntentCategory.INFORMATION,
        description="User asking for definition or meaning",
        examples=["What is AI?", "Define machine learning", "What does this mean?", "Explain quantum computing", "คืออะไร"],
        patterns=[
            r"\b(what\s+is|define|definition|meaning|explain)\b",
            r"\bคืออะไร\b"
        ],
        keywords=["what is", "define", "definition", "meaning", "explain", "คืออะไร"],
        related_intents=["question", "help"],
        entities=["object", "concept"]
    ),

    # Transaction intents
    "purchase": IntentDefinition(
        intent="purchase",
        category=IntentCategory.TRANSACTION,
        description="User wants to buy or purchase something",
        examples=["I want to buy this", "Purchase a ticket", "Order food", "Buy now", "ซื้อ"],
        patterns=[
            r"\b(buy|purchase|order|checkout)\b",
            r"\bซื้อ\b"
        ],
        keywords=["buy", "purchase", "order", "checkout", "ซื้อ"],
        related_intents=["payment"],
        entities=["object", "money", "number"]
    ),

    "payment": IntentDefinition(
        intent="payment",
        category=IntentCategory.TRANSACTION,
        description="User wants to make a payment",
        examples=["I want to pay", "Process payment", "Pay the bill", "Invoice payment", "จ่ายเงิน"],
        patterns=[
            r"\b(pay|payment|bill|invoice|charge)\b",
            r"\bจ่ายเงิน\b"
        ],
        keywords=["pay", "payment", "bill", "invoice", "จ่ายเงิน"],
        related_intents=["purchase"],
        entities=["money", "object"]
    ),

    "booking": IntentDefinition(
        intent="booking",
        category=IntentCategory.TRANSACTION,
        description="User wants to make a booking or reservation",
        examples=["Book a table", "Reserve a room", "Make an appointment", "Schedule a meeting", "จอง"],
        patterns=[
            r"\b(book|reserve|appointment|schedule)\b",
            r"\bจอง\b"
        ],
        keywords=["book", "reserve", "appointment", "schedule", "จอง"],
        related_intents=["create", "purchase"],
        entities=["object", "date", "time", "number"]
    ),

    "cancellation": IntentDefinition(
        intent="cancellation",
        category=IntentCategory.TRANSACTION,
        description="User wants to cancel something",
        examples=["Cancel my order", "I want a refund", "Abort the transaction", "Cancel reservation", "ยกเลิก"],
        patterns=[
            r"\b(cancel|refund|abort)\b",
            r"\bยกเลิก\b"
        ],
        keywords=["cancel", "refund", "abort", "ยกเลิก"],
        related_intents=["delete"],
        entities=["object"]
    ),
}


def get_intent_definition(intent: str) -> Optional[IntentDefinition]:
    """Get intent definition by name"""
    return BUILTIN_INTENTS.get(intent)


def get_all_intents() -> List[str]:
    """Get all intent names"""
    return list(BUILTIN_INTENTS.keys())


def get_intents_by_category(category: IntentCategory) -> List[str]:
    """Get all intents in a category"""
    return [
        intent
        for intent, defn in BUILTIN_INTENTS.items()
        if defn.category == category
    ]


def add_custom_intent(definition: IntentDefinition) -> None:
    """Add a custom intent definition"""
    BUILTIN_INTENTS[definition.intent] = definition


def remove_intent(intent: str) -> bool:
    """Remove an intent definition"""
    if intent in BUILTIN_INTENTS:
        del BUILTIN_INTENTS[intent]
        return True
    return False


# ============================================================================
# NLP - text preprocessing (ported from app/nlp/preprocessor.py)
# ============================================================================

class TextPreprocessor:
    """Text preprocessing for intent classification"""

    def __init__(self):
        # Common contractions
        self.contractions = {
            "won't": "will not",
            "can't": "cannot",
            "n't": " not",
            "'re": " are",
            "'ve": " have",
            "'ll": " will",
            "'d": " would",
            "'m": " am",
        }

        # Stop words (common words with little meaning)
        self.stop_words = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "up", "about",
            "into", "through", "during", "before", "after", "above",
            "below", "between", "under", "again", "further", "then",
            "once"
        }

    def normalize(self, text: str) -> str:
        """
        Normalize text:
        - Lowercase
        - Expand contractions
        - Remove extra whitespace
        """
        text = text.lower()

        for contraction, expansion in self.contractions.items():
            text = text.replace(contraction, expansion)

        text = " ".join(text.split())

        return text

    def tokenize(self, text: str) -> List[str]:
        """Simple word tokenization"""
        # Keep alphanumeric and Thai characters
        text = re.sub(r'[^\w\s฀-๿]', ' ', text)
        return text.split()

    def remove_stop_words(self, tokens: List[str]) -> List[str]:
        """Remove common stop words"""
        return [token for token in tokens if token not in self.stop_words]

    def preprocess(self, text: str, remove_stops: bool = False) -> List[str]:
        """
        Full preprocessing pipeline

        Args:
            text: Input text
            remove_stops: Whether to remove stop words

        Returns:
            List of processed tokens
        """
        normalized = self.normalize(text)
        tokens = self.tokenize(normalized)

        if remove_stops:
            tokens = self.remove_stop_words(tokens)

        return tokens

    def get_ngrams(self, tokens: List[str], n: int = 2) -> List[str]:
        """Generate n-grams from tokens"""
        ngrams = []
        for i in range(len(tokens) - n + 1):
            ngram = " ".join(tokens[i:i + n])
            ngrams.append(ngram)
        return ngrams

    def extract_phrases(self, text: str) -> List[str]:
        """Extract common phrases"""
        patterns = [
            r'\b(how\s+to\s+\w+)',
            r'\b(what\s+is\s+\w+)',
            r'\b(where\s+is\s+\w+)',
            r'\b(when\s+\w+)',
            r'\b(why\s+\w+)',
        ]

        phrases = []
        for pattern in patterns:
            matches = re.findall(pattern, text.lower())
            phrases.extend(matches)

        return phrases


# ============================================================================
# NLP - pattern matching (ported from app/nlp/pattern_matcher.py)
# ============================================================================

class PatternMatcher:
    """Pattern-based intent matching"""

    def __init__(self):
        self.compiled_patterns: Dict[str, List[re.Pattern]] = {}

    def add_patterns(self, intent: str, patterns: List[str]):
        """
        Add regex patterns for an intent

        Args:
            intent: Intent name
            patterns: List of regex pattern strings
        """
        if intent not in self.compiled_patterns:
            self.compiled_patterns[intent] = []

        for pattern in patterns:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                self.compiled_patterns[intent].append(compiled)
            except re.error:
                # Invalid regex, skip
                continue

    def match(self, text: str, intent: str) -> float:
        """
        Match text against intent patterns

        Args:
            text: Text to match
            intent: Intent to check

        Returns:
            Match score (0.0 - 1.0)
        """
        if intent not in self.compiled_patterns:
            return 0.0

        patterns = self.compiled_patterns[intent]
        if not patterns:
            return 0.0

        # If ANY pattern matches, return 1.0 (strong match)
        # This is better for multi-language patterns where only one language is used
        for pattern in patterns:
            if pattern.search(text):
                return 1.0

        return 0.0

    def match_all(self, text: str) -> List[Tuple[str, float]]:
        """
        Match text against all intents

        Args:
            text: Text to match

        Returns:
            List of (intent, score) tuples, sorted by score
        """
        results = []

        for intent in self.compiled_patterns:
            score = self.match(text, intent)
            if score > 0:
                results.append((intent, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def check_keywords(self, text: str, keywords: List[str]) -> float:
        """
        Check keyword presence in text

        Args:
            text: Text to check
            keywords: List of keywords

        Returns:
            Keyword score (0.0 - 1.0)
        """
        if not keywords:
            return 0.0

        text_lower = text.lower()
        matches = sum(1 for keyword in keywords if keyword.lower() in text_lower)

        return matches / len(keywords)

    def check_structure(self, text: str) -> Dict[str, bool]:
        """
        Check sentence structure features

        Returns:
            Dictionary of structure features
        """
        return {
            "is_question": bool(re.search(r'\?$', text)),
            "starts_with_wh": bool(re.search(r'^\s*(what|why|how|when|where|who|which)\b', text, re.IGNORECASE)),
            "has_imperative": bool(re.search(r'^\s*(show|find|get|give|tell|help|please)\b', text, re.IGNORECASE)),
            "has_modal": bool(re.search(r'\b(can|could|would|should|may|might|will)\b', text, re.IGNORECASE)),
            "has_negation": bool(re.search(r'\b(not|no|never|nothing|nowhere|none)\b', text, re.IGNORECASE)),
        }


# ============================================================================
# Entity extraction (ported from app/core/entity_extractor.py)
# ============================================================================

class EntityExtractor:
    """Extract entities from text"""

    def __init__(self):
        # Entity patterns
        self.patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b\d{3}[-.]?\d{4}\b',  # Simplified pattern like 555-1234
            "url": r'https?://[^\s]+',
            "number": r'\b\d+\b',
            "money": r'\$\s?\d+(?:,\d{3})*(?:\.\d{2})?|\d+(?:,\d{3})*(?:\.\d{2})?\s?(?:dollars?|baht|USD|THB)',
            "date": r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\b',
            "time": r'\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\s?[APap][Mm])?\b',
        }

        # Common location keywords
        self.location_keywords = {
            "in", "at", "to", "from", "near", "nearby",
            "downtown", "uptown", "city", "town", "village",
            "airport", "station", "mall", "center", "square"
        }

        # Common person indicators
        self.person_indicators = {
            "mr", "mrs", "ms", "dr", "prof", "sir", "madam"
        }

    def extract(self, text: str, entity_types: Optional[List[str]] = None) -> List[Entity]:
        """
        Extract entities from text

        Args:
            text: Text to extract from
            entity_types: Specific types to extract (None = all)

        Returns:
            List of extracted entities
        """
        entities = []

        # Extract pattern-based entities
        for entity_type, pattern in self.patterns.items():
            if entity_types is None or entity_type in entity_types:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entities.append(Entity(
                        entity=match.group(),
                        type=entity_type,
                        value=self._parse_value(entity_type, match.group()),
                        start=match.start(),
                        end=match.end(),
                        confidence=0.9
                    ))

        # Extract location entities
        if entity_types is None or "location" in entity_types:
            locations = self._extract_locations(text)
            entities.extend(locations)

        # Extract person entities
        if entity_types is None or "person" in entity_types:
            persons = self._extract_persons(text)
            entities.extend(persons)

        # Extract object entities
        if entity_types is None or "object" in entity_types:
            objects = self._extract_objects(text)
            entities.extend(objects)

        return entities

    def _parse_value(self, entity_type: str, text: str) -> Any:
        """Parse entity value based on type"""
        if entity_type == "number":
            try:
                return int(text)
            except ValueError:
                return float(text)
        elif entity_type == "money":
            numeric = re.sub(r'[^\d.]', '', text)
            try:
                return float(numeric)
            except ValueError:
                return text
        elif entity_type == "date":
            # Simple date parsing
            return text  # Would use dateutil.parser in production
        else:
            return text

    def _extract_locations(self, text: str) -> List[Entity]:
        """Extract location entities"""
        entities = []

        words = text.split()
        for i, word in enumerate(words):
            if word.lower() in self.location_keywords:
                if i + 1 < len(words) and words[i + 1][0].isupper():
                    location = words[i + 1]
                    if i + 2 < len(words) and words[i + 2][0].isupper():
                        location += " " + words[i + 2]

                    entities.append(Entity(
                        entity=location,
                        type="location",
                        value=location,
                        confidence=0.7
                    ))

        return entities

    def _extract_persons(self, text: str) -> List[Entity]:
        """Extract person entities"""
        entities = []

        words = text.split()
        for i, word in enumerate(words):
            if word.lower().rstrip('.') in self.person_indicators:
                if i + 1 < len(words) and words[i + 1][0].isupper():
                    name = words[i + 1]
                    if i + 2 < len(words) and words[i + 2][0].isupper():
                        name += " " + words[i + 2]

                    entities.append(Entity(
                        entity=name,
                        type="person",
                        value=name,
                        confidence=0.75
                    ))

        return entities

    def _extract_objects(self, text: str) -> List[Entity]:
        """Extract object/thing entities"""
        entities = []

        # Simple noun phrase extraction: "a/an/the + adjective? + noun"
        pattern = r'\b(?:a|an|the)\s+(?:\w+\s+)*(\w+)\b'
        matches = re.finditer(pattern, text, re.IGNORECASE)

        for match in matches:
            obj = match.group(1)
            if obj.lower() not in {'thing', 'one', 'way', 'time', 'day'}:
                entities.append(Entity(
                    entity=obj,
                    type="object",
                    value=obj,
                    confidence=0.6
                ))

        return entities

    def extract_sentiment(self, text: str) -> str:
        """
        Extract sentiment from text

        Returns:
            "positive", "negative", or "neutral"
        """
        positive_words = {
            'good', 'great', 'excellent', 'amazing', 'wonderful',
            'fantastic', 'love', 'like', 'best', 'awesome'
        }
        negative_words = {
            'bad', 'terrible', 'awful', 'hate', 'worst',
            'horrible', 'poor', 'disappointing', 'useless'
        }

        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        else:
            return "neutral"


# ============================================================================
# Context management (ported from app/core/context_manager.py)
# ============================================================================

@dataclass
class SessionContext:
    """Session context information"""
    session_id: str
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=1))


class ContextManager:
    """Manage conversation context"""

    def __init__(self, default_ttl: int = 3600):
        """
        Initialize context manager

        Args:
            default_ttl: Default time-to-live in seconds
        """
        self.default_ttl = default_ttl
        self.contexts: Dict[str, SessionContext] = {}

    def set_context(self, session_id: str, context: Dict[str, Any], ttl: Optional[int] = None) -> SessionContext:
        """
        Set context for a session

        Args:
            session_id: Session identifier
            context: Context data
            ttl: Time to live in seconds

        Returns:
            SessionContext object
        """
        if ttl is None:
            ttl = self.default_ttl

        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl)

        session_context = SessionContext(
            session_id=session_id,
            context=context,
            created_at=now,
            last_used=now,
            expires_at=expires_at
        )

        self.contexts[session_id] = session_context
        return session_context

    def get_context(self, session_id: str) -> Optional[SessionContext]:
        """
        Get context for a session

        Args:
            session_id: Session identifier

        Returns:
            SessionContext if found and not expired, None otherwise
        """
        if session_id not in self.contexts:
            return None

        session_context = self.contexts[session_id]

        if datetime.now() > session_context.expires_at:
            del self.contexts[session_id]
            return None

        session_context.last_used = datetime.now()
        return session_context

    def update_context(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update context for a session

        Args:
            session_id: Session identifier
            updates: Context updates

        Returns:
            True if updated, False if session not found
        """
        session_context = self.get_context(session_id)
        if not session_context:
            return False

        session_context.context.update(updates)
        session_context.last_used = datetime.now()
        return True

    def delete_context(self, session_id: str) -> bool:
        """
        Delete context for a session

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False if not found
        """
        if session_id in self.contexts:
            del self.contexts[session_id]
            return True
        return False

    def cleanup_expired(self):
        """Remove expired contexts"""
        now = datetime.now()
        expired_sessions = [
            session_id
            for session_id, context in self.contexts.items()
            if now > context.expires_at
        ]

        for session_id in expired_sessions:
            del self.contexts[session_id]

    def get_all_sessions(self) -> List[str]:
        """Get all active session IDs"""
        self.cleanup_expired()
        return list(self.contexts.keys())

    def get_context_value(self, session_id: str, key: str, default: Any = None) -> Any:
        """
        Get a specific value from context

        Args:
            session_id: Session identifier
            key: Context key
            default: Default value if not found

        Returns:
            Context value or default
        """
        session_context = self.get_context(session_id)
        if not session_context:
            return default

        return session_context.context.get(key, default)


# ============================================================================
# IntentClassifier - main engine (ported from app/core/intent_classifier.py)
# ============================================================================

class IntentClassifier:
    """Main intent classification engine"""

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        use_context: bool = True
    ):
        """
        Initialize intent classifier

        Args:
            confidence_threshold: Minimum confidence for intent
            use_context: Whether to use context for classification
        """
        self.confidence_threshold = confidence_threshold
        self.use_context = use_context

        # Initialize components
        self.preprocessor = TextPreprocessor()
        self.pattern_matcher = PatternMatcher()
        self.entity_extractor = EntityExtractor()
        self.context_manager = ContextManager()

        # Load built-in intents
        self._load_intents()

        # Statistics
        self.stats = {
            "total_classifications": 0,
            "total_confidence": 0.0,
            "total_processing_time": 0.0,
            "intent_counts": {}
        }

    def _load_intents(self):
        """Load intent patterns into pattern matcher"""
        for intent_name, intent_def in BUILTIN_INTENTS.items():
            self.pattern_matcher.add_patterns(intent_name, intent_def.patterns)

    def classify(
        self,
        text: str,
        context: Optional[Dict] = None,
        min_confidence: float = 0.5
    ) -> ClassificationResponse:
        """
        Classify intent from text

        Args:
            text: Text to classify
            context: Context information
            min_confidence: Minimum confidence threshold

        Returns:
            ClassificationResponse with detected intents
        """
        start_time = time.time()

        # Preprocess text
        tokens = self.preprocessor.preprocess(text, remove_stops=False)
        text_normalized = " ".join(tokens)

        # Get context if session_id provided
        context_used = False
        if context and "session_id" in context:
            session_context = self.context_manager.get_context(context["session_id"])
            if session_context:
                context.update(session_context.context)
                context_used = True

        # Calculate intent scores
        intent_scores = self._calculate_intent_scores(text, text_normalized, tokens, context)

        # Filter by confidence
        intent_scores = [
            score for score in intent_scores
            if score.confidence >= min_confidence
        ]

        # Sort by confidence
        intent_scores.sort(key=lambda x: x.confidence, reverse=True)

        # Get primary intent
        primary_intent = intent_scores[0].intent if intent_scores else "unknown"

        # Extract entities
        entities = self.entity_extractor.extract(text)

        # Update context if session provided
        if context and "session_id" in context:
            self.context_manager.update_context(
                context["session_id"],
                {"previous_intent": primary_intent}
            )

        processing_time = time.time() - start_time

        # Update statistics (after processing_time is known, so
        # get_statistics() can report a real measured average instead of a
        # hardcoded placeholder)
        self._update_stats(
            primary_intent,
            intent_scores[0].confidence if intent_scores else 0.0,
            processing_time,
        )

        # Check if clarification needed
        clarification_needed = (
            not intent_scores or
            intent_scores[0].confidence < 0.7
        )

        return ClassificationResponse(
            text=text,
            primary_intent=primary_intent,
            intents=intent_scores,
            entities=entities,
            context_used=context_used,
            clarification_needed=clarification_needed,
            suggested_prompts=None,  # Set by ALGO-18 integration
            processing_time=processing_time
        )

    def _calculate_intent_scores(
        self,
        original_text: str,
        normalized_text: str,
        tokens: List[str],
        context: Optional[Dict]
    ) -> List[IntentScore]:
        """
        Calculate scores for all intents

        Args:
            original_text: Original input text
            normalized_text: Normalized text
            tokens: Tokenized text
            context: Context information

        Returns:
            List of IntentScore objects
        """
        scores = []

        for intent_name, intent_def in BUILTIN_INTENTS.items():
            score = self._score_intent(
                original_text,
                normalized_text,
                tokens,
                intent_def,
                context
            )

            if score > 0:
                scores.append(IntentScore(
                    intent=intent_name,
                    confidence=score,
                    category=intent_def.category.value
                ))

        return scores

    def _score_intent(
        self,
        original_text: str,
        normalized_text: str,
        tokens: List[str],
        intent_def: IntentDefinition,
        context: Optional[Dict]
    ) -> float:
        """
        Calculate score for a single intent

        Scoring components:
        - Pattern matching (40%)
        - Keyword matching (30%)
        - Context relevance (20%)
        - Structure features (10%)

        Args:
            original_text: Original text
            normalized_text: Normalized text
            tokens: Tokenized text
            intent_def: Intent definition
            context: Context information

        Returns:
            Confidence score (0.0 - 1.0)
        """
        # Pattern matching score
        pattern_score = self.pattern_matcher.match(original_text, intent_def.intent)

        # Keyword matching score
        keyword_score = self.pattern_matcher.check_keywords(normalized_text, intent_def.keywords)

        # Context score
        context_score = 0.0
        if context and "previous_intent" in context:
            prev_intent = context["previous_intent"]
            if prev_intent in intent_def.related_intents:
                context_score = 0.5

        # Structure features score
        structure_features = self.pattern_matcher.check_structure(original_text)
        structure_score = self._calculate_structure_score(structure_features, intent_def)

        # Weighted combination
        total_score = (
            pattern_score * 0.4 +
            keyword_score * 0.3 +
            context_score * 0.2 +
            structure_score * 0.1
        )

        return min(total_score, 1.0)

    def _calculate_structure_score(
        self,
        features: Dict[str, bool],
        intent_def: IntentDefinition
    ) -> float:
        """Calculate score based on sentence structure"""
        score = 0.0

        # Question intents favor question structures
        if intent_def.intent in {"question", "help"}:
            if features["is_question"] or features["starts_with_wh"]:
                score += 0.5

        # Action intents favor imperatives
        if intent_def.category == IntentCategory.ACTION:
            if features["has_imperative"]:
                score += 0.5

        # Query intents favor modals
        if intent_def.category == IntentCategory.QUERY:
            if features["has_modal"]:
                score += 0.3

        return min(score, 1.0)

    def classify_batch(
        self,
        texts: List[str],
        min_confidence: float = 0.5
    ) -> List[ClassificationResponse]:
        """
        Classify multiple texts

        Args:
            texts: List of texts to classify
            min_confidence: Minimum confidence threshold

        Returns:
            List of classification responses
        """
        return [
            self.classify(text, min_confidence=min_confidence)
            for text in texts
        ]

    def add_custom_intent(self, intent_def: IntentDefinition):
        """Add a custom intent definition"""
        BUILTIN_INTENTS[intent_def.intent] = intent_def
        self.pattern_matcher.add_patterns(intent_def.intent, intent_def.patterns)
        self.stats["intent_counts"][intent_def.intent] = 0

    def get_intent_definition(self, intent: str) -> Optional[IntentDefinition]:
        """Get intent definition by name"""
        return get_intent_definition(intent)

    def get_all_intents(self) -> List[str]:
        """Get all intent names"""
        return get_all_intents()

    def get_intents_by_category(self, category: IntentCategory) -> List[str]:
        """Get all intents in a category"""
        return [
            intent
            for intent, defn in BUILTIN_INTENTS.items()
            if defn.category == category
        ]

    def _update_stats(self, intent: str, confidence: float, processing_time: float = 0.0):
        """Update classification statistics"""
        self.stats["total_classifications"] += 1
        self.stats["total_confidence"] += confidence
        self.stats["total_processing_time"] += processing_time

        if intent not in self.stats["intent_counts"]:
            self.stats["intent_counts"][intent] = 0
        self.stats["intent_counts"][intent] += 1

    def get_statistics(self) -> Dict:
        """Get classification statistics"""
        total = self.stats["total_classifications"]

        if total == 0:
            avg_confidence = 0.0
            avg_processing_time_ms = 0.0
        else:
            avg_confidence = self.stats["total_confidence"] / total
            avg_processing_time_ms = (self.stats["total_processing_time"] / total) * 1000

        # Most common intents
        most_common = sorted(
            self.stats["intent_counts"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return {
            "total_classifications": total,
            "average_confidence": round(avg_confidence, 3),
            "most_common_intents": [
                {"intent": intent, "count": count}
                for intent, count in most_common
            ],
            "accuracy_rate": round(avg_confidence, 2),  # Simplified
            "avg_processing_time": f"{avg_processing_time_ms:.1f}ms"  # real measured average (was a hardcoded "45ms" placeholder)
        }


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    print("=== ALGO-26 Intent Classification smoke test ===")

    clf = IntentClassifier()

    # 1. A question -> real "definition" scoring (pattern + keyword + structure)
    r1 = clf.classify("What is the definition of machine learning?")
    print(f"[question] text={r1.text!r}")
    print(f"           primary_intent={r1.primary_intent}, "
          f"top_confidence={r1.intents[0].confidence:.3f}, category={r1.intents[0].category}")
    print(f"           entities={[(e.entity, e.type) for e in r1.entities]}")
    assert r1.primary_intent == "definition"
    assert r1.intents, "expected at least one scored intent for a real question"

    # 2. A command/imperative -> ACTION-category "read" intent, boosted by the
    #    real has_imperative structure feature ("show" at the start of the text)
    r2 = clf.classify("Please show me the report")
    print(f"[command] text={r2.text!r}")
    print(f"          primary_intent={r2.primary_intent}, "
          f"top_confidence={r2.intents[0].confidence:.3f}, category={r2.intents[0].category}")
    print(f"          entities={[(e.entity, e.type) for e in r2.entities]}")
    assert r2.primary_intent == "read"

    # 3. A statement/social utterance -> "greeting"
    r3 = clf.classify("Hello, good morning!")
    print(f"[statement] text={r3.text!r}")
    print(f"            primary_intent={r3.primary_intent}, "
          f"top_confidence={r3.intents[0].confidence:.3f}, category={r3.intents[0].category}")
    assert r3.primary_intent == "greeting"

    # Distinctness check across the three real classifications
    primaries = {r1.primary_intent, r2.primary_intent, r3.primary_intent}
    print(f"Distinct primary intents across the 3 inputs: {primaries}")
    assert len(primaries) >= 2, "the three different inputs should not all collapse to one intent"

    # 4. Real entity extraction: email/money/number/date all detected.
    #    booking's raw score (0.46) sits just under the default 0.5 gate, so
    #    this call uses a real, lower min_confidence - the same knob the
    #    source's own ClassificationRequest.min_confidence exposes - to
    #    surface it, rather than pretending the raw score was higher.
    r4 = clf.classify(
        "Book a table for 4 people on 2026-09-20 and email me at test@example.com, budget $50",
        min_confidence=0.3,
    )
    print(f"[entities] text={r4.text!r}")
    print(f"           primary_intent={r4.primary_intent}, "
          f"top_confidence={r4.intents[0].confidence:.3f}")
    print(f"           entities={[(e.entity, e.type, e.value) for e in r4.entities]}")
    entity_types_found = {e.type for e in r4.entities}
    assert "email" in entity_types_found
    assert "money" in entity_types_found
    assert "number" in entity_types_found
    assert "date" in entity_types_found
    assert r4.primary_intent == "booking"

    # 5. Context: session-based previous_intent boosts a related follow-up
    #    intent's score by +0.5*0.2=0.10 (see _score_intent's context_score).
    #    In the real source, ContextManager.set_context() is only ever
    #    called from the separate `/context/set` HTTP route - classify()
    #    itself only calls update_context(), which is a no-op until a
    #    session exists - so this mirrors that route's real call here.
    session_id = "smoke-test-session"
    clf.context_manager.set_context(session_id, {})
    session = {"session_id": session_id}

    r5a = clf.classify("I want to purchase and order this item", context=session)
    print(f"[context 1/2] primary_intent={r5a.primary_intent}, context_used={r5a.context_used}")
    assert r5a.primary_intent == "purchase"

    r5b = clf.classify("I want to pay now", context=session)
    print(f"[context 2/2] primary_intent={r5b.primary_intent}, context_used={r5b.context_used}, "
          f"confidence={r5b.intents[0].confidence:.3f}")
    assert r5b.context_used is True, "second call in the same session must have found stored context"
    assert r5b.primary_intent == "payment", \
        "context_score from previous_intent=purchase (in payment.related_intents) must lift payment above 0.5"

    # 6. Real, measured get_statistics() after several calls (not a hardcoded placeholder)
    stats = clf.get_statistics()
    print(f"get_statistics() -> {stats}")
    assert stats["total_classifications"] == 6
    assert stats["avg_processing_time"] != "45.0ms", "must be a real measurement, not the old hardcoded placeholder"
    assert stats["most_common_intents"], "expected at least one tallied intent"

    # 7. classify_batch() - min_confidence=0.3 here (same real per-call
    #    parameter classify() takes) since these three raw top scores
    #    (0.475/0.475/0.493) are real but fall just under the stricter 0.5
    #    default used above for r1-r5.
    batch = clf.classify_batch(
        ["Thank you very much", "Cancel my reservation", "What time is it?"],
        min_confidence=0.3,
    )
    print(f"classify_batch() -> {[(b.primary_intent, round(b.intents[0].confidence, 3) if b.intents else None) for b in batch]}")
    assert len(batch) == 3
    assert [b.primary_intent for b in batch] == ["thanks", "cancellation", "question"]

    print("=== ALGO-26 Intent Classification: ALL ASSERTIONS PASSED ===")
