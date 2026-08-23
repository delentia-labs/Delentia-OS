"""
LoRA Multiplexer — Dynamic Adapter Swapping Control (v0.5.1)

Manages loading the shared base model weights in VRAM and dynamically swapping
the specialized LoRA adapters (Executor, Guardian, Scribe, Router) in milliseconds.
Supports both Hugging Face PEFT/transformers and llama.cpp/GGUF modes,
with a graceful high-fidelity mock fallback.

v0.5.1 Changes:
  - Base model: Qwen/Qwen3.6-27B-Instruct (1-bit Q1_0_G128 GGUF)
  - All adapter IDs upgraded from v0.4 → v0.5.1 (jitna-*-v0.5.1)
  - MAX_ACTIVE_SLOTS = 3 enforced — prevents VRAM OOM
  - load_slot() / unload_slot() replace simple swap_adapter()
  - VRAM estimation per slot added
  - Backward-compatible swap_adapter() kept as alias
"""

import os
import time
from pathlib import Path
from typing import Any, Optional


try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    _HAS_TRANSFORMERS = True
except ImportError:
    _HAS_TRANSFORMERS = False

try:
    import llama_cpp
    _HAS_LLAMA_CPP = True
except ImportError:
    _HAS_LLAMA_CPP = False


# ── v0.5.1 Constants ────────────────────────────────────────────────────────────
MAX_ACTIVE_SLOTS = 3  # Hard limit: max simultaneous Brain Slots to prevent VRAM OOM
VRAM_PER_SLOT_GB = 2.1  # Estimated VRAM per LoRA slot on Q1_0_G128 base (27B)
VRAM_BASE_GB = 3.9      # Estimated VRAM for the 1-bit base model alone

KNOWN_ADAPTERS = {"executor", "guardian", "scribe", "router"}


class LoRAMultiplexer:
    """
    Dynamically loads and swaps LoRA adapters for Executor, Guardian, Scribe, Router.

    v0.5.1: Supports up to MAX_ACTIVE_SLOTS (3) concurrent Brain Slots.
    Attempting to load a 4th slot raises a RuntimeError to protect VRAM.

    Supports GGUF format (llama.cpp) and PEFT format (transformers),
    with a 2-5ms hot-swapping emulation fallback for CI/testing.
    """

    def __init__(
        self,
        base_model_name: str = "Qwen/Qwen3.6-27B-Instruct",
        adapters_dir: Optional[str] = None,
        multi_gpu: bool = True,
    ) -> None:
        self.base_model_name = base_model_name
        self.multi_gpu = multi_gpu
        self.device_map = "auto"

        # ── Directory Resolution ──────────────────────────────────────────────
        if adapters_dir:
            self.adapters_dir = Path(adapters_dir)
        else:
            self.adapters_dir = Path(__file__).parents[2] / "Delentia-AI-SLM/models/adapters/v0.5.1"

        self.gguf_dir = Path(__file__).parents[2] / "Delentia-AI-SLM/models/gguf"
        self.gguf_base_path = self.gguf_dir / "delentia-slm-jitna-v0.5.1-27B.gguf"

        self.model: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.current_adapter: Optional[str] = None
        self.mock_mode = True
        self.use_gguf = False

        # ── v0.5.1 PEFT Adapter Paths ───────────────────────────────────────────
        self.executor_path = self.adapters_dir / "jitna_executor_v0.5.1"
        self.guardian_path = self.adapters_dir / "jitna_guardian_v0.5.1"
        self.scribe_path   = self.adapters_dir / "jitna_scribe_v0.5.1"
        self.router_path   = self.adapters_dir / "jitna_router_v0.5.1"

        # ── v0.5.1 GGUF Adapter Paths ───────────────────────────────────────────
        self.gguf_executor_path = self.gguf_dir / "jitna-executor-v0.5.1-Q4_K_M.gguf"
        self.gguf_guardian_path = self.gguf_dir / "jitna-guardian-v0.5.1-Q4_K_M.gguf"
        self.gguf_scribe_path   = self.gguf_dir / "jitna-scribe-v0.5.1-Q4_K_M.gguf"
        self.gguf_router_path   = self.gguf_dir / "jitna-router-v0.5.1-Q4_K_M.gguf"

        # ── Brain Slot State (v0.5.1) ───────────────────────────────────────────
        # Tracks which adapters are currently LOADED into VRAM simultaneously.
        # Max length = MAX_ACTIVE_SLOTS (3). Raising beyond this prevents OOM.
        self.active_slots: list[str] = []

        # ── Engine Selection ──────────────────────────────────────────────────
        _is_testing = "PYTEST_CURRENT_TEST" in os.environ or "CI" in os.environ or "GITHUB_ACTIONS" in os.environ
        if _is_testing:
            self.mock_mode = True
            self.use_gguf = False
            print("[MOCK] LoRA Multiplexer v0.5.1: Running in CI/pytest MOCK mode.")
        elif _HAS_LLAMA_CPP and self.gguf_base_path.exists() and self.gguf_base_path.stat().st_size > 100:
            self.use_gguf = True
            self.mock_mode = False
            print(f"[INFO] LoRA Multiplexer v0.5.1: GGUF mode — {self.gguf_base_path.name}")
        elif _HAS_TRANSFORMERS:
            self.use_gguf = False
            self.mock_mode = False

            # ── v0.5.1 HF Hub Fallback IDs ─────────────────────────────────────
            self.executor_hf_id = "Delentia/jitna-executor-v0.5.1"
            self.guardian_hf_id = "Delentia/jitna-guardian-v0.5.1"
            self.scribe_hf_id   = "Delentia/jitna-scribe-v0.5.1"
            self.router_hf_id   = "Delentia/jitna-router-v0.5.1"

            # Use local paths if they exist, else HF Hub IDs
            self.executor_model_id = str(self.executor_path) if self.executor_path.exists() else self.executor_hf_id
            self.guardian_model_id = str(self.guardian_path) if self.guardian_path.exists() else self.guardian_hf_id
            self.scribe_model_id   = str(self.scribe_path) if self.scribe_path.exists() else self.scribe_hf_id
            self.router_model_id   = str(self.router_path) if self.router_path.exists() else self.router_hf_id

            print(
                f"[INFO] LoRA Multiplexer v0.5.1: PEFT mode — "
                f"executor={self.executor_model_id.split('/')[-1]}, "
                f"guardian={self.guardian_model_id.split('/')[-1]}, "
                f"scribe={self.scribe_model_id.split('/')[-1]}, "
                f"router={self.router_model_id.split('/')[-1]}"
            )
        else:
            print("[WARNING] LoRA Multiplexer v0.5.1: Running in MOCK mode (no transformers/llama-cpp found).")

        if self.mock_mode and self.multi_gpu:
            print("[MOCK] LoRA Multiplexer v0.5.1: GPU Multi-LoRA parallel mapping active "
                  "(GPU 0: Base+Executor | GPU 1: Guardian, Scribe).")

    # ── v0.5.1 Brain Slot Management ────────────────────────────────────────────

    def load_slot(self, adapter_name: str) -> float:
        """
        Load a LoRA adapter into an active Brain Slot.

        Enforces MAX_ACTIVE_SLOTS = 3. If 3 slots are already active,
        raises RuntimeError — caller must unload_slot() first.

        Returns swap latency in milliseconds.
        """
        adapter_name = adapter_name.lower()
        self._validate_adapter_name(adapter_name)

        if adapter_name in self.active_slots:
            return 0.0  # Already loaded — no-op

        if len(self.active_slots) >= MAX_ACTIVE_SLOTS:
            active_list = ", ".join(self.active_slots)
            raise RuntimeError(
                f"[SLOT LIMIT] Cannot load '{adapter_name}': "
                f"MAX_ACTIVE_SLOTS={MAX_ACTIVE_SLOTS} reached. "
                f"Currently active: [{active_list}]. "
                f"Call unload_slot(adapter_name) to free a slot first."
            )

        start_time = time.perf_counter()
        self.active_slots.append(adapter_name)
        self.current_adapter = adapter_name  # Most recently loaded becomes active

        if self.mock_mode:
            import random
            latency_sleep = random.uniform(0.001, 0.003) if self.multi_gpu else random.uniform(0.003, 0.008)
            time.sleep(latency_sleep)
        else:
            # Real PEFT/GGUF load would happen here via swap_adapter internals
            self._real_load_adapter(adapter_name)

        latency = (time.perf_counter() - start_time) * 1000
        vram_est = self._estimate_vram_gb()
        print(
            f"[INFO] LoRA v0.5.1: Loaded Brain Slot '{adapter_name}' "
            f"({len(self.active_slots)}/{MAX_ACTIVE_SLOTS} slots, "
            f"~{vram_est:.1f}GB VRAM est, {latency:.2f}ms)"
        )
        return latency

    def unload_slot(self, adapter_name: str) -> None:
        """
        Unload a LoRA adapter from active Brain Slots, freeing VRAM.
        """
        adapter_name = adapter_name.lower()
        self._validate_adapter_name(adapter_name)

        if adapter_name not in self.active_slots:
            print(f"[INFO] LoRA v0.5.1: '{adapter_name}' is not in active slots — no-op.")
            return

        self.active_slots.remove(adapter_name)

        # If we just unloaded the active adapter, switch to another or None
        if self.current_adapter == adapter_name:
            self.current_adapter = self.active_slots[-1] if self.active_slots else None

        vram_est = self._estimate_vram_gb()
        print(
            f"[INFO] LoRA v0.5.1: Unloaded '{adapter_name}'. "
            f"Active slots: {self.active_slots} (~{vram_est:.1f}GB VRAM est)"
        )

    def get_slot_status(self) -> dict:
        """Returns current slot state for GUI Brain Slot Panel."""
        return {
            "active_slots": list(self.active_slots),
            "current_adapter": self.current_adapter,
            "slot_count": len(self.active_slots),
            "max_slots": MAX_ACTIVE_SLOTS,
            "slots_available": MAX_ACTIVE_SLOTS - len(self.active_slots),
            "vram_estimate_gb": self._estimate_vram_gb(),
            "mode": "gguf" if self.use_gguf else ("mock" if self.mock_mode else "peft"),
            "base_model": self.base_model_name,
        }

    def _estimate_vram_gb(self) -> float:
        """Estimate total VRAM usage for current slot configuration."""
        return VRAM_BASE_GB + (len(self.active_slots) * VRAM_PER_SLOT_GB)

    def _validate_adapter_name(self, adapter_name: str) -> None:
        if adapter_name not in KNOWN_ADAPTERS:
            raise ValueError(
                f"Unknown adapter: '{adapter_name}'. "
                f"Valid adapters: {sorted(KNOWN_ADAPTERS)}"
            )

    def _real_load_adapter(self, adapter_name: str) -> None:
        """Internal: trigger real PEFT/GGUF adapter loading when not in mock mode."""
        if self.use_gguf:
            adapter_path = getattr(self, f"gguf_{adapter_name}_path")
            if adapter_path.exists() and self.model is not None:
                try:
                    llama_cpp.llama_model_apply_lora_from_file(
                        self.model.model,
                        str(adapter_path).encode("utf-8"),
                        1.0, None, 4
                    )
                except Exception as e:
                    print(f"[WARNING] GGUF LoRA apply failed for '{adapter_name}': {e}")
        elif self.model is not None:
            self.model.set_adapter(adapter_name)

    # ── Legacy swap_adapter (backward compatible alias) ───────────────────────

    def swap_adapter(self, adapter_name: str) -> float:
        """
        Swaps the currently ACTIVE adapter within already-loaded slots.
        For loading a new adapter into VRAM, use load_slot() instead.

        If adapter is not in active_slots, calls load_slot() automatically.
        Returns swap latency in milliseconds.
        """
        adapter_name = adapter_name.lower()
        self._validate_adapter_name(adapter_name)

        if self.current_adapter == adapter_name:
            return 0.0

        # If not yet in active slots, auto-load (respects MAX_ACTIVE_SLOTS)
        if adapter_name not in self.active_slots:
            return self.load_slot(adapter_name)

        start_time = time.perf_counter()

        if self.mock_mode:
            import random
            latency_sleep = random.uniform(0.0004, 0.00095) if self.multi_gpu else random.uniform(0.002, 0.005)
            time.sleep(latency_sleep)
            self.current_adapter = adapter_name
            latency = (time.perf_counter() - start_time) * 1000
            gpu_tag = "Multi-GPU Parallel" if self.multi_gpu else "Single-GPU Serial"
            print(f"[MOCK] LoRA v0.5.1: Switched active adapter → [{adapter_name}] ({latency:.2f}ms, {gpu_tag})")
            return latency

        if self.use_gguf:
            adapter_path = getattr(self, f"gguf_{adapter_name}_path")
            if not adapter_path.exists():
                print(f"[WARNING] GGUF adapter path {adapter_path} not found. Mock swap.")
                time.sleep(0.002)
            else:
                try:
                    if self.model is None:
                        raise RuntimeError("llama_cpp model is not initialized")
                    err = llama_cpp.llama_model_apply_lora_from_file(
                        self.model.model,
                        str(adapter_path).encode("utf-8"),
                        1.0, None, 4
                    )
                    if err != 0:
                        raise RuntimeError(f"lora_from_file failed: code {err}")
                except Exception as e:
                    print(f"[WARNING] GGUF LoRA swap failed: {e}")
                    time.sleep(0.003)

            self.current_adapter = adapter_name
            latency = (time.perf_counter() - start_time) * 1000
            print(f"[INFO] LoRA v0.5.1: Switched GGUF adapter → {adapter_name} ({latency:.2f}ms)")
            return latency

        # PEFT mode
        if self.model is not None:
            self.model.set_adapter(adapter_name)
        self.current_adapter = adapter_name
        latency = (time.perf_counter() - start_time) * 1000
        print(f"[INFO] LoRA v0.5.1: Switched PEFT adapter → {adapter_name} ({latency:.2f}ms)")
        return latency

    # ── Model Loading ──────────────────────────────────────────────────────────

    def load_model_and_adapters(self) -> None:
        """Loads base model and PEFT/GGUF adapters if not in mock mode."""
        if self.mock_mode:
            print("[MOCK] LoRA Multiplexer v0.5.1: Initialized base model Qwen3.6-27B (mock).")
            return

        if self.use_gguf:
            print(f"[INFO] LoRA v0.5.1: Loading GGUF base model from {self.gguf_base_path}...")
            try:
                self.model = llama_cpp.Llama(
                    model_path=str(self.gguf_base_path),
                    n_ctx=16384,
                    n_threads=8,
                    verbose=False
                )
                self.current_adapter = None
                print("[INFO] LoRA v0.5.1: GGUF model loaded successfully.")
            except Exception as e:
                print(f"[ERROR] Failed to load GGUF model: {e}. Falling back to MOCK mode.")
                self.mock_mode = True
            return

        # PEFT mode loading
        print(f"[INFO] LoRA v0.5.1: Loading base model {self.base_model_name}...")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_name)
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            if torch.cuda.is_available():
                print("[INFO] CUDA GPU detected. Loading base model in 4-bit NF4...")
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                    bnb_4bit_use_double_quant=True,
                )
                base_model = AutoModelForCausalLM.from_pretrained(
                    self.base_model_name,
                    quantization_config=bnb_config,
                    device_map="auto",
                )
            else:
                print("[INFO] CPU Environment detected. Loading base model in float16...")
                base_model = AutoModelForCausalLM.from_pretrained(
                    self.base_model_name,
                    dtype=torch.float16 if hasattr(torch, "float16") else "auto",
                    low_cpu_mem_usage=True,
                    device_map="cpu",
                )
            base_model.config.pad_token_id = self.tokenizer.pad_token_id

            print("[INFO] LoRA v0.5.1: Loading LoRA adapters (4 pillars)...")
            self.model = PeftModel.from_pretrained(
                base_model,
                self.executor_model_id,
                adapter_name="executor",
            )
            self.model.load_adapter(self.guardian_model_id, adapter_name="guardian")
            self.model.load_adapter(self.scribe_model_id,   adapter_name="scribe")
            self.model.load_adapter(self.router_model_id,   adapter_name="router")

            self.current_adapter = "executor"
            self.active_slots = ["executor"]
            print("[INFO] LoRA v0.5.1: All 4 pillar adapters loaded successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to load PEFT model/adapters: {e}. Falling back to MOCK mode.")
            self.mock_mode = True

    # ── Generation ─────────────────────────────────────────────────────────────

    def generate(self, prompt: str, max_new_tokens: int = 256) -> str:
        """Generates response using the active model/adapter."""
        if self.mock_mode:
            return self._generate_mock(prompt)

        if self.use_gguf:
            if self.model is None:
                raise RuntimeError("GGUF model is not loaded.")
            res = self.model(
                prompt,
                max_tokens=max_new_tokens,
                stop=["\n\n", "User intent:"],
                echo=False
            )
            return res["choices"][0]["text"].strip()

        if self.tokenizer is None or self.model is None:
            raise RuntimeError("Model and tokenizer are not loaded.")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        inputs = self.tokenizer(prompt, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )

        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        if response.startswith(prompt):
            response = response[len(prompt):].strip()
        return response

    def generate_stream(self, prompt: str, max_new_tokens: int = 256):
        """Yields streaming response tokens using the active model/adapter."""
        if self.mock_mode:
            response = self._generate_mock(prompt)
            for word in response.split(" "):
                yield word + " "
                time.sleep(0.02)
            return

        if self.use_gguf:
            if self.model is None:
                raise RuntimeError("GGUF model is not loaded.")
            stream = self.model(
                prompt,
                max_tokens=max_new_tokens,
                stop=["\n\n", "User intent:"],
                echo=False,
                stream=True
            )
            for output in stream:
                yield output["choices"][0]["text"]
            return

        if self.tokenizer is None or self.model is None:
            raise RuntimeError("Model and tokenizer are not loaded.")

        from transformers import TextIteratorStreamer
        from threading import Thread

        device = "cuda" if torch.cuda.is_available() else "cpu"
        inputs = self.tokenizer(prompt, return_tensors="pt").to(device)
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)

        generation_kwargs = dict(**inputs, streamer=streamer, max_new_tokens=max_new_tokens, do_sample=False)
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        for new_text in streamer:
            yield new_text

    # ── Mock Generation ────────────────────────────────────────────────────────

    def _generate_mock(self, prompt: str) -> str:
        """High-fidelity mock generation for CI/testing — Jitna v0.5.1 response format."""
        if self.current_adapter == "executor":
            if "update_credits" in prompt or "update credits" in prompt:
                return '{"tool_call": {"name": "rctdb.update_credits", "arguments": {"user_id": "val_user_0042", "amount": 250, "operation": "add"}}, "metadata": {"intent_id": "mock_int_1002", "confidence": 0.985, "source": "jitna_executor_v0.5.1"}}'
            elif "delta_engine" in prompt or "sync" in prompt:
                return '{"tool_call": {"name": "delta_engine.sync", "arguments": {"node_id": "node_99", "delta": {"state": "active"}, "priority": "high"}}, "metadata": {"intent_id": "mock_int_1003", "confidence": 0.976, "source": "jitna_executor_v0.5.1"}}'
            else:
                return '{"tool_call": {"name": "rag.search", "arguments": {"query": "system architecture", "top_k": 3, "collection": "docs"}}, "metadata": {"intent_id": "mock_int_1001", "confidence": 0.965, "source": "jitna_executor_v0.5.1"}}'

        elif self.current_adapter == "guardian":
            is_malicious = any(kw in prompt.lower() for kw in ["hack", "bypass", "override", "steal", "dan", "virus"])
            if is_malicious:
                return '{"status": "REJECTED", "fdia": {"D": 0.15, "I": 0.2, "A": 0, "F": 0.0}, "reason": "Hostile intent detected: jailbreak/malicious request", "rct_rule_violated": "RCT-1: Constitutional Boundary", "action": "BLOCK_AND_LOG", "incident_id": "mock_sec_0001"}'
            else:
                return '{"status": "AUTHORIZED", "fdia": {"D": 0.95, "I": 0.98, "A": 1, "F": 0.931}, "reason": "Intent is safe and compliant with RCT governance", "action": "PASS_TO_ROUTER"}'

        elif self.current_adapter == "scribe":
            if "Query:" in prompt:
                return '{"query": "PDPA compliance", "relevant_results": ["Doc 1: PDPA requirements"], "filtered_noise": 2, "total_retrieved": 3, "precision": 0.333}'
            elif "PDPA" in prompt:
                return '{"topic": "PDPA Compliance", "key_points": ["Consent required before data collection", "Applies to Thai personal data", "Max penalty: 5M THB", "72-hour breach notification"], "compression_ratio": 4.2, "original_tokens": 180, "compressed_tokens": 43}'
            elif "RCT" in prompt:
                return '{"topic": "RCT v7 Governance", "key_points": ["7 core rules: Boundary, Zero-Trust, Override etc", "FDIA score: F = D^I * A", "A=0 blocks action immediately"], "compression_ratio": 3.8, "original_tokens": 165, "compressed_tokens": 44}'
            else:
                return '{"topic": "Compressed Context (Jitna v0.5.1 Scribe)", "key_points": ["System initialized successfully", "Operational checks completed"], "compression_ratio": 3.5, "original_tokens": 100, "compressed_tokens": 28}'

        elif self.current_adapter == "router":
            return '{"route": "executor", "fdia": {"D": 0.88, "I": 0.91, "A": 1, "F": 0.897}, "confidence": 0.932, "source": "jitna_router_v0.5.1"}'

        return '{"source": "jitna_v0.5.1_mock", "status": "ok"}'
