"""
Round 44 item I.1: real, CliRunner-driven tests for `delentia workflow run`
(rct_control_plane/cli.py's new `workflow` command group).

These exercise the whole real chain: YAML file on disk -> workflow_yaml_loader
-> real WorkflowEngine (real networkx DAG scheduling) -> real FusionEngine for
`type: fusion` tasks - no mocking. The only thing kept out is the full
AlgorithmKernel41 (torch/FAISS/etc.), which this command deliberately never
imports (see cli.py's `workflow_run` docstring/comment for why).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def cli_runner():
    from click.testing import CliRunner

    return CliRunner()


@pytest.fixture
def cli():
    from rct_control_plane.cli import cli as _cli

    return _cli


def _write(tmp_path, text):
    p = tmp_path / "workflow.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


class TestWorkflowRun:
    def test_single_real_fusion_task_completes(self, cli_runner, cli, tmp_path):
        path = _write(tmp_path, """
name: single-fuse
tasks:
  - id: t1
    type: fusion
    config:
      fusion_config:
        modalities: {text: [0.1, 0.2, 0.3]}
        fusion_strategy: hybrid
""")
        result = cli_runner.invoke(cli, ["workflow", "run", path])
        assert result.exit_code == 0
        assert "completed" in result.output
        assert "t1: completed" in result.output
        assert "[simulated]" not in result.output  # real FusionEngine ran, not a stub

    def test_dependency_chain_runs_in_order_and_completes(self, cli_runner, cli, tmp_path):
        path = _write(tmp_path, """
name: chained-fuse
mode: sequential
tasks:
  - id: a
    type: fusion
    depends_on: []
    config: {fusion_config: {modalities: {text: [0.1, 0.2]}}}
  - id: b
    type: fusion
    depends_on: [a]
    config: {fusion_config: {modalities: {text: [0.3, 0.4]}}}
""")
        result = cli_runner.invoke(cli, ["workflow", "run", path])
        assert result.exit_code == 0
        # a must be reported before b in sequential mode's output ordering
        assert result.output.index("a: completed") < result.output.index("b: completed")

    def test_invalid_yaml_exits_nonzero_with_clear_error(self, cli_runner, cli, tmp_path):
        path = _write(tmp_path, "name: bad\ntasks:\n  - id: t1\n    type: not_a_real_type\n")
        result = cli_runner.invoke(cli, ["workflow", "run", path])
        assert result.exit_code == 1
        assert "no real executor" in result.output

    def test_missing_file_exits_nonzero(self, cli_runner, cli, tmp_path):
        result = cli_runner.invoke(cli, ["workflow", "run", str(tmp_path / "ghost.yaml")])
        assert result.exit_code != 0

    def test_help_text_is_real(self, cli_runner, cli):
        result = cli_runner.invoke(cli, ["workflow", "run", "--help"])
        assert result.exit_code == 0
        assert "YAML_PATH" in result.output
