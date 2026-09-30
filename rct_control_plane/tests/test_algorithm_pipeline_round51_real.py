"""
Round 51: all 41 algorithms as stages around a governed episode.

Real kernel and real algorithms; the LLM's decision is scripted as in the other
loop tests. What is proven: every algorithm id has an adapter, every adapter
either runs or says why it did not, user data flows through the retrieval
algorithms (and stays inside its namespace), advice reaches the prompt, and the
per-algorithm record is stored with the episode.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import http.server
import socketserver
import threading

import pytest

from rct_control_plane import algorithm_pipeline as ap
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.algorithm_pipeline import AlgorithmPipeline, PipelineContext, PipelineOptions
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from rct_control_plane.tests.test_intent_growth_round51_real import FINISH, LS, _loop, _script

GOAL = "Read the file pyproject.toml in the repository and tell me the project name"
ALL_IDS = [f"ALGO-{n:02d}" for n in range(1, 42)]


@pytest.fixture(scope="module")
def kernel():
    return AlgorithmKernel41()


def _ctx(kernel, tmp_path, namespace="pipe", **opts):
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "p.db"))
    skills = SkillLibrary(db_path=str(tmp_path / "s.db"))
    memory = AgentMemory(namespace, persistence)
    kernel._agent_memory = memory
    options = PipelineOptions(**opts)
    pipeline = AlgorithmPipeline(kernel, persistence, namespace, memory=memory, skills=skills, options=options)
    clarity, I, compiled = kernel.synthesize_fdia_inputs(GOAL)
    intent = getattr(compiled, "intent", None)
    ctx = PipelineContext(
        goal=GOAL, namespace=namespace, kernel=kernel, persistence=persistence, memory=memory, skills=skills, options=options,
        clarity=clarity, D=0.7, I=I, compile_result=compiled,
        intent_type=str(getattr(getattr(intent, "intent_type", None), "value", "UNKNOWN")) if intent else "UNKNOWN",
    )
    return pipeline, ctx, persistence


class TestEveryAlgorithmHasAnAdapter:
    def test_all_41_ids_are_covered_and_every_adapter_is_async(self):
        assert ap.AlgorithmPipeline.algorithm_ids() == ALL_IDS
        assert ap.adapter_source_sanity()

    def test_each_adapter_belongs_to_a_known_stage(self):
        assert {a.stage for a in ap.ADAPTERS} <= set(ap.STAGES)
        assert set(ap.STAGES) == {a.stage for a in ap.ADAPTERS}

    def test_model_network_and_file_writing_algorithms_are_flagged(self):
        flagged = {a.algo_id for a in ap.ADAPTERS if a.llm or a.network or a.writes}
        assert {"ALGO-09", "ALGO-11", "ALGO-12", "ALGO-33", "ALGO-32", "ALGO-28", "ALGO-29", "ALGO-34", "ALGO-39", "ALGO-23"} <= flagged


class TestPreEpisodeStages:
    def test_understand_recall_plan_run_without_errors_on_a_normal_goal(self, kernel, tmp_path):
        pipeline, ctx, persistence = _ctx(kernel, tmp_path)
        asyncio.run(AgentMemory("pipe", persistence).store("The project name is written in pyproject.toml under the name key", MemoryType.FACT, importance=0.9))

        async def go():
            out = []
            for stage in ("understand", "recall", "plan", "act"):
                traces, advice = await pipeline.run_stage(stage, ctx, phase="pre")
                out.append((traces, advice))
            return out
        stages = asyncio.run(go())
        traces = [t for ts, _ in stages for t in ts]
        assert [t for t in traces if t.status == "error"] == [], [(t.algo_id, t.reason) for t in traces if t.status == "error"]
        ran = {t.algo_id for t in traces if t.status == "ok"}
        assert {"ALGO-04", "ALGO-37", "ALGO-02", "ALGO-01", "ALGO-16", "ALGO-18", "ALGO-13", "ALGO-05", "ALGO-21", "ALGO-15", "ALGO-20"} <= ran
        for t in traces:
            if t.status == "not_triggered":
                assert t.reason, t.algo_id            # never silent about why
        all_advice = " ".join(line for _, adv in stages for line in adv)
        assert "pyproject.toml" in all_advice          # the user's own memory came back through the retrieval algorithms

    def test_one_users_data_is_never_returned_for_another(self, kernel, tmp_path):
        pipeline, ctx, persistence = _ctx(kernel, tmp_path, namespace="alice")
        asyncio.run(AgentMemory("bob", persistence).store("Bob keeps the project name secret inside pyproject.toml", MemoryType.FACT))
        asyncio.run(AgentMemory("alice", persistence).store("Alice reads the project name from pyproject.toml", MemoryType.FACT))
        _, advice = asyncio.run(pipeline.run_stage("recall", ctx, phase="pre"))
        text = " ".join(advice)
        assert "Alice" in text and "Bob" not in text

    def test_modality_algorithms_say_why_they_did_not_run(self, kernel, tmp_path):
        pipeline, ctx, _ = _ctx(kernel, tmp_path)
        traces, _ = asyncio.run(pipeline.run_stage("act", ctx, phase="pre"))
        by_id = {t.algo_id: t for t in traces}
        assert by_id["ALGO-34"].status == "not_triggered" and "URL" in by_id["ALGO-34"].reason
        assert by_id["ALGO-27"].status == "not_triggered" and "video" in by_id["ALGO-27"].reason
        assert by_id["ALGO-14"].status == "not_triggered"
        assert by_id["ALGO-39"].status == "not_triggered"

    def test_model_calling_algorithms_stay_off_unless_allowed(self, kernel, tmp_path):
        pipeline, ctx, _ = _ctx(kernel, tmp_path)
        traces, _ = asyncio.run(pipeline.run_stage("plan", ctx, phase="pre"))
        by_id = {t.algo_id: t for t in traces}
        assert by_id["ALGO-32"].status == "not_triggered" and "allow_llm" in by_id["ALGO-32"].reason
        assert by_id["ALGO-11"].status == "not_triggered"
        assert by_id["ALGO-12"].status == "not_triggered" and "allow_llm" in by_id["ALGO-12"].reason

    def test_a_failing_algorithm_is_reported_and_does_not_stop_the_others(self, kernel, tmp_path, monkeypatch):
        pipeline, ctx, _ = _ctx(kernel, tmp_path)
        monkeypatch.setattr(kernel, "algo_37_planning_depth_expander", lambda task: (_ for _ in ()).throw(RuntimeError("boom")))
        traces, _ = asyncio.run(pipeline.run_stage("understand", ctx, phase="pre"))
        by_id = {t.algo_id: t for t in traces}
        assert by_id["ALGO-37"].status == "error" and "boom" in by_id["ALGO-37"].reason
        assert by_id["ALGO-02"].status == "ok"

    def test_only_the_enabled_algorithms_run(self, kernel, tmp_path):
        pipeline, ctx, _ = _ctx(kernel, tmp_path, enabled={"ALGO-04", "ALGO-01"})
        traces, _ = asyncio.run(pipeline.run_stage("understand", ctx, phase="pre"))
        assert {t.algo_id for t in traces} == {"ALGO-04", "ALGO-01"}


class _Site(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = b"<html><body><p>The project is delentia-os.</p></body></html>"
        self.send_response(200 if self.path != "/robots.txt" else 404)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestModalityAlgorithmsRunOnRealInputs:
    def test_url_algorithms_run_against_a_real_local_server_when_allowed(self, kernel, tmp_path):
        server = socketserver.TCPServer(("127.0.0.1", 0), _Site)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
            pipeline, ctx, _ = _ctx(kernel, tmp_path, allow_network=True, fixtures={"url": url})
            traces, _ = asyncio.run(pipeline.run_stage("act", ctx, phase="pre"))
        finally:
            server.shutdown()
        by_id = {t.algo_id: t for t in traces}
        assert by_id["ALGO-34"].status == "ok" and by_id["ALGO-34"].summary["status"] == 200
        assert by_id["ALGO-28"].status == "ok" and by_id["ALGO-28"].summary["status"] == 200
        assert by_id["ALGO-29"].status == "ok", by_id["ALGO-29"].reason

    def test_url_algorithms_refuse_the_network_unless_allowed(self, kernel, tmp_path):
        pipeline, ctx, _ = _ctx(kernel, tmp_path, fixtures={"url": "http://127.0.0.1:9/x"})
        traces, _ = asyncio.run(pipeline.run_stage("act", ctx, phase="pre"))
        assert all(t.status == "not_triggered" and "allow_network" in t.reason for t in traces if t.algo_id in ("ALGO-34", "ALGO-28", "ALGO-29"))

    def test_video_analysis_runs_on_a_real_generated_video(self, kernel, tmp_path):
        cv2 = pytest.importorskip("cv2")
        np = pytest.importorskip("numpy")
        path = str(tmp_path / "v.mp4")
        writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 2, (64, 64))
        for i in range(6):
            writer.write(np.full((64, 64, 3), i * 40, dtype=np.uint8))
        writer.release()
        pipeline, ctx, _ = _ctx(kernel, tmp_path, fixtures={"video_path": path}, enabled={"ALGO-27"})
        traces, _ = asyncio.run(pipeline.run_stage("act", ctx, phase="pre"))
        assert traces[0].status == "ok" and traces[0].summary["scenes"] >= 1


class TestInTheLoop:
    def test_the_episode_carries_the_per_algorithm_record_and_the_advice_reaches_the_prompt(self, kernel, tmp_path, monkeypatch):
        state = _script(monkeypatch, [[LS, FINISH]])
        loop = _loop(tmp_path, kernel, namespace="pipeloop", db="pl.db")
        asyncio.run(AgentMemory("pipeloop", loop._persistence).store(
            "The project name is written in pyproject.toml under the name key", MemoryType.FACT, importance=0.9))
        loop._algorithm_pipeline = AlgorithmPipeline(
            kernel, loop._persistence, "pipeloop", memory=kernel._agent_memory, skills=loop._skill_library,
            options=PipelineOptions(enabled={a for a in ALL_IDS if a not in ("ALGO-33", "ALGO-34", "ALGO-36")}, allow_writes=False))
        result = asyncio.run(loop.run(GOAL))

        assert result["stopped_reason"] == "llm_finished"
        pipeline = result["pipeline"]
        assert pipeline["errors"] == 0 and pipeline["ok"] >= 25
        stages_seen = {t["stage"] for t in pipeline["traces"]}
        assert set(ap.STAGES) <= stages_seen
        assert "Advice from the algorithm pipeline" in state["contexts"][0]
        rows = [r for r in loop._persistence.recent_audit(200) if r.get("entity_type") == "algorithm_pipeline"]
        assert rows and "by_algorithm" in rows[0]["changes"]

    def test_the_pipeline_is_off_by_default_and_the_env_switch_turns_it_on(self, kernel, tmp_path, monkeypatch):
        _script(monkeypatch, [[FINISH]])
        monkeypatch.delenv("DELENTIA_ALGORITHM_PIPELINE", raising=False)
        off = asyncio.run(_loop(tmp_path, kernel, db="off.db").run(GOAL))
        assert "pipeline" not in off
        monkeypatch.setenv("DELENTIA_ALGORITHM_PIPELINE", "1")
        loop = _loop(tmp_path, kernel, db="on.db")
        loop._algorithm_pipeline = None
        assert loop._get_pipeline() is not None


class TestNoHiddenModelCalls:
    def test_hallucination_filter_runs_its_patterns_without_calling_a_model(self, kernel, tmp_path, monkeypatch):
        """ALGO-33 used to ask the local model about every answer that matched no pattern."""
        called = []

        async def boom(self, text):
            called.append(text)
            return None
        from rct_control_plane.algo_33_fghf import HallucinationDetector
        monkeypatch.setattr(HallucinationDetector, "_check_via_llm", boom)
        pipeline, ctx, _ = _ctx(kernel, tmp_path, enabled={"ALGO-33"})
        ctx.result = {"final_answer": "The project is called delentia-os.", "steps": []}
        traces, _ = asyncio.run(pipeline.run_stage("verify", ctx, phase="post"))
        assert traces[0].status == "ok" and called == []
        assert traces[0].summary["model_second_opinion"] is False

    def test_the_model_second_opinion_is_used_only_when_allowed(self, kernel, tmp_path, monkeypatch):
        called = []

        async def fake(self, text):
            called.append(text)
            return None
        from rct_control_plane.algo_33_fghf import HallucinationDetector
        monkeypatch.setattr(HallucinationDetector, "_check_via_llm", fake)
        pipeline, ctx, _ = _ctx(kernel, tmp_path, enabled={"ALGO-33"}, allow_llm=True)
        ctx.result = {"final_answer": "The project is called delentia-os.", "steps": []}
        asyncio.run(pipeline.run_stage("verify", ctx, phase="post"))
        assert len(called) == 1


class TestEmbeddingIsNotFooledByStopwords:
    def test_unrelated_sentences_sharing_only_common_words_do_not_look_alike(self, kernel, tmp_path):
        import numpy as np
        _, ctx, _ = _ctx(kernel, tmp_path)

        def cos(a, b):
            a, b = np.array(a), np.array(b)
            return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        memory = "The release checklist is: run the full test suite, update the changelog, tag the release, publish to npm last."
        related = cos(ctx.embed("Recall what you remember about the release checklist."), ctx.embed(memory))
        unrelated = cos(ctx.embed("Read the file pyproject.toml in the repository and tell me the project name."), ctx.embed(memory))
        assert related > 0.25 and unrelated < 0.1
