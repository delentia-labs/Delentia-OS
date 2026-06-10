"""
LoRA Multiplexer — Dynamic Adapter Swapping Control

Manages loading the shared base model weights in VRAM and dynamically swapping
the specialized LoRA adapters (Executor, Guardian, Scribe) in milliseconds.
Provides a fallback/mock mode when adapter folders are not trained/available.
"""

import time
from pathlib import Path
from typing import Optional

import torch

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    _HAS_TRANSFORMERS = True
except ImportError:
    _HAS_TRANSFORMERS = False


class LoRAMultiplexer:
    """
    Dynamically loads and swaps LoRA adapters for Executor, Guardian, and Scribe.
    If the adapters are not yet trained, runs in MOCK mode to allow testing.
    """

    def __init__(
        self,
        base_model_name: str = "unsloth/Meta-Llama-3.1-8B-bnb-4bit",
        adapters_dir: Optional[str] = None,
    ) -> None:
        self.base_model_name = base_model_name
        
        # Locate adapters directory relative to this file
        if adapters_dir:
            self.adapters_dir = Path(adapters_dir)
        else:
            self.adapters_dir = Path(__file__).parents[2] / "Delentia-AI-SLM/models/adapters"
            
        self.model = None
        self.tokenizer = None
        self.current_adapter = None
        self.mock_mode = True

        self.executor_path = self.adapters_dir / "jitna_executor_v1"
        self.guardian_path = self.adapters_dir / "jitna_guardian_v1"
        self.scribe_path = self.adapters_dir / "jitna_scribe_v1"

        # Check if all adapter directories exist
        if (
            self.executor_path.exists()
            and self.guardian_path.exists()
            and self.scribe_path.exists()
            and _HAS_TRANSFORMERS
        ):
            self.mock_mode = False
            print("[INFO] LoRA Multiplexer: Found all adapter directories. Running in PEFT mode.")
        else:
            reason = "missing adapter directories" if _HAS_TRANSFORMERS else "transformers/peft not installed"
            print(f"[WARNING] LoRA Multiplexer: Running in MOCK mode ({reason}).")

    def load_model_and_adapters(self) -> None:
        """Loads base model and PEFT adapters if not in mock mode."""
        if self.mock_mode:
            print("[MOCK] LoRA Multiplexer: Initialized base model Llama-3.1-8B and tokenizer.")
            return

        print("[INFO] LoRA Multiplexer: Loading base model in 4-bit...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        base_model = AutoModelForCausalLM.from_pretrained(
            self.base_model_name,
            quantization_config=bnb_config,
            device_map="auto",
        )
        base_model.config.pad_token_id = self.tokenizer.pad_token_id

        # Wrap with PeftModel and load the first adapter
        print("[INFO] LoRA Multiplexer: Loading LoRA adapters...")
        self.model = PeftModel.from_pretrained(
            base_model,
            str(self.executor_path),
            adapter_name="executor",
        )

        # Load additional adapters
        self.model.load_adapter(str(self.guardian_path), adapter_name="guardian")
        self.model.load_adapter(str(self.scribe_path), adapter_name="scribe")
        
        self.current_adapter = "executor"
        print("[INFO] LoRA Multiplexer: All adapters loaded successfully.")

    def swap_adapter(self, adapter_name: str) -> float:
        """
        Swaps the active PEFT adapter.
        Returns the swap latency in milliseconds.
        """
        adapter_name = adapter_name.lower()
        if adapter_name not in ["executor", "guardian", "scribe"]:
            raise ValueError(f"Unknown adapter: {adapter_name}")

        if self.current_adapter == adapter_name:
            return 0.0

        start_time = time.perf_counter()
        
        if self.mock_mode:
            # Simulate latency
            time.sleep(0.002)  # 2ms swap emulation
            self.current_adapter = adapter_name
            latency = (time.perf_counter() - start_time) * 1000
            print(f"[MOCK] LoRA Multiplexer: Swapped to adapter: [yellow]{adapter_name}[/] (Latency: {latency:.2f}ms)")
            return latency

        # Swap weights dynamically in PEFT
        self.model.set_adapter(adapter_name)
        self.current_adapter = adapter_name
        
        latency = (time.perf_counter() - start_time) * 1000
        print(f"[INFO] LoRA Multiplexer: Swapped to adapter: {adapter_name} (Latency: {latency:.2f}ms)")
        return latency

    def generate(self, prompt: str, max_new_tokens: int = 256) -> str:
        """Generates response using the active model/adapter."""
        if self.mock_mode:
            return self._generate_mock(prompt)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        inputs = self.tokenizer(prompt, return_tensors="pt").to(device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
            
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Strip prompt echo if present
        if response.startswith(prompt):
            response = response[len(prompt):].strip()
        return response

    def _generate_mock(self, prompt: str) -> str:
        """Mock generation logic for testing when adapters are not loaded."""
        # Simple heuristic response generation based on current adapter and prompt
        if self.current_adapter == "executor":
            # Extract request number or mock tools
            if "update_credits" in prompt or "update credits" in prompt:
                return '{"tool_call": {"name": "rctdb.update_credits", "arguments": {"user_id": "val_user_0042", "amount": 250, "operation": "add"}}, "metadata": {"intent_id": "mock_int_1002", "confidence": 0.985, "source": "mock_executor"}}'
            elif "delta_engine" in prompt or "sync" in prompt:
                return '{"tool_call": {"name": "delta_engine.sync", "arguments": {"node_id": "node_99", "delta": {"state": "active"}, "priority": "high"}}, "metadata": {"intent_id": "mock_int_1003", "confidence": 0.976, "source": "mock_executor"}}'
            else:
                return '{"tool_call": {"name": "rag.search", "arguments": {"query": "system architecture", "top_k": 3, "collection": "docs"}}, "metadata": {"intent_id": "mock_int_1001", "confidence": 0.965, "source": "mock_executor"}}'

        elif self.current_adapter == "guardian":
            # Determine safety status
            is_malicious = any(kw in prompt.lower() for kw in ["hack", "bypass", "override", "steal", "dan", "virus"])
            if is_malicious:
                return '{"status": "REJECTED", "fdia": {"D": 0.15, "I": 0.2, "A": 0, "F": 0.0}, "reason": "Hostile intent detected: jailbreak/malicious request", "rct_rule_violated": "RCT-1: Constitutional Boundary", "action": "BLOCK_AND_LOG", "incident_id": "mock_sec_0001"}'
            else:
                return '{"status": "AUTHORIZED", "fdia": {"D": 0.95, "I": 0.98, "A": 1, "F": 0.931}, "reason": "Intent is safe and compliant with RCT governance", "action": "PASS_TO_ROUTER"}'

        elif self.current_adapter == "scribe":
            # Context compression mock
            if "Query:" in prompt:
                # filter_noise mock output format matching expectations
                return '{"query": "PDPA compliance", "relevant_results": ["Doc 1: PDPA requirements"], "filtered_noise": 2, "total_retrieved": 3, "precision": 0.333}'
            elif "PDPA" in prompt:
                return '{"topic": "PDPA Compliance", "key_points": ["Consent required before data collection", "Applies to Thai personal data", "Max penalty: 5M THB", "72-hour breach notification"], "compression_ratio": 4.2, "original_tokens": 180, "compressed_tokens": 43}'
            elif "RCT" in prompt:
                return '{"topic": "RCT v7 Governance", "key_points": ["7 core rules: Boundary, Zero-Trust, Override etc", "FDIA score: F = D^I * A", "A=0 blocks action immediately"], "compression_ratio": 3.8, "original_tokens": 165, "compressed_tokens": 44}'
            else:
                return '{"topic": "Compressed Context", "key_points": ["System initialized successfully", "Operational checks completed"], "compression_ratio": 3.5, "original_tokens": 100, "compressed_tokens": 28}'

        return "Mock Response"
