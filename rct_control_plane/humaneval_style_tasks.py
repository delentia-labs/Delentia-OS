"""
HumanEval-style micro-benchmark task set — Round 26 Phase 18 Task 40.

Master doc (DELENTIA_OS_MASTER_SYSTEM_ARCHITECTURE.md, section 3, ALGO-24
Benchmark Suite) specifies running "เกณฑ์มาตรฐาน GAIA และ HumanEval"
(GAIA and HumanEval benchmarks) for accuracy. The real `KernelBenchmarkSuite`
(algorithm_kernel_41.py's algo_24_benchmark) only measures real wall-clock
LATENCY of the kernel's own methods — no correctness/accuracy scoring of
any kind exists.

This module is HONESTLY scoped: 5 real, small coding problems with a real
reference solution and a real assert-based test each, executed for real via
the existing sandbox (sandbox.run_sandboxed) — never claiming to be the
official 164-problem HumanEval suite.
"""

from __future__ import annotations

from typing import Dict, List

HUMANEVAL_STYLE_TASKS: List[Dict[str, str]] = [
    {
        "task_id": "is_palindrome",
        "prompt": "Write is_palindrome(s: str) -> bool that returns True iff s reads the same forwards and backwards.",
        "reference_solution": "def is_palindrome(s):\n    return s == s[::-1]",
        "test_code": "assert is_palindrome('racecar') is True\nassert is_palindrome('abc') is False",
    },
    {
        "task_id": "factorial",
        "prompt": "Write factorial(n: int) -> int computing n!.",
        "reference_solution": "def factorial(n):\n    result = 1\n    for i in range(2, n + 1):\n        result *= i\n    return result",
        "test_code": "assert factorial(0) == 1\nassert factorial(5) == 120",
    },
    {
        "task_id": "is_prime",
        "prompt": "Write is_prime(n: int) -> bool.",
        "reference_solution": "def is_prime(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n ** 0.5) + 1):\n        if n % i == 0:\n            return False\n    return True",
        "test_code": "assert is_prime(7) is True\nassert is_prime(8) is False\nassert is_prime(1) is False",
    },
    {
        "task_id": "reverse_string",
        "prompt": "Write reverse_string(s: str) -> str.",
        "reference_solution": "def reverse_string(s):\n    return s[::-1]",
        "test_code": "assert reverse_string('hello') == 'olleh'\nassert reverse_string('') == ''",
    },
    {
        "task_id": "nth_fibonacci",
        "prompt": "Write nth_fibonacci(n: int) -> int, 0-indexed (nth_fibonacci(0) == 0, nth_fibonacci(1) == 1).",
        "reference_solution": "def nth_fibonacci(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a",
        "test_code": "assert nth_fibonacci(0) == 0\nassert nth_fibonacci(1) == 1\nassert nth_fibonacci(10) == 55",
    },
]
