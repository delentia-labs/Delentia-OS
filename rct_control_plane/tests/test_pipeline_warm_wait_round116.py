"""PL1 Amendment 2: an episode's pipeline waits for the warm-up thread OFF the event loop, so the server keeps answering while the language libraries load."""
import asyncio
import threading
import time

from rct_control_plane import algorithm_pipeline


def test_the_wait_lets_the_event_loop_run(monkeypatch):
    release = threading.Event()
    thread = threading.Thread(target=release.wait, args=(5,), daemon=True)
    thread.start()
    monkeypatch.setattr(algorithm_pipeline, "_WARM_THREAD", thread)
    ticks = []

    async def main():
        async def ticker():
            while not release.is_set():
                ticks.append(time.perf_counter())
                await asyncio.sleep(0.02)
        tick_task = asyncio.create_task(ticker())
        asyncio.get_running_loop().call_later(0.5, release.set)
        started = time.perf_counter()
        await algorithm_pipeline.wait_for_warm_up(timeout=5)
        waited = time.perf_counter() - started
        await tick_task
        return waited
    waited = asyncio.run(main())
    assert waited >= 0.4, "the episode waited for the warm-up"
    assert len(ticks) >= 10, "the event loop kept running other work while it waited"


def test_no_warm_up_thread_means_no_wait(monkeypatch):
    monkeypatch.setattr(algorithm_pipeline, "_WARM_THREAD", None)
    started = time.perf_counter()
    asyncio.run(algorithm_pipeline.wait_for_warm_up())
    assert time.perf_counter() - started < 0.5


def test_a_finished_warm_up_is_not_waited_for(monkeypatch):
    done = threading.Thread(target=lambda: None)
    done.start()
    done.join()
    monkeypatch.setattr(algorithm_pipeline, "_WARM_THREAD", done)
    started = time.perf_counter()
    asyncio.run(algorithm_pipeline.wait_for_warm_up())
    assert time.perf_counter() - started < 0.5
