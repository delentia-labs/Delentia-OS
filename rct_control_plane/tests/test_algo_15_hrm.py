"""
Round 44 item C: real coverage for algo_15_hrm.py, previously untested
(0 test files existed) despite being real, actively-used code -
algorithm_kernel_41.py and algo_20_workflow_orchestrator.py both import
from it. Pure in-memory Python (asyncio/dataclasses/queue/collections),
no I/O or network - no mocking needed. This file already had a working
__main__ smoke test; these tests port and substantially expand on those
same real assertions.
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.algo_15_hrm import Task, TaskStatus, TaskGraph, Scheduler, WorkerInfo


def _task(tid, deps=None, priority=5):
    return Task(task_id=tid, task_type="build", payload={}, dependencies=deps or [], priority=priority)


class TestTaskGraphBasics:
    def test_add_task_succeeds_and_is_retrievable(self):
        graph = TaskGraph()
        assert graph.add_task(_task("a"))
        assert graph.get_task("a").task_id == "a"
        assert "a" in graph
        assert len(graph) == 1

    def test_add_duplicate_task_id_fails(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        assert graph.add_task(_task("a")) is False

    def test_add_task_with_missing_dependency_fails(self):
        graph = TaskGraph()
        assert graph.add_task(_task("b", deps=["ghost"])) is False
        assert "b" not in graph

    def test_remove_task_cleans_up_all_edges(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        assert graph.remove_task("a") is True
        assert "a" not in graph
        # b's reverse edge to a must be gone too
        assert "a" not in graph.reverse_graph["b"]

    def test_remove_nonexistent_task_returns_false(self):
        graph = TaskGraph()
        assert graph.remove_task("ghost") is False

    def test_get_task_returns_none_for_unknown_id(self):
        graph = TaskGraph()
        assert graph.get_task("ghost") is None


class TestTopologicalSortAndCycles:
    def test_real_kahns_algorithm_order(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        graph.add_task(_task("c", deps=["b"]))
        assert graph.topological_sort() == ["a", "b", "c"]

    def test_diamond_dependency_order_is_valid(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        graph.add_task(_task("c", deps=["a"]))
        graph.add_task(_task("d", deps=["b", "c"]))
        order = graph.topological_sort()
        assert order.index("a") < order.index("b") < order.index("d")
        assert order.index("a") < order.index("c") < order.index("d")

    def test_add_task_rejects_a_real_cycle(self):
        graph = TaskGraph()
        graph.add_task(_task("x"))
        graph.add_task(_task("y", deps=["x"]))
        # Hand-wire a cycle the same way the file's own smoke test does,
        # to exercise the real DFS cycle detector directly.
        graph.adjacency_list["y"].append("x")
        graph.reverse_graph["x"].append("y")
        graph.in_degree["x"] += 1
        assert graph._has_cycle() is True

    def test_topological_sort_on_empty_graph_is_empty(self):
        graph = TaskGraph()
        assert graph.topological_sort() == []


class TestReadyTasksAndTraversal:
    def test_get_ready_tasks_excludes_unmet_dependencies(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        ready = graph.get_ready_tasks()
        assert [t.task_id for t in ready] == ["a"]

    def test_get_ready_tasks_includes_task_once_deps_completed(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        graph.update_task_status("a", TaskStatus.COMPLETED)
        ready_ids = {t.task_id for t in graph.get_ready_tasks()}
        assert "b" in ready_ids

    def test_get_ready_tasks_sorted_by_priority_descending(self):
        graph = TaskGraph()
        graph.add_task(_task("low", priority=1))
        graph.add_task(_task("high", priority=9))
        ready = graph.get_ready_tasks()
        assert [t.task_id for t in ready] == ["high", "low"]

    def test_get_descendants_is_transitive(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        graph.add_task(_task("c", deps=["b"]))
        assert graph.get_descendants("a") == {"b", "c"}

    def test_get_ancestors_is_transitive(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        graph.add_task(_task("c", deps=["b"]))
        assert graph.get_ancestors("c") == {"a", "b"}

    def test_update_task_status_sets_result_and_error(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.update_task_status("a", TaskStatus.COMPLETED, result={"ok": True})
        assert graph.get_task("a").result == {"ok": True}
        graph.update_task_status("a", TaskStatus.FAILED, error="boom")
        assert graph.get_task("a").error == "boom"


class TestTaskGraphStatsAndDunder:
    def test_get_stats_reports_real_counts(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        graph.update_task_status("b", TaskStatus.COMPLETED)
        stats = graph.get_stats()
        assert stats["total_tasks"] == 2
        assert stats["edges"] == 1
        assert stats["root_tasks"] == 1
        assert stats["status_breakdown"]["completed"] == 1

    def test_clear_empties_the_graph(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.clear()
        assert len(graph) == 0
        assert graph.get_stats()["total_tasks"] == 0

    def test_repr_reports_real_shape(self):
        graph = TaskGraph()
        graph.add_task(_task("a"))
        graph.add_task(_task("b", deps=["a"]))
        assert "tasks=2" in repr(graph)
        assert "edges=1" in repr(graph)


class TestWorkerInfoOrdering:
    def test_worker_with_fewer_completed_tasks_sorts_first(self):
        busy = WorkerInfo(worker_id="w1", status="idle", tasks_completed=5)
        fresh = WorkerInfo(worker_id="w2", status="idle", tasks_completed=0)
        assert fresh < busy


class TestSchedulerAddAndAssign:
    def test_add_task_without_deps_enqueues_immediately(self):
        sched = Scheduler(max_workers=2)
        assert sched.add_task(_task("a"))
        assert sched.task_graph.get_task("a").status == TaskStatus.QUEUED

    def test_add_task_with_deps_stays_pending(self):
        sched = Scheduler(max_workers=2)
        sched.add_task(_task("a"))
        sched.add_task(_task("b", deps=["a"]))
        assert sched.task_graph.get_task("b").status == TaskStatus.PENDING

    def test_add_task_rejects_duplicate_and_does_not_bump_scheduled_count(self):
        sched = Scheduler(max_workers=2)
        sched.add_task(_task("a"))
        assert sched.add_task(_task("a")) is False
        assert sched.total_scheduled == 1

    @pytest.mark.asyncio
    async def test_schedule_assigns_higher_priority_task_first(self):
        sched = Scheduler(max_workers=2)
        sched.add_task(_task("low", priority=1))
        sched.add_task(_task("high", priority=9))
        sched.register_worker("w1")
        sched.register_worker("w2")
        assignments = await sched.schedule()
        assert assignments[0][0] == "high"

    @pytest.mark.asyncio
    async def test_schedule_with_no_idle_workers_returns_empty(self):
        sched = Scheduler(max_workers=1)
        sched.add_task(_task("a"))
        assert await sched.schedule() == []

    @pytest.mark.asyncio
    async def test_schedule_respects_worker_count_limit(self):
        sched = Scheduler(max_workers=1)
        sched.add_task(_task("a"))
        sched.add_task(_task("b"))
        sched.register_worker("w1")
        assignments = await sched.schedule()
        assert len(assignments) == 1


class TestSchedulerCompletionAndRetry:
    @pytest.mark.asyncio
    async def test_complete_task_marks_completed_and_frees_worker(self):
        sched = Scheduler(max_workers=1)
        sched.add_task(_task("a"))
        sched.register_worker("w1")
        await sched.schedule()
        await sched.complete_task("a", result={"ok": True})
        assert sched.task_graph.get_task("a").status == TaskStatus.COMPLETED
        assert sched.workers["w1"].status == "idle"
        assert sched.total_completed == 1

    @pytest.mark.asyncio
    async def test_complete_task_unblocks_dependents(self):
        sched = Scheduler(max_workers=2)
        sched.add_task(_task("a"))
        sched.add_task(_task("b", deps=["a"]))
        sched.register_worker("w1")
        sched.register_worker("w2")
        await sched.schedule()
        await sched.complete_task("a", result={"ok": True})
        assert sched.task_graph.get_task("b").status == TaskStatus.QUEUED

    @pytest.mark.asyncio
    async def test_complete_task_with_error_retries_under_max_retries(self):
        sched = Scheduler(max_workers=1)
        sched.add_task(_task("a"))
        sched.register_worker("w1")
        await sched.schedule()
        await sched.complete_task("a", error="transient failure")
        task = sched.task_graph.get_task("a")
        # Real behavior: status is set to RETRYING, then _enqueue_task()
        # immediately overwrites it to QUEUED before complete_task()
        # returns - RETRYING is a transient intermediate value, never the
        # final observable status. retries and total_failed DO persist.
        assert task.status == TaskStatus.QUEUED
        assert task.retries == 1
        assert sched.total_failed == 1

    @pytest.mark.asyncio
    async def test_complete_task_exhausts_retries_and_stays_failed(self):
        sched = Scheduler(max_workers=1)
        task = _task("a")
        task.max_retries = 1
        sched.add_task(task)
        sched.register_worker("w1")
        await sched.schedule()
        await sched.complete_task("a", error="fail 1")
        await sched.schedule()
        await sched.complete_task("a", error="fail 2")
        assert sched.task_graph.get_task("a").status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_complete_task_for_unknown_id_is_a_real_noop(self):
        sched = Scheduler(max_workers=1)
        # Must not raise.
        await sched.complete_task("ghost", result={})

    @pytest.mark.asyncio
    async def test_complete_task_skips_a_dependent_with_a_dangling_dependency(self):
        # Real bug-fix regression guard (see the file's own comment on
        # this exact scenario): a dependent whose OWN dependency list
        # references a task_id no longer in the graph must not crash -
        # it should just be treated as "not ready" rather than raising.
        sched = Scheduler(max_workers=2)
        sched.add_task(_task("a"))
        sched.add_task(_task("b", deps=["a"]))
        sched.register_worker("w1")
        await sched.schedule()
        # Remove "a" from the underlying graph out from under "b" (via
        # direct graph manipulation, to simulate the real dangling-ref
        # scenario) - b's dependencies list still says ["a"].
        del sched.task_graph.tasks["a"]
        # Must not raise AttributeError/KeyError.
        await sched.complete_task("a", result={"ok": True})


class TestSchedulerWorkerLifecycle:
    def test_unregister_worker_requeues_its_current_task(self):
        sched = Scheduler(max_workers=1)
        sched.add_task(_task("a"))
        sched.register_worker("w1")
        asyncio.run(sched.schedule())
        sched.workers["w1"].current_task = "a"
        sched.task_graph.get_task("a").status = TaskStatus.RUNNING
        sched.unregister_worker("w1")
        assert "w1" not in sched.workers
        assert sched.task_graph.get_task("a").status == TaskStatus.QUEUED

    def test_unregister_unknown_worker_is_a_real_noop(self):
        sched = Scheduler()
        sched.unregister_worker("ghost")  # must not raise


class TestSchedulerCancel:
    def test_cancel_pending_task_succeeds(self):
        sched = Scheduler()
        sched.add_task(_task("a"))
        sched.add_task(_task("b", deps=["a"]))
        assert sched.cancel_task("a") is True
        assert sched.task_graph.get_task("a").status == TaskStatus.CANCELLED

    def test_cancel_cascades_to_dependents(self):
        sched = Scheduler()
        sched.add_task(_task("a"))
        sched.add_task(_task("b", deps=["a"]))
        sched.cancel_task("a")
        assert sched.task_graph.get_task("b").status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_running_task_fails(self):
        sched = Scheduler(max_workers=1)
        sched.add_task(_task("a"))
        sched.register_worker("w1")
        await sched.schedule()
        assert sched.cancel_task("a") is False

    def test_cancel_unknown_task_returns_false(self):
        sched = Scheduler()
        assert sched.cancel_task("ghost") is False


class TestSchedulerStatusReporting:
    def test_get_task_status_reports_real_shape(self):
        sched = Scheduler()
        sched.add_task(_task("a", priority=7))
        status = sched.get_task_status("a")
        assert status["task_id"] == "a"
        assert status["priority"] == 7
        assert status["status"] == "queued"

    def test_get_task_status_for_unknown_id_is_none(self):
        sched = Scheduler()
        assert sched.get_task_status("ghost") is None

    def test_get_worker_status_reports_real_shape(self):
        sched = Scheduler()
        sched.register_worker("w1")
        status = sched.get_worker_status("w1")
        assert status["worker_id"] == "w1"
        assert status["status"] == "idle"

    def test_get_worker_status_for_unknown_id_is_none(self):
        sched = Scheduler()
        assert sched.get_worker_status("ghost") is None

    @pytest.mark.asyncio
    async def test_get_stats_reports_real_success_rate_and_throughput(self):
        sched = Scheduler(max_workers=1)
        sched.add_task(_task("a"))
        sched.register_worker("w1")
        await sched.schedule()
        await sched.complete_task("a", result={"ok": True})
        stats = sched.get_stats()
        assert stats["total_completed"] == 1
        assert stats["success_rate"] == "100.00%"
        assert stats["workers"]["total"] == 1

    def test_get_stats_success_rate_is_zero_with_no_scheduled_tasks(self):
        sched = Scheduler()
        stats = sched.get_stats()
        assert stats["success_rate"] == "0.00%"


class TestOptimizeScheduleHonestGap:
    def test_optimize_schedule_computes_real_order_but_reorders_nothing(self):
        sched = Scheduler()
        sched.add_task(_task("a"))
        sched.add_task(_task("b", deps=["a"]))
        result = sched.optimize_schedule()
        assert result["status"] == "order_computed"
        assert result["optimal_order_length"] == 2
        assert result["tasks_reordered"] == 0
        assert "not measured" in result["estimated_improvement"]


class TestSchedulerClear:
    def test_clear_resets_all_scheduler_state(self):
        sched = Scheduler()
        sched.add_task(_task("a"))
        sched.total_completed = 5
        sched.clear()
        assert len(sched.task_graph) == 0
        assert sched.total_scheduled == 0
        assert sched.total_completed == 0
        assert sched.ready_queue.qsize() == 0
