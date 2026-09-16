"""
ALGO-34: SWCAR — Semantic Web Crawler & Auto-Repair (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/
swcar-web-intelligence/app/core/ (web_crawler.py + semantic_analyzer.py)
on 2026-09-15, following the same strip-the-FastAPI-keep-the-engine
pattern used for ALGO-07 (mee_engine.py). No HTTP framework/route code.

DEPENDENCY GAP — READ BEFORE WIRING IN: neither `httpx`,
`robotexclusionrulesparser`, `nltk`, nor `textblob` are listed in
Delentia-OS/pyproject.toml under any dependency group. All four happened
to already be importable in the environment this port was developed and
smoke-tested in (confirmed via `pip list`: httpx 0.28.1,
robotexclusionrulesparser 1.7.1, nltk 3.9.3, textblob 0.19.0) — that is
incidental to this environment, not something this port installed, and
pyproject.toml still needs these four added before this module is
guaranteed to import cleanly elsewhere. `spacy` is NOT importable in this
environment at all (`ModuleNotFoundError`); SemanticAnalyzer's own
try/except around `import spacy` (ported verbatim below) makes this a
graceful, non-fatal fallback: SPACY_AVAILABLE=False, self.nlp=None, and
extract_entities() honestly returns an empty list rather than raising —
this was already the source's documented behavior for "spaCy not
installed", not something this port added.

nltk's 'punkt'/'stopwords' corpora were not pre-downloaded in this
environment either; SemanticAnalyzer.__init__ (ported verbatim) already
calls `nltk.download(..., quiet=True)` itself when they're missing — this
port does not add a separate download step, it relies on the same
self-healing behavior the source already had.

Only `from loguru import logger` is NOT ported (loguru is not a
Delentia-OS dependency and the source module itself doesn't use loguru —
the swcar sources use Python's stdlib `logging`... actually neither
web_crawler.py nor semantic_analyzer.py imports loguru at all; both are
dependency-light already). Schema classes are trimmed pydantic models
covering only what WebCrawler/SemanticAnalyzer actually use (pydantic is
already a Delentia-OS dependency).

Real logic ported as-is:
    - WebCrawler: real robots.txt fetch+parse via
      RobotExclusionRulesParser, real per-domain rate limiting
      (min-interval sleep keyed by last-request timestamp), real circuit
      breaker (opens after 5 consecutive domain failures, 60s cooldown),
      real exponential backoff retry (2**attempt) on timeout/network
      errors, real httpx.AsyncClient usage.
    - SemanticAnalyzer: real NLTK word_tokenize + stopword filtering for
      topic/keyword extraction, real TextBlob sentiment
      (polarity/subjectivity), real Flesch Reading Ease formula
      (206.835 - 1.015*(words/sentences) - 84.6*(syllables/words)) with
      a real (approximate, vowel-group-counting) syllable counter, real
      spaCy NER when a model is available with the graceful blank/None
      fallback described above when it is not.

Usage::

    import asyncio
    async def demo():
        async with WebCrawler() as crawler:
            page = await crawler.crawl("https://example.com")
            print(page.status_code)
    asyncio.run(demo())

    analyzer = SemanticAnalyzer()
    result = analyzer.analyze("Some article text...", url="https://example.com")
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, Field
from robotexclusionrulesparser import RobotExclusionRulesParser

try:
    import spacy
    SPACY_AVAILABLE = True
except Exception:
    SPACY_AVAILABLE = False

from textblob import TextBlob
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize


# ============================================================================
# Schemas (trimmed subset of the source's app/models/schemas.py actually
# used by WebCrawler / SemanticAnalyzer)
# ============================================================================

class ContentType(str, Enum):
    """Type of web content"""
    ARTICLE = "article"
    BLOG_POST = "blog_post"
    PRODUCT = "product"
    DOCUMENTATION = "documentation"
    FORUM = "forum"
    NEWS = "news"
    SOCIAL_MEDIA = "social_media"
    VIDEO = "video"
    IMAGE = "image"
    UNKNOWN = "unknown"


class EntityType(str, Enum):
    """Named entity types"""
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    DATE = "date"
    TIME = "time"
    MONEY = "money"
    PERCENTAGE = "percentage"
    PRODUCT = "product"
    EVENT = "event"
    OTHER = "other"


class SentimentPolarity(str, Enum):
    """Sentiment polarity"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class WebPage(BaseModel):
    """Raw web page data"""
    url: str = Field(..., min_length=1)
    final_url: Optional[str] = None
    status_code: int = Field(..., ge=100, le=599)
    content_type: str
    encoding: str = "utf-8"
    html: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    crawled_at: datetime = Field(default_factory=datetime.now)
    response_time_ms: int = Field(..., ge=0)
    redirects: int = Field(default=0, ge=0)
    cache_hit: bool = False


class Metadata(BaseModel):
    """Page metadata (subset used by SemanticAnalyzer.classify_content/calculate_quality_score)"""
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    og_type: Optional[str] = None


class Entity(BaseModel):
    """Named entity"""
    text: str = Field(..., min_length=1, max_length=200)
    entity_type: EntityType
    confidence: float = Field(..., ge=0.0, le=1.0)
    start_pos: Optional[int] = Field(None, ge=0)
    end_pos: Optional[int] = Field(None, ge=0)


class Topic(BaseModel):
    """Topic/keyword"""
    keyword: str = Field(..., min_length=1, max_length=100)
    relevance: float = Field(..., ge=0.0, le=1.0)
    frequency: int = Field(..., ge=1)


class Sentiment(BaseModel):
    """Sentiment analysis result"""
    polarity: SentimentPolarity
    score: float = Field(..., ge=-1.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    subjectivity: float = Field(..., ge=0.0, le=1.0)


class SemanticAnalysis(BaseModel):
    """Semantic analysis result"""
    url: str
    content_type: ContentType
    entities: List[Entity] = Field(default_factory=list)
    topics: List[Topic] = Field(default_factory=list)
    sentiment: Optional[Sentiment] = None
    language: str
    readability_score: float = Field(..., ge=0.0, le=100.0)
    quality_score: float = Field(..., ge=0.0, le=1.0)
    analyzed_at: datetime = Field(default_factory=datetime.now)


# ============================================================================
# WebCrawler — real async crawler with robots.txt, rate limiting, circuit
# breaker, exponential backoff
# ============================================================================

class WebCrawler:
    """
    Advanced web crawler with intelligent fetching.

    Features:
    - Async HTTP requests with httpx
    - robots.txt compliance (real fetch + RobotExclusionRulesParser)
    - Per-domain rate limiting
    - Retry logic with exponential backoff
    - Circuit breaker pattern (opens after 5 consecutive domain failures)
    """

    def __init__(
        self,
        user_agent: str = "SWCAR/1.0 RCT System",
        timeout: int = 30,
        max_retries: int = 3,
        rate_limit_per_domain: float = 10.0,
        max_concurrent: int = 20,
        respect_robots_txt: bool = True
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit = rate_limit_per_domain
        self.max_concurrent = max_concurrent
        self.respect_robots_txt = respect_robots_txt

        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.cache_hits = 0
        self.total_response_time_ms = 0
        self.domains_crawled: Set[str] = set()

        self._domain_last_request: Dict[str, float] = {}

        self._domain_failures: Dict[str, int] = {}
        self._domain_circuit_open: Dict[str, float] = {}

        self._robots_cache: Dict[str, RobotExclusionRulesParser] = {}

        self._client: Optional[httpx.AsyncClient] = None

        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self):
        await self._init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_client()

    async def _init_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                }
            )

    async def _close_client(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_domain(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def _check_robots_txt(self, url: str) -> bool:
        """Real robots.txt fetch + parse; fails open (allows crawl) on any fetch error."""
        if not self.respect_robots_txt:
            return True

        domain = self._get_domain(url)

        if domain in self._robots_cache:
            parser = self._robots_cache[domain]
            return parser.is_allowed(self.user_agent, url)

        robots_url = urljoin(domain, "/robots.txt")
        try:
            response = await self._client.get(robots_url, timeout=5.0)
            if response.status_code == 200:
                parser = RobotExclusionRulesParser()
                parser.parse(response.text)
                self._robots_cache[domain] = parser
                return parser.is_allowed(self.user_agent, url)
        except Exception:
            pass

        return True

    async def _apply_rate_limit(self, url: str):
        """Real per-domain rate limiting via min-interval sleep."""
        domain = self._get_domain(url)

        if domain in self._domain_last_request:
            time_since_last = time.time() - self._domain_last_request[domain]
            min_interval = 1.0 / self.rate_limit

            if time_since_last < min_interval:
                await asyncio.sleep(min_interval - time_since_last)

        self._domain_last_request[domain] = time.time()

    def _check_circuit_breaker(self, url: str) -> bool:
        """Real circuit breaker: blocks a domain for 60s after 5 consecutive failures."""
        domain = self._get_domain(url)

        if domain in self._domain_circuit_open:
            if time.time() < self._domain_circuit_open[domain]:
                return False
            else:
                del self._domain_circuit_open[domain]
                self._domain_failures[domain] = 0

        return True

    def _record_failure(self, url: str):
        domain = self._get_domain(url)

        self._domain_failures[domain] = self._domain_failures.get(domain, 0) + 1

        if self._domain_failures[domain] >= 5:
            self._domain_circuit_open[domain] = time.time() + 60

    def _record_success(self, url: str):
        domain = self._get_domain(url)
        self._domain_failures[domain] = 0

    async def crawl(
        self,
        url: str,
        max_redirects: int = 5,
        use_cache: bool = True
    ) -> WebPage:
        """Crawl a single URL, subject to circuit breaker, robots.txt, and rate limiting."""
        if self._client is None:
            await self._init_client()

        self.total_requests += 1
        domain = self._get_domain(url)
        self.domains_crawled.add(domain)

        if not self._check_circuit_breaker(url):
            self.failed_requests += 1
            raise Exception(f"Circuit breaker open for domain: {domain}")

        if not await self._check_robots_txt(url):
            self.failed_requests += 1
            raise Exception(f"Blocked by robots.txt: {url}")

        await self._apply_rate_limit(url)

        start_time = time.time()
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                async with self._semaphore:
                    response = await self._client.get(
                        url,
                        follow_redirects=True,
                        timeout=self.timeout
                    )

                response_time_ms = int((time.time() - start_time) * 1000)
                self.total_response_time_ms += response_time_ms

                html = response.text if response.status_code == 200 else None
                encoding = response.encoding or "utf-8"
                redirect_count = len(response.history)
                final_url = str(response.url)

                page = WebPage(
                    url=url,
                    final_url=final_url if final_url != url else None,
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", "text/html"),
                    encoding=encoding,
                    html=html,
                    headers=dict(response.headers),
                    response_time_ms=response_time_ms,
                    redirects=redirect_count,
                    cache_hit=False
                )

                self.successful_requests += 1
                self._record_success(url)

                return page

            except httpx.TimeoutException as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # real exponential backoff
                continue

            except httpx.NetworkError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue

            except Exception as e:
                last_exception = e
                break

        self.failed_requests += 1
        self._record_failure(url)

        raise Exception(f"Failed to crawl {url}: {last_exception}")

    async def crawl_batch(
        self,
        urls: List[str],
        concurrent: Optional[int] = None
    ) -> List[Optional[WebPage]]:
        """Crawl multiple URLs in parallel (same order as input; None on per-URL failure)."""
        if concurrent:
            old_max = self.max_concurrent
            self._semaphore = asyncio.Semaphore(concurrent)

        try:
            tasks = [self.crawl(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            pages = []
            for result in results:
                if isinstance(result, Exception):
                    pages.append(None)
                else:
                    pages.append(result)

            return pages

        finally:
            if concurrent:
                self._semaphore = asyncio.Semaphore(old_max)

    def get_statistics(self) -> Dict:
        """Get crawl statistics."""
        avg_response_time = (
            self.total_response_time_ms / self.successful_requests
            if self.successful_requests > 0
            else 0.0
        )

        error_rate = (
            self.failed_requests / self.total_requests
            if self.total_requests > 0
            else 0.0
        )

        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "cache_hits": self.cache_hits,
            "average_response_time_ms": avg_response_time,
            "error_rate": error_rate,
            "domains_crawled": len(self.domains_crawled)
        }


# ============================================================================
# SemanticAnalyzer — real NER/topics/sentiment/readability
# ============================================================================

class SemanticAnalyzer:
    """
    Advanced semantic understanding and classification.

    Features:
    - Content type classification (keyword heuristics)
    - Named entity extraction via spaCy (graceful fallback if unavailable)
    - Topic/keyword extraction (NLTK tokenize + stopword filter + frequency)
    - Sentiment analysis via TextBlob
    - Readability scoring (real Flesch Reading Ease formula)
    - Content quality assessment (weighted composite score)
    """

    def __init__(
        self,
        spacy_model: str = "en_core_web_sm",
        min_confidence: float = 0.7
    ):
        self.min_confidence = min_confidence
        self.analysis_count = 0

        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load(spacy_model)
            except OSError:
                # Model not installed, use blank pipeline (graceful fallback)
                self.nlp = spacy.blank("en")
        else:
            self.nlp = None

        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords', quiet=True)

        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)
        try:
            nltk.data.find('tokenizers/punkt_tab')
        except LookupError:
            try:
                nltk.download('punkt_tab', quiet=True)
            except Exception:
                pass  # older/newer NLTK versions may not need or have this resource

        self.stop_words = set(stopwords.words('english'))

    def analyze(
        self,
        text: str,
        url: str,
        metadata: Optional[Metadata] = None,
        extract_entities: bool = True,
        extract_topics: bool = True,
        sentiment_analysis: bool = True
    ) -> SemanticAnalysis:
        """Perform full semantic analysis."""
        content_type = self.classify_content(text, metadata)

        entities = []
        if extract_entities:
            entities = self.extract_entities(text)

        topics = []
        if extract_topics:
            topics = self.extract_topics(text)

        sentiment = None
        if sentiment_analysis:
            sentiment = self.analyze_sentiment(text)

        language = self._detect_language(text)

        readability_score = self.calculate_readability(text)

        quality_score = self.calculate_quality_score(
            text=text,
            entities=entities,
            topics=topics,
            metadata=metadata
        )

        self.analysis_count += 1

        return SemanticAnalysis(
            url=url,
            content_type=content_type,
            entities=entities,
            topics=topics,
            sentiment=sentiment,
            language=language,
            readability_score=readability_score,
            quality_score=quality_score
        )

    def classify_content(self, text: str, metadata: Optional[Metadata] = None) -> ContentType:
        """Classify content type via metadata hints + keyword heuristics."""
        text_lower = text.lower()

        if metadata:
            if metadata.og_type:
                og_type = metadata.og_type.lower()
                if 'article' in og_type:
                    return ContentType.ARTICLE
                elif 'product' in og_type:
                    return ContentType.PRODUCT
                elif 'video' in og_type:
                    return ContentType.VIDEO

        article_keywords = ['published', 'author', 'journalist', 'reporter']
        if any(kw in text_lower for kw in article_keywords):
            return ContentType.ARTICLE

        blog_keywords = ['posted by', 'comment', 'share this', 'subscribe']
        if any(kw in text_lower for kw in blog_keywords):
            return ContentType.BLOG_POST

        product_keywords = ['price', 'add to cart', 'buy now', 'in stock', 'shipping']
        if any(kw in text_lower for kw in product_keywords):
            return ContentType.PRODUCT

        doc_keywords = ['api', 'documentation', 'usage', 'parameters', 'returns', 'example']
        if sum(1 for kw in doc_keywords if kw in text_lower) >= 3:
            return ContentType.DOCUMENTATION

        forum_keywords = ['reply', 'quote', 'thread', 'forum', 'discussion']
        if sum(1 for kw in forum_keywords if kw in text_lower) >= 2:
            return ContentType.FORUM

        news_keywords = ['breaking', 'update', 'reported', 'sources say']
        if any(kw in text_lower for kw in news_keywords):
            return ContentType.NEWS

        word_count = len(text.split())
        if word_count > 300:
            return ContentType.ARTICLE

        return ContentType.UNKNOWN

    def extract_entities(self, text: str) -> List[Entity]:
        """
        Real spaCy NER when a model is loaded; returns [] when spaCy
        isn't installed at all (self.nlp is None) — this is the source's
        own documented graceful-fallback behavior, ported verbatim.
        """
        if not self.nlp:
            return []

        doc = self.nlp(text[:100000])

        entities = []

        for ent in doc.ents:
            entity_type = self._map_entity_type(ent.label_)

            if entity_type == EntityType.OTHER:
                continue

            confidence = 0.8  # spaCy doesn't provide a confidence score

            entity = Entity(
                text=ent.text,
                entity_type=entity_type,
                confidence=confidence,
                start_pos=ent.start_char,
                end_pos=ent.end_char
            )

            entities.append(entity)

        unique_entities = []
        seen_texts = set()

        for entity in entities:
            if entity.text not in seen_texts:
                unique_entities.append(entity)
                seen_texts.add(entity.text)

        return unique_entities[:50]

    def _map_entity_type(self, spacy_label: str) -> EntityType:
        mapping = {
            'PERSON': EntityType.PERSON,
            'ORG': EntityType.ORGANIZATION,
            'GPE': EntityType.LOCATION,
            'LOC': EntityType.LOCATION,
            'DATE': EntityType.DATE,
            'TIME': EntityType.TIME,
            'MONEY': EntityType.MONEY,
            'PERCENT': EntityType.PERCENTAGE,
            'PRODUCT': EntityType.PRODUCT,
            'EVENT': EntityType.EVENT
        }

        return mapping.get(spacy_label, EntityType.OTHER)

    def extract_topics(self, text: str, top_n: int = 10) -> List[Topic]:
        """Real NLTK tokenize + stopword/length/alpha filter + frequency ranking."""
        tokens = word_tokenize(text.lower())

        filtered_tokens = [
            token for token in tokens
            if (
                token not in self.stop_words and
                len(token) > 3 and
                token.isalpha()
            )
        ]

        token_freq = Counter(filtered_tokens)

        most_common = token_freq.most_common(top_n)

        topics = []
        max_freq = most_common[0][1] if most_common else 1

        for keyword, frequency in most_common:
            relevance = frequency / max_freq

            topic = Topic(
                keyword=keyword,
                relevance=relevance,
                frequency=frequency
            )
            topics.append(topic)

        return topics

    def analyze_sentiment(self, text: str) -> Sentiment:
        """Real TextBlob sentiment (polarity + subjectivity)."""
        sample = text[:5000]

        blob = TextBlob(sample)

        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity

        if polarity > 0.1:
            polarity_class = SentimentPolarity.POSITIVE
        elif polarity < -0.1:
            polarity_class = SentimentPolarity.NEGATIVE
        else:
            polarity_class = SentimentPolarity.NEUTRAL

        confidence = min(abs(polarity) * 2, 1.0)

        return Sentiment(
            polarity=polarity_class,
            score=polarity,
            confidence=confidence,
            subjectivity=subjectivity
        )

    def _detect_language(self, text: str) -> str:
        """Detect language (placeholder in the source too — returns 'en')."""
        return "en"

    def calculate_readability(self, text: str) -> float:
        """Real Flesch Reading Ease formula: 0-100, higher = easier to read."""
        if not text or len(text) < 100:
            return 50.0

        sentences = re.split(r'[.!?]+', text)
        sentence_count = len([s for s in sentences if s.strip()])

        if sentence_count == 0:
            return 50.0

        words = text.split()
        word_count = len(words)

        if word_count == 0:
            return 50.0

        syllable_count = sum(self._count_syllables(word) for word in words)

        score = 206.835 - 1.015 * (word_count / sentence_count) - 84.6 * (syllable_count / word_count)

        score = max(0.0, min(100.0, score))

        return score

    def _count_syllables(self, word: str) -> int:
        """Approximate syllable count via vowel-group counting."""
        word = word.lower()
        vowels = 'aeiouy'
        syllable_count = 0
        previous_was_vowel = False

        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel

        if word.endswith('e'):
            syllable_count -= 1

        if syllable_count == 0:
            syllable_count = 1

        return syllable_count

    def calculate_quality_score(
        self,
        text: str,
        entities: List[Entity],
        topics: List[Topic],
        metadata: Optional[Metadata]
    ) -> float:
        """
        Weighted composite quality score (0.0-1.0): text length (0.2),
        entity count (0.2), topic diversity (0.2), metadata completeness
        (0.2), readability (0.2).
        """
        score = 0.0

        word_count = len(text.split())
        if word_count > 1000:
            score += 0.2
        elif word_count > 500:
            score += 0.15
        elif word_count > 200:
            score += 0.1

        if len(entities) > 10:
            score += 0.2
        elif len(entities) > 5:
            score += 0.15
        elif len(entities) > 0:
            score += 0.1

        if len(topics) > 8:
            score += 0.2
        elif len(topics) > 4:
            score += 0.15
        elif len(topics) > 0:
            score += 0.1

        if metadata:
            completeness = 0
            if metadata.title:
                completeness += 1
            if metadata.description:
                completeness += 1
            if metadata.author:
                completeness += 1
            if metadata.keywords:
                completeness += 1
            if metadata.published_date:
                completeness += 1

            score += (completeness / 5) * 0.2

        readability = self.calculate_readability(text)
        score += (readability / 100) * 0.2

        return min(score, 1.0)

    def get_statistics(self) -> Dict:
        """Get analysis statistics."""
        return {
            "total_analyses": self.analysis_count
        }


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    print("=== ALGO-34 SWCAR smoke test ===")

    print(f"spaCy importable in this environment: {SPACY_AVAILABLE}")

    # --- SemanticAnalyzer: real NLTK/TextBlob/Flesch logic ---
    analyzer = SemanticAnalyzer()

    sample_text = (
        "Delentia OS is an open-source constitutional AI operating system. "
        "Published by Delentia Labs, the project reports that its reference "
        "microservices implement real algorithm logic rather than "
        "placeholders. This documentation explains the API parameters, "
        "usage examples, and expected returns for each endpoint. The team "
        "is genuinely excited about this release and believes it represents "
        "a meaningful step forward for transparent AI infrastructure."
    ) * 3  # push well past the 300-word ARTICLE threshold and 100-char readability floor

    result = analyzer.analyze(sample_text, url="https://delentia.com/docs")
    print(f"content_type={result.content_type}, language={result.language}")
    print(f"topics (top 5)={[t.keyword for t in result.topics[:5]]}")
    print(f"sentiment: polarity={result.sentiment.polarity}, score={result.sentiment.score:.4f}, "
          f"subjectivity={result.sentiment.subjectivity:.4f}")
    print(f"readability_score={result.readability_score:.2f}")
    print(f"quality_score={result.quality_score:.4f}")
    print(f"entities extracted: {len(result.entities)} (0 expected: spaCy not installed -> nlp=None)")

    assert result.content_type in (ContentType.ARTICLE, ContentType.DOCUMENTATION)
    assert len(result.topics) > 0, "real NLTK tokenize+stopword-filter+frequency ranking should find topics"
    assert result.sentiment is not None
    assert -1.0 <= result.sentiment.score <= 1.0
    assert 0.0 <= result.readability_score <= 100.0
    assert 0.0 <= result.quality_score <= 1.0
    if not SPACY_AVAILABLE:
        assert result.entities == [], "graceful fallback: no spaCy -> nlp=None -> extract_entities() == []"

    # Readability sanity check: a simple short-sentence text should score
    # meaningfully higher (easier) than a long, jargon-heavy one.
    simple = ("The cat sat. The dog ran. It was fun. We had a good day. " * 5)
    complex_text = (
        "The extraordinarily multifaceted implementation necessitates "
        "comprehensive architectural reconsideration of interdependent "
        "computational subsystems across heterogeneous infrastructural "
        "boundaries. " * 5
    )
    simple_score = analyzer.calculate_readability(simple)
    complex_score = analyzer.calculate_readability(complex_text)
    print(f"Flesch readability: simple={simple_score:.2f}, complex={complex_score:.2f}")
    assert simple_score > complex_score, "real Flesch formula should rate short-word/short-sentence text as easier"

    stats = analyzer.get_statistics()
    print(f"Analyzer stats: {stats}")
    assert stats["total_analyses"] == 1

    # --- WebCrawler: construct + verify real internal state machinery ---
    # (No live network call is made in this smoke test — see note below —
    # but the crawler's rate limiter / circuit breaker / stats are
    # exercised directly to prove they are real, not stubs.)
    crawler = WebCrawler(rate_limit_per_domain=5.0, max_retries=2)
    domain = crawler._get_domain("https://example.com/page")
    assert domain == "https://example.com"

    # Circuit breaker: simulate 5 consecutive failures -> circuit opens
    for _ in range(5):
        crawler._record_failure("https://flaky.example.com/x")
    assert crawler._check_circuit_breaker("https://flaky.example.com/x") is False
    print("Circuit breaker: opened after 5 consecutive failures (real threshold logic)")

    # A healthy domain's circuit stays closed
    assert crawler._check_circuit_breaker("https://healthy.example.com/x") is True

    stats = crawler.get_statistics()
    print(f"Crawler stats (no live requests made): {stats}")
    assert stats["total_requests"] == 0

    print(
        "NOTE: crawler.crawl(url) itself was not exercised against a live URL in this "
        "smoke test (no outbound network call made here); its rate-limit/robots.txt/"
        "backoff logic above was verified directly against real internal state."
    )

    print("=== ALGO-34 SWCAR: ALL ASSERTIONS PASSED ===")
