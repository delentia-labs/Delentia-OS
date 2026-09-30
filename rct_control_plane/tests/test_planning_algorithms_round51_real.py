"""
Round 51: ALGO-02, ALGO-37 and ALGO-38 do what their names say.
(They used to return 1/(rank+1), three fixed strings, and `len(constraints) > 0`.)
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
from rct_control_plane.planning_algorithms import expand_plan, prioritize_goals, solve_constraints


@pytest.fixture(scope="module")
def kernel():
    return AlgorithmKernel41()


class TestPlanDepth:
    def test_stages_follow_the_intent_type(self):
        query = expand_plan("find the owner", "QUERY", "FILE", "LOW")
        deploy = expand_plan("ship it", "DEPLOY", "INFRASTRUCTURE", "SYSTEMIC")
        assert any("Read" in line for line in query) and not any("Approval" in line for line in query)
        assert any("Dry run" in line for line in deploy) and any("Approval checkpoint" in line for line in deploy)
        assert any("Map impact" in line for line in deploy)
        assert len(deploy) > len(query) + 2

    def test_every_line_names_its_position_and_task(self):
        lines = expand_plan("do x", "DEBUG", "FILE", "LOW")
        assert lines[0].startswith("do x -> Stage 1/4") and lines[-1].startswith("do x -> Stage 4/4")

    def test_the_kernel_expander_compiles_the_intent_so_different_tasks_get_different_plans(self, kernel):
        read = kernel.algo_37_planning_depth_expander("Read the file pyproject.toml and tell me the project name")
        deploy = kernel.algo_37_planning_depth_expander("Deploy the new database schema to production")
        assert read != deploy and len(deploy) > len(read)
        assert any("Approval checkpoint" in line for line in deploy)

    def test_unknown_types_still_get_a_generic_plan(self):
        assert len(expand_plan("zzz", None, None, None)) == 3


class TestConstraintSolver:
    def test_a_compatible_set_is_satisfiable_and_reports_the_bounds(self):
        r = solve_constraints(["COST <= 5", "COST >= 1", "TIME LTE 300"])
        assert r.satisfiable and r.bounds["COST"] == {"min": 1.0, "max": 5.0} and r.bounds["TIME"]["max"] == 300.0

    def test_contradicting_bounds_are_a_conflict(self):
        r = solve_constraints(["COST <= 2", "COST >= 5"])
        assert not r.satisfiable and "COST" in r.conflicts[0]

    def test_strict_bounds_that_meet_are_a_conflict_non_strict_are_not(self):
        assert not solve_constraints(["TIME < 10", "TIME >= 10"]).satisfiable
        assert solve_constraints(["TIME <= 10", "TIME >= 10"]).satisfiable

    def test_two_different_equalities_conflict(self):
        assert not solve_constraints(["COST == 1", "COST == 2"]).satisfiable

    def test_a_requirement_against_its_negation_is_a_conflict(self):
        r = solve_constraints(["must store passwords", "no store passwords"])
        assert not r.satisfiable

    def test_free_text_is_kept_and_assumed_satisfiable(self):
        r = solve_constraints(["keep the tone friendly"])
        assert r.satisfiable and r.free_text == ["keep the tone friendly"]

    def test_compiled_intent_constraints_are_understood(self, kernel):
        compiled = kernel._intent_compiler.compile(natural_language="Summarise the notes within 5 minutes and spend at most $2",
                                                   user_id="t", user_tier="PRO")
        constraints = compiled.intent.constraints
        assert len(constraints) == 2
        assert kernel.algo_38_solve(constraints)["satisfiable"] is True

    def test_the_bool_entry_point_is_false_without_constraints_and_false_on_conflict(self, kernel):
        assert kernel.algo_38_constraint_solver([]) is False
        assert kernel.algo_38_constraint_solver(["COST <= 1", "COST >= 9"]) is False
        assert kernel.algo_38_constraint_solver(["COST <= 9"]) is True


class TestMultiObjectivePlanner:
    def test_priorities_sum_to_one_and_dominated_goals_rank_lower(self):
        scores = prioritize_goals(["verify and deliver the result", "delete production data irreversibly", "map the repository"])
        assert sum(s.priority for s in scores) == pytest.approx(1.0, abs=1e-3)
        by_goal = {s.goal: s for s in scores}
        assert by_goal["verify and deliver the result"].pareto_rank == 1
        assert by_goal["delete production data irreversibly"].priority < by_goal["verify and deliver the result"].priority

    def test_the_kernel_orders_goals_by_rank_not_by_the_order_given(self, kernel):
        r = kernel.algo_02_moip(["delete production data irreversibly", "verify and deliver the result"])
        assert r["planned_goals"][0] == "verify and deliver the result"
        assert "verify and deliver the result" in r["pareto_front"]

    def test_empty_input_is_fine(self, kernel):
        assert kernel.algo_02_moip([])["planned_goals"] == []

    def test_the_full_pipeline_no_longer_checks_hardcoded_tax_constraints(self, kernel):
        result = kernel.process_intent_full_pipeline("Read the file pyproject.toml and tell me the project name")
        assert result["constraints_satisfied"] is True          # vacuous: the request states none
        assert result["depth_stages"] and "Stage 1/" in result["depth_stages"][0]
