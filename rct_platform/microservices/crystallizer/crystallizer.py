"""
ALGO-41: The Crystallizer - Golden Keyword Extraction & Auto-Concept Expansion

This module detects high-entropy keywords in user conversations and expands them
into actionable concept maps, bridging abstract ideas to concrete implementations.

Core Function: Transform vague inputs into structured intents
Target: Enable users to discover their own requirements through interactive keyword exploration
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import logging
import re

logger = logging.getLogger(__name__)


class KeywordCategory(Enum):
    """Categories of detected keywords"""
    TECHNICAL = "technical"       # Framework names, tech terms
    CONCEPTUAL = "conceptual"     # Abstract ideas (sovereignty, security)
    BUSINESS = "business"         # Business logic terms
    DOMAIN = "domain"            # Domain-specific terms


@dataclass
class GoldenKeyword:
    """A detected high-entropy keyword"""
    word: str
    entropy_score: float          # 0.0 - 1.0
    category: KeywordCategory
    context: str                  # Surrounding text
    position: int                 # Position in text
    related_intents: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "entropy_score": self.entropy_score,
            "category": self.category.value,
            "context": self.context,
            "position": self.position,
            "related_intents": self.related_intents
        }


@dataclass
class ConceptNode:
    """A node in the concept expansion graph"""
    keyword: str
    definition: str
    related_concepts: List[str]
    tech_stack_implications: List[str]
    suggested_actions: List[Dict[str, str]]
    examples: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "definition": self.definition,
            "related_concepts": self.related_concepts,
            "tech_stack_implications": self.tech_stack_implications,
            "suggested_actions": self.suggested_actions,
            "examples": self.examples
        }


@dataclass
class ConceptMap:
    """Complete concept expansion for a keyword"""
    root_keyword: GoldenKeyword
    definition: str
    expansion_nodes: List[ConceptNode]
    actionable_next_steps: List[Dict[str, str]]
    ui_schema: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_keyword": self.root_keyword.to_dict(),
            "definition": self.definition,
            "expansion_nodes": [node.to_dict() for node in self.expansion_nodes],
            "actionable_next_steps": self.actionable_next_steps,
            "ui_schema": self.ui_schema
        }


class EntropyScanner:
    """
    Scans text streams for high-entropy keywords
    
    High entropy = high information content = important concept
    """
    
    def __init__(self):
        # Technical terms that are always high value
        self.technical_terms = {
            "next.js", "react", "vue", "angular", "svelte",
            "python", "django", "fastapi", "flask",
            "go", "fiber", "gin",
            "postgresql", "mysql", "mongodb", "redis",
            "kubernetes", "docker", "serverless",
            "graphql", "rest", "grpc",
            "jwt", "oauth", "auth0"
        }
        
        # Conceptual terms that indicate deep requirements
        self.conceptual_terms = {
            "sovereignty", "privacy", "security", "compliance",
            "scalability", "performance", "availability",
            "realtime", "offline", "sync",
            "ownership", "control", "freedom"
        }
        
        # Business logic terms
        self.business_terms = {
            "inventory", "payment", "subscription", "analytics",
            "dashboard", "reporting", "workflow", "automation",
            "notification", "email", "sms", "webhook"
        }
        
        # Stop words to ignore
        self.stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "up", "about",
            "into", "through", "during", "is", "are", "was", "were",
            "ได้", "คือ", "เป็น", "ที่", "จะ", "ให้", "กับ", "ใน"
        }
    
    def scan_stream(self, text: str) -> List[GoldenKeyword]:
        """Scan text for golden keywords"""
        keywords = []
        words = self._tokenize(text)
        
        for i, word in enumerate(words):
            word_lower = word.lower()
            
            # Skip stop words
            if word_lower in self.stop_words:
                continue
            
            # Calculate entropy score
            score = self._calculate_entropy(word_lower)
            
            if score >= 0.8:  # Threshold for "golden"
                category = self._categorize_word(word_lower)
                context = self._extract_context(words, i)
                
                keyword = GoldenKeyword(
                    word=word,
                    entropy_score=score,
                    category=category,
                    context=context,
                    position=i
                )
                
                keywords.append(keyword)
        
        return keywords
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization"""
        # Remove punctuation except hyphens and dots (for tech terms)
        text = re.sub(r'[^\w\s\-\.]', ' ', text)
        return text.split()
    
    def _calculate_entropy(self, word: str) -> float:
        """
        Calculate information entropy of a word
        
        High entropy = high information content = important
        """
        score = 0.0
        
        # Check against known high-value terms
        if word in self.technical_terms:
            score += 0.9
        if word in self.conceptual_terms:
            score += 0.95
        if word in self.business_terms:
            score += 0.85
        
        # Length heuristic (longer technical terms tend to be more specific)
        if len(word) > 8:
            score += 0.1
        
        # Capital letters in middle (camelCase or PascalCase)
        if any(c.isupper() for c in word[1:]):
            score += 0.2
        
        # Contains numbers or special chars (version numbers, etc)
        if any(c.isdigit() for c in word):
            score += 0.15
        
        # Compound words with hyphens or dots
        if '-' in word or '.' in word:
            score += 0.2
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _categorize_word(self, word: str) -> KeywordCategory:
        """Determine keyword category"""
        if word in self.technical_terms:
            return KeywordCategory.TECHNICAL
        elif word in self.conceptual_terms:
            return KeywordCategory.CONCEPTUAL
        elif word in self.business_terms:
            return KeywordCategory.BUSINESS
        else:
            return KeywordCategory.DOMAIN
    
    def _extract_context(self, words: List[str], position: int, window: int = 3) -> str:
        """Extract surrounding context for a keyword"""
        start = max(0, position - window)
        end = min(len(words), position + window + 1)
        context_words = words[start:end]
        
        # Highlight the keyword
        context_words[position - start] = f"**{context_words[position - start]}**"
        
        return " ".join(context_words)


class KnowledgeBase:
    """
    Knowledge base for concept expansion
    
    In production, this would query GraphRAG or vector database
    """
    
    def __init__(self):
        self.concepts = {
            "sovereignty": {
                "definition": "Complete ownership and control over your data and infrastructure",
                "related": ["privacy", "self-hosting", "open-source", "local-ai"],
                "tech_implications": [
                    "Self-hosted databases (PostgreSQL, not managed services)",
                    "On-premise or private cloud deployment",
                    "Local AI models (Ollama, llama.cpp)",
                    "85/15 architecture (85% local, 15% cloud)"
                ],
                "actions": [
                    {"id": "setup_local_db", "label": "Setup self-hosted database"},
                    {"id": "configure_local_ai", "label": "Configure local AI models"},
                    {"id": "plan_infra", "label": "Plan sovereignty-first infrastructure"}
                ]
            },
            
            "realtime": {
                "definition": "Instant bidirectional communication between client and server",
                "related": ["websocket", "sse", "polling", "push-notifications"],
                "tech_implications": [
                    "WebSocket protocol (Socket.io, Supabase Realtime)",
                    "Server-Sent Events for one-way streaming",
                    "Redis Pub/Sub for message distribution",
                    "Edge functions for low latency"
                ],
                "actions": [
                    {"id": "implement_websocket", "label": "Implement WebSocket connection"},
                    {"id": "setup_redis", "label": "Setup Redis for pub/sub"},
                    {"id": "design_realtime_api", "label": "Design realtime API architecture"}
                ]
            },
            
            "inventory": {
                "definition": "System for tracking and managing stock/items",
                "related": ["stock", "warehouse", "sku", "tracking"],
                "tech_implications": [
                    "Database with ACID properties (PostgreSQL)",
                    "Optimistic locking for concurrent updates",
                    "Event sourcing for audit trail",
                    "Real-time stock updates"
                ],
                "actions": [
                    {"id": "design_schema", "label": "Design inventory database schema"},
                    {"id": "implement_tracking", "label": "Implement stock tracking logic"},
                    {"id": "create_dashboard", "label": "Create inventory dashboard"}
                ]
            },
            
            "next.js": {
                "definition": "React framework with server-side rendering and modern features",
                "related": ["react", "vercel", "app-router", "server-components"],
                "tech_implications": [
                    "Server-side rendering for SEO",
                    "API routes for backend logic",
                    "App Router for modern routing",
                    "Edge runtime for global deployment"
                ],
                "actions": [
                    {"id": "create_nextjs_app", "label": "Create Next.js application"},
                    {"id": "setup_api_routes", "label": "Setup API routes"},
                    {"id": "configure_deployment", "label": "Configure Vercel deployment"}
                ]
            }
        }
    
    def get_concept(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Retrieve concept information"""
        return self.concepts.get(keyword.lower())
    
    def search_related(self, keyword: str) -> List[str]:
        """Find concepts related to keyword"""
        concept = self.get_concept(keyword)
        if concept:
            return concept.get("related", [])
        return []


class Crystallizer:
    """
    The Crystallizer Engine - Transforms vague ideas into structured concepts
    
    Main workflow:
    1. Scan conversation for golden keywords
    2. Expand each keyword into concept map
    3. Suggest actionable next steps
    4. Generate interactive UI
    """
    
    def __init__(self):
        self.scanner = EntropyScanner()
        self.knowledge_base = KnowledgeBase()
        logger.info("Crystallizer initialized")
    
    async def crystallize(self, conversation_text: str) -> List[ConceptMap]:
        """
        Main crystallization process
        
        Takes raw conversation text and returns structured concept maps
        """
        logger.info(f"Crystallizing text: {conversation_text[:100]}...")
        
        # Step 1: Scan for golden keywords
        keywords = self.scanner.scan_stream(conversation_text)
        
        if not keywords:
            logger.info("No golden keywords detected")
            return []
        
        # Step 2: Expand each keyword
        concept_maps = []
        for keyword in keywords:
            concept_map = await self.expand_concept(keyword)
            if concept_map:
                concept_maps.append(concept_map)
        
        return concept_maps
    
    async def expand_concept(self, keyword: GoldenKeyword) -> Optional[ConceptMap]:
        """Expand a golden keyword into a full concept map"""
        
        # Query knowledge base
        concept_data = self.knowledge_base.get_concept(keyword.word)
        
        if not concept_data:
            # Fallback: create basic expansion
            concept_data = {
                "definition": f"Concept related to {keyword.word}",
                "related": [],
                "tech_implications": [],
                "actions": []
            }
        
        # Create expansion nodes
        expansion_nodes = []
        for related in concept_data.get("related", []):
            related_data = self.knowledge_base.get_concept(related)
            if related_data:
                node = ConceptNode(
                    keyword=related,
                    definition=related_data["definition"],
                    related_concepts=related_data["related"],
                    tech_stack_implications=related_data["tech_implications"],
                    suggested_actions=related_data["actions"]
                )
                expansion_nodes.append(node)
        
        # Generate UI schema
        ui_schema = self._generate_ui_schema(keyword, concept_data, expansion_nodes)
        
        return ConceptMap(
            root_keyword=keyword,
            definition=concept_data["definition"],
            expansion_nodes=expansion_nodes,
            actionable_next_steps=concept_data.get("actions", []),
            ui_schema=ui_schema
        )
    
    def _generate_ui_schema(
        self,
        keyword: GoldenKeyword,
        concept_data: Dict[str, Any],
        nodes: List[ConceptNode]
    ) -> Dict[str, Any]:
        """
        Generate interactive UI schema for frontend
        
        This creates the "holographic card" that appears on hover/click
        """
        return {
            "type": "concept_card",
            "title": keyword.word,
            "highlight_color": "#FFD700",  # Gold
            "sections": [
                {
                    "type": "definition",
                    "content": concept_data["definition"]
                },
                {
                    "type": "graph",
                    "nodes": [
                        {"id": keyword.word, "label": keyword.word, "type": "root"},
                        *[{"id": node.keyword, "label": node.keyword, "type": "related"} 
                          for node in nodes]
                    ],
                    "edges": [
                        {"from": keyword.word, "to": node.keyword}
                        for node in nodes
                    ]
                },
                {
                    "type": "implications",
                    "title": "Tech Stack Implications",
                    "items": concept_data.get("tech_implications", [])
                },
                {
                    "type": "actions",
                    "title": "What you can do",
                    "buttons": concept_data.get("actions", [])
                }
            ],
            "triggers": {
                "hover": "preview",
                "click": "expand_full"
            }
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get Crystallizer statistics"""
        return {
            "total_concepts": len(self.knowledge_base.concepts),
            "entropy_threshold": 0.8,
            "average_expansion_depth": 2,
            "average_crystallization_time": "0.1s"
        }


__version__ = "1.0.0"
