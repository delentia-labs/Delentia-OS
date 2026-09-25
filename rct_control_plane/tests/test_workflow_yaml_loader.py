"""
Round 44 item I.1: real tests for workflow_yaml_loader.py, the new
DAG-workflow-YAML front-end. Verifies the loader parses valid files into
exactly the (name, tasks, mode) shape algo_20_workflow_orchestrator expects,
and rejects (not silently accepts) every real failure mode: malformed YAML,
missing fields, a task type without a real executor, duplicate ids, a
dangling dependency, and a real cycle (via WorkflowDefinition's own
networkx-backed validate()).
"""
import pytest

from rct_control_plane.workflow_yaml_loader import load_workflow_yaml, WorkflowYamlError


def _write(tmp_path, text):
    p = tmp_path / "workflow.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


class TestValidWorkflows:
    def test_minimal_single_task_loads(self, tmp_path):
        path = _write(tmp_path, """
name: minimal
tasks:
  - id: t1
    type: fusion
""")
        name, tasks, mode = load_workflow_yaml(path)
        assert name == "minimal"
        assert mode == "parallel"  # real default
        assert tasks == [{
            "id": "t1", "type": "fusion", "config": {}, "depends_on": [],
            "resources": {}, "retry_config": None, "timeout_seconds": 3600,
        }]

    def test_multi_task_with_real_dependency_chain(self, tmp_path):
        path = _write(tmp_path, """
name: chained
mode: sequential
tasks:
  - id: a
    type: fusion
    depends_on: []
  - id: b
    type: fusion
    depends_on: [a]
  - id: c
    type: fusion
    depends_on: [a, b]
""")
        name, tasks, mode = load_workflow_yaml(path)
        assert mode == "sequential"
        assert [t["id"] for t in tasks] == ["a", "b", "c"]
        assert tasks[2]["depends_on"] == ["a", "b"]

    def test_full_field_set_is_carried_through(self, tmp_path):
        path = _write(tmp_path, """
name: full
tasks:
  - id: t1
    type: fusion
    config: {source_a: "x", source_b: "y"}
    resources: {cpu: 2}
    timeout_seconds: 120
    retry_config: {max_retries: 5, backoff_multiplier: 3, initial_delay_seconds: 2}
""")
        _, tasks, _ = load_workflow_yaml(path)
        task = tasks[0]
        assert task["config"] == {"source_a": "x", "source_b": "y"}
        assert task["resources"] == {"cpu": 2}
        assert task["timeout_seconds"] == 120
        assert task["retry_config"] == {"max_retries": 5, "backoff_multiplier": 3, "initial_delay_seconds": 2}


class TestRejectedWorkflows:
    def test_missing_file_is_rejected(self, tmp_path):
        with pytest.raises(WorkflowYamlError, match="not found"):
            load_workflow_yaml(str(tmp_path / "does_not_exist.yaml"))

    def test_malformed_yaml_is_rejected(self, tmp_path):
        path = _write(tmp_path, "name: [unclosed")
        with pytest.raises(WorkflowYamlError, match="Malformed YAML"):
            load_workflow_yaml(path)

    def test_non_mapping_top_level_is_rejected(self, tmp_path):
        path = _write(tmp_path, "- just\n- a\n- list\n")
        with pytest.raises(WorkflowYamlError, match="mapping"):
            load_workflow_yaml(path)

    def test_missing_name_is_rejected(self, tmp_path):
        path = _write(tmp_path, "tasks:\n  - id: t1\n    type: fusion\n")
        with pytest.raises(WorkflowYamlError, match="name"):
            load_workflow_yaml(path)

    def test_invalid_mode_is_rejected(self, tmp_path):
        path = _write(tmp_path, "name: x\nmode: whenever\ntasks:\n  - id: t1\n    type: fusion\n")
        with pytest.raises(WorkflowYamlError, match="mode"):
            load_workflow_yaml(path)

    def test_empty_tasks_list_is_rejected(self, tmp_path):
        path = _write(tmp_path, "name: x\ntasks: []\n")
        with pytest.raises(WorkflowYamlError, match="tasks"):
            load_workflow_yaml(path)

    def test_task_missing_id_is_rejected(self, tmp_path):
        path = _write(tmp_path, "name: x\ntasks:\n  - type: fusion\n")
        with pytest.raises(WorkflowYamlError, match="'id'"):
            load_workflow_yaml(path)

    def test_task_with_unreal_type_is_rejected_not_silently_simulated(self, tmp_path):
        # The whole point of I.1.2(a): a type with no real executor must be
        # refused at load time, not accepted and left to run as a silent
        # "simulated": true no-op that the engine still marks COMPLETED.
        path = _write(tmp_path, "name: x\ntasks:\n  - id: t1\n    type: http_fetch\n")
        with pytest.raises(WorkflowYamlError, match="no real executor"):
            load_workflow_yaml(path)

    def test_duplicate_task_ids_are_rejected(self, tmp_path):
        path = _write(tmp_path, """
name: x
tasks:
  - id: dup
    type: fusion
  - id: dup
    type: fusion
""")
        with pytest.raises(WorkflowYamlError, match="Duplicate"):
            load_workflow_yaml(path)

    def test_dangling_dependency_is_rejected(self, tmp_path):
        path = _write(tmp_path, """
name: x
tasks:
  - id: t1
    type: fusion
    depends_on: [ghost]
""")
        with pytest.raises(WorkflowYamlError, match="non-existent"):
            load_workflow_yaml(path)

    def test_real_cycle_is_rejected(self, tmp_path):
        # A -> B -> A: a genuine cycle, caught by WorkflowDefinition's own
        # real nx.is_directed_acyclic_graph() check (reused, not reimplemented).
        path = _write(tmp_path, """
name: x
tasks:
  - id: a
    type: fusion
    depends_on: [b]
  - id: b
    type: fusion
    depends_on: [a]
""")
        with pytest.raises(WorkflowYamlError, match="cycle"):
            load_workflow_yaml(path)
