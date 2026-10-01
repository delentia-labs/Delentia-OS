"""
Round 52: the linear-time scans in safe_text.py return exactly what the regular expressions they
replaced returned (CodeQL py/polynomial-redos flagged those). The original patterns live here as the
oracle; the inputs are thousands of random strings over a small alphabet chosen to hit every edge
(identifier runs, digits at the start, dots and slashes, quotes, backticks, parentheses, braces),
plus the adversarial shape CodeQL describes. A final test checks the time stays flat as the input grows.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import random
import re
import time

import pytest

from rct_control_plane import safe_text as st

OLD_JSON = re.compile(r"\{.*\}", re.DOTALL)
OLD_SUBST = re.compile(r"\$\(([^)]*)\)|`([^`]*)`")
OLD_FILE = re.compile(r"([a-z_][a-z0-9_]*\.(py|js|ts|java|cpp|go|rs|rb))")
OLD_PATH = re.compile(r"([a-z_./][a-z0-9_./]*[a-z0-9_])")
OLD_TOKENS = re.compile(r"(\d+)\s*tokens?")
OLD_PARAMS = re.compile(r"parameters\s*\{([^}]*)\}", re.DOTALL)
OLD_ASSIGN = re.compile(r"(\w+)\s*=\s*(.+)")
OLD_EDGE = re.compile(r"^[./-]+|[./-]+$")


def strings(alphabet, count=4000, longest=24, seed=7):
    rng = random.Random(seed)
    for _ in range(count):
        yield "".join(rng.choice(alphabet) for _ in range(rng.randint(0, longest)))


def test_json_span():
    for s in strings(list("{}ab \n"), longest=14):
        m = OLD_JSON.search(s)
        assert st.json_object_span(s) == (m.group(0) if m else None), repr(s)


def test_substitutions():
    for s in strings(list("$()`ab \n"), longest=16):
        want = [(m.group(1) if m.group(1) is not None else m.group(2)) for m in OLD_SUBST.finditer(s)]
        assert st.substitutions(s) == want, repr(s)


def test_filenames():
    alphabet = list("ab_9.") + ["py", "js", "ts", "java", "cpp", "go", "rs", "rb", "c", " "]
    rng = random.Random(11)
    for _ in range(4000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
        assert st.filename_matches(s) == OLD_FILE.findall(s), repr(s)


def test_paths():
    for s in strings(list("ab_9./ -"), longest=18):
        assert st.path_matches(s) == OLD_PATH.findall(s), repr(s)


def test_token_counts():
    alphabet = list("19 \t") + ["token", "tokens", "x", "٣"]
    rng = random.Random(5)
    for _ in range(4000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 10)))
        assert st.token_counts(s) == OLD_TOKENS.findall(s), repr(s)


def test_parameters_block():
    alphabet = ["parameters", "{", "}", " ", "\n", "a", "="]
    rng = random.Random(3)
    for _ in range(4000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 9)))
        m = OLD_PARAMS.search(s)
        assert st.parameters_block(s) == (m.group(1) if m else None), repr(s)


def test_assignment_on_stripped_and_unstripped_lines():
    alphabet = list("ab_9 =\t-") + ["é"]
    rng = random.Random(9)
    for _ in range(6000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 9)))
        m = OLD_ASSIGN.match(s)
        want = (m.group(1), m.group(2)) if m else None
        assert st.assignment(s) == want, repr(s)


def test_strip_punct_matches_the_edge_pattern():
    for s in strings(list("ab./-_9"), longest=12):
        assert s.strip("./-") == OLD_EDGE.sub("", s), repr(s)


ADVERSARIAL = [
    ("json_object_span", lambda: "{" * 60000), ("substitutions-dollar", lambda: "$(" * 60000), ("substitutions-tick", lambda: "`" * 60001),
    ("filename_matches", lambda: "_" * 60000), ("path_matches-dots", lambda: "." * 60000), ("path_matches-digits", lambda: "_9" * 30000),
    ("token_counts", lambda: "0" * 60000), ("parameters_block", lambda: "parameters{" * 8000), ("assignment", lambda: "0" * 60000),
]
FUNCTIONS = {"json_object_span": st.json_object_span, "substitutions-dollar": st.substitutions, "substitutions-tick": st.substitutions,
             "filename_matches": st.filename_matches, "path_matches-dots": st.path_matches, "path_matches-digits": st.path_matches,
             "token_counts": st.token_counts, "parameters_block": st.parameters_block, "assignment": st.assignment}


@pytest.mark.parametrize("name", [n for n, _ in ADVERSARIAL])
def test_adversarial_inputs_stay_fast(name):
    payload = dict(ADVERSARIAL)[name]()          # built here: a 60 000-character parameter id overflows Windows' environment limit
    started = time.perf_counter()
    FUNCTIONS[name](payload)
    assert time.perf_counter() - started < 1.0, f"{name} took {time.perf_counter() - started:.2f}s"
