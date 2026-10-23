"""DAG execution invariants and governed budget integration, without an LLM."""
import asyncio
import copy

import pytest
from hypothesis import given, strategies as st

from rct_control_plane.component_execution import ComponentScheduler, Handler, validate_program
from rct_control_plane.rct_plan import PlanItem
from rct_control_plane.budget_execution import validate_executor
from rct_control_plane.intent_contract import IntentContractStore, IntentContractError
from rct_control_plane.tests import test_verified_budget_real as verified_tests

setup = verified_tests.setup


@pytest.fixture
def world(tmp_path, monkeypatch):
    import os
    if os.name != "posix":
        pytest.skip("governed verified reads require POSIX no-follow support")
    return verified_tests.world.__wrapped__(tmp_path, monkeypatch)


class Empty(PlanItem):
    pass


class Number(PlanItem):
    value: int


class Pair(PlanItem):
    left: Number
    right: Number


class One(PlanItem):
    source: Number


REGISTRY = {
    "observed.number": Handler(Empty, Number, "observation", None),
    "add": Handler(Pair, Number, "compute", lambda i: {"value": i.left.value + i.right.value}),
    "double": Handler(One, Number, "compute", lambda i: {"value": i.source.value * 2}),
}
NODES = [
    {"id": "a", "handler": "observed.number", "phase": "observation"},
    {"id": "b", "handler": "observed.number", "phase": "observation"},
    {"id": "sum", "handler": "add", "phase": "compute", "depends_on": ["a", "b"], "inputs": {"left": "a", "right": "b"}},
    {"id": "double", "handler": "double", "phase": "compute", "depends_on": ["sum"], "inputs": {"source": "sum"}},
]


def engine(nodes=None, registry=None, callback=None, answers=None, criteria=()):
    return ComponentScheduler({"schema_version": 1, "nodes": copy.deepcopy(nodes or NODES)},
        registry or REGISTRY, criteria, answers or {}, callback or (lambda key, output: None))


@given(st.permutations(NODES), st.integers(-1000,1000), st.integers(-1000,1000))
def test_topology_not_serialization_order_drives_fan_in_and_chain(nodes, left, right):
    receipts = []
    scheduler = engine(nodes, callback=lambda key, output: receipts.append((key, output)))
    scheduler.observe("a", {"value": left})
    assert scheduler.drain("compute") == 0
    scheduler.observe("b", {"value": right})
    assert scheduler.drain("compute") == 2
    assert scheduler.outputs["double"] == {"value": 2 * (left + right)}
    assert [r[0] for r in receipts] == ["a", "b", "sum", "double"]
    scheduler.require_complete()
    assert scheduler.drain("compute") == 0


@pytest.mark.parametrize("mutation", ["duplicate", "cycle", "dangling", "handler", "phase", "edge", "port", "type", "criterion", "unknown", "version"])
def test_invalid_program_refused_before_handlers_run(mutation):
    nodes = copy.deepcopy(NODES)
    value = {"schema_version": 1, "nodes": nodes}
    if mutation == "duplicate": nodes.append(copy.deepcopy(nodes[0]))
    elif mutation == "cycle": nodes[0]["depends_on"] = ["double"]
    elif mutation == "dangling": nodes[2]["depends_on"] += ["absent"]
    elif mutation == "handler": nodes[0]["handler"] = "arbitrary.tool"
    elif mutation == "phase": nodes[0]["phase"] = "compute"
    elif mutation == "edge": nodes[2]["depends_on"] = ["a"]
    elif mutation == "port": nodes[2]["inputs"]["extra"] = "a"
    elif mutation == "type": nodes[2]["inputs"]["left"] = "double"; nodes[3]["handler"] = "observed.number"; nodes[2]["depends_on"].append("double")
    elif mutation == "criterion": nodes[2]["criteria"] = ["C1"]
    elif mutation == "unknown": nodes[2]["requires"] = ["budget"]
    else: value["schema_version"] = True
    with pytest.raises(ValueError): validate_program(value, REGISTRY, [], {})


def test_missing_criterion_is_rejected():
    with pytest.raises(ValueError, match="criterion"):
        engine(criteria=["C1"])


def test_failed_receipt_callback_does_not_release_descendants():
    def fail(key, output):
        if key == "sum": raise OSError("disk full")
    scheduler = engine(callback=fail)
    scheduler.observe("a", {"value": 2}); scheduler.observe("b", {"value": 3})
    with pytest.raises(OSError): scheduler.drain("compute")
    assert set(scheduler.outputs) == {"a", "b"}
    with pytest.raises(ValueError, match="reconciliation"): scheduler.drain("compute")
    with pytest.raises(ValueError): scheduler.require_complete()


def test_invalid_output_cannot_make_success_receipt():
    registry = dict(REGISTRY)
    registry["add"] = Handler(Pair, Number, "compute", lambda i: {"value": True})
    receipts = []
    scheduler = engine(registry=registry, callback=lambda key, output: receipts.append(key))
    scheduler.observe("a", {"value": 2}); scheduler.observe("b", {"value": 3})
    with pytest.raises(ValueError): scheduler.drain("compute")
    assert receipts == ["a", "b"] and "double" not in scheduler.outputs


def test_observation_cannot_be_generated_and_missing_inputs_wait():
    nodes = copy.deepcopy(NODES); nodes[2]["requires"] = ["confirmed"]
    scheduler = engine(nodes, answers={"confirmed": None})
    with pytest.raises(ValueError): scheduler.observe("sum", {"value": 3})
    scheduler.observe("a", {"value": 1}); scheduler.observe("b", {"value": 2})
    assert scheduler.drain("compute") == 0
    with pytest.raises(ValueError): scheduler.require_complete()
    with pytest.raises(ValueError): scheduler.observe("a", {"value": 1})


def test_mutable_handler_arguments_do_not_change_prior_output():
    def mutate(i):
        i.left.value = 999
        return {"value": i.left.value + i.right.value}
    registry = dict(REGISTRY);registry["add"] = Handler(Pair, Number, "compute", mutate)
    scheduler = engine(registry=registry)
    scheduler.observe("a", {"value": 1});scheduler.observe("b", {"value": 2})
    scheduler.drain("compute")
    assert scheduler.outputs["a"] == {"value": 1}


def test_governed_budget_reordered_graph_executes_every_criterion(tmp_path, world):
    from rct_control_plane.budget_execution import compile_program
    loop, context, criteria = setup(tmp_path, world, extra_criteria=[{"kind":"file_unchanged", "value":"quote.json"}])
    store = IntentContractStore(loop._persistence, "verified")
    c = store.create("Compare with my budget",criteria,world,context)
    c["plan"]["components"].reverse()
    c["plan"]["execution_program"] = compile_program(c["plan"])
    c = store.transition(c, "plan_ready")
    result = asyncio.run(loop.continue_intent(c["id"],c["version"]))
    assert result["acceptance_verification"]["satisfied"]
    receipts = result["intent_contract"]["execution_receipts"]
    assert len(receipts) == 7
    done = set()
    graph = {n["id"]: n for n in c["plan"]["components"]}
    for receipt in receipts:
        assert set(graph[receipt["component_id"]]["depends_on"]) <= done
        done.add(receipt["component_id"])


@pytest.mark.parametrize("mutation", ["version", "program", "criterion"])
def test_stored_executor_mutations_refused_without_fallback(tmp_path, world, mutation):
    loop, context, criteria = setup(tmp_path, world)
    store = IntentContractStore(loop._persistence, "verified")
    c = store.create("Compare with my budget", criteria, world, context)
    if mutation == "version": c["plan"]["semantic_planning"]["executor"] = "future_v99"
    elif mutation == "program": c["plan"]["execution_program"]["nodes"][0]["handler"] = "arbitrary.write"
    else: c["plan"]["components"][-1]["criteria"] = []
    with pytest.raises(IntentContractError): validate_executor(c["plan"])


def test_legacy_plan_without_ir_remains_supported(tmp_path, world):
    loop, context, criteria = setup(tmp_path, world)
    c = IntentContractStore(loop._persistence,"verified").create("Compare with my budget",criteria,world,context)
    c["plan"].pop("execution_program")
    validate_executor(c["plan"])


@pytest.mark.parametrize("case", ["symlink", "race", "fifo", "secret", "oversize", "invalid_limit"])
def test_actual_mcp_verified_acquisition_refuses_without_content(tmp_path, world, monkeypatch, case):
    import json
    import os
    from rct_control_plane import mcp_server
    outside = tmp_path / "outside.txt"; outside.write_text("PRIVATE_OUTSIDE_BYTES")
    path = world / "quote.json"; path.write_text("public")
    relative = "quote.json"
    if case == "symlink": path.unlink(); path.symlink_to(outside)
    elif case == "fifo": path.unlink(); os.mkfifo(path)
    elif case == "secret": relative = ".env"; (world / relative).write_text("PRIVATE_SECRET")
    elif case == "oversize": path.write_text("x" * 20001)
    elif case == "race":
        original = os.open
        swapped = False
        def swap(name, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and str(name) == str(world):
                swapped = True; path.unlink(); path.symlink_to(outside)
            return original(name, flags, *args, **kwargs)
        monkeypatch.setattr(os, "open", swap)
    result = asyncio.run(mcp_server.mcp.call_tool("delentia_read_repo_file", {
        "relative_path": relative, "max_bytes": 20001 if case == "invalid_limit" else 20000, "verified_read": True}))
    value = json.loads(result.content[0].text)
    assert "error" in value and "content_text" not in value
    assert "PRIVATE_" not in json.dumps(value)
