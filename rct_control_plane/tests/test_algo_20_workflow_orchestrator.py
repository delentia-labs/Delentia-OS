"""
Round 45 item C (group 2): real tests for ALGO-20's WorkflowEngine and
IntegrationManager - 0% coverage before this file. This module has NO
external network calls at all (the source's HTTP integrations were
replaced with real in-process calls into ALGO-15's Scheduler and ALGO-19's
FusionEngine - see this module's own docstring) - both used here as real,
already-lightweight instances, not mocks, matching this project's "real,
not mocked" discipline. Retry-path tests use small delays so they stay
fast.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio

import pytest

from rct_control_plane.algo_15_hrm import Scheduler
from rct_control_plane.algo_19_fusion import FusionEngine
from rct_control_plane.algo_20_workflow_orchestrator import (
    ResourceRequirements, ResourceManager, DataFusionIntegration, IntegrationManager,
    TaskStatus, WorkflowStatus, ExecutionMode, TaskConfig, TaskExecution,
    WorkflowDefinition, WorkflowExecution, WorkflowEngine,
)


def _task(id, depends_on=None, type="generic", retry_config=None):
    return {"id": id, "type": type, "config": {}, "depends_on": depends_on or [],
            "resources": {}, "retry_config": retry_config}


class TestResourceRequirements:
    def test_to_dict_and_from_dict_round_trip(self):
        req = ResourceRequirements(cpu=4, memory="8GB", gpu=1)
        assert ResourceRequirements.from_dict(req.to_dict()) == req

    def test_from_dict_fills_in_defaults_for_missing_keys(self):
        req = ResourceRequirements.from_dict({"cpu": 2})
        assert req.memory == "1GB"
        assert req.gpu == 0


class TestResourceManagerWithoutHrm:
    @pytest.mark.asyncio
    async def test_allocate_falls_back_to_local_when_no_scheduler_configured(self):
        manager = ResourceManager(hrm_scheduler=None)
        allocation = await manager.allocate_resources("t1", ResourceRequirements())
        assert allocation.allocated is True
        assert allocation.message == "Resources allocated locally"

    @pytest.mark.asyncio
    async def test_deallocate_unknown_task_returns_false(self):
        manager = ResourceManager(hrm_scheduler=None)
        assert await manager.deallocate_resources("no-such-task") is False

    @pytest.mark.asyncio
    async def test_check_hrm_health_is_false_without_a_scheduler(self):
        manager = ResourceManager(hrm_scheduler=None)
        assert await manager.check_hrm_health() is False

    @pytest.mark.asyncio
    async def test_get_available_resources_returns_static_defaults(self):
        manager = ResourceManager(hrm_scheduler=None)
        resources = await manager.get_available_resources()
        assert resources["cpu"] == 16


class TestResourceManagerWithRealHrmScheduler:
    @pytest.mark.asyncio
    async def test_allocation_via_a_real_scheduler_auto_registers_a_worker(self):
        scheduler = Scheduler()
        manager = ResourceManager(hrm_scheduler=scheduler)
        assert not scheduler.workers  # confirms the real starting state

        allocation = await manager.allocate_resources("t1", ResourceRequirements())
        assert allocation.allocated is True
        assert "HRM Scheduler" in allocation.message
        assert len(scheduler.workers) == 1

    @pytest.mark.asyncio
    async def test_check_hrm_health_is_true_with_a_real_scheduler(self):
        manager = ResourceManager(hrm_scheduler=Scheduler())
        assert await manager.check_hrm_health() is True

    @pytest.mark.asyncio
    async def test_deallocate_completes_the_real_admitted_hrm_task(self):
        scheduler = Scheduler()
        manager = ResourceManager(hrm_scheduler=scheduler)
        await manager.allocate_resources("t1", ResourceRequirements())

        result = await manager.deallocate_resources("t1")
        assert result is True
        assert "t1" not in manager.allocations


class TestDataFusionIntegration:
    @pytest.mark.asyncio
    async def test_without_a_fusion_engine_returns_an_honest_error(self):
        integration = DataFusionIntegration(fusion_engine=None)
        result = await integration.fuse_data({"a": [1.0, 2.0]})
        assert result == {"error": "Fusion engine not configured"}

    @pytest.mark.asyncio
    async def test_real_fusion_engine_produces_a_real_fused_representation(self):
        integration = DataFusionIntegration(fusion_engine=FusionEngine())
        result = await integration.fuse_data({
            "text": [1.0, 2.0, 3.0], "vector": [4.0, 5.0, 6.0],
        }, strategy="hybrid")
        assert "fused_representation" in result
        assert result["strategy_used"] == "hybrid"

    @pytest.mark.asyncio
    async def test_invalid_strategy_string_returns_an_error_not_a_crash(self):
        integration = DataFusionIntegration(fusion_engine=FusionEngine())
        result = await integration.fuse_data({"a": [1.0]}, strategy="not_a_real_strategy")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_feature_extraction_methods_are_honest_about_the_gap(self):
        integration = DataFusionIntegration(fusion_engine=FusionEngine())
        assert "error" in await integration.extract_text_features("some text")
        assert "error" in await integration.extract_vector_features([1.0, 2.0])

    @pytest.mark.asyncio
    async def test_check_fusion_health_reflects_configuration(self):
        assert await DataFusionIntegration(FusionEngine()).check_fusion_health() is True
        assert await DataFusionIntegration(None).check_fusion_health() is False


class TestIntegrationManager:
    @pytest.mark.asyncio
    async def test_check_all_services_reports_both_as_healthy_when_configured(self):
        manager = IntegrationManager(hrm_scheduler=Scheduler(), fusion_engine=FusionEngine())
        status = await manager.check_all_services()
        assert status == {"hrm_service": "healthy", "fusion_service": "healthy"}

    @pytest.mark.asyncio
    async def test_check_all_services_reports_unavailable_when_not_configured(self):
        manager = IntegrationManager()
        status = await manager.check_all_services()
        assert status == {"hrm_service": "unavailable", "fusion_service": "unavailable"}

    @pytest.mark.asyncio
    async def test_execute_fusion_task_delegates_to_the_real_fusion_engine(self):
        manager = IntegrationManager(fusion_engine=FusionEngine())
        result = await manager.execute_fusion_task({
            "fusion_config": {"modalities": {"a": [1.0, 2.0]}, "fusion_strategy": "late"}
        })
        assert "fused_representation" in result

    @pytest.mark.asyncio
    async def test_allocate_and_deallocate_task_resources_wrappers(self):
        manager = IntegrationManager(hrm_scheduler=Scheduler())
        allocation = await manager.allocate_task_resources("t1", {"cpu": 2})
        assert allocation.allocated is True
        assert await manager.deallocate_task_resources("t1") is True


class TestWorkflowDefinitionValidation:
    def test_valid_dag_passes(self):
        wf = WorkflowDefinition(id="w1", name="n", description="d", tasks=[
            TaskConfig(id="a", type="x", config={}, depends_on=[], resources={}),
            TaskConfig(id="b", type="x", config={}, depends_on=["a"], resources={}),
        ])
        assert wf.validate() is True

    def test_duplicate_task_ids_raise(self):
        wf = WorkflowDefinition(id="w1", name="n", description="d", tasks=[
            TaskConfig(id="a", type="x", config={}, depends_on=[], resources={}),
            TaskConfig(id="a", type="x", config={}, depends_on=[], resources={}),
        ])
        with pytest.raises(ValueError, match="Duplicate task IDs"):
            wf.validate()

    def test_missing_dependency_raises(self):
        wf = WorkflowDefinition(id="w1", name="n", description="d", tasks=[
            TaskConfig(id="a", type="x", config={}, depends_on=["ghost"], resources={}),
        ])
        with pytest.raises(ValueError, match="non-existent task"):
            wf.validate()

    def test_real_cycle_is_detected_via_networkx(self):
        wf = WorkflowDefinition(id="w1", name="n", description="d", tasks=[
            TaskConfig(id="a", type="x", config={}, depends_on=["b"], resources={}),
            TaskConfig(id="b", type="x", config={}, depends_on=["a"], resources={}),
        ])
        with pytest.raises(ValueError, match="cycles"):
            wf.validate()


class TestTaskConfigDefaults:
    def test_default_retry_config_is_filled_in(self):
        task = TaskConfig(id="a", type="x", config={}, depends_on=[], resources={})
        assert task.retry_config == {"max_retries": 3, "backoff_multiplier": 2, "initial_delay_seconds": 1}

    def test_explicit_retry_config_is_preserved(self):
        task = TaskConfig(id="a", type="x", config={}, depends_on=[], resources={},
                           retry_config={"max_retries": 0})
        assert task.retry_config == {"max_retries": 0}


class TestTaskExecution:
    def test_duration_is_none_before_completion(self):
        te = TaskExecution(task_id="a", status=TaskStatus.RUNNING)
        assert te.duration_seconds() is None

    def test_add_log_appends_a_real_entry(self):
        te = TaskExecution(task_id="a", status=TaskStatus.PENDING)
        te.add_log("INFO", "a real message")
        assert te.logs[0]["message"] == "a real message"


class TestWorkflowExecutionSummary:
    def test_progress_with_no_tasks_is_zero(self):
        ex = WorkflowExecution(execution_id="e1", workflow_id="w1", status=WorkflowStatus.RUNNING, mode=ExecutionMode.SEQUENTIAL)
        assert ex.progress() == 0.0

    def test_progress_reflects_completed_fraction(self):
        ex = WorkflowExecution(execution_id="e1", workflow_id="w1", status=WorkflowStatus.RUNNING, mode=ExecutionMode.SEQUENTIAL,
                                task_executions={
                                    "a": TaskExecution(task_id="a", status=TaskStatus.COMPLETED),
                                    "b": TaskExecution(task_id="b", status=TaskStatus.PENDING),
                                })
        assert ex.progress() == 0.5

    def test_task_summary_counts_every_status_bucket(self):
        ex = WorkflowExecution(execution_id="e1", workflow_id="w1", status=WorkflowStatus.RUNNING, mode=ExecutionMode.SEQUENTIAL,
                                task_executions={
                                    "a": TaskExecution(task_id="a", status=TaskStatus.COMPLETED),
                                    "b": TaskExecution(task_id="b", status=TaskStatus.FAILED),
                                    "c": TaskExecution(task_id="c", status=TaskStatus.RUNNING),
                                    "d": TaskExecution(task_id="d", status=TaskStatus.PENDING),
                                })
        assert ex.task_summary() == {"total": 4, "pending": 1, "running": 1, "completed": 1, "failed": 1}


class TestWorkflowEngineCreateAndManage:
    @pytest.fixture
    def engine(self):
        return WorkflowEngine()

    @pytest.mark.asyncio
    async def test_create_workflow_stores_and_returns_it(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        assert engine.get_workflow(workflow.id) is workflow

    @pytest.mark.asyncio
    async def test_create_workflow_rejects_an_invalid_dag(self, engine):
        with pytest.raises(ValueError, match="cycles"):
            await engine.create_workflow("wf1", "desc", tasks=[
                _task("a", depends_on=["b"]), _task("b", depends_on=["a"]),
            ])

    @pytest.mark.asyncio
    async def test_get_unknown_workflow_returns_none(self, engine):
        assert engine.get_workflow("no-such-workflow") is None

    @pytest.mark.asyncio
    async def test_delete_workflow_removes_it(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        assert await engine.delete_workflow(workflow.id) is True
        assert engine.get_workflow(workflow.id) is None

    @pytest.mark.asyncio
    async def test_delete_unknown_workflow_returns_false(self, engine):
        assert await engine.delete_workflow("no-such-workflow") is False

    @pytest.mark.asyncio
    async def test_list_workflows_reflects_real_created_workflows(self, engine):
        await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        await engine.create_workflow("wf2", "desc", tasks=[_task("a")])
        listed = engine.list_workflows()
        assert len(listed) == 2
        assert all(w["status"] == "created" for w in listed)

    @pytest.mark.asyncio
    async def test_list_workflows_filters_by_status_using_real_execution_state(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]

        assert len(engine.list_workflows(status="completed")) == 1
        assert len(engine.list_workflows(status="running")) == 0

    @pytest.mark.asyncio
    async def test_delete_workflow_with_a_real_running_execution_raises(self, engine, monkeypatch):
        async def _slow_task(self, task):
            await asyncio.sleep(5)
            return {"result": "success"}
        monkeypatch.setattr(WorkflowEngine, "_run_task_type", _slow_task)

        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await asyncio.sleep(0.05)  # let it actually start running

        with pytest.raises(ValueError, match="active executions"):
            await engine.delete_workflow(workflow.id)

        await engine.stop_execution(workflow.id, execution.execution_id)  # real cleanup


class TestWorkflowExecutionSequential:
    @pytest.fixture
    def engine(self):
        return WorkflowEngine()

    @pytest.mark.asyncio
    async def test_start_execution_unknown_workflow_raises(self, engine):
        with pytest.raises(ValueError, match="not found"):
            await engine.start_execution("no-such-workflow")

    @pytest.mark.asyncio
    async def test_sequential_execution_of_simulated_tasks_completes_successfully(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[
            _task("a"), _task("b", depends_on=["a"]),
        ])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.SEQUENTIAL)
        await engine.execution_tasks[execution.execution_id]  # wait for the real background task

        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.task_executions["a"].status == TaskStatus.COMPLETED
        assert execution.task_executions["a"].output["simulated"] is True

    @pytest.mark.asyncio
    async def test_sequential_execution_respects_topological_order(self, engine):
        order = []
        workflow = await engine.create_workflow("wf1", "desc", tasks=[
            _task("a"), _task("b", depends_on=["a"]), _task("c", depends_on=["b"]),
        ])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.SEQUENTIAL)
        await engine.execution_tasks[execution.execution_id]

        for tid in ("a", "b", "c"):
            order.append(execution.task_executions[tid].started_at)
        assert order == sorted(order)  # 'a' started before 'b' before 'c'


class TestWorkflowExecutionParallel:
    @pytest.fixture
    def engine(self):
        return WorkflowEngine()

    @pytest.mark.asyncio
    async def test_parallel_execution_completes_all_independent_tasks(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a"), _task("b"), _task("c")])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.PARALLEL, max_parallel_tasks=2)
        await engine.execution_tasks[execution.execution_id]

        assert execution.status == WorkflowStatus.COMPLETED
        assert all(te.status == TaskStatus.COMPLETED for te in execution.task_executions.values())

    @pytest.mark.asyncio
    async def test_parallel_execution_respects_dependency_ordering(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[
            _task("a"), _task("b"), _task("c", depends_on=["a", "b"]),
        ])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.PARALLEL)
        await engine.execution_tasks[execution.execution_id]

        c_start = execution.task_executions["c"].started_at
        assert execution.task_executions["a"].completed_at <= c_start
        assert execution.task_executions["b"].completed_at <= c_start

    @pytest.mark.asyncio
    async def test_hybrid_mode_also_completes_successfully(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a"), _task("b")])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.HYBRID)
        await engine.execution_tasks[execution.execution_id]
        assert execution.status == WorkflowStatus.COMPLETED


class TestWorkflowExecutionFusionTask:
    @pytest.mark.asyncio
    async def test_fusion_task_type_calls_the_real_fusion_engine(self):
        integration = IntegrationManager(fusion_engine=FusionEngine())
        engine = WorkflowEngine(integration_manager=integration)
        workflow = await engine.create_workflow("wf1", "desc", tasks=[{
            "id": "fuse1", "type": "fusion", "depends_on": [], "resources": {},
            "config": {"fusion_config": {"modalities": {"a": [1.0, 2.0]}, "fusion_strategy": "hybrid"}},
        }])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.SEQUENTIAL)
        await engine.execution_tasks[execution.execution_id]

        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.task_executions["fuse1"].output["simulated"] is False

    @pytest.mark.asyncio
    async def test_fusion_task_error_result_raises_and_is_caught_by_the_retry_loop(self):
        integration = IntegrationManager(fusion_engine=None)  # "not configured" -> real error result
        engine = WorkflowEngine(integration_manager=integration)
        workflow = await engine.create_workflow("wf1", "desc", tasks=[{
            "id": "fuse1", "type": "fusion", "depends_on": [], "resources": {},
            "config": {"fusion_config": {"modalities": {"a": [1.0]}}},
            "retry_config": {"max_retries": 0},
        }])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.SEQUENTIAL)
        await engine.execution_tasks[execution.execution_id]

        assert execution.task_executions["fuse1"].status == TaskStatus.FAILED
        assert "fusion task failed" in execution.task_executions["fuse1"].error

    @pytest.mark.asyncio
    async def test_fusion_task_without_an_integration_manager_falls_back_to_simulated(self):
        engine = WorkflowEngine(integration_manager=None)
        workflow = await engine.create_workflow("wf1", "desc", tasks=[
            {"id": "fuse1", "type": "fusion", "depends_on": [], "resources": {}, "config": {}},
        ])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.SEQUENTIAL)
        await engine.execution_tasks[execution.execution_id]
        assert execution.task_executions["fuse1"].output["simulated"] is True


class TestTaskRetryAndFailure:
    @pytest.fixture
    def engine(self):
        return WorkflowEngine()

    @pytest.mark.asyncio
    async def test_a_task_that_always_fails_retries_the_configured_number_of_times(self, engine, monkeypatch):
        call_count = {"n": 0}

        async def _always_fail(self, task):
            call_count["n"] += 1
            raise RuntimeError("simulated real failure")
        monkeypatch.setattr(WorkflowEngine, "_run_task_type", _always_fail)

        workflow = await engine.create_workflow("wf1", "desc", tasks=[
            _task("a", retry_config={"max_retries": 2, "initial_delay_seconds": 0.01, "backoff_multiplier": 1}),
        ])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.SEQUENTIAL)
        await engine.execution_tasks[execution.execution_id]

        assert execution.status == WorkflowStatus.FAILED
        assert execution.task_executions["a"].status == TaskStatus.FAILED
        assert execution.task_executions["a"].retry_count == 2
        assert call_count["n"] == 3  # 1 initial attempt + 2 retries

    @pytest.mark.asyncio
    async def test_a_task_that_succeeds_on_a_later_retry_ends_completed(self, engine, monkeypatch):
        attempts = {"n": 0}

        async def _fail_once_then_succeed(self, task):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient failure")
            return {"task_id": task.id, "result": "success"}
        monkeypatch.setattr(WorkflowEngine, "_run_task_type", _fail_once_then_succeed)

        workflow = await engine.create_workflow("wf1", "desc", tasks=[
            _task("a", retry_config={"max_retries": 2, "initial_delay_seconds": 0.01, "backoff_multiplier": 1}),
        ])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.SEQUENTIAL)
        await engine.execution_tasks[execution.execution_id]

        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.task_executions["a"].retry_count == 1

    @pytest.mark.asyncio
    async def test_sequential_execution_stops_after_a_failed_task(self, engine, monkeypatch):
        async def _always_fail(self, task):
            raise RuntimeError("boom")
        monkeypatch.setattr(WorkflowEngine, "_run_task_type", _always_fail)

        workflow = await engine.create_workflow("wf1", "desc", tasks=[
            _task("a", retry_config={"max_retries": 0}),
            _task("b", depends_on=["a"], retry_config={"max_retries": 0}),
        ])
        execution = await engine.start_execution(workflow.id, mode=ExecutionMode.SEQUENTIAL)
        await engine.execution_tasks[execution.execution_id]

        assert execution.task_executions["a"].status == TaskStatus.FAILED
        assert execution.task_executions["b"].status == TaskStatus.PENDING  # never reached


class TestExecutionControl:
    @pytest.fixture
    def engine(self):
        return WorkflowEngine()

    @pytest.mark.asyncio
    async def test_stop_execution_cancels_a_running_execution(self, engine, monkeypatch):
        async def _slow_task(self, task):
            await asyncio.sleep(5)
            return {"result": "success"}
        monkeypatch.setattr(WorkflowEngine, "_run_task_type", _slow_task)

        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await asyncio.sleep(0.05)  # let it actually start running

        stopped = await engine.stop_execution(workflow.id, execution.execution_id)
        assert stopped is True
        assert execution.status == WorkflowStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_stop_unknown_execution_returns_false(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        assert await engine.stop_execution(workflow.id, "no-such-execution") is False

    @pytest.mark.asyncio
    async def test_pause_and_resume_a_running_execution(self, engine, monkeypatch):
        async def _slow_task(self, task):
            await asyncio.sleep(5)
            return {"result": "success"}
        monkeypatch.setattr(WorkflowEngine, "_run_task_type", _slow_task)

        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await asyncio.sleep(0.05)

        assert await engine.pause_execution(workflow.id, execution.execution_id) is True
        assert execution.status == WorkflowStatus.PAUSED
        assert await engine.resume_execution(workflow.id, execution.execution_id) is True
        assert execution.status == WorkflowStatus.RUNNING

        await engine.stop_execution(workflow.id, execution.execution_id)  # real cleanup

    @pytest.mark.asyncio
    async def test_pause_a_non_running_execution_returns_false(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]  # let it finish (already COMPLETED)
        assert await engine.pause_execution(workflow.id, execution.execution_id) is False

    @pytest.mark.asyncio
    async def test_resume_a_non_paused_execution_returns_false(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]  # already COMPLETED, never paused
        assert await engine.resume_execution(workflow.id, execution.execution_id) is False

    @pytest.mark.asyncio
    async def test_stop_an_already_completed_execution_returns_false(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]
        assert await engine.stop_execution(workflow.id, execution.execution_id) is False


class TestStatusAndHistoryQueries:
    @pytest.fixture
    def engine(self):
        return WorkflowEngine()

    @pytest.mark.asyncio
    async def test_get_execution_status_unknown_returns_none(self, engine):
        assert engine.get_execution_status("no-wf", "no-exec") is None

    @pytest.mark.asyncio
    async def test_get_execution_status_reflects_real_progress(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]

        status = engine.get_execution_status(workflow.id, execution.execution_id)
        assert status["status"] == "completed"
        assert status["progress"] == 1.0

    @pytest.mark.asyncio
    async def test_get_task_details_unknown_task_returns_none(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]
        assert engine.get_task_details(workflow.id, "no-such-task", execution.execution_id) is None

    @pytest.mark.asyncio
    async def test_get_task_details_returns_real_output_and_logs(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]

        details = engine.get_task_details(workflow.id, "a", execution.execution_id)
        assert details["status"] == "completed"
        assert details["output"]["simulated"] is True
        assert len(details["logs"]) >= 2

    @pytest.mark.asyncio
    async def test_get_execution_history_reports_success_rate(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]

        history = engine.get_execution_history(workflow.id)
        assert history[0]["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_get_stats_aggregates_across_all_executions(self, engine):
        workflow = await engine.create_workflow("wf1", "desc", tasks=[_task("a")])
        execution = await engine.start_execution(workflow.id)
        await engine.execution_tasks[execution.execution_id]

        stats = engine.get_stats()
        assert stats["total_workflows"] == 1
        assert stats["total_executions"] == 1
        assert stats["success_rate"] == 1.0
        assert stats["tasks_executed"] == 1
