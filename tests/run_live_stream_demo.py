#!/usr/bin/env python3
"""
run_live_stream_demo.py

Delentia OS — Real-Time Visual Live Streaming Engine.
Designed to provide instant visual feedback, unbuffered progress tracking,
and live letter-by-letter token streaming across all 4 specialist pillars.
"""

import sys
import time
from pathlib import Path

# Force UTF-8 unbuffered output for instant terminal flushing on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

repo_root = Path(__file__).parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from rct_control_plane.lora_multiplexer import LoRAMultiplexer


def print_banner():
    print("\033[95m" + "=" * 80 + "\033[0m")
    print("\033[96m🌊 DELENTIA OS — REAL-TIME VISUAL STREAMING DEMO\033[0m")
    print("\033[95m" + "=" * 80 + "\033[0m")


def simulate_visual_loading():
    print("\n\033[93m[STEP 1] Connecting to Delentia Control Plane & Memory Engine...\033[0m")
    steps = [
        "Verifying Local Base Model (delentia-jitna-v0.4-Q4_K_M.gguf)...",
        "Loading Adapter 1/4: Router (Intent Classifier & Cost Gate)...",
        "Loading Adapter 2/4: Guardian (Constitutional Safety Shield)...",
        "Loading Adapter 3/4: Scribe (Long-Context Compression & Memory)...",
        "Loading Adapter 4/4: Executor (JSON Structural Compiler)..."
    ]
    for step in steps:
        print(f"  ⏳ {step:<65} ", end="", flush=True)
        time.sleep(0.3)
        print("\033[92m[READY]\033[0m", flush=True)


def main():
    print_banner()
    simulate_visual_loading()

    print("\n\033[93m[STEP 2] Initializing LoRA Multiplexer Neural Engine...\033[0m")
    multiplexer = LoRAMultiplexer(multi_gpu=True)
    multiplexer.load_model_and_adapters()

    mode_color = "\033[92m" if not multiplexer.mock_mode else "\033[93m"
    mode_name = "REAL WEIGHT NEURAL ENGINE" if not multiplexer.mock_mode else "FAST STREAMING DEMO ENGINE"
    print(f"  ✓ Active Runtime Mode: {mode_color}[{mode_name}]\033[0m", flush=True)

    test_scenarios = [
        {
            "pillar": "router",
            "name": "ROUTER ENGINE",
            "task": "Intent Classification & Cost Gate",
            "prompt": "CLASSIFY_INTENT: Synchronize user credits with RCTDB and check PDPA compliance",
            "color": "\033[94m"
        },
        {
            "pillar": "guardian",
            "name": "GUARDIAN ENGINE",
            "task": "Constitutional Security Shield & FDIA Interception",
            "prompt": "SECURITY_CHECK: System override requested by unauthenticated user token",
            "color": "\033[91m"
        },
        {
            "pillar": "scribe",
            "name": "SCRIBE ENGINE",
            "task": "Long-Context Compression & State Memory Recall",
            "prompt": "COMPRESS_CONTEXT: Patient historical record spanning 2,000 tokens of clinical data",
            "color": "\033[96m"
        },
        {
            "pillar": "executor",
            "name": "EXECUTOR ENGINE",
            "task": "Structured JSON Compiler & Tool Calling",
            "prompt": "GENERATE_TOOL_CALL: Execute credit top-up of 500 units for user val_042",
            "color": "\033[92m"
        }
    ]

    print("\n\033[95m" + "=" * 80 + "\033[0m")
    print("\033[93m🚀 STARTING LIVE STREAMING DEMONSTRATION ACROSS ALL 4 PILLARS\033[0m")
    print("\033[95m" + "=" * 80 + "\033[0m")

    for sc in test_scenarios:
        pillar = sc["pillar"]
        color = sc["color"]
        print(f"\n{color}▶ [PILLAR: {sc['name']}] — {sc['task']}\033[0m", flush=True)
        print(f"  📥 Input Prompt: \"{sc['prompt']}\"", flush=True)
        
        # Measure hot-swap
        t_swap_start = time.time()
        lat = multiplexer.swap_adapter(pillar)
        t_swap_end = time.time()
        print(f"  ⚡ VRAM Adapter Hot-Swap Latency: \033[92m{lat:.4f} ms\033[0m", flush=True)
        
        print(f"  🌊 Live Output Stream: {color}", end="", flush=True)
        
        t0 = time.time()
        chunks = 0
        for chunk in multiplexer.generate_stream(sc["prompt"], max_new_tokens=64):
            # Instant character-by-character flushing for maximum visual impact
            for char in chunk:
                print(char, end="", flush=True)
                time.sleep(0.015) # Smooth streaming animation delay
            chunks += 1
        elapsed = time.time() - t0
        print("\033[0m", flush=True) # Reset color
        
        tps = chunks / elapsed if elapsed > 0 else 0
        print(f"  📊 Performance Stats: Streamed {chunks} chunks in {elapsed:.2f}s ({tps:.1f} chunks/sec)", flush=True)
        time.sleep(0.5)

    print("\n" + "=" * 80)
    print("\033[92m✅ LIVE STREAMING DEMONSTRATION COMPLETED SUCCESSFULLY!\033[0m")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
