"""
Round 54: is TOON (ALGO-42, toon_formatter.py) worth putting in the agent's prompts?

The module claims "40-50% fewer tokens than JSON". The Master document also calls it "Typed Object Oriented Notation" with
a schema role; it is a token-saving serialisation, not a type system. This measures the saving on payloads the runtime
really builds, with the tokenizer the cost estimate uses (tiktoken cl100k when installed), against compact JSON
(no spaces after separators) and against indented JSON, and checks that the round trip is lossless.

    python scripts/measure_toon_tokens.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def count_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, -(-len(text) // 4))


def payloads() -> Dict[str, Any]:
    import asyncio
    from rct_control_plane.mcp_server import mcp
    tools = [{"name": t.name, "description": (t.description or "").strip()[:140]} for t in asyncio.run(mcp.list_tools())]
    runs = [{"iterations": 2 + i % 3, "duration_s": round(1.5 + i * 0.37, 2), "finished": 1, "aligned_with_intent": i % 2, "tool_calls": 1 + i % 2,
             "data_D": round(0.6 + (i % 5) * 0.07, 2), "route_path": "fast" if i % 2 else "slow", "stopped_reason": "llm_finished"} for i in range(20)]
    audit = [{"id": 1000 + i, "entity_type": "governed_loop_fdia_gate", "action": "fdia_gate_evaluated", "actor": f"user-{i % 3}",
              "changes": {"tool_name": "delentia_read_repo_file", "D": 0.9, "I": 1.0, "A": 1.0, "F": 0.9, "blocked": False}} for i in range(12)]
    packet = {"packet_id": "6afff5d6-7fa3-4f2c-92b0-b1a77fd42a93", "source_agent_id": "gateway_api", "message_type": "intent_request", "priority": 3,
              "payload": {"intent": "สรุปกฎหมาย PDPA ให้ผู้บริหาร", "income": 1000000, "tags": ["finance", "thai_tax"]}}
    memories = [{"memory_id": f"m{i}", "content": f"The staging database for project {i} is orion-stage-{i}", "score": round(0.9 - i * 0.05, 2)} for i in range(8)]
    prose = {"final_answer": "The project is called sample-service and the version is 0.3.1. It is a tiny service used to exercise the agent. " * 3}
    return {"tool list (36 name + description)": tools, "experiment runs (20 uniform rows)": runs, "audit rows (12, nested)": audit,
            "one JITNA-style packet": packet, "recalled memories (8)": memories, "one long answer (prose)": prose}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    from rct_control_plane.toon_formatter import toon_deserialize, toon_serialize
    rows: List[Dict[str, Any]] = []
    for name, data in payloads().items():
        compact = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
        toon = toon_serialize(data)
        try:
            lossless = toon_deserialize(toon) == data
        except Exception:
            lossless = False
        c, p, t = count_tokens(compact), count_tokens(pretty), count_tokens(toon)
        rows.append({"payload": name, "json_compact_tokens": c, "json_indented_tokens": p, "toon_tokens": t,
                     "vs_compact_pct": round(100 * (c - t) / c, 1), "vs_indented_pct": round(100 * (p - t) / p, 1), "lossless_round_trip": lossless})
    print(f"{'payload':38} {'compact':>8} {'indented':>9} {'toon':>6} {'saves vs compact':>17} {'vs indented':>12} {'lossless':>9}")
    for r in rows:
        print(f"{r['payload']:38} {r['json_compact_tokens']:>8} {r['json_indented_tokens']:>9} {r['toon_tokens']:>6} {r['vs_compact_pct']:>16}% {r['vs_indented_pct']:>11}% {str(r['lossless_round_trip']):>9}")
    total_c = sum(r["json_compact_tokens"] for r in rows)
    total_t = sum(r["toon_tokens"] for r in rows)
    print(f"\nall payloads together: compact JSON {total_c} tokens, TOON {total_t} tokens ({round(100 * (total_c - total_t) / total_c, 1)}% vs compact)")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
