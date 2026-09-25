"""
Round 44 item C (group 2): real coverage for algo_31_albas.py, previously
untested (0% coverage) despite being real, kernel-wired code
(algorithm_kernel_41.py imports ScalingEngine/LoadPredictor/ScalingPolicy/
ScalingMetrics/PolicyType directly and wires algo_31_albas/
algo_31_albas_evaluate to them). Real policy-evaluation math (target-
tracking proportional control, step-scaling threshold ladders, simple-
scaling binary thresholds, predictive scaling) and real time-series math
(exponential smoothing with trend, linear-regression trend detection,
z-score anomaly detection, pattern matching) - no mocking. The file's own
__main__ smoke test (already-proven-correct assertions) is ported below
as a real pytest function, then expanded with per-branch edge cases.
"""
import pytest

from rct_control_plane.algo_31_albas import (
    ActionType, LoadPredictor, PolicyType, PredictionResult,
    ScalingAction, ScalingEngine, ScalingMetrics, ScalingPolicy,
)


def _policy(**overrides):
    defaults = dict(
        id="p1", name="Policy", policy_type=PolicyType.TARGET_TRACKING,
        metric="cpu", target_value=50.0, scale_up_threshold=80.0,
        scale_down_threshold=20.0, cooldown_seconds=0, min_instances=2,
        max_instances=10, scale_up_increment=3,
    )
    defaults.update(overrides)
    return ScalingPolicy(**defaults)


def _metrics(**overrides):
    defaults = dict(cpu_usage=50.0, memory_usage=50.0)
    defaults.update(overrides)
    return ScalingMetrics(**defaults)


@pytest.fixture
def engine():
    return ScalingEngine()


class TestSmokeTestPorted:
    """The file's own __main__ smoke test, ported to real pytest
    assertions - already-proven-correct, real math."""

    @pytest.mark.asyncio
    async def test_target_tracking_scales_up_under_high_cpu_and_executes(self, engine):
        policy = _policy(policy_type=PolicyType.TARGET_TRACKING)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)

        action = await engine.evaluate_scaling(_metrics(cpu_usage=95.0, memory_usage=60.0))
        assert action is not None
        assert action.type == ActionType.SCALE_UP
        assert action.target_instances > action.current_instances

        executed = await engine.execute_scaling_action(action)
        assert executed is True
        assert engine.current_instances == action.target_instances
        assert engine.is_in_cooldown() is False  # cooldown_seconds=0

        stats = engine.get_statistics()
        assert stats["total_actions"] == 1
        assert stats["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_step_scaling_emergency_threshold(self, engine):
        policy = _policy(policy_type=PolicyType.STEP_SCALING, scale_up_threshold=70.0, max_instances=50)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)

        action = await engine.evaluate_scaling(_metrics(cpu_usage=96.0))
        assert "Emergency" in action.reason
        assert action.instances_change == 5

    @pytest.mark.asyncio
    async def test_load_predictor_real_upward_trend_end_to_end(self):
        import random
        predictor = LoadPredictor(history_window_minutes=5, prediction_window_minutes=10)
        random.seed(42)
        base_cpu = 40.0
        for i in range(40):
            cpu = base_cpu + i * 1.2 + random.uniform(-2, 2)
            mem = 55.0 + i * 0.5 + random.uniform(-1, 1)
            rps = 100.0 + i * 3.0
            predictor.add_metrics(_metrics(cpu_usage=min(cpu, 100.0), memory_usage=min(mem, 100.0), requests_per_second=rps))

        pred_value, confidence = predictor.predict_load("cpu_usage", "exponential")
        assert pred_value > base_cpu
        assert 0.0 <= confidence <= 1.0
        assert predictor.detect_trend("cpu_usage") == "increasing"
        assert predictor.detect_anomaly(999.0, "cpu_usage") is True
        assert predictor.detect_anomaly(float(pred_value), "cpu_usage") is False

        result = predictor.predict_scaling_need(current_instances=3, target_cpu=50.0, target_memory=70.0)
        assert result.recommended_instances >= 3


class TestScalingEnginePolicyManagement:
    def test_get_active_policy_none_when_unset(self, engine):
        assert engine.get_active_policy() is None

    def test_set_active_policy_ignores_unknown_id(self, engine):
        engine.set_active_policy("ghost")
        assert engine.active_policy_id is None

    def test_get_active_policy_returns_registered_policy(self, engine):
        policy = _policy()
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        assert engine.get_active_policy() is policy

    @pytest.mark.asyncio
    async def test_evaluate_scaling_with_no_active_policy_returns_none(self, engine):
        assert await engine.evaluate_scaling(_metrics()) is None

    @pytest.mark.asyncio
    async def test_evaluate_scaling_with_disabled_policy_returns_none(self, engine):
        policy = _policy(enabled=False)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        assert await engine.evaluate_scaling(_metrics(cpu_usage=99.0)) is None

    @pytest.mark.asyncio
    async def test_evaluate_scaling_while_in_cooldown_returns_none(self, engine):
        policy = _policy()
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.set_cooldown(60)
        assert engine.is_in_cooldown() is True
        assert await engine.evaluate_scaling(_metrics(cpu_usage=99.0)) is None

    def test_cooldown_expires_naturally(self, engine):
        engine.set_cooldown(-1)  # already in the past
        assert engine.is_in_cooldown() is False


class TestTargetTracking:
    @pytest.mark.asyncio
    async def test_scales_down_below_threshold(self, engine):
        policy = _policy(target_value=50.0, scale_down_threshold=40.0, min_instances=1)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 5
        action = await engine.evaluate_scaling(_metrics(cpu_usage=10.0))
        assert action.type == ActionType.SCALE_DOWN
        assert action.target_instances < 5

    @pytest.mark.asyncio
    async def test_steady_state_returns_none(self, engine):
        policy = _policy(target_value=50.0, min_instances=2, max_instances=2)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 2
        # desired == current at metric == target with min==max==current
        action = await engine.evaluate_scaling(_metrics(cpu_usage=50.0))
        assert action is None

    @pytest.mark.asyncio
    async def test_target_value_zero_keeps_current_instances(self, engine):
        policy = _policy(target_value=0.0)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        action = await engine.evaluate_scaling(_metrics(cpu_usage=90.0))
        assert action is None  # desired_instances == current_instances

    @pytest.mark.asyncio
    async def test_unknown_metric_name_returns_none(self, engine):
        policy = _policy(metric="totally_unknown_metric")
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        assert await engine.evaluate_scaling(_metrics()) is None


class TestStepScaling:
    @pytest.mark.asyncio
    async def test_high_load_85_to_90(self, engine):
        policy = _policy(policy_type=PolicyType.STEP_SCALING, scale_up_threshold=70.0, max_instances=50)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        action = await engine.evaluate_scaling(_metrics(cpu_usage=87.0))
        assert "High load" in action.reason
        assert action.instances_change == 3

    @pytest.mark.asyncio
    async def test_threshold_exceeded(self, engine):
        policy = _policy(policy_type=PolicyType.STEP_SCALING, scale_up_threshold=70.0, scale_up_increment=2, max_instances=50)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        action = await engine.evaluate_scaling(_metrics(cpu_usage=75.0))
        assert "Threshold exceeded" in action.reason
        assert action.instances_change == 2

    @pytest.mark.asyncio
    async def test_low_utilization_scales_down(self, engine):
        policy = _policy(policy_type=PolicyType.STEP_SCALING, min_instances=1)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 5
        action = await engine.evaluate_scaling(_metrics(cpu_usage=10.0))
        assert action.type == ActionType.SCALE_DOWN
        assert "Low utilization" in action.reason

    @pytest.mark.asyncio
    async def test_low_utilization_at_min_instances_returns_none(self, engine):
        policy = _policy(policy_type=PolicyType.STEP_SCALING, min_instances=2)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 2  # already at min
        action = await engine.evaluate_scaling(_metrics(cpu_usage=10.0))
        assert action is None

    @pytest.mark.asyncio
    async def test_steady_state_returns_none(self, engine):
        policy = _policy(policy_type=PolicyType.STEP_SCALING, scale_up_threshold=80.0)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        action = await engine.evaluate_scaling(_metrics(cpu_usage=50.0))  # between 30 and 80
        assert action is None

    @pytest.mark.asyncio
    async def test_unknown_metric_name_returns_none(self, engine):
        policy = _policy(policy_type=PolicyType.STEP_SCALING, metric="totally_unknown_metric")
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        assert await engine.evaluate_scaling(_metrics()) is None

    @pytest.mark.asyncio
    async def test_max_instances_cap_prevents_actual_scale_up(self, engine):
        policy = _policy(policy_type=PolicyType.STEP_SCALING, scale_up_threshold=70.0, max_instances=5)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 5  # already at cap
        action = await engine.evaluate_scaling(_metrics(cpu_usage=96.0))
        assert action is None  # actual_add == 0


class TestSimpleScaling:
    @pytest.mark.asyncio
    async def test_scales_up_over_threshold(self, engine):
        policy = _policy(policy_type=PolicyType.SIMPLE_SCALING, scale_up_threshold=80.0, scale_up_increment=1, max_instances=50)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        action = await engine.evaluate_scaling(_metrics(cpu_usage=90.0))
        assert action.type == ActionType.SCALE_UP
        assert "Simple scaling" in action.reason

    @pytest.mark.asyncio
    async def test_scales_down_under_threshold(self, engine):
        policy = _policy(policy_type=PolicyType.SIMPLE_SCALING, scale_down_threshold=20.0, min_instances=1)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 5
        action = await engine.evaluate_scaling(_metrics(cpu_usage=5.0))
        assert action.type == ActionType.SCALE_DOWN

    @pytest.mark.asyncio
    async def test_between_thresholds_returns_none(self, engine):
        policy = _policy(policy_type=PolicyType.SIMPLE_SCALING, scale_up_threshold=80.0, scale_down_threshold=20.0)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        action = await engine.evaluate_scaling(_metrics(cpu_usage=50.0))
        assert action is None

    @pytest.mark.asyncio
    async def test_unknown_metric_name_returns_none(self, engine):
        policy = _policy(policy_type=PolicyType.SIMPLE_SCALING, metric="totally_unknown_metric")
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        assert await engine.evaluate_scaling(_metrics()) is None


class TestPredictiveScaling:
    @pytest.mark.asyncio
    async def test_no_prediction_falls_back_to_target_tracking(self, engine):
        policy = _policy(policy_type=PolicyType.PREDICTIVE)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        action = await engine.evaluate_scaling(_metrics(cpu_usage=95.0), prediction=None)
        assert action is not None
        assert action.type == ActionType.SCALE_UP

    @pytest.mark.asyncio
    async def test_recommended_above_current_scales_up(self, engine):
        policy = _policy(policy_type=PolicyType.PREDICTIVE, scale_up_increment=2, max_instances=50)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 3
        prediction = PredictionResult(
            window_minutes=10, predicted_cpu=90.0, predicted_memory=50.0, predicted_rps=100.0,
            predicted_connections=200, confidence=0.8, recommended_instances=8, recommendation_reason="test",
        )
        action = await engine.evaluate_scaling(_metrics(cpu_usage=90.0), prediction=prediction)
        assert action.type == ActionType.SCALE_UP
        assert "Predictive" in action.reason

    @pytest.mark.asyncio
    async def test_recommended_below_current_scales_down(self, engine):
        policy = _policy(policy_type=PolicyType.PREDICTIVE, min_instances=1)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 8
        prediction = PredictionResult(
            window_minutes=10, predicted_cpu=10.0, predicted_memory=10.0, predicted_rps=5.0,
            predicted_connections=10, confidence=0.9, recommended_instances=2, recommendation_reason="quiet",
        )
        action = await engine.evaluate_scaling(_metrics(cpu_usage=10.0), prediction=prediction)
        assert action.type == ActionType.SCALE_DOWN

    @pytest.mark.asyncio
    async def test_recommended_equal_current_returns_none(self, engine):
        policy = _policy(policy_type=PolicyType.PREDICTIVE)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        engine.current_instances = 4
        prediction = PredictionResult(
            window_minutes=10, predicted_cpu=50.0, predicted_memory=50.0, predicted_rps=50.0,
            predicted_connections=100, confidence=0.7, recommended_instances=4, recommendation_reason="steady",
        )
        action = await engine.evaluate_scaling(_metrics(cpu_usage=50.0), prediction=prediction)
        assert action is None


class TestExecuteScalingActionAndHistory:
    @pytest.mark.asyncio
    async def test_history_and_statistics_track_mixed_outcomes(self, engine):
        up = ScalingAction(id="a1", type=ActionType.SCALE_UP, instances_change=2, reason="r",
                            current_instances=2, target_instances=4)
        down = ScalingAction(id="a2", type=ActionType.SCALE_DOWN, instances_change=-1, reason="r",
                              current_instances=4, target_instances=3)
        await engine.execute_scaling_action(up)
        await engine.execute_scaling_action(down)

        stats = engine.get_statistics()
        assert stats["total_actions"] == 2
        assert stats["scale_up_count"] == 1
        assert stats["scale_down_count"] == 1
        assert stats["success_count"] == 2
        assert stats["current_instances"] == 3

    def test_empty_statistics(self, engine):
        stats = engine.get_statistics()
        assert stats == {"total_actions": 0, "scale_up_count": 0, "scale_down_count": 0, "success_rate": 0.0}

    @pytest.mark.asyncio
    async def test_get_scaling_history_respects_limit(self, engine):
        for i in range(5):
            action = ScalingAction(id=f"a{i}", type=ActionType.SCALE_UP, instances_change=1, reason="r",
                                    current_instances=i, target_instances=i + 1)
            await engine.execute_scaling_action(action)
        assert len(engine.get_scaling_history(limit=2)) == 2

    @pytest.mark.asyncio
    async def test_execute_sets_cooldown_from_active_policy(self, engine):
        policy = _policy(cooldown_seconds=3600)
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)
        action = ScalingAction(id="a1", type=ActionType.SCALE_UP, instances_change=1, reason="r",
                                current_instances=2, target_instances=3)
        await engine.execute_scaling_action(action)
        assert engine.is_in_cooldown() is True


class TestLoadPredictorPredictLoad:
    def test_empty_history_returns_zero(self):
        predictor = LoadPredictor()
        assert predictor.predict_load("cpu_usage") == (0.0, 0.0)

    def test_one_or_two_points_returns_current_value_low_confidence(self):
        predictor = LoadPredictor()
        predictor.add_metrics(_metrics(cpu_usage=42.0))
        value, confidence = predictor.predict_load("cpu_usage")
        assert value == 42.0
        assert confidence == 0.3

    def test_moving_average_method(self):
        predictor = LoadPredictor()
        for cpu in [40.0, 50.0, 60.0]:
            predictor.add_metrics(_metrics(cpu_usage=cpu))
        value, confidence = predictor.predict_load("cpu_usage", "moving_average")
        assert value == pytest.approx(50.0)
        assert 0.0 <= confidence <= 1.0

    def test_unknown_method_falls_back_to_exponential(self):
        predictor = LoadPredictor()
        for cpu in [40.0, 50.0, 60.0]:
            predictor.add_metrics(_metrics(cpu_usage=cpu))
        default_result = predictor.predict_load("cpu_usage", "exponential")
        fallback_result = predictor.predict_load("cpu_usage", "unknown_method_xyz")
        assert default_result == fallback_result

    def test_pattern_method_falls_back_when_insufficient_history(self):
        predictor = LoadPredictor()
        for cpu in [40.0, 50.0, 60.0]:
            predictor.add_metrics(_metrics(cpu_usage=cpu))
        exp_result = predictor.predict_load("cpu_usage", "exponential")
        pattern_result = predictor.predict_load("cpu_usage", "pattern")
        assert exp_result == pattern_result

    def test_pattern_method_with_real_recurring_pattern(self):
        predictor = LoadPredictor()
        # A real repeating 12-point cycle, long enough (>24 points) for
        # real pattern matching to find a genuine best match.
        cycle = [30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 50.0, 45.0, 40.0, 35.0, 30.0, 25.0]
        for _ in range(4):
            for cpu in cycle:
                predictor.add_metrics(_metrics(cpu_usage=cpu))
        value, confidence = predictor.predict_load("cpu_usage", "pattern")
        assert value >= 0.0
        assert 0.0 <= confidence <= 1.0


class TestExponentialSmoothingDirect:
    def test_fewer_than_two_points_returns_zero(self):
        predictor = LoadPredictor()
        predictor.add_metrics(_metrics(cpu_usage=10.0))
        assert predictor._predict_exponential_smoothing("cpu_usage") == (0.0, 0.0)


class TestDetectTrend:
    def test_fewer_than_three_points_is_stable(self):
        predictor = LoadPredictor()
        predictor.add_metrics(_metrics(cpu_usage=10.0))
        assert predictor.detect_trend("cpu_usage") == "stable"

    def test_flat_series_is_stable(self):
        predictor = LoadPredictor()
        for _ in range(10):
            predictor.add_metrics(_metrics(cpu_usage=50.0))
        assert predictor.detect_trend("cpu_usage") == "stable"

    def test_real_increasing_series(self):
        predictor = LoadPredictor()
        for i in range(10):
            predictor.add_metrics(_metrics(cpu_usage=10.0 + i * 5.0))
        assert predictor.detect_trend("cpu_usage") == "increasing"

    def test_real_decreasing_series(self):
        predictor = LoadPredictor()
        for i in range(10):
            predictor.add_metrics(_metrics(cpu_usage=100.0 - i * 5.0))
        assert predictor.detect_trend("cpu_usage") == "decreasing"


class TestDetectAnomaly:
    def test_fewer_than_twelve_points_is_never_an_anomaly(self):
        predictor = LoadPredictor()
        for _ in range(5):
            predictor.add_metrics(_metrics(cpu_usage=50.0))
        assert predictor.detect_anomaly(9999.0, "cpu_usage") is False

    def test_zero_std_dev_is_never_an_anomaly(self):
        predictor = LoadPredictor()
        for _ in range(12):
            predictor.add_metrics(_metrics(cpu_usage=50.0))
        assert predictor.detect_anomaly(999.0, "cpu_usage") is False

    def test_real_spike_is_detected(self):
        predictor = LoadPredictor()
        for i in range(20):
            predictor.add_metrics(_metrics(cpu_usage=50.0 + (i % 3)))
        assert predictor.detect_anomaly(9999.0, "cpu_usage") is True

    def test_normal_value_is_not_an_anomaly(self):
        predictor = LoadPredictor()
        for i in range(20):
            predictor.add_metrics(_metrics(cpu_usage=50.0 + (i % 3)))
        assert predictor.detect_anomaly(51.0, "cpu_usage") is False


class TestPredictScalingNeed:
    def test_sufficient_capacity_reason(self):
        predictor = LoadPredictor()
        for _ in range(5):
            predictor.add_metrics(_metrics(cpu_usage=50.0, memory_usage=50.0, requests_per_second=10.0))
        result = predictor.predict_scaling_need(current_instances=100, target_cpu=50.0, target_memory=50.0)
        assert "sufficient" in result.recommendation_reason.lower() or result.recommended_instances == 100

    def test_zero_target_cpu_keeps_required_by_cpu_at_current(self):
        predictor = LoadPredictor()
        for _ in range(5):
            predictor.add_metrics(_metrics(cpu_usage=90.0, memory_usage=10.0))
        result = predictor.predict_scaling_need(current_instances=3, target_cpu=0.0, target_memory=100.0)
        assert result.recommended_instances >= 3

    def test_zero_target_memory_keeps_required_by_memory_at_current(self):
        predictor = LoadPredictor()
        for _ in range(5):
            predictor.add_metrics(_metrics(cpu_usage=10.0, memory_usage=90.0))
        result = predictor.predict_scaling_need(current_instances=3, target_cpu=100.0, target_memory=0.0)
        assert result.recommended_instances >= 3

    def test_low_load_never_recommends_below_current_instances(self):
        # Real finding while writing this test: predict_scaling_need's
        # `recommended = max(required_by_cpu, required_by_memory,
        # current_instances)` includes current_instances as one of the
        # max() operands, so recommended can structurally never fall
        # below it - the "decrease" reason branch a few lines below is
        # genuinely unreachable through any real input, not just
        # difficult to trigger. Documented here rather than silently
        # "fixed" (not asked to change scaling behavior) - this
        # predictor only ever recommends holding steady or scaling up.
        predictor = LoadPredictor()
        for _ in range(5):
            predictor.add_metrics(_metrics(cpu_usage=1.0, memory_usage=1.0, requests_per_second=1.0))
        result = predictor.predict_scaling_need(current_instances=10, target_cpu=50.0, target_memory=50.0)
        assert result.recommended_instances == 10
        assert "sufficient" in result.recommendation_reason.lower()


class TestLearnPatternAndStatistics:
    def test_learn_pattern_stores_cpu_sequence(self):
        predictor = LoadPredictor()
        sequence = [_metrics(cpu_usage=float(i)) for i in range(5)]
        predictor.learn_pattern("burst", sequence)
        assert predictor.patterns["burst"] == [0.0, 1.0, 2.0, 3.0, 4.0]

    def test_get_statistics_empty(self):
        predictor = LoadPredictor()
        assert predictor.get_statistics() == {}

    def test_get_statistics_with_real_data(self):
        predictor = LoadPredictor()
        for i in range(12):
            predictor.add_metrics(_metrics(cpu_usage=40.0 + i, memory_usage=30.0 + i))
        predictor.learn_pattern("p1", [_metrics(cpu_usage=1.0)])
        stats = predictor.get_statistics()
        assert stats["data_points"] == 12
        assert stats["learned_patterns"] == 1
        assert "trend_cpu" in stats and "trend_memory" in stats
