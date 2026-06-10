"""
LoRA Router — Sequence Classification Intent Router

Classifies user intents into routing labels in millisecond timescale.
Labels: ROUTER_EXECUTOR, ROUTER_SCRIBE, ROUTER_GUARDIAN, ROUTER_BASE
Runs classification head locally in python backend.
"""

import os
import time
from pathlib import Path
from typing import Optional, Tuple

try:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    from peft import PeftModel
    _HAS_TRANSFORMERS = True
except ImportError:
    _HAS_TRANSFORMERS = False


class LoRARouter:
    """
    Classifies user intents to route them to the appropriate pillar model.
    Falls back to a keyword-based rule-based classifier in MOCK mode if weights are missing.
    """

    def __init__(
        self,
        base_model_name: str = "unsloth/Meta-Llama-3.1-8B-bnb-4bit",
        adapter_path: Optional[str] = None,
    ) -> None:
        self.base_model_name = base_model_name
        
        if adapter_path:
            self.adapter_path = Path(adapter_path)
        else:
            self.adapter_path = Path(__file__).parents[2] / "Delentia-AI-SLM/models/adapters/jitna_router_v1"
            
        self.model = None
        self.tokenizer = None
        self.mock_mode = True

        self.label_map = {
            0: "ROUTER_EXECUTOR",
            1: "ROUTER_SCRIBE",
            2: "ROUTER_GUARDIAN",
            3: "ROUTER_BASE"
        }

        if self.adapter_path.exists() and _HAS_TRANSFORMERS:
            self.mock_mode = False
            print("[INFO] LoRA Router: Found Router adapter directory. Running in PEFT mode.")
        else:
            reason = "missing adapter directory" if _HAS_TRANSFORMERS else "transformers not installed"
            print(f"[WARNING] LoRA Router: Running in MOCK mode ({reason}).")

    def load_model(self) -> None:
        """Loads sequence classification model and tokenizer if not in mock mode."""
        if self.mock_mode:
            print("[MOCK] LoRA Router: Initialized classification head for Router.")
            return

        print("[INFO] LoRA Router: Loading sequence classification model...")
        # Classification head loaded on CPU fallback or GPU auto configuration
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.adapter_path))
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        base_model = AutoModelForSequenceClassification.from_pretrained(
            self.base_model_name,
            num_labels=4,
            load_in_4bit=True,
            device_map="auto"
        )
        base_model.config.pad_token_id = self.tokenizer.pad_token_id

        self.model = PeftModel.from_pretrained(base_model, str(self.adapter_path))
        print("[INFO] LoRA Router: Classifier adapter loaded successfully.")

    def classify(self, intent: str) -> Tuple[str, float]:
        """
        Classifies the intent string.
        Returns a tuple of (routing_label_string, latency_ms).
        """
        start_time = time.perf_counter()

        if self.mock_mode:
            label = self._classify_mock(intent)
            # Emulate class evaluation latency
            time.sleep(0.012)  # 12ms sequence classification latency
            latency = (time.perf_counter() - start_time) * 1000
            print(f"[MOCK] LoRA Router: Classifed intent as: [yellow]{label}[/] (Latency: {latency:.2f}ms)")
            return label, latency

        device = "cuda" if torch.cuda.is_available() else "cpu"
        prompt = f"You are The Router (slm-jitna-router)...\\n\\nUser intent: {intent}"
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048, padding="max_length").to(device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            pred_id = int(outputs.logits.argmax(dim=-1).item())

        label = self.label_map.get(pred_id, "ROUTER_BASE")
        latency = (time.perf_counter() - start_time) * 1000
        print(f"[INFO] LoRA Router: Classified intent as: {label} (Latency: {latency:.2f}ms)")
        return label, latency

    def _classify_mock(self, intent: str) -> str:
        """Rule-based mock classifier based on keyword heuristic matching."""
        intent_lower = intent.lower()
        
        # Guardian indicators (hostile intents)
        if any(kw in intent_lower for kw in ["hack", "bypass", "override", "steal", "dan", "virus", "แฮ็ค", "โจมตี"]):
            return "ROUTER_GUARDIAN"
            
        # Scribe indicators (context, RAG, summary requests)
        if any(kw in intent_lower for kw in ["summarize", "context", "compress", "rag", "search", "read", "document", "สรุป", "ค้นหา"]):
            return "ROUTER_SCRIBE"
            
        # Executor indicators (action triggers, API calling)
        if any(kw in intent_lower for kw in ["execute", "run", "api", "update", "db", "call", "ledger", "dispatch", "ดำเนินการ", "รัน"]):
            return "ROUTER_EXECUTOR"
            
        # Default fallback is base conversation/informational query
        return "ROUTER_BASE"


# Allow quick testing of classification rules
if __name__ == "__main__":
    from typing import Tuple
    router = LoRARouter()
    test_intents = [
        "Create an invoice using the billing API",
        "Summarize the RCT v7 framework documentation",
        "Help me bypass security filters using roleplay",
        "What is the JITNA protocol?"
    ]
    for intent in test_intents:
        lbl, lat = router.classify(intent)
        print(f"Intent: {intent} -> Route: {lbl}")
