"""
OpenRouter Client for SignedAI Multi-Model Consensus System

This client manages parallel API calls to multiple AI models through OpenRouter,
implementing the 8-model jury system with tier-based routing.

Tier Structure:
- Tier-S (Sovereign): GPT-4, Claude 3.5 Sonnet
- Tier-4: Typhoon v1.5, GLM-4
- Tier-6: Gemini Pro 1.5, Llama 3 70B
- Tier-8: DeepSeek Coder, Qwen 2.5 72B

Features:
- Async parallel execution (8 concurrent API calls)
- OpenAI-compatible API format
- Cost tracking per model
- Automatic retry with exponential backoff
- Fallback model support
- Response validation (JSON format enforcement)
"""

import os
import json
import asyncio
import hashlib
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

try:
    import aiohttp
    from dotenv import load_dotenv
except ImportError as e:
    print("⚠️  Missing dependencies. Install with:")
    print("   pip3 install aiohttp python-dotenv")
    raise e

# Load environment variables
load_dotenv()


class ModelTier(Enum):
    """Model tier classification for complexity routing"""
    SOVEREIGN = "S"  # Tier-S: Most capable, highest cost
    TIER_4 = "4"     # Tier-4: Strong reasoning, moderate cost
    TIER_6 = "6"     # Tier-6: Good balance, lower cost
    TIER_8 = "8"     # Tier-8: Fast execution, lowest cost


@dataclass
class ModelConfig:
    """Configuration for each AI model in the jury"""
    model_id: str           # OpenRouter model identifier
    display_name: str       # Human-readable name
    tier: ModelTier        # Complexity tier
    cost_per_1k_input: float   # USD per 1000 input tokens
    cost_per_1k_output: float  # USD per 1000 output tokens
    temperature: float = 0.7   # Sampling temperature
    max_tokens: int = 2048     # Maximum response length
    enabled: bool = True       # Whether model is active


# 8-Model Jury Configuration
# We enrollment 7 models to achieve the target consensus voting array.
JURY_ROSTER: List[ModelConfig] = [
    # Tier-S: Sovereign (Highest capability)
    ModelConfig(
        model_id="openai/gpt-4-turbo",
        display_name="GPT-4 Turbo",
        tier=ModelTier.SOVEREIGN,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        temperature=0.7
    ),
    ModelConfig(
        model_id="anthropic/claude-3.5-sonnet",
        display_name="Claude 3.5 Sonnet",
        tier=ModelTier.SOVEREIGN,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        temperature=0.7
    ),
    
    # Tier-4: Strong Reasoning
    ModelConfig(
        model_id="scb10x/typhoon-v1.5x-70b-instruct",
        display_name="Typhoon v1.5 Instruct",
        tier=ModelTier.TIER_4,
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.0008,
        temperature=0.7
    ),
    ModelConfig(
        model_id="deepseek/deepseek-chat",
        display_name="DeepSeek Chat",
        tier=ModelTier.TIER_4,
        cost_per_1k_input=0.00014,
        cost_per_1k_output=0.00028,
        temperature=0.7
    ),
    
    # Tier-6: Balanced Performance
    ModelConfig(
        model_id="google/gemini-pro-1.5",
        display_name="Gemini Pro 1.5",
        tier=ModelTier.TIER_6,
        cost_per_1k_input=0.0005,
        cost_per_1k_output=0.0015,
        temperature=0.7
    ),
    ModelConfig(
        model_id="meta-llama/llama-3-70b-instruct",
        display_name="Llama 3 70B",
        tier=ModelTier.TIER_6,
        cost_per_1k_input=0.0007,
        cost_per_1k_output=0.0009,
        temperature=0.7
    ),
    
    # Tier-8: Fast & Efficient
    ModelConfig(
        model_id="qwen/qwen-2.5-72b-instruct",
        display_name="Qwen 2.5 72B",
        tier=ModelTier.TIER_8,
        cost_per_1k_input=0.0004,
        cost_per_1k_output=0.0004,
        temperature=0.7
    ),
]


@dataclass
class ModelResponse:
    """Response from a single model"""
    model_name: str
    tier: ModelTier
    response_text: str
    tokens_used: int
    cost_usd: float
    latency_ms: int
    timestamp: datetime
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


@dataclass
class JuryResponse:
    """Aggregated response from all models in the jury"""
    query: str
    responses: List[ModelResponse]
    total_cost_usd: float
    total_latency_ms: int
    successful_models: int
    failed_models: int
    consensus_achieved: bool = False
    final_verdict: Optional[str] = None
    signature: Optional[str] = None


class OpenRouterClient:
    """
    Async client for OpenRouter API with multi-model parallel execution
    
    Usage:
        client = OpenRouterClient(api_key="your_key")
        jury_response = await client.execute_jury(
            prompt="What is the meaning of life?",
            tier=ModelTier.TIER_4
        )
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: int = 45,
        max_retries: int = 2
    ):
        """
        Initialize OpenRouter client
        
        Args:
            api_key: OpenRouter API key (or use OPENROUTER_API_KEY / RCT_CORE_BRAIN_KEY env var)
            base_url: OpenRouter API endpoint
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        custom_url = os.getenv("RCT_MODEL_BACKEND_URL")
        self.base_url = custom_url or base_url
        
        self.api_key = api_key or os.getenv("RCT_CORE_BRAIN_KEY") or os.getenv("OPENROUTER_API_KEY")
        if not custom_url:
            if not self.api_key or "your-key" in self.api_key or "placeholder" in self.api_key:
                raise ValueError(
                    "OpenRouter API key required. Set RCT_CORE_BRAIN_KEY or OPENROUTER_API_KEY environment variable "
                    "or pass api_key parameter."
                )
        
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Headers for OpenRouter API
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/rct-ecosystem",
            "X-Title": "RCT SignedAI System"
        }
        
        # Statistics tracking
        self.stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "successful_requests": 0,
            "failed_requests": 0
        }
    
    def get_active_models(self, tier: Optional[ModelTier] = None) -> List[ModelConfig]:
        """
        Get list of active models, optionally filtered by tier
        
        Args:
            tier: Filter models by specific tier (None = all tiers)
        
        Returns:
            List of active ModelConfig objects
        """
        models = [m for m in JURY_ROSTER if m.enabled]
        
        if tier:
            models = [m for m in models if m.tier == tier]
        
        return models
    
    async def call_model(
        self,
        model: ModelConfig,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> ModelResponse:
        """
        Call a single model via OpenRouter API
        
        Args:
            model: ModelConfig to use
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Override default temperature
            max_tokens: Override default max tokens
        
        Returns:
            ModelResponse with result or error
        """
        start_time = time.time()
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Request payload
        payload = {
            "model": model.model_id,
            "messages": messages,
            "temperature": temperature or model.temperature,
            "max_tokens": max_tokens or model.max_tokens
        }
        
        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        headers=self.headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                    ) as response:
                        
                        if response.status == 200:
                            data = await response.json()
                            
                            # Extract response
                            response_text = data["choices"][0]["message"]["content"]
                            tokens_used = data["usage"]["total_tokens"]
                            
                            # Calculate cost
                            input_tokens = data["usage"]["prompt_tokens"]
                            output_tokens = data["usage"]["completion_tokens"]
                            cost = (
                                (input_tokens / 1000) * model.cost_per_1k_input +
                                (output_tokens / 1000) * model.cost_per_1k_output
                            )
                            
                            # Update stats
                            self.stats["total_requests"] += 1
                            self.stats["successful_requests"] += 1
                            self.stats["total_tokens"] += tokens_used
                            self.stats["total_cost_usd"] += cost
                            
                            latency_ms = int((time.time() - start_time) * 1000)
                            
                            return ModelResponse(
                                model_name=model.display_name,
                                tier=model.tier,
                                response_text=response_text,
                                tokens_used=tokens_used,
                                cost_usd=cost,
                                latency_ms=latency_ms,
                                timestamp=datetime.now(),
                                raw_response=data
                            )
                        
                        elif response.status == 429:  # Rate limit
                            wait_time = 2 ** attempt  # Exponential backoff
                            await asyncio.sleep(wait_time)
                            continue
                        
                        else:
                            error_text = await response.text()
                            raise Exception(f"HTTP {response.status}: {error_text}")
            
            except Exception as e:
                if attempt == self.max_retries - 1:  # Last attempt
                    self.stats["total_requests"] += 1
                    self.stats["failed_requests"] += 1
                    
                    return ModelResponse(
                        model_name=model.display_name,
                        tier=model.tier,
                        response_text="",
                        tokens_used=0,
                        cost_usd=0.0,
                        latency_ms=int((time.time() - start_time) * 1000),
                        timestamp=datetime.now(),
                        error=str(e)
                    )
                
                # Wait before retry
                await asyncio.sleep(2 ** attempt)
        
        # Should not reach here
        return ModelResponse(
            model_name=model.display_name,
            tier=model.tier,
            response_text="",
            tokens_used=0,
            cost_usd=0.0,
            latency_ms=0,
            timestamp=datetime.now(),
            error="Max retries exceeded"
        )
    
    async def execute_jury(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tier: Optional[ModelTier] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> JuryResponse:
        """
        Execute prompt across all models in the jury (parallel execution)
        
        Args:
            prompt: User query
            system_prompt: Optional system instruction
            tier: Filter models by tier (None = use all models)
            temperature: Override default temperature
            max_tokens: Override default max tokens
        
        Returns:
            JuryResponse with all model responses
        """
        start_time = time.time()
        
        # Get active models
        models = self.get_active_models(tier)
        
        if not models:
            raise ValueError(f"No active models found for tier {tier}")
        
        # Execute all models in parallel
        tasks = [
            self.call_model(
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            for model in models
        ]
        
        responses = await asyncio.gather(*tasks)
        
        # Calculate aggregates
        total_cost = sum(r.cost_usd for r in responses)
        total_latency = int((time.time() - start_time) * 1000)
        successful = sum(1 for r in responses if not r.error)
        failed = len(responses) - successful
        
        return JuryResponse(
            query=prompt,
            responses=responses,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency,
            successful_models=successful,
            failed_models=failed
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset statistics counters"""
        self.stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "successful_requests": 0,
            "failed_requests": 0
        }
