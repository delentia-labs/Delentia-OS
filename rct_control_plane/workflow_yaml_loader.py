"""
DAG-workflow-YAML — Phase 1 (Round 44 item I.1)

Loads a `.yaml` workflow definition into the exact same shape
`AlgorithmKernel41.algo_20_workflow_orchestrator(name, tasks, mode)` already
accepts today (`name: str`, `tasks: List[Dict[str, Any]]`, `mode: str`) — this
module adds no new engine, no new semantics, and no new task-execution
capability. The real DAG engine (`algo_20_workflow_orchestrator.py`'s
`WorkflowEngine`/`WorkflowDefinition`, real `networkx` DAG + cycle detection,
real `nx.topological_sort`/dependency-respecting parallel scheduling) already
exists and is already kernel-wired; this file is only a front-end so an
operator can hand `delentia` a `.yaml` file instead of hand-writing Python.

Task-type allowlist
--------------------
As of this round, `WorkflowEngine._run_task_type()` has a REAL executor for
exactly one task type: ``"fusion"`` (dispatches to
``IntegrationManager.execute_fusion_task()`` -> real ALGO-19 Data Fusion).
Every other `type` value falls through to an honestly-labeled
(`"simulated": True`) no-op that the scheduler still marks COMPLETED for
dependency-resolution purposes — so a YAML file with a typo'd or
not-yet-implemented task type would silently "succeed" without doing
anything real. This loader refuses that outcome at load time instead: any
task whose `type` is not in `_REAL_TASK_TYPES` is rejected before the
workflow ever reaches the engine, with an error naming the offending task
and type. Widen `_REAL_TASK_TYPES` only when a real executor is added for
that type in `algo_20_workflow_orchestrator.py`.

Apache 2.0 — Delentia Labs (https://delentia.com)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from rct_control_plane.algo_20_workflow_orchestrator import TaskConfig, WorkflowDefinition

# Task types with a real executor in WorkflowEngine._run_task_type() today.
# See module docstring "Task-type allowlist".
_REAL_TASK_TYPES = {"fusion"}


class WorkflowYamlError(ValueError):
    """Raised for any problem with a workflow YAML file — malformed YAML,
    a missing required field, a task type without a real executor, or a
    DAG that fails WorkflowDefinition's own validation (duplicate ids,
    dangling dependency, cycle)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowYamlError(message)


def load_workflow_yaml(path: str) -> Tuple[str, List[Dict[str, Any]], str]:
    """
    Parse and validate a workflow YAML file.

    Returns ``(name, tasks, mode)`` in exactly the shape
    ``AlgorithmKernel41.algo_20_workflow_orchestrator(name, tasks, mode)``
    expects, so a caller does::

        name, tasks, mode = load_workflow_yaml(path)
        result = await kernel.algo_20_workflow_orchestrator(name, tasks, mode)

    Raises ``WorkflowYamlError`` (a ``ValueError`` subclass) on any problem,
    with a message naming the specific issue. Nothing is executed here —
    this function only parses and validates.
    """
    file_path = Path(path)
    _require(file_path.is_file(), f"Workflow YAML file not found: {path}")

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkflowYamlError(f"Could not read {path}: {exc}") from exc

    try:
        doc = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise WorkflowYamlError(f"Malformed YAML in {path}: {exc}") from exc

    _require(isinstance(doc, dict), f"{path}: top level must be a YAML mapping (name/mode/tasks)")

    name = doc.get("name")
    _require(isinstance(name, str) and name.strip() != "", f"{path}: missing or empty required field 'name'")

    mode = doc.get("mode", "parallel")
    _require(
        mode in ("sequential", "parallel", "hybrid"),
        f"{path}: 'mode' must be one of sequential/parallel/hybrid, got {mode!r}",
    )

    raw_tasks = doc.get("tasks")
    _require(isinstance(raw_tasks, list) and len(raw_tasks) > 0, f"{path}: 'tasks' must be a non-empty list")

    tasks: List[Dict[str, Any]] = []
    for i, raw_task in enumerate(raw_tasks):
        _require(isinstance(raw_task, dict), f"{path}: tasks[{i}] must be a mapping")

        task_id = raw_task.get("id")
        _require(isinstance(task_id, str) and task_id.strip() != "", f"{path}: tasks[{i}] missing required field 'id'")

        task_type = raw_task.get("type")
        _require(isinstance(task_type, str) and task_type.strip() != "", f"{path}: task '{task_id}' missing required field 'type'")
        _require(
            task_type in _REAL_TASK_TYPES,
            f"{path}: task '{task_id}' has type '{task_type}', which has no real executor yet "
            f"(only {sorted(_REAL_TASK_TYPES)} are real today — see workflow_yaml_loader.py "
            f"module docstring). Refusing to load a workflow that would silently no-op.",
        )

        depends_on = raw_task.get("depends_on", [])
        _require(isinstance(depends_on, list), f"{path}: task '{task_id}'.depends_on must be a list")

        tasks.append({
            "id": task_id,
            "type": task_type,
            "config": raw_task.get("config", {}),
            "depends_on": depends_on,
            "resources": raw_task.get("resources", {}),
            "retry_config": raw_task.get("retry_config"),
            "timeout_seconds": raw_task.get("timeout_seconds", 3600),
        })

    # Reuse WorkflowDefinition's own real validation (duplicate ids, dangling
    # dependency, cycle detection via networkx) rather than re-implementing
    # it here, so the error a bad YAML file gets matches the error the
    # engine itself would raise at runtime for the same bad shape.
    task_configs = [
        TaskConfig(
            id=t["id"], type=t["type"], config=t["config"], depends_on=t["depends_on"],
            resources=t["resources"], retry_config=t["retry_config"], timeout_seconds=t["timeout_seconds"],
        )
        for t in tasks
    ]
    try:
        WorkflowDefinition(id="validation-only", name=name, description=name, tasks=task_configs).validate()
    except ValueError as exc:
        raise WorkflowYamlError(f"{path}: {exc}") from exc

    return name, tasks, mode
