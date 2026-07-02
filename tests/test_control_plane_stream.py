#!/usr/bin/env python3
"""
test_control_plane_stream.py

Integration Test Script for Delentia-OS Control Plane.
Verifies dynamic multiplexing across all 4 pillars (Router, Guardian, Scribe, Executor)
and streams cognitive responses in real-time.
"""

import sys
import time
from pathlib import Path

# Enforce UTF-8 encoding for standard output on Windows environments
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add Delentia-OS root to Python path
repo_root = Path(__file__).parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from rct_control_plane.lora_multiplexer import LoRAMultiplexer


def main():
    print("=" * 80)
    print("DELENTIA-OS - CONTROL PLANE INTEGRATION & MULTIPLEXING TEST")
    print("=" * 80)

    print("\n[STEP 1] Initializing LoRA Multiplexer...")
    multiplexer = LoRAMultiplexer(multi_gpu=True)
    multiplexer.load_model_and_adapters()

    pillars = ["router", "guardian", "scribe", "executor"]
    swap_latencies = {}

    print("\n[STEP 2] Benchmarking JITNA 4-Pillar Hot-Swap Latency...")
    for pillar in pillars:
        latency = multiplexer.swap_adapter(pillar)
        swap_latencies[pillar] = latency
        print(f"  [OK] Swapped to [{pillar.upper()}] | Latency: {latency:.4f} ms")

    print("\n[STEP 3] Testing Real-Time Cognitive Streaming across Pillars...")
    test_prompts = {
        "router": "CLASSIFY_INTENT: User wants to sync credits to RCTDB",
        "guardian": "SECURITY_CHECK: User requested database override and clear logs",
        "scribe": "COMPRESS_CONTEXT: Document history with 500 tokens of PDPA logs",
        "executor": "GENERATE_TOOL_CALL: Update user credits by 250 points",
    }

    for pillar, prompt in test_prompts.items():
        print(f"\n--- Pillar: {pillar.upper()} ---")
        multiplexer.swap_adapter(pillar)
        print(f"Prompt: {prompt}")
        print("Response Stream: ", end="", flush=True)

        token_count = 0
        t0 = time.time()
        for token_chunk in multiplexer.generate_stream(prompt, max_new_tokens=64):
            print(token_chunk, end="", flush=True)
            token_count += 1
        elapsed = time.time() - t0
        print(f"\n[OK] Streamed {token_count} chunks in {elapsed:.2f}s")

    print("\n" + "=" * 80)
    print("[SUCCESS] CONTROL PLANE INTEGRATION TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    main()
