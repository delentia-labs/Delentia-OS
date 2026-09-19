"""
Real ALGO-24 HumanEval-style correctness benchmark tests — Round 26 Phase 18
Task 40.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41


def test_reference_solutions_all_pass_real_execution():
    kernel = AlgorithmKernel41()
    result = asyncio.run(kernel.algo_24_humaneval_style_benchmark())

    assert result["pass_rate"] == 1.0, f"expected all real reference solutions to pass; got {result['task_results']}"
    assert len(result["task_results"]) == 5


def test_a_deliberately_broken_candidate_solution_fails_for_real():
    kernel = AlgorithmKernel41()
    broken = {"is_palindrome": "def is_palindrome(s):\n    return True"}  # wrong: always True

    result = asyncio.run(kernel.algo_24_humaneval_style_benchmark(candidate_solutions=broken))

    palindrome_result = next(r for r in result["task_results"] if r["task_id"] == "is_palindrome")
    assert palindrome_result["passed"] is False
    assert result["pass_rate"] < 1.0
