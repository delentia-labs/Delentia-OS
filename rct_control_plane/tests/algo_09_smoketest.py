"""
Smoke test for ALGO-09 Reflexion+ (real 5-step loop, real Ollama calls,
real ALGO-10-backed memory). Run directly:
    python rct_control_plane/tests/algo_09_smoketest.py

Uses a low quality_threshold and max_iterations=2 to keep wall-clock time
bounded (each iteration issues 3 live Ollama calls at ~15-20s each) while
still exercising the real generate -> judge -> reflect -> (maybe repeat)
loop, the real ConvergenceDetector, and the real ALGO-10 memory
store/retrieve round trip.
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algo_09_reflexion_plus import ReflexionEngine


async def main():
    print("=" * 70)
    print("ALGO-09 Reflexion+ smoke test (live Ollama + ALGO-10 memory)")
    print("=" * 70)

    engine = ReflexionEngine(
        quality_threshold=0.5,   # low bar so the loop can converge quickly
        max_iterations=2,
        use_memory=True,
    )

    query = "In one or two sentences, what is the capital of France and why is it significant?"
    print(f"\nQuery: {query}")
    print(f"Model: {engine.model} @ {engine.llm_url}")
    print("Starting reflexion cycle (real generate -> judge -> reflect loop)...\n")

    session_id = await engine.start_reflexion(query)

    status = engine.get_status(session_id)
    print(f"session_id: {session_id}")
    print(f"status: {status['status']}")
    print(f"iterations run: {status['current_iteration']}")
    print(f"best_score: {status['best_score']}")
    assert status["status"] == "complete"
    assert status["current_iteration"] >= 1

    result = engine.get_final_result(session_id)
    print("\n--- REAL OLLAMA GENERATED ANSWER (final_answer) ---")
    print(result["final_answer"])
    print("\n--- REAL OLLAMA JUDGE FEEDBACK (iteration 1) ---")
    first = result["all_attempts"][0]
    print(f"score={first['score']}")
    print(f"feedback={first['feedback']}")
    print(f"strengths={first['strengths']}")
    print(f"weaknesses={first['weaknesses']}")
    print("\n--- REAL OLLAMA REFLECTION (iteration 1) ---")
    print(first["reflection"])

    assert isinstance(result["final_answer"], str) and len(result["final_answer"]) > 0
    assert isinstance(first["score"], float)

    # Real ALGO-10 memory round trip: the session should now be retrievable.
    stats = await engine.memory.get_reflexion_stats()
    print("\n--- ALGO-10 memory stats after this session ---")
    print(stats)
    assert stats["reflexion_sessions_stored"] >= 1

    similar = await engine.memory.retrieve_similar_reflexions(query="capital of France", limit=3, min_score=0.0)
    print(f"\nretrieve_similar_reflexions('capital of France') -> {len(similar)} match(es)")
    assert len(similar) >= 1
    assert similar[0]["session_id"] == session_id

    print("\nALL ALGO-09 ASSERTIONS PASSED (real Ollama + real ALGO-10 memory)")


if __name__ == "__main__":
    asyncio.run(main())
