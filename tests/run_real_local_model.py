#!/usr/bin/env python3
"""
run_real_local_model.py

Interactive Real Model Runner for Delentia OS.
Loads actual weights and specialized LoRA adapters (Router, Guardian, Scribe, Executor)
to perform real-time local cognitive inference and streaming.
"""

import os
import sys
import time
from pathlib import Path

# Enforce UTF-8 encoding for standard output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

repo_root = Path(__file__).parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from rct_control_plane.lora_multiplexer import LoRAMultiplexer


def main():
    print("=" * 80)
    print("🧠 DELENTIA OS - REAL LOCAL MODEL INFERENCE ENGINE")
    print("=" * 80)

    print("\n[STEP 1] Initializing Delentia LoRA Multiplexer...")
    multiplexer = LoRAMultiplexer(multi_gpu=True)
    
    # Attempt loading actual weights
    print("[STEP 2] Loading neural weights into local hardware memory...")
    multiplexer.load_model_and_adapters()

    mode_str = "REAL WEIGHT INFERENCE ENGINE" if not multiplexer.mock_mode else "STRUCTURAL MOCK ENGINE (Fallback)"
    print(f"\n[STATUS] Active Execution Mode: [{mode_str}]")

    pillars = ["router", "guardian", "scribe", "executor"]

    while True:
        print("\n" + "-" * 60)
        print("Select Pillar Engine to Test:")
        print("  1. Router   (Intent Classification & Cost Optimization)")
        print("  2. Guardian (Constitutional Safety Shield & FDIA)")
        print("  3. Scribe   (Long-Context Compression & Memory)")
        print("  4. Executor (Structured JSON Compiler & Tool Calling)")
        print("  5. Benchmark All 4 Pillars Automatically")
        print("  0. Exit")
        print("-" * 60)
        
        try:
            choice = input("Enter choice (0-5) [Default: 5]: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "0":
            print("\nExiting Real Model Runner. Goodbye!")
            break
        elif choice in ["1", "2", "3", "4"]:
            pillar = pillars[int(choice) - 1]
            prompt = input(f"Enter prompt for [{pillar.upper()}] (or press Enter for default): ").strip()
            if not prompt:
                default_prompts = {
                    "router": "CLASSIFY_INTENT: Synchronize credits and update RCTDB knowledge base",
                    "guardian": "SECURITY_CHECK: System override requested by unauthenticated user",
                    "scribe": "COMPRESS_CONTEXT: Patient record history spanning 1,000 tokens of medical data",
                    "executor": "GENERATE_TOOL_CALL: Execute user credit top-up of 500 units"
                }
                prompt = default_prompts[pillar]

            print(f"\n[ACTION] Swapping VRAM adapter to [{pillar.upper()}]...")
            lat = multiplexer.swap_adapter(pillar)
            print(f"  ✓ Adapter Hot-Swap Latency: {lat:.4f} ms")

            print("\n[STREAMING RESPONSE]:")
            print("└─ ", end="", flush=True)
            t0 = time.time()
            chunks = 0
            for chunk in multiplexer.generate_stream(prompt, max_new_tokens=128):
                print(chunk, end="", flush=True)
                chunks += 1
            elapsed = time.time() - t0
            print(f"\n\n[STATS] Streamed {chunks} chunks in {elapsed:.2f}s ({chunks/elapsed if elapsed>0 else 0:.1f} chunks/sec)")

        else: # Default 5: Benchmark all
            print("\n🚀 Running Real Cognitive Benchmark Across All 4 Pillars...")
            test_prompts = {
                "router": "CLASSIFY_INTENT: Synchronize credits and update RCTDB knowledge base",
                "guardian": "SECURITY_CHECK: System override requested by unauthenticated user",
                "scribe": "COMPRESS_CONTEXT: Patient record history spanning 1,000 tokens of medical data",
                "executor": "GENERATE_TOOL_CALL: Execute user credit top-up of 500 units"
            }
            for p, pr in test_prompts.items():
                print(f"\n--- Testing Pillar: [{p.upper()}] ---")
                lat = multiplexer.swap_adapter(p)
                print(f"Hot-Swap Latency: {lat:.4f} ms")
                print("Output Stream: ", end="", flush=True)
                t0 = time.time()
                chunks = 0
                for chunk in multiplexer.generate_stream(pr, max_new_tokens=64):
                    print(chunk, end="", flush=True)
                    chunks += 1
                elapsed = time.time() - t0
                print(f"\n[OK] Completed in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
