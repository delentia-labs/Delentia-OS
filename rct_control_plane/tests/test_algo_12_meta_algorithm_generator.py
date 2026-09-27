"""
Round 45 item C (test coverage continuation): real tests for ALGO-12's
MetaAlgorithmEngine - pure in-memory composition/validation logic (dataclass
registry + graph-building), 0% coverage before this file. The one external
boundary this module has (`_generate_composition_name`'s optional Ollama
call) is the one place mocked here, consistent with this project's existing
convention of treating an LLM call as the acceptable mock boundary while
testing everything else against the real engine.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

import rct_control_plane.algo_12_meta_algorithm_generator as meta_mod
from rct_control_plane.algo_12_meta_algorithm_generator import (
    MetaAlgorithmEngine, CompositionMode, ValidationStatus, BaseAlgorithm, AlgorithmType,
)


@pytest.fixture
def engine():
    return MetaAlgorithmEngine()


class TestDefaultRegistry:
    def test_six_default_algorithms_registered(self, engine):
        algos = engine.list_algorithms()
        assert len(algos) == 6
        ids = {a["id"] for a in algos}
        assert ids == {"map", "reduce", "filter", "analyze", "optimize", "generate"}

    def test_get_algorithm_by_id(self, engine):
        algo = engine.get_algorithm("map")
        assert algo is not None
        assert algo.name == "Map"

    def test_get_unknown_algorithm_returns_none(self, engine):
        assert engine.get_algorithm("does-not-exist") is None

    def test_register_custom_algorithm(self, engine):
        custom = BaseAlgorithm(
            id="custom-sort", name="Sort", algorithm_type=AlgorithmType.TRANSFORM,
            description="sort elements", input_schema={"type": "array"},
            output_schema={"type": "array"},
        )
        engine.register_algorithm(custom)
        assert engine.get_algorithm("custom-sort") is custom
        assert len(engine.list_algorithms()) == 7


class TestSequentialComposition:
    @pytest.mark.asyncio
    async def test_composes_and_validates_successfully(self, engine):
        session_id = await engine.compose(
            component_ids=["filter", "map", "reduce"],
            mode=CompositionMode.SEQUENTIAL,
            goal="Process and aggregate filtered data",
        )
        session = engine.get_session(session_id)
        assert session["status"] == "complete"
        composed = session["composed_algorithm"]
        assert composed["composition_mode"] == "sequential"
        assert len(composed["composition_graph"]["edges"]) == 2
        assert composed["input_schema"] == {"type": "array", "items": "any"}  # filter's input
        assert composed["output_schema"] == {"type": "any"}  # reduce's output
        assert session["validation_result"]["is_valid"] is True
        assert engine.get_composed_algorithm(composed["id"]) is not None

    @pytest.mark.asyncio
    async def test_unknown_component_fails_cleanly(self, engine):
        session_id = await engine.compose(
            component_ids=["does-not-exist"], mode=CompositionMode.SEQUENTIAL, goal="Should fail",
        )
        session = engine.get_session(session_id)
        assert session["status"] == "failed"
        assert "not found" in session["error"]
        # A failed session's composed_algorithm is never populated or stored.
        assert "composed_algorithm" not in session
        assert len(engine.list_composed_algorithms()) == 0

    @pytest.mark.asyncio
    async def test_depth_exceeding_composition_produces_real_warning(self, engine):
        many_ids = ["map", "filter", "reduce", "analyze", "optimize", "generate"]
        session_id = await engine.compose(
            component_ids=many_ids, mode=CompositionMode.SEQUENTIAL, goal="Exceed max depth",
        )
        session = engine.get_session(session_id)
        assert session["status"] == "complete"  # a warning alone doesn't fail validation
        warnings = session["validation_result"]["warnings"]
        assert any("exceeds recommended maximum" in w for w in warnings)
        assert session["validation_result"]["suggestions"]  # populated whenever warnings exist

    @pytest.mark.asyncio
    async def test_type_mismatch_between_adjacent_components_warns(self, engine):
        # "analyze"'s output ({"type": "object", ...}) feeds "map"'s input
        # ({"type": "array", ...}) - neither side is "any", so this is a
        # real, detectable type mismatch per _validate_composition's own
        # simplified type-checking rule.
        session_id = await engine.compose(
            component_ids=["analyze", "map"], mode=CompositionMode.SEQUENTIAL, goal="mismatched types",
        )
        session = engine.get_session(session_id)
        assert any("Type mismatch" in w for w in session["validation_result"]["warnings"])

    @pytest.mark.asyncio
    async def test_performance_constraint_flags_high_complexity(self, engine):
        # Force an O(n^2)-complexity component via a custom registration so
        # the "performance" constraint keyword path is genuinely exercised.
        engine.register_algorithm(BaseAlgorithm(
            id="quadratic", name="Quadratic Op", algorithm_type=AlgorithmType.TRANSFORM,
            description="d", input_schema={"type": "any"}, output_schema={"type": "any"},
            complexity="O(n^2)",
        ))
        session_id = await engine.compose(
            component_ids=["quadratic"], mode=CompositionMode.SEQUENTIAL, goal="g",
            constraints=["must meet performance targets"],
        )
        session = engine.get_session(session_id)
        assert any("Performance constraint" in w for w in session["validation_result"]["warnings"])


class TestUnexpectedInternalErrorIsCaughtCleanly:
    @pytest.mark.asyncio
    async def test_compose_never_crashes_the_caller_on_an_unexpected_internal_error(self, engine, monkeypatch):
        """compose()'s outer try/except is the last line of defense against
        any bug in the composition/validation internals - forces a real
        exception out of _compose_sequential to confirm it's actually
        caught and turned into a clean failed session, not left to
        propagate out to whatever called compose()."""
        async def _boom(*a, **k):
            raise RuntimeError("simulated internal composition bug")
        monkeypatch.setattr(engine, "_compose_sequential", _boom)

        session_id = await engine.compose(
            component_ids=["map"], mode=CompositionMode.SEQUENTIAL, goal="g",
        )
        session = engine.get_session(session_id)
        assert session["status"] == "failed"
        assert session["error"] == "simulated internal composition bug"


class TestParallelComposition:
    @pytest.mark.asyncio
    async def test_composes_with_fan_out_fan_in_graph(self, engine):
        session_id = await engine.compose(
            component_ids=["analyze", "optimize"], mode=CompositionMode.PARALLEL,
            goal="Analyze and optimize simultaneously",
        )
        session = engine.get_session(session_id)
        assert session["status"] == "complete"
        composed = session["composed_algorithm"]
        assert composed["composition_mode"] == "parallel"
        edges = composed["composition_graph"]["edges"]
        # 2 fan-out (input->each) + 2 fan-in (each->merge) = 4 edges for 2 components.
        assert len(edges) == 4
        assert composed["output_schema"]["properties"].keys() == {"analyze", "optimize"}


class TestConditionalComposition:
    @pytest.mark.asyncio
    async def test_two_components_produce_true_false_branches(self, engine):
        session_id = await engine.compose(
            component_ids=["filter", "map"], mode=CompositionMode.CONDITIONAL, goal="route by condition",
        )
        session = engine.get_session(session_id)
        composed = session["composed_algorithm"]
        assert composed["composition_graph"]["branches"] == {"true": "filter", "false": "map"}

    @pytest.mark.asyncio
    async def test_single_component_duplicates_into_both_branches(self, engine):
        """A single-component conditional composition has no real "else"
        branch - the engine's documented fallback duplicates the one
        component into both true/false branches rather than crashing."""
        session_id = await engine.compose(
            component_ids=["filter"], mode=CompositionMode.CONDITIONAL, goal="only one branch",
        )
        session = engine.get_session(session_id)
        composed = session["composed_algorithm"]
        assert composed["composition_graph"]["branches"] == {"true": "filter", "false": "filter"}
        assert composed["components"] == ["filter", "filter"]


class TestIterativeComposition:
    @pytest.mark.asyncio
    async def test_uses_first_component_as_loop_body(self, engine):
        session_id = await engine.compose(
            component_ids=["map", "reduce"], mode=CompositionMode.ITERATIVE, goal="repeat until converged",
        )
        session = engine.get_session(session_id)
        composed = session["composed_algorithm"]
        assert composed["composition_graph"]["body"]["id"] == "map"
        assert composed["composition_graph"]["max_iterations"] == 100
        assert composed["input_schema"] == engine.get_algorithm("map").input_schema


class TestRecursiveComposition:
    @pytest.mark.asyncio
    async def test_uses_first_component_as_recursive_body(self, engine):
        session_id = await engine.compose(
            component_ids=["reduce"], mode=CompositionMode.RECURSIVE, goal="divide and conquer",
        )
        session = engine.get_session(session_id)
        composed = session["composed_algorithm"]
        assert composed["composition_graph"]["body"]["id"] == "reduce"
        assert composed["composition_graph"]["base_case"] == "input size <= threshold"


class TestComplexityAnalysis:
    @pytest.mark.parametrize("complexities,mode,expected", [
        (["O(n)"], CompositionMode.SEQUENTIAL, "O(n)"),
        (["O(n)", "O(n log n)"], CompositionMode.SEQUENTIAL, "O(n log n)"),
        (["O(n)", "O(n^2)"], CompositionMode.SEQUENTIAL, "O(n^2)"),
        (["O(n)", "O(n^3)"], CompositionMode.SEQUENTIAL, "O(n^3)"),
        (["O(n^2)", "O(n^3)"], CompositionMode.SEQUENTIAL, "O(n^3)"),  # n^3 dominates
        (["O(n)"], CompositionMode.PARALLEL, "O(n)"),
        (["O(n)", "O(n^2)"], CompositionMode.PARALLEL, "O(n^2)"),
        (["O(n)", "O(n^3)"], CompositionMode.PARALLEL, "O(n^3)"),
    ])
    def test_sequential_and_parallel_take_the_dominant_complexity(self, engine, complexities, mode, expected):
        assert engine._analyze_complexity(complexities, mode) == expected

    def test_iterative_wraps_the_first_complexity(self, engine):
        assert engine._analyze_complexity(["O(n)", "O(n^2)"], CompositionMode.ITERATIVE) == "O(k x O(n))"

    def test_iterative_with_no_complexities_falls_back_to_on(self, engine):
        assert engine._analyze_complexity([], CompositionMode.ITERATIVE) == "O(k x O(n))"

    def test_recursive_is_always_n_log_n(self, engine):
        assert engine._analyze_complexity(["O(n^3)"], CompositionMode.RECURSIVE) == "O(n log n)"


class TestCompositionNamingFallback:
    """Round 45: the module's one external boundary - an optional Ollama
    naming call - mocked here rather than hit for real, both to keep this
    test file network-free and to avoid competing with this same round's
    live-Ollama scenario battery for the local Ollama backend."""

    @pytest.mark.asyncio
    async def test_falls_back_to_hardcoded_name_when_httpx_unavailable(self, engine, monkeypatch):
        monkeypatch.setattr(meta_mod, "_HAS_HTTPX", False)
        session_id = await engine.compose(
            component_ids=["map"], mode=CompositionMode.SEQUENTIAL, goal="g",
        )
        session = engine.get_session(session_id)
        assert session["composed_algorithm"]["name"] == "Sequential Composition"

    @pytest.mark.asyncio
    async def test_falls_back_to_hardcoded_name_when_the_llm_call_raises(self, engine, monkeypatch):
        class _RaisingClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k): raise RuntimeError("simulated network failure")

        monkeypatch.setattr(meta_mod, "_HAS_HTTPX", True)
        monkeypatch.setattr(meta_mod.httpx, "AsyncClient", _RaisingClient)
        session_id = await engine.compose(
            component_ids=["map"], mode=CompositionMode.PARALLEL, goal="g",
        )
        session = engine.get_session(session_id)
        assert session["composed_algorithm"]["name"] == "Parallel Composition"

    @pytest.mark.asyncio
    async def test_uses_the_llm_provided_name_on_a_real_200_response(self, engine, monkeypatch):
        class _FakeResponse:
            status_code = 200
            def json(self): return {"response": '  "Smart Filter Pipeline"  '}

        class _FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k): return _FakeResponse()

        monkeypatch.setattr(meta_mod, "_HAS_HTTPX", True)
        monkeypatch.setattr(meta_mod.httpx, "AsyncClient", _FakeClient)
        session_id = await engine.compose(
            component_ids=["map"], mode=CompositionMode.SEQUENTIAL, goal="g",
        )
        session = engine.get_session(session_id)
        # Quotes stripped, whitespace stripped - real cleanup logic exercised.
        assert session["composed_algorithm"]["name"] == "Smart Filter Pipeline"


class TestSessionAndAlgorithmLookup:
    def test_get_session_for_unknown_id_returns_error_dict(self, engine):
        assert engine.get_session("no-such-session") == {"error": "Session not found"}

    @pytest.mark.asyncio
    async def test_list_sessions_reflects_all_compose_calls(self, engine):
        await engine.compose(["map"], CompositionMode.SEQUENTIAL, goal="a")
        await engine.compose(["reduce"], CompositionMode.SEQUENTIAL, goal="b")
        sessions = engine.list_sessions()
        assert len(sessions) == 2
        assert {s["goal"] for s in sessions} == {"a", "b"}

    @pytest.mark.asyncio
    async def test_delete_session_removes_it_and_returns_true(self, engine):
        session_id = await engine.compose(["map"], CompositionMode.SEQUENTIAL, goal="a")
        assert engine.delete_session(session_id) is True
        assert engine.get_session(session_id) == {"error": "Session not found"}

    def test_delete_unknown_session_returns_false(self, engine):
        assert engine.delete_session("no-such-session") is False

    def test_get_composed_algorithm_for_unknown_id_returns_none(self, engine):
        assert engine.get_composed_algorithm("no-such-algorithm") is None

    @pytest.mark.asyncio
    async def test_list_composed_algorithms_excludes_failed_sessions(self, engine):
        await engine.compose(["map"], CompositionMode.SEQUENTIAL, goal="ok")
        await engine.compose(["does-not-exist"], CompositionMode.SEQUENTIAL, goal="fails")
        assert len(engine.list_composed_algorithms()) == 1


class TestValidationStatusEnum:
    def test_valid_status_values_exist(self):
        assert ValidationStatus.VALID.value == "valid"
        assert ValidationStatus.INVALID.value == "invalid"
        assert ValidationStatus.WARNING.value == "warning"
