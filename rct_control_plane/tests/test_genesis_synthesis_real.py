"""
Real ALGO-39 on-the-fly module synthesis tests — Round 27 Phase 21 Task 45.

Master doc (DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md, section 3, ALGO-39)
specifies "on-the-fly module synthesis when no existing tool supports the
task." The real algo_39_genesis_engine only does static README/.gitignore
scaffolding (already honestly disclosed as such). This adds a real, modest
single-function synthesis capability - a real local-LLM call, a real file
written to disk, and real verification via the existing sandbox (same
proven pattern as Round 26's algo_24_humaneval_style_benchmark) - not a
fabricated "it worked" claim. A harder capability_spec could legitimately
come back verified: False; that would be honest, not a test bug. This test
uses a tightly-specified, deterministic capability that local Ollama has
already proven reliable for (Round 26's HumanEval-style reference
solutions are of comparable simplicity).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

# Round 30 (item 4 of Round 29's candidate list): migrated onto
# shared_kernel - reviewed safe: real LLM call + sandbox execution, pure
# function of the passed capability_spec/function_name/smoke_test_code.


def test_synthesizes_and_verifies_a_real_simple_function(shared_kernel):
    result = asyncio.run(shared_kernel.algo_39_genesis_synthesize_module(
        capability_spec="returns True if the input integer is even, False otherwise",
        function_name="is_even_generated",
        smoke_test_code="assert is_even_generated(4) is True\nassert is_even_generated(3) is False",
    ))

    assert result["synthesized"] is True
    assert os.path.exists(result["file_path"])
    assert result["verified"] is True, f"generated code failed its real smoke test: {result.get('stdout')}"
