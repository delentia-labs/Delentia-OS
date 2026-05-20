"""
Tests for rct_control_plane — execution_graph_ir, dsl_parser, intent_schema,
control_plane_state, policy_language, intent_compiler.
All public API surfaces with no external I/O dependencies.
"""

import pytest
from decimal import Decimal

from rct_control_plane.control_plane_state import (
    ControlPlanePhase,
    ControlPlaneState,
    TransitionResult,
    VALID_TRANSITIONS,
)
from rct_control_plane.dsl_parser import DSLParser, DSLParseError
from rct_control_plane.execution_graph_ir import (
    DependencyEdge,
    DependencyType,
    ExecutionGraph,
    ExecutionNode,
    NodeStatus,
    NodeType,
    ResourceRequirement,
)
from rct_control_plane.intent_compiler import (
    IntentCompiler,
    quick_compile,
)
from rct_control_plane.intent_schema import (
    BudgetSpec,
    ContextBundle,
    IntentObject,
    IntentPriority,
    IntentType,
    RiskProfile,
    ScopeObject,
    ScopeType,
)
from rct_control_plane.policy_language import (
    ConditionOperator,
    PolicyAction,
    PolicyCondition,
    PolicyEvaluator,
    PolicyEvaluationResult,
    PolicyPriority,
    PolicyRule,
    PolicyScope,
)

# ---------------------------------------------------------------------------
# execution_graph_ir
# ---------------------------------------------------------------------------


class TestExecutionGraph:
    def test_create_empty_graph(self):
        graph = ExecutionGraph(intent_id="test-001")
        assert graph.intent_id == "test-001"
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_add_node(self):
        graph = ExecutionGraph(intent_id="test-002")
        node = ExecutionNode(
            id="node_a",
            node_type=NodeType.AGENT_CAPABILITY,
            capability="code_analysis",
        )
        graph.add_node(node)
        assert "node_a" in graph.nodes
        assert graph.nodes["node_a"].capability == "code_analysis"

    def test_duplicate_node_raises(self):
        graph = ExecutionGraph(intent_id="test-003")
        node = ExecutionNode(id="node_a", node_type=NodeType.TOOL_CALL)
        graph.add_node(node)
        with pytest.raises(ValueError, match="already exists"):
            graph.add_node(node)

    def test_add_edge(self):
        graph = ExecutionGraph(intent_id="test-004")
        n1 = ExecutionNode(
            id="a", node_type=NodeType.AGENT_CAPABILITY, capability="read"
        )
        n2 = ExecutionNode(
            id="b", node_type=NodeType.AGENT_CAPABILITY, capability="write"
        )
        graph.add_node(n1)
        graph.add_node(n2)
        edge = DependencyEdge(
            from_node="a", to_node="b", dependency_type=DependencyType.SEQUENTIAL
        )
        graph.add_edge(edge)
        assert len(graph.edges) == 1

    def test_cycle_detection(self):
        graph = ExecutionGraph(intent_id="test-cycle")
        n1 = ExecutionNode(id="a", node_type=NodeType.AGENT_CAPABILITY)
        n2 = ExecutionNode(id="b", node_type=NodeType.AGENT_CAPABILITY)
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(DependencyEdge(from_node="a", to_node="b"))
        with pytest.raises(ValueError, match="[Cc]ycle"):
            graph.add_edge(DependencyEdge(from_node="b", to_node="a"))

    def test_validate_empty_graph_ok(self):
        graph = ExecutionGraph(intent_id="empty")
        errors = graph.validate()
        assert errors == []

    def test_graph_id_is_auto_generated(self):
        g1 = ExecutionGraph(intent_id="x")
        g2 = ExecutionGraph(intent_id="x")
        assert g1.graph_id != g2.graph_id

    def test_node_status_default_pending(self):
        node = ExecutionNode(id="n", node_type=NodeType.CHECKPOINT)
        assert node.status == NodeStatus.PENDING

    def test_node_estimated_cost_default_zero(self):
        node = ExecutionNode(id="n", node_type=NodeType.TOOL_CALL)
        assert node.estimated_cost == Decimal("0.0")

    def test_node_type_tool_call(self):
        node = ExecutionNode(
            id="t", node_type=NodeType.TOOL_CALL, tool_name="grep_tool"
        )
        assert node.node_type == NodeType.TOOL_CALL
        assert node.tool_name == "grep_tool"

    def test_resource_requirement_defaults(self):
        res = ResourceRequirement()
        assert res.max_cost_usd is None
        assert res.requires_gpu is False


# ---------------------------------------------------------------------------
# dsl_parser
# ---------------------------------------------------------------------------


class TestDSLParser:
    DSL_SIMPLE = """\
intent "test_intent" {
    phase analyze {
        node AnalyzeNode {
            agent_capability = "code_analysis"
            cost = 0.50
            timeout = 60s
        }
    }
}
"""

    DSL_TWO_PHASES = """\
intent "multi_phase" {
    phase analyze {
        node Analyze {
            agent_capability = "analysis"
            cost = 0.25
        }
    }
    phase implement {
        node Implement {
            agent_capability = "code_write"
            cost = 0.75
            depends_on = [Analyze]
        }
    }
}
"""

    def test_parse_simple_dsl(self):
        parser = DSLParser()
        graph = parser.parse(self.DSL_SIMPLE, intent_id="abc")
        assert len(graph.nodes) == 1
        assert "AnalyzeNode" in graph.nodes

    def test_parse_sets_intent_id(self):
        parser = DSLParser()
        graph = parser.parse(self.DSL_SIMPLE, intent_id="my-intent-123")
        assert graph.intent_id == "my-intent-123"

    def test_parse_capability(self):
        parser = DSLParser()
        graph = parser.parse(self.DSL_SIMPLE, intent_id="x")
        node = graph.nodes["AnalyzeNode"]
        assert node.capability == "code_analysis"

    def test_parse_cost(self):
        parser = DSLParser()
        graph = parser.parse(self.DSL_SIMPLE, intent_id="x")
        node = graph.nodes["AnalyzeNode"]
        assert node.estimated_cost == Decimal("0.50")

    def test_parse_duration(self):
        parser = DSLParser()
        graph = parser.parse(self.DSL_SIMPLE, intent_id="x")
        node = graph.nodes["AnalyzeNode"]
        assert node.estimated_duration_seconds == 60

    def test_parse_two_phase_creates_edge(self):
        parser = DSLParser()
        graph = parser.parse(self.DSL_TWO_PHASES, intent_id="mp")
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1  # Analyze → Implement

    def test_parse_no_intent_block_raises(self):
        parser = DSLParser()
        with pytest.raises(DSLParseError, match="No intent block"):
            parser.parse("not valid dsl", intent_id="x")

    def test_parse_total_cost_calculated(self):
        parser = DSLParser()
        graph = parser.parse(self.DSL_TWO_PHASES, intent_id="x")
        assert graph.total_estimated_cost == Decimal("1.00")


# ---------------------------------------------------------------------------
# intent_schema
# ---------------------------------------------------------------------------


class TestIntentSchema:
    def _make_intent(self, goal: str = "refactor auth module") -> IntentObject:
        return IntentObject(
            goal=goal,
            intent_type=IntentType.REFACTOR,
            scope=ScopeObject(scope_type=ScopeType.MODULE, target="auth/"),
            context=ContextBundle(user_id="u1", user_tier="PRO"),
        )

    def test_intent_object_creates(self):
        intent = self._make_intent()
        assert intent.goal == "refactor auth module"
        assert intent.intent_type == IntentType.REFACTOR

    def test_intent_id_auto_generated(self):
        i1 = self._make_intent()
        i2 = self._make_intent()
        assert i1.id != i2.id

    def test_intent_default_priority(self):
        intent = self._make_intent()
        assert intent.priority == IntentPriority.MEDIUM

    def test_intent_default_risk_profile(self):
        intent = self._make_intent()
        assert intent.risk_profile == RiskProfile.LOW

    def test_intent_empty_goal_raises(self):
        with pytest.raises(Exception):
            IntentObject(
                goal="",
                intent_type=IntentType.DEPLOY,
                scope=ScopeObject(scope_type=ScopeType.FILE, target="x.py"),
                context=ContextBundle(user_id="u", user_tier="FREE"),
            )

    def test_budget_spec_defaults(self):
        budget = BudgetSpec()
        assert budget.max_cost_usd is None
        assert budget.max_time is None

    def test_budget_spec_negative_cost_raises(self):
        with pytest.raises(Exception):
            BudgetSpec(max_cost_usd=Decimal("-5.00"))

    def test_scope_object_target(self):
        scope = ScopeObject(scope_type=ScopeType.FILE, target="src/main.py")
        assert scope.target == "src/main.py"

    def test_context_bundle_request_id_auto(self):
        ctx1 = ContextBundle(user_id="u", user_tier="FREE")
        ctx2 = ContextBundle(user_id="u", user_tier="FREE")
        assert ctx1.request_id != ctx2.request_id


# ---------------------------------------------------------------------------
# control_plane_state
# ---------------------------------------------------------------------------


class TestControlPlaneState:
    def test_valid_transitions_defined(self):
        assert ControlPlanePhase.INTENT_RECEIVED in VALID_TRANSITIONS

    def test_initial_phase(self):
        state = ControlPlaneState(intent_id="i1")
        assert state.phase == ControlPlanePhase.INTENT_RECEIVED

    def test_valid_transition_succeeds(self):
        state = ControlPlaneState(intent_id="i1")
        result = state.transition_to(ControlPlanePhase.INTENT_COMPILED)
        assert result == TransitionResult.SUCCESS
        assert state.phase == ControlPlanePhase.INTENT_COMPILED

    def test_invalid_transition_rejected(self):
        state = ControlPlaneState(intent_id="i2")
        # Cannot jump from INTENT_RECEIVED to COMPLETED
        result = state.transition_to(ControlPlanePhase.COMPLETED)
        assert result == TransitionResult.INVALID_TRANSITION
        assert state.phase == ControlPlanePhase.INTENT_RECEIVED

    def test_cancel_from_any_active_phase(self):
        state = ControlPlaneState(intent_id="i3")
        result = state.transition_to(ControlPlanePhase.CANCELLED)
        assert result == TransitionResult.SUCCESS

    def test_fail_from_intent_received(self):
        state = ControlPlaneState(intent_id="i4")
        result = state.transition_to(ControlPlanePhase.FAILED)
        assert result == TransitionResult.SUCCESS


# ---------------------------------------------------------------------------
# policy_language — PolicyCondition, PolicyRule, PolicyEvaluator
# ---------------------------------------------------------------------------


class TestPolicyCondition:
    """Tests for individual PolicyCondition evaluation."""

    def test_equals_operator(self):
        cond = PolicyCondition(
            field="risk", operator=ConditionOperator.EQUALS, value="HIGH"
        )
        assert cond.evaluate({"risk": "HIGH"}) is True
        assert cond.evaluate({"risk": "LOW"}) is False

    def test_not_equals_operator(self):
        cond = PolicyCondition(
            field="tier", operator=ConditionOperator.NOT_EQUALS, value="FREE"
        )
        assert cond.evaluate({"tier": "PRO"}) is True
        assert cond.evaluate({"tier": "FREE"}) is False

    def test_greater_than_operator(self):
        cond = PolicyCondition(
            field="cost_usd",
            operator=ConditionOperator.GREATER_THAN,
            value=Decimal("100"),
        )
        assert cond.evaluate({"cost_usd": Decimal("200")}) is True
        assert cond.evaluate({"cost_usd": Decimal("50")}) is False

    def test_less_or_equal_operator(self):
        cond = PolicyCondition(
            field="count", operator=ConditionOperator.LESS_OR_EQUAL, value=10
        )
        assert cond.evaluate({"count": 10}) is True
        assert cond.evaluate({"count": 11}) is False

    def test_in_operator(self):
        cond = PolicyCondition(
            field="intent_type",
            operator=ConditionOperator.IN,
            value=["DEPLOY", "TRANSFORM"],
        )
        assert cond.evaluate({"intent_type": "DEPLOY"}) is True
        assert cond.evaluate({"intent_type": "REFACTOR"}) is False

    def test_not_in_operator(self):
        cond = PolicyCondition(
            field="env",
            operator=ConditionOperator.NOT_IN,
            value=["staging", "production"],
        )
        assert cond.evaluate({"env": "dev"}) is True
        assert cond.evaluate({"env": "production"}) is False

    def test_contains_operator(self):
        cond = PolicyCondition(
            field="tags", operator=ConditionOperator.CONTAINS, value="security"
        )
        assert cond.evaluate({"tags": "security-audit"}) is True
        assert cond.evaluate({"tags": "build-test"}) is False

    def test_matches_regex_operator(self):
        cond = PolicyCondition(
            field="name", operator=ConditionOperator.MATCHES, value=r"^deploy-\d+"
        )
        assert cond.evaluate({"name": "deploy-123"}) is True
        assert cond.evaluate({"name": "build-123"}) is False

    def test_missing_field_returns_false(self):
        cond = PolicyCondition(
            field="nonexistent", operator=ConditionOperator.EQUALS, value="x"
        )
        assert cond.evaluate({"other": "y"}) is False

    def test_condition_to_dict(self):
        cond = PolicyCondition(
            field="cost",
            operator=ConditionOperator.GREATER_THAN,
            value=Decimal("50"),
            description="Cost cap",
        )
        d = cond.to_dict()
        assert d["field"] == "cost"
        assert d["operator"] == ">"
        assert d["description"] == "Cost cap"


class TestPolicyRule:
    """Tests for PolicyRule evaluation with AND logic."""

    def test_single_condition_triggers(self):
        rule = PolicyRule(
            name="cost_rule",
            conditions=[
                PolicyCondition(
                    field="cost", operator=ConditionOperator.GREATER_THAN, value=100
                )
            ],
            action=PolicyAction.REJECT,
        )
        assert rule.evaluate({"cost": 200}) is True

    def test_disabled_rule_never_triggers(self):
        rule = PolicyRule(
            name="disabled",
            conditions=[
                PolicyCondition(field="x", operator=ConditionOperator.EQUALS, value=1)
            ],
            enabled=False,
        )
        assert rule.evaluate({"x": 1}) is False

    def test_and_logic_all_must_pass(self):
        rule = PolicyRule(
            name="multi",
            conditions=[
                PolicyCondition(field="a", operator=ConditionOperator.EQUALS, value=1),
                PolicyCondition(field="b", operator=ConditionOperator.EQUALS, value=2),
            ],
        )
        assert rule.evaluate({"a": 1, "b": 2}) is True
        assert rule.evaluate({"a": 1, "b": 3}) is False

    def test_rule_to_dict_roundtrip(self):
        rule = PolicyRule(
            name="test",
            description="desc",
            action=PolicyAction.ESCALATE,
            priority=PolicyPriority.HIGH,
        )
        d = rule.to_dict()
        restored = PolicyRule.from_dict(d)
        assert restored.name == "test"
        assert restored.action == PolicyAction.ESCALATE


class TestPolicyEvaluator:
    """Tests for PolicyEvaluator.evaluate_intent()."""

    def _make_intent(
        self,
        intent_type=IntentType.REFACTOR,
        user_tier="PRO",
        risk=RiskProfile.LOW,
        cost=None,
    ):
        budget = BudgetSpec(max_cost_usd=cost) if cost else BudgetSpec()
        return IntentObject(
            goal="test goal",
            intent_type=intent_type,
            scope=ScopeObject(scope_type=ScopeType.MODULE, target="auth/"),
            context=ContextBundle(user_id="u1", user_tier=user_tier),
            risk_profile=risk,
            budget=budget,
        )

    def test_no_rules_approves(self):
        ev = PolicyEvaluator()
        result = ev.evaluate_intent(self._make_intent())
        assert result.decision == PolicyAction.APPROVE
        assert len(result.triggered_rules) == 0

    def test_reject_rule_blocks(self):
        ev = PolicyEvaluator()
        ev.add_rule(
            PolicyRule(
                name="block_deploy",
                conditions=[
                    PolicyCondition(
                        field="intent_type",
                        operator=ConditionOperator.EQUALS,
                        value=IntentType.DEPLOY,
                    )
                ],
                action=PolicyAction.REJECT,
                priority=PolicyPriority.CRITICAL,
            )
        )
        result = ev.evaluate_intent(self._make_intent(intent_type=IntentType.DEPLOY))
        assert result.decision == PolicyAction.REJECT
        assert len(result.violations) == 1

    def test_escalate_rule_wins(self):
        ev = PolicyEvaluator()
        ev.add_rule(
            PolicyRule(
                name="escalate_systemic",
                conditions=[
                    PolicyCondition(
                        field="risk_profile",
                        operator=ConditionOperator.EQUALS,
                        value=RiskProfile.SYSTEMIC,
                    )
                ],
                action=PolicyAction.ESCALATE,
                priority=PolicyPriority.HIGH,
                action_metadata={"escalate_to": "security_team"},
            )
        )
        result = ev.evaluate_intent(self._make_intent(risk=RiskProfile.SYSTEMIC))
        assert result.decision == PolicyAction.ESCALATE
        assert result.escalated is True

    def test_require_approval_accumulates(self):
        ev = PolicyEvaluator()
        ev.add_rule(
            PolicyRule(
                name="approval_needed",
                conditions=[
                    PolicyCondition(
                        field="user_tier",
                        operator=ConditionOperator.EQUALS,
                        value="FREE",
                    )
                ],
                action=PolicyAction.REQUIRE_APPROVAL,
                priority=PolicyPriority.MEDIUM,
            )
        )
        result = ev.evaluate_intent(self._make_intent(user_tier="FREE"))
        assert result.requires_approval is True
        assert result.is_approved() is False

    def test_notify_adds_warning(self):
        ev = PolicyEvaluator()
        ev.add_rule(
            PolicyRule(
                name="warn_refactor",
                description="Refactor warning",
                conditions=[
                    PolicyCondition(
                        field="intent_type",
                        operator=ConditionOperator.EQUALS,
                        value=IntentType.REFACTOR,
                    )
                ],
                action=PolicyAction.NOTIFY,
                priority=PolicyPriority.LOW,
            )
        )
        result = ev.evaluate_intent(self._make_intent())
        assert len(result.warnings) == 1

    def test_priority_ordering_reject_first(self):
        ev = PolicyEvaluator()
        ev.add_rule(
            PolicyRule(
                name="low_notify",
                conditions=[
                    PolicyCondition(
                        field="user_tier",
                        operator=ConditionOperator.EQUALS,
                        value="PRO",
                    )
                ],
                action=PolicyAction.NOTIFY,
                priority=PolicyPriority.LOW,
            )
        )
        ev.add_rule(
            PolicyRule(
                name="critical_reject",
                conditions=[
                    PolicyCondition(
                        field="user_tier",
                        operator=ConditionOperator.EQUALS,
                        value="PRO",
                    )
                ],
                action=PolicyAction.REJECT,
                priority=PolicyPriority.CRITICAL,
            )
        )
        result = ev.evaluate_intent(self._make_intent())
        assert result.decision == PolicyAction.REJECT

    def test_build_context_includes_graph_metrics(self):
        ev = PolicyEvaluator()
        intent = self._make_intent()
        graph = ExecutionGraph(intent_id="g1")
        ctx = ev._build_context(intent, graph)
        assert "node_count" in ctx
        assert "estimated_cost_usd" in ctx

    def test_evaluation_result_to_dict(self):
        result = PolicyEvaluationResult(intent_id="i1", decision=PolicyAction.REJECT)
        d = result.to_dict()
        assert d["decision"] == "reject"
        assert d["intent_id"] == "i1"
        assert "governance_score" in d

    def test_remove_rule(self):
        ev = PolicyEvaluator()
        rule = PolicyRule(name="temp")
        ev.add_rule(rule)
        assert len(ev.rules) == 1
        ev.remove_rule(rule.rule_id)
        assert len(ev.rules) == 0

    def test_clear_rules(self):
        ev = PolicyEvaluator()
        ev.add_rule(PolicyRule(name="a"))
        ev.add_rule(PolicyRule(name="b"))
        ev.clear_rules()
        assert len(ev.rules) == 0

    def test_get_enabled_rules(self):
        ev = PolicyEvaluator()
        ev.add_rule(PolicyRule(name="on", enabled=True))
        ev.add_rule(PolicyRule(name="off", enabled=False))
        assert len(ev.get_enabled_rules()) == 1

    def test_evaluation_result_approved_when_no_violations(self):
        result = PolicyEvaluationResult(intent_id="x")
        assert result.is_approved() is True

    def test_graph_scope_rule_skipped_without_graph(self):
        ev = PolicyEvaluator()
        ev.add_rule(
            PolicyRule(
                name="graph_only",
                scope=PolicyScope.GRAPH,
                conditions=[
                    PolicyCondition(
                        field="node_count",
                        operator=ConditionOperator.GREATER_THAN,
                        value=5,
                    )
                ],
                action=PolicyAction.REJECT,
            )
        )
        result = ev.evaluate_intent(self._make_intent(), graph=None)
        assert result.decision == PolicyAction.APPROVE

    def test_evaluation_has_time_ms(self):
        ev = PolicyEvaluator()
        result = ev.evaluate_intent(self._make_intent())
        assert result.evaluation_time_ms >= 0

    def test_reject_rule_sets_zero_governance_score(self):
        ev = PolicyEvaluator()
        ev.add_rule(
            PolicyRule(
                name="block_deploy",
                conditions=[
                    PolicyCondition(
                        field="intent_type",
                        operator=ConditionOperator.EQUALS,
                        value=IntentType.DEPLOY,
                    )
                ],
                action=PolicyAction.REJECT,
                priority=PolicyPriority.CRITICAL,
            )
        )
        result = ev.evaluate_intent(self._make_intent(intent_type=IntentType.DEPLOY))
        assert result.governance_score == 0.0
        assert result.governance_label == "BLOCKED"

    def test_require_approval_caps_governance_score(self):
        ev = PolicyEvaluator()
        ev.add_rule(
            PolicyRule(
                name="approval_needed",
                conditions=[
                    PolicyCondition(
                        field="user_tier",
                        operator=ConditionOperator.EQUALS,
                        value="FREE",
                    )
                ],
                action=PolicyAction.REQUIRE_APPROVAL,
                priority=PolicyPriority.MEDIUM,
            )
        )
        result = ev.evaluate_intent(self._make_intent(user_tier="FREE"))
        assert result.governance_score <= 0.5
        assert result.governance_label == "REVIEW REQUIRED"


# ---------------------------------------------------------------------------
# intent_compiler — IntentCompiler, quick_compile
# ---------------------------------------------------------------------------


class TestIntentCompiler:
    """Tests for IntentCompiler full pipeline."""

    def setup_method(self):
        self.compiler = IntentCompiler()

    def test_compile_refactor_intent(self):
        result = self.compiler.compile(
            "Refactor the auth module to use clean architecture",
            user_id="u1",
            user_tier="PRO",
        )
        assert result.success is True
        assert result.intent.intent_type == IntentType.REFACTOR

    def test_compile_deploy_intent(self):
        result = self.compiler.compile(
            "Deploy the application to production", user_id="u1", user_tier="PRO"
        )
        assert result.success is True
        assert result.intent.intent_type == IntentType.DEPLOY

    def test_compile_build_app_intent(self):
        result = self.compiler.compile(
            "Build a REST API for inventory management", user_id="u1", user_tier="PRO"
        )
        assert result.success is True
        assert result.intent.intent_type == IntentType.BUILD_APP

    def test_compile_extracts_cost_constraint(self):
        result = self.compiler.compile(
            "Refactor the module with max cost $2.50", user_id="u1", user_tier="PRO"
        )
        assert result.success is True
        assert result.intent.budget.max_cost_usd == Decimal("2.50")

    def test_compile_extracts_time_constraint(self):
        result = self.compiler.compile(
            "Optimize search within 2 hours", user_id="u1", user_tier="PRO"
        )
        assert result.success is True
        assert result.intent.budget.max_time is not None
        assert result.intent.budget.max_time.total_seconds() == 7200

    def test_compile_critical_priority(self):
        result = self.compiler.compile(
            "Urgently deploy the fix immediately", user_id="u1", user_tier="PRO"
        )
        assert result.success is True
        assert result.intent.priority == IntentPriority.CRITICAL

    def test_compile_high_risk_deploy(self):
        result = self.compiler.compile(
            "Deploy the system-wide migration", user_id="u1", user_tier="PRO"
        )
        assert result.success is True
        assert result.intent.risk_profile == RiskProfile.SYSTEMIC

    def test_compile_increments_counter(self):
        initial = self.compiler.compiled_count
        self.compiler.compile("Refactor code", user_id="u1", user_tier="PRO")
        assert self.compiler.compiled_count == initial + 1

    def test_compile_sets_compilation_time(self):
        result = self.compiler.compile("Test something", user_id="u1", user_tier="PRO")
        assert result.compilation_time_ms >= 0

    def test_lex_extracts_keywords(self):
        lexical = self.compiler.lex("Refactor and optimize the module")
        assert "refactor" in lexical.keywords
        assert (
            "optimize" in lexical.keywords or "improve performance" in lexical.keywords
        )

    def test_lex_extracts_cost_value(self):
        lexical = self.compiler.lex("keep cost under $5.00")
        assert "max_cost" in lexical.constraints
        assert lexical.constraints["max_cost"] == Decimal("5.00")

    def test_lex_extracts_time_value(self):
        lexical = self.compiler.lex("finish within 30 minutes")
        assert "max_time" in lexical.constraints

    def test_suggest_template_refactor(self):
        intent = IntentObject(
            goal="refactor",
            intent_type=IntentType.REFACTOR,
            scope=ScopeObject(scope_type=ScopeType.MODULE, target="."),
            context=ContextBundle(user_id="u", user_tier="PRO"),
        )
        assert self.compiler.suggest_template(intent) == "refactor_template"

    def test_suggest_template_unknown_returns_generic(self):
        intent = IntentObject(
            goal="test",
            intent_type=IntentType.TEST,
            scope=ScopeObject(scope_type=ScopeType.MODULE, target="."),
            context=ContextBundle(user_id="u", user_tier="PRO"),
        )
        assert self.compiler.suggest_template(intent) == "generic_template"

    def test_quick_compile_convenience(self):
        result = quick_compile("Refactor the code")
        assert result.success is True
        assert result.intent.intent_type == IntentType.REFACTOR
