"""
Round 85, found by the six-hour soak of the host: memory recall asked the embedding model with a blocking HTTP call ON the event loop, so while the model loaded (up to its 20 s timeout) the server answered
nothing else, /health included. The ranking now runs in a worker thread; the loop keeps answering. The test makes the embedding call slow on purpose and measures the longest gap of a heartbeat that runs beside it.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import time

import pytest

from rct_control_plane import memory_embeddings
from rct_control_plane.agent_memory import AgentMemory, MemoryType
from rct_control_plane.persistence import ControlPlanePersistence


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DELENTIA_MEMORY_EMBED", "off")
    persistence = ControlPlanePersistence(str(tmp_path / "m.db"))
    mem = AgentMemory("alice", persistence)
    for text in ("The staging database is stg-db-1", "The promotion price is 90 baht", "Meeting notes live in the notes folder"):
        asyncio.run(mem.store(text, MemoryType.FACT))
    return mem


async def _longest_gap_while(coro, beat=0.02):
    gaps, last, stop = [], time.perf_counter(), False

    async def heartbeat():
        nonlocal last
        while not stop:
            await asyncio.sleep(beat)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now
    task = asyncio.create_task(heartbeat())
    result = await coro
    waited = time.perf_counter() - last                                         # a loop that never got to run the heartbeat shows up here, not in `gaps`
    stop = True
    await task
    return result, max(gaps + [waited])


def test_a_slow_embedding_call_does_not_freeze_the_event_loop(memory, monkeypatch):
    def slow(*args, **kwargs):
        time.sleep(1.0)                                                         # the blocking HTTP call to a model that is still loading
        return None                                                             # None = "no embedding answer": recall falls back to the lexical path
    monkeypatch.setattr(memory_embeddings, "enabled", lambda: True)
    monkeypatch.setattr(memory_embeddings, "similarities", slow)

    # Warm the code path first: the first call on a cold CI worker imports and compiles on the loop (0.7 s was seen on Python 3.12 in CI), which is not the embedding call.
    asyncio.run(memory.recall_scored("what is the price", limit=3))

    async def go():
        return await _longest_gap_while(memory.recall_scored("what is the price", limit=3))
    results, longest = asyncio.run(go())
    assert results, "recall still answers"
    assert longest < 0.5, f"the loop was blocked for {longest:.2f}s while the embedding call ran"
    plain, longest2 = asyncio.run(_longest_gap_while(memory.recall("notes", limit=3)))
    assert plain is not None and longest2 < 0.5


def test_recall_gives_the_same_answer_as_before_off_the_loop(memory, monkeypatch):
    monkeypatch.setattr(memory_embeddings, "enabled", lambda: False)
    got = asyncio.run(memory.recall_scored("staging database", limit=2))
    assert got and "stg-db-1" in got[0]["content"]


def test_the_test_can_fail_when_the_ranking_runs_on_the_loop(memory, monkeypatch):
    """Negative control: with the old behaviour put back (ranking called directly on the loop) the same measurement sees the freeze."""
    def slow(*args, **kwargs):
        time.sleep(1.0)
        return None
    monkeypatch.setattr(memory_embeddings, "enabled", lambda: True)
    monkeypatch.setattr(memory_embeddings, "similarities", slow)

    async def on_loop(self, query, candidates, limit):
        return self._ranked(query, candidates, limit)
    monkeypatch.setattr(AgentMemory, "_ranked_off_loop", on_loop)
    _, longest = asyncio.run(_longest_gap_while(memory.recall_scored("what is the price", limit=3)))
    assert longest >= 0.9, "the old behaviour freezes the loop for the whole call, and the measurement sees it"
