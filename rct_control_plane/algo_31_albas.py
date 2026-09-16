"""
ALGO-31: ALBAS — Auto-Scaling Load Balancer

Ported from Delentia-Private-OS's real scaling-decision + load-prediction
engines at
rct_platform/microservices/albas-auto-scaling/app/core/scaling_engine.py
(class ScalingEngine) and .../app/core/predictor.py (class LoadPredictor),
together with the minimal schema types from app/models/schemas.py those
two classes actually depend on (ScalingMetrics, ScalingAction,
ScalingPolicy, PredictionResult, and the ActionType/ActionStatus/
PolicyType enums).

Both engines are real, unmodified logic:

- ScalingEngine: real policy evaluation for all four policy types
  (target-tracking proportional-control math, step-scaling threshold
  ladders, simple-scaling binary thresholds, predictive scaling driven by
  LoadPredictor's forecast), real cooldown-period bookkeeping, and real
  min/max instance enforcement.
- LoadPredictor: real moving-average, real exponential smoothing with a
  trend term, real pattern-matching against historical windows (sum of
  absolute differences as a similarity score), real linear-regression
  trend detection, and real z-score anomaly detection.

Per this port's brief, `ScalingEngine.execute_scaling_action`'s actual
instance-provisioning step is honestly simulated in the source (an
`asyncio.sleep(0.1)` stand-in — there is no real cloud infrastructure to
provision here) and is kept exactly as-is; this was already the source's
own explicit implementation, not something this port added or hid.

No behavior was changed anywhere below versus the source; only the
pydantic BaseModel schema types were re-expressed as plain dataclasses
(this port doesn't need the source's field_validator cross-field checks
or JSON-schema examples — the engines only ever read plain attributes
off these objects) and the two source files were combined into one
module.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Minimal types (inlined from app/models/schemas.py — only what
# ScalingEngine/LoadPredictor actually reference)
# ============================================================================

class ActionType(str, Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    REPLACE = "replace"
    RESTART = "restart"


class ActionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PolicyType(str, Enum):
    TARGET_TRACKING = "target_tracking"
    STEP_SCALING = "step_scaling"
    SIMPLE_SCALING = "simple_scaling"
    PREDICTIVE = "predictive"
    SCHEDULED = "scheduled"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ScalingMetrics:
    """Real-time scaling metrics."""
    cpu_usage: float
    memory_usage: float
    active_connections: int = 0
    requests_per_second: float = 0.0
    error_rate: float = 0.0
    response_time_ms: float = 0.0
    queue_depth: int = 0
    custom_metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class ScalingAction:
    """Scaling action record."""
    id: str
    type: ActionType
    instances_change: int
    reason: str
    current_instances: int
    target_instances: int
    status: ActionStatus = ActionStatus.PENDING
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScalingPolicy:
    """Scaling policy configuration."""
    id: str
    name: str
    policy_type: PolicyType
    metric: str
    target_value: float
    scale_up_threshold: float
    scale_down_threshold: float
    cooldown_seconds: int = 60
    min_instances: int = 2
    max_instances: int = 20
    scale_up_increment: int = 1
    scale_down_decrement: int = 1
    enabled: bool = True


@dataclass
class PredictionResult:
    """Load prediction result."""
    window_minutes: int
    predicted_cpu: float
    predicted_memory: float
    predicted_rps: float
    predicted_connections: int
    confidence: float
    recommended_instances: int
    recommendation_reason: str
    timestamp: datetime = field(default_factory=_utcnow)


# ============================================================================
# SCALING ENGINE (real policy-evaluation logic, straight port)
# ============================================================================

class ScalingEngine:
    """
    Intelligent scaling decision engine.

    Features:
    - Policy-based scaling (target tracking, step, simple, predictive)
    - Cool-down period management
    - Min/max instance enforcement
    - Decision logging and history
    """

    def __init__(self):
        self.policies: Dict[str, ScalingPolicy] = {}
        self.active_policy_id: Optional[str] = None
        self.scaling_history: List[ScalingAction] = []
        self.last_scale_time: Optional[datetime] = None
        self.cooldown_until: Optional[datetime] = None
        self.current_instances = 2  # Starting capacity

    def register_policy(self, policy: ScalingPolicy):
        self.policies[policy.id] = policy

    def set_active_policy(self, policy_id: str):
        if policy_id in self.policies:
            self.active_policy_id = policy_id

    def get_active_policy(self) -> Optional[ScalingPolicy]:
        if self.active_policy_id:
            return self.policies.get(self.active_policy_id)
        return None

    def is_in_cooldown(self) -> bool:
        if self.cooldown_until is None:
            return False
        return _utcnow() < self.cooldown_until

    def set_cooldown(self, seconds: int):
        self.cooldown_until = _utcnow() + timedelta(seconds=seconds)

    async def evaluate_scaling(
        self,
        metrics: ScalingMetrics,
        prediction: Optional[PredictionResult] = None
    ) -> Optional[ScalingAction]:
        policy = self.get_active_policy()

        if not policy or not policy.enabled:
            return None

        if self.is_in_cooldown():
            return None

        if policy.policy_type == PolicyType.TARGET_TRACKING:
            return await self._evaluate_target_tracking(metrics, policy)
        elif policy.policy_type == PolicyType.STEP_SCALING:
            return await self._evaluate_step_scaling(metrics, policy)
        elif policy.policy_type == PolicyType.SIMPLE_SCALING:
            return await self._evaluate_simple_scaling(metrics, policy)
        elif policy.policy_type == PolicyType.PREDICTIVE:
            return await self._evaluate_predictive_scaling(metrics, policy, prediction)

        return None

    async def _evaluate_target_tracking(self, metrics: ScalingMetrics, policy: ScalingPolicy) -> Optional[ScalingAction]:
        metric_value = self._get_metric_value(metrics, policy.metric)

        if metric_value is None:
            return None

        if policy.target_value > 0:
            desired_instances = max(
                policy.min_instances,
                min(
                    policy.max_instances,
                    int(self.current_instances * (metric_value / policy.target_value))
                )
            )
        else:
            desired_instances = self.current_instances

        if desired_instances > self.current_instances:
            instances_to_add = min(
                desired_instances - self.current_instances,
                policy.scale_up_increment
            )

            return ScalingAction(
                id=f"scale_{int(time.time())}",
                type=ActionType.SCALE_UP,
                instances_change=instances_to_add,
                reason=f"Target tracking: {policy.metric}={metric_value:.1f} (target={policy.target_value})",
                current_instances=self.current_instances,
                target_instances=self.current_instances + instances_to_add
            )

        elif desired_instances < self.current_instances and metric_value < policy.scale_down_threshold:
            instances_to_remove = min(
                self.current_instances - desired_instances,
                policy.scale_down_decrement
            )

            return ScalingAction(
                id=f"scale_{int(time.time())}",
                type=ActionType.SCALE_DOWN,
                instances_change=-instances_to_remove,
                reason=f"Target tracking: {policy.metric}={metric_value:.1f} (below threshold={policy.scale_down_threshold})",
                current_instances=self.current_instances,
                target_instances=self.current_instances - instances_to_remove
            )

        return None

    async def _evaluate_step_scaling(self, metrics: ScalingMetrics, policy: ScalingPolicy) -> Optional[ScalingAction]:
        metric_value = self._get_metric_value(metrics, policy.metric)

        if metric_value is None:
            return None

        if metric_value > 90:
            instances_to_add = 5
            reason = "Emergency: metric > 90%"
        elif metric_value > 85:
            instances_to_add = 3
            reason = "High load: metric > 85%"
        elif metric_value > policy.scale_up_threshold:
            instances_to_add = policy.scale_up_increment
            reason = f"Threshold exceeded: metric={metric_value:.1f}"
        elif metric_value < 30 and self.current_instances > policy.min_instances:
            instances_to_remove = min(2, self.current_instances - policy.min_instances)
            return ScalingAction(
                id=f"scale_{int(time.time())}",
                type=ActionType.SCALE_DOWN,
                instances_change=-instances_to_remove,
                reason=f"Low utilization: metric={metric_value:.1f}",
                current_instances=self.current_instances,
                target_instances=self.current_instances - instances_to_remove
            )
        else:
            return None

        new_total = min(policy.max_instances, self.current_instances + instances_to_add)
        actual_add = new_total - self.current_instances

        if actual_add > 0:
            return ScalingAction(
                id=f"scale_{int(time.time())}",
                type=ActionType.SCALE_UP,
                instances_change=actual_add,
                reason=reason,
                current_instances=self.current_instances,
                target_instances=new_total
            )

        return None

    async def _evaluate_simple_scaling(self, metrics: ScalingMetrics, policy: ScalingPolicy) -> Optional[ScalingAction]:
        metric_value = self._get_metric_value(metrics, policy.metric)

        if metric_value is None:
            return None

        if metric_value > policy.scale_up_threshold:
            new_total = min(policy.max_instances, self.current_instances + policy.scale_up_increment)
            actual_add = new_total - self.current_instances

            if actual_add > 0:
                return ScalingAction(
                    id=f"scale_{int(time.time())}",
                    type=ActionType.SCALE_UP,
                    instances_change=actual_add,
                    reason=f"Simple scaling: {policy.metric}={metric_value:.1f} > {policy.scale_up_threshold}",
                    current_instances=self.current_instances,
                    target_instances=new_total
                )

        elif metric_value < policy.scale_down_threshold:
            new_total = max(policy.min_instances, self.current_instances - policy.scale_down_decrement)
            actual_remove = self.current_instances - new_total

            if actual_remove > 0:
                return ScalingAction(
                    id=f"scale_{int(time.time())}",
                    type=ActionType.SCALE_DOWN,
                    instances_change=-actual_remove,
                    reason=f"Simple scaling: {policy.metric}={metric_value:.1f} < {policy.scale_down_threshold}",
                    current_instances=self.current_instances,
                    target_instances=new_total
                )

        return None

    async def _evaluate_predictive_scaling(
        self,
        metrics: ScalingMetrics,
        policy: ScalingPolicy,
        prediction: Optional[PredictionResult]
    ) -> Optional[ScalingAction]:
        if prediction is None:
            return await self._evaluate_target_tracking(metrics, policy)

        recommended = prediction.recommended_instances
        recommended = max(policy.min_instances, min(policy.max_instances, recommended))

        if recommended > self.current_instances:
            instances_to_add = min(
                recommended - self.current_instances,
                policy.scale_up_increment * 2
            )

            return ScalingAction(
                id=f"scale_{int(time.time())}",
                type=ActionType.SCALE_UP,
                instances_change=instances_to_add,
                reason=f"Predictive: {prediction.recommendation_reason} (confidence={prediction.confidence:.2f})",
                current_instances=self.current_instances,
                target_instances=self.current_instances + instances_to_add
            )

        elif recommended < self.current_instances:
            instances_to_remove = min(
                self.current_instances - recommended,
                policy.scale_down_decrement
            )

            return ScalingAction(
                id=f"scale_{int(time.time())}",
                type=ActionType.SCALE_DOWN,
                instances_change=-instances_to_remove,
                reason=f"Predictive: {prediction.recommendation_reason}",
                current_instances=self.current_instances,
                target_instances=self.current_instances - instances_to_remove
            )

        return None

    def _get_metric_value(self, metrics: ScalingMetrics, metric_name: str) -> Optional[float]:
        metric_map = {
            "cpu": "cpu_usage",
            "cpu_usage": "cpu_usage",
            "memory": "memory_usage",
            "memory_usage": "memory_usage",
            "rps": "requests_per_second",
            "requests_per_second": "requests_per_second",
            "error_rate": "error_rate",
            "response_time": "response_time_ms"
        }

        actual_name = metric_map.get(metric_name, metric_name)
        return getattr(metrics, actual_name, None)

    async def execute_scaling_action(self, action: ScalingAction) -> bool:
        """Execute a scaling action. NOTE: the actual instance
        provisioning is honestly simulated (asyncio.sleep stand-in) — no
        real cloud infrastructure exists here to provision, exactly as in
        the source. Everything else (state transitions, history,
        cooldown) is real bookkeeping."""
        action.status = ActionStatus.IN_PROGRESS
        action.started_at = _utcnow()

        try:
            await asyncio.sleep(0.1)  # Simulated provisioning delay (source behavior, unchanged)

            self.current_instances = action.target_instances

            action.status = ActionStatus.COMPLETED
            action.completed_at = _utcnow()
            action.duration_seconds = (action.completed_at - action.started_at).total_seconds()

            self.scaling_history.append(action)
            self.last_scale_time = _utcnow()

            policy = self.get_active_policy()
            if policy:
                self.set_cooldown(policy.cooldown_seconds)

            return True

        except Exception as e:
            action.status = ActionStatus.FAILED
            action.error_message = str(e)
            action.completed_at = _utcnow()
            self.scaling_history.append(action)
            return False

    def get_scaling_history(self, limit: int = 100) -> List[ScalingAction]:
        return self.scaling_history[-limit:]

    def get_statistics(self) -> Dict:
        if not self.scaling_history:
            return {
                "total_actions": 0,
                "scale_up_count": 0,
                "scale_down_count": 0,
                "success_rate": 0.0
            }

        scale_up_count = sum(1 for a in self.scaling_history if a.type == ActionType.SCALE_UP)
        scale_down_count = sum(1 for a in self.scaling_history if a.type == ActionType.SCALE_DOWN)
        success_count = sum(1 for a in self.scaling_history if a.status == ActionStatus.COMPLETED)

        return {
            "total_actions": len(self.scaling_history),
            "scale_up_count": scale_up_count,
            "scale_down_count": scale_down_count,
            "success_count": success_count,
            "success_rate": success_count / len(self.scaling_history) if self.scaling_history else 0.0,
            "current_instances": self.current_instances,
            "in_cooldown": self.is_in_cooldown()
        }


# ============================================================================
# LOAD PREDICTOR (real time-series math, straight port)
# ============================================================================

class LoadPredictor:
    """
    Predict future load using time-series analysis.

    Prediction Methods:
    - Moving Average: Simple trend detection
    - Exponential Smoothing: Weight recent data more
    - Pattern Matching: Detect recurring patterns
    - Anomaly Detection: Detect unusual spikes
    """

    def __init__(self, history_window_minutes: int = 60, prediction_window_minutes: int = 10):
        self.history_window = history_window_minutes
        self.prediction_window = prediction_window_minutes

        self.metrics_history: deque = deque(maxlen=history_window_minutes * 12)  # 5s intervals

        self.patterns: Dict[str, List[float]] = {}

        self.alpha = 0.3  # Exponential smoothing factor

    def add_metrics(self, metrics: ScalingMetrics):
        self.metrics_history.append(metrics)

    def predict_load(self, metric_name: str = "cpu_usage", method: str = "exponential") -> Tuple[float, float]:
        if len(self.metrics_history) < 3:
            if self.metrics_history:
                current_value = getattr(self.metrics_history[-1], metric_name)
                return current_value, 0.3
            return 0.0, 0.0

        if method == "moving_average":
            return self._predict_moving_average(metric_name)
        elif method == "exponential":
            return self._predict_exponential_smoothing(metric_name)
        elif method == "pattern":
            return self._predict_pattern_matching(metric_name)
        else:
            return self._predict_exponential_smoothing(metric_name)

    def _predict_moving_average(self, metric_name: str, window: int = 12) -> Tuple[float, float]:
        recent_metrics = list(self.metrics_history)[-window:]
        values = [getattr(m, metric_name) for m in recent_metrics]

        if not values:
            return 0.0, 0.0

        avg = sum(values) / len(values)

        variance = sum((v - avg) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance)
        confidence = max(0.0, 1.0 - (std_dev / (avg + 1)))

        return avg, confidence

    def _predict_exponential_smoothing(self, metric_name: str) -> Tuple[float, float]:
        if len(self.metrics_history) < 2:
            return 0.0, 0.0

        values = [getattr(m, metric_name) for m in self.metrics_history]

        level = values[0]
        trend = values[1] - values[0] if len(values) > 1 else 0

        beta = 0.2  # Trend smoothing factor

        for value in values[1:]:
            prev_level = level
            level = self.alpha * value + (1 - self.alpha) * (level + trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend

        steps = self.prediction_window // 5  # 5-second intervals
        prediction = level + (trend * steps)

        prediction = max(0.0, prediction)

        recent_values = values[-12:]  # Last minute
        variance = sum((v - level) ** 2 for v in recent_values) / len(recent_values)
        confidence = max(0.0, 1.0 - (math.sqrt(variance) / (level + 1)))

        return prediction, min(0.95, confidence)

    def _predict_pattern_matching(self, metric_name: str) -> Tuple[float, float]:
        if len(self.metrics_history) < 24:  # Need at least 2 minutes
            return self._predict_exponential_smoothing(metric_name)

        current_pattern = [
            getattr(m, metric_name)
            for m in list(self.metrics_history)[-12:]  # Last minute
        ]

        best_match_score = 0.0
        best_match_continuation = 0.0

        history_values = [getattr(m, metric_name) for m in self.metrics_history]

        for i in range(len(history_values) - 24):
            pattern = history_values[i:i + 12]
            continuation = history_values[i + 12:i + 14]  # Next 10 seconds

            if not continuation:
                continue

            diff = sum(abs(a - b) for a, b in zip(current_pattern, pattern))
            similarity = 1.0 / (1.0 + diff)

            if similarity > best_match_score:
                best_match_score = similarity
                best_match_continuation = sum(continuation) / len(continuation)

        if best_match_score > 0.5:
            return best_match_continuation, best_match_score
        else:
            return self._predict_exponential_smoothing(metric_name)

    def detect_trend(self, metric_name: str, window_minutes: int = 5) -> str:
        window_points = window_minutes * 12
        recent = list(self.metrics_history)[-window_points:]

        if len(recent) < 3:
            return "stable"

        values = [getattr(m, metric_name) for m in recent]

        n = len(values)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "stable"

        slope = numerator / denominator

        if abs(slope) < 0.5:
            return "stable"
        elif slope > 0:
            return "increasing"
        else:
            return "decreasing"

    def detect_anomaly(self, current_value: float, metric_name: str, threshold_std_dev: float = 2.0) -> bool:
        if len(self.metrics_history) < 12:
            return False

        values = [getattr(m, metric_name) for m in self.metrics_history]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            return False

        z_score = abs(current_value - mean) / std_dev
        return z_score > threshold_std_dev

    def predict_scaling_need(
        self,
        current_instances: int,
        target_cpu: float = 70.0,
        target_memory: float = 75.0
    ) -> PredictionResult:
        pred_cpu, conf_cpu = self.predict_load("cpu_usage", "exponential")
        pred_memory, conf_memory = self.predict_load("memory_usage", "exponential")
        pred_rps, conf_rps = self.predict_load("requests_per_second", "exponential")

        confidence = (conf_cpu + conf_memory + conf_rps) / 3.0

        if target_cpu > 0:
            required_by_cpu = math.ceil(current_instances * (pred_cpu / target_cpu))
        else:
            required_by_cpu = current_instances

        if target_memory > 0:
            required_by_memory = math.ceil(current_instances * (pred_memory / target_memory))
        else:
            required_by_memory = current_instances

        recommended = max(required_by_cpu, required_by_memory, current_instances)

        if recommended > current_instances:
            reason = f"Predicted load increase: CPU {pred_cpu:.1f}%, Memory {pred_memory:.1f}%"
        elif recommended < current_instances:
            reason = f"Predicted load decrease: CPU {pred_cpu:.1f}%, Memory {pred_memory:.1f}%"
        else:
            reason = f"Current capacity sufficient: CPU {pred_cpu:.1f}%, Memory {pred_memory:.1f}%"

        return PredictionResult(
            window_minutes=self.prediction_window,
            predicted_cpu=min(100.0, pred_cpu),
            predicted_memory=min(100.0, pred_memory),
            predicted_rps=pred_rps,
            predicted_connections=int(pred_rps * 2),
            confidence=confidence,
            recommended_instances=recommended,
            recommendation_reason=reason
        )

    def learn_pattern(self, pattern_name: str, metrics_sequence: List[ScalingMetrics]):
        cpu_values = [m.cpu_usage for m in metrics_sequence]
        self.patterns[pattern_name] = cpu_values

    def get_statistics(self) -> Dict:
        if not self.metrics_history:
            return {}

        recent = list(self.metrics_history)[-12:]
        cpu_values = [m.cpu_usage for m in recent]
        memory_values = [m.memory_usage for m in recent]

        return {
            "data_points": len(self.metrics_history),
            "avg_cpu": sum(cpu_values) / len(cpu_values),
            "avg_memory": sum(memory_values) / len(memory_values),
            "trend_cpu": self.detect_trend("cpu_usage"),
            "trend_memory": self.detect_trend("memory_usage"),
            "learned_patterns": len(self.patterns)
        }


if __name__ == "__main__":
    import asyncio as _asyncio
    import random as _random

    async def _main():
        print("=" * 70)
        print("ALGO-31 ALBAS — smoke test (real policy math + real predictor math)")
        print("=" * 70)

        # --- Target-tracking policy: scale up under sustained high CPU ---
        engine = ScalingEngine()
        policy = ScalingPolicy(
            id="cpu-target",
            name="CPU Target Tracking",
            policy_type=PolicyType.TARGET_TRACKING,
            metric="cpu",
            target_value=50.0,
            scale_up_threshold=80.0,
            scale_down_threshold=20.0,
            cooldown_seconds=0,
            min_instances=2,
            max_instances=10,
            scale_up_increment=3,
        )
        engine.register_policy(policy)
        engine.set_active_policy(policy.id)

        high_cpu_metrics = ScalingMetrics(cpu_usage=95.0, memory_usage=60.0, requests_per_second=500.0)
        action = await engine.evaluate_scaling(high_cpu_metrics)
        print(f"\n[ScalingEngine] target-tracking @ cpu=95% -> {action.type.value}, "
              f"{action.current_instances} -> {action.target_instances}")
        assert action is not None
        assert action.type == ActionType.SCALE_UP
        assert action.target_instances > action.current_instances

        executed = await engine.execute_scaling_action(action)
        print(f"[ScalingEngine] execute_scaling_action -> {executed}, current_instances={engine.current_instances}")
        assert executed is True
        assert engine.current_instances == action.target_instances
        assert engine.is_in_cooldown() is False  # cooldown_seconds=0

        stats = engine.get_statistics()
        print(f"[ScalingEngine] stats -> {stats}")
        assert stats["total_actions"] == 1
        assert stats["success_rate"] == 1.0

        # --- Step-scaling policy: emergency threshold (>90%) ---
        step_policy = ScalingPolicy(
            id="cpu-step",
            name="CPU Step Scaling",
            policy_type=PolicyType.STEP_SCALING,
            metric="cpu",
            target_value=50.0,
            scale_up_threshold=70.0,
            scale_down_threshold=20.0,
            cooldown_seconds=0,
            min_instances=2,
            max_instances=50,
        )
        engine2 = ScalingEngine()
        engine2.register_policy(step_policy)
        engine2.set_active_policy(step_policy.id)
        emergency_action = await engine2.evaluate_scaling(ScalingMetrics(cpu_usage=96.0, memory_usage=50.0))
        print(f"[ScalingEngine] step-scaling @ cpu=96% -> {emergency_action.reason} "
              f"(+{emergency_action.instances_change})")
        assert "Emergency" in emergency_action.reason
        assert emergency_action.instances_change == 5

        # --- LoadPredictor: real exponential smoothing + trend + anomaly detection ---
        predictor = LoadPredictor(history_window_minutes=5, prediction_window_minutes=10)
        _random.seed(42)
        base_cpu = 40.0
        for i in range(40):
            # Genuine upward-trending synthetic series (not random noise only)
            cpu = base_cpu + i * 1.2 + _random.uniform(-2, 2)
            mem = 55.0 + i * 0.5 + _random.uniform(-1, 1)
            rps = 100.0 + i * 3.0
            predictor.add_metrics(ScalingMetrics(cpu_usage=min(cpu, 100.0), memory_usage=min(mem, 100.0), requests_per_second=rps))

        pred_value, confidence = predictor.predict_load("cpu_usage", "exponential")
        print(f"\n[LoadPredictor] exponential-smoothing predicted cpu_usage={pred_value:.2f}, confidence={confidence:.3f}")
        assert pred_value > base_cpu  # real upward trend should predict higher than the start
        assert 0.0 <= confidence <= 1.0

        trend = predictor.detect_trend("cpu_usage")
        print(f"[LoadPredictor] detect_trend(cpu_usage) -> {trend}")
        assert trend == "increasing"

        is_anomaly_high = predictor.detect_anomaly(999.0, "cpu_usage")
        is_anomaly_normal = predictor.detect_anomaly(float(pred_value), "cpu_usage")
        print(f"[LoadPredictor] detect_anomaly(999) -> {is_anomaly_high}, detect_anomaly(predicted) -> {is_anomaly_normal}")
        assert is_anomaly_high is True
        assert is_anomaly_normal is False

        prediction_result = predictor.predict_scaling_need(current_instances=3, target_cpu=50.0, target_memory=70.0)
        print(f"[LoadPredictor] predict_scaling_need -> recommended_instances="
              f"{prediction_result.recommended_instances}, reason={prediction_result.recommendation_reason!r}")
        assert prediction_result.recommended_instances >= 3

        # --- Predictive scaling policy driven by the real predictor output ---
        pred_policy = ScalingPolicy(
            id="predictive",
            name="Predictive Scaling",
            policy_type=PolicyType.PREDICTIVE,
            metric="cpu",
            target_value=50.0,
            scale_up_threshold=80.0,
            scale_down_threshold=20.0,
            cooldown_seconds=0,
            min_instances=1,
            max_instances=50,
            scale_up_increment=2,
        )
        engine3 = ScalingEngine()
        engine3.current_instances = 3
        engine3.register_policy(pred_policy)
        engine3.set_active_policy(pred_policy.id)
        predictive_action = await engine3.evaluate_scaling(
            ScalingMetrics(cpu_usage=float(pred_value), memory_usage=60.0), prediction=prediction_result
        )
        print(f"[ScalingEngine] predictive-scaling -> {predictive_action}")
        if prediction_result.recommended_instances > 3:
            assert predictive_action is not None
            assert predictive_action.type == ActionType.SCALE_UP

        print("\nALL ASSERTIONS PASSED")

    _asyncio.run(_main())
