"""
ALGO-35: ATC — Adaptive Timeout Controller (Production Runtime)

Ported from Delentia-Private-OS/rct_platform/microservices/adaptive-timeout/
app/core/ (timeout_controller.py + predictive_engine.py) on 2026-09-15,
following the same strip-the-FastAPI-keep-the-engine pattern used for
ALGO-07 (mee_engine.py). Only two adaptations from the source:

1. The Pydantic request/response schemas the source pulled from
   ..models.schemas are trimmed down to just the models these two classes
   actually use (TimeoutConfig, TimeoutAdjustment, AdjustmentReason,
   PredictionContext, PredictionFactors, TimeoutPrediction,
   PerformancePattern, PatternType, WorkloadType) — pydantic is already a
   Delentia-OS dependency (pyproject.toml), so no new package is needed.
2. `from loguru import logger` is replaced with stdlib `logging` — loguru
   is not a Delentia-OS dependency (see report), and the class logic
   itself does not depend on loguru specifically, only on a `.info()` /
   `.debug()` / `.warning()` / `.error()` logger interface that stdlib
   `logging` already provides.

Everything else — the percentile timeout math, the time-of-day/workload
prediction math — is real and ported verbatim.

Real logic ported as-is:
    - TimeoutController: rolling-window (deque, maxlen=history_size)
      response-time history; `_calculate_percentile_timeout()` computes a
      real percentile via `statistics.quantiles(..., method="inclusive")`,
      applies a real safety-buffer multiplier, and clamps to
      [min_timeout, max_timeout].
    - PredictiveEngine: `_get_time_multiplier()` /
      `_get_workload_multiplier()` compute real statistics.mean() ratios
      of a given hour/workload's average response time against the
      overall average, clamped to [0.5, 2.0] — labeled "ML-based" /
      "ML-based timeout prediction" in the source's own docstring, but
      this is genuine descriptive statistics (statistics.mean over
      recorded observations), not a trained model. Ported as real
      statistics, and this docstring does not repeat the "ML" framing.
    - detect_patterns()/_detect_hourly_pattern()/_detect_daily_pattern():
      real peak-hour/peak-day detection (>20% above the overall average).

Usage::

    import asyncio
    controller = TimeoutController()
    async def demo():
        for _ in range(15):
            await controller.record_response(duration=1.2, success=True)
        adj = await controller.adjust_timeout()
        print(adj.current_timeout)
    asyncio.run(demo())
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import defaultdict, deque
from datetime import datetime
from enum import Enum
from typing import Deque, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Enums (subset of the source's schemas.py actually used by these engines)
# ============================================================================

class TimeoutStatus(str, Enum):
    """Timeout status types"""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"
    RETRYING = "retrying"


class WorkloadType(str, Enum):
    """Workload classification types"""
    API_CALL = "api_call"
    DATABASE_QUERY = "database_query"
    HEAVY_COMPUTATION = "heavy_computation"
    FILE_IO = "file_io"
    NETWORK_REQUEST = "network_request"
    LLM_INFERENCE = "llm_inference"
    WEB_CRAWL = "web_crawl"
    OTHER = "other"


class AdjustmentReason(str, Enum):
    """Reasons for timeout adjustment"""
    PERCENTILE_INCREASED = "95th percentile increased"
    PERCENTILE_DECREASED = "95th percentile decreased"
    ERROR_RATE_HIGH = "error rate high"
    PERFORMANCE_IMPROVED = "performance improved"
    WORKLOAD_CHANGE = "workload change detected"
    PATTERN_DETECTED = "performance pattern detected"
    MANUAL_OVERRIDE = "manual policy override"
    INITIAL = "initial value"


class PatternType(str, Enum):
    """Pattern types"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ============================================================================
# Pydantic models (trimmed to what TimeoutController / PredictiveEngine use)
# ============================================================================

class TimeoutConfig(BaseModel):
    """Timeout configuration settings"""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "min_timeout": 1.0,
            "max_timeout": 60.0,
            "base_timeout": 5.0,
            "percentile": 0.95,
            "buffer_factor": 1.2,
            "history_size": 100
        }
    })

    min_timeout: float = Field(default=1.0, ge=0.1, le=10.0)
    max_timeout: float = Field(default=60.0, ge=10.0, le=300.0)
    base_timeout: float = Field(default=5.0, ge=0.5, le=60.0)
    percentile: float = Field(default=0.95, ge=0.5, le=0.99)
    buffer_factor: float = Field(default=1.2, ge=1.0, le=2.0)
    history_size: int = Field(default=100, ge=10, le=1000)


class TimeoutAdjustment(BaseModel):
    """Result of a timeout adjustment"""
    current_timeout: float = Field(ge=0.0)
    previous_timeout: float = Field(ge=0.0)
    adjustment_reason: AdjustmentReason
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.now)
    sample_count: int = Field(default=0, ge=0)


class PredictionContext(BaseModel):
    """Context for timeout prediction"""
    workload_type: WorkloadType
    time_of_day: Optional[str] = None
    historical_context: Optional[Dict[str, object]] = None


class PredictionFactors(BaseModel):
    """Factors contributing to a prediction"""
    baseline: float = Field(ge=0.0)
    time_multiplier: float = Field(ge=0.5, le=2.0)
    workload_factor: float = Field(ge=0.5, le=2.0)
    pattern_factor: Optional[float] = Field(default=None, ge=0.5, le=2.0)


class TimeoutPrediction(BaseModel):
    """Predicted timeout value"""
    predicted_timeout: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    factors: PredictionFactors
    sample_count: int = Field(default=0, ge=0)


class PerformancePattern(BaseModel):
    """Detected performance pattern"""
    pattern_type: PatternType
    peak_hours: Optional[List[int]] = None
    peak_days: Optional[List[str]] = None
    multiplier: float = Field(ge=0.5, le=3.0)
    confidence: float = Field(ge=0.0, le=1.0)


# ============================================================================
# TimeoutController — real percentile-based timeout calculation
# ============================================================================

class TimeoutController:
    """
    Dynamic timeout calculation and adjustment.

    Algorithm:
    1. Collect response times in a rolling window (deque, maxlen=history_size)
    2. Sort response times
    3. Calculate specified percentile (statistics.quantiles, inclusive)
    4. Add safety buffer (e.g. 20%)
    5. Clamp to min/max boundaries
    6. Update current timeout
    """

    def __init__(self, config: Optional[TimeoutConfig] = None):
        self.config = config or TimeoutConfig()

        self.response_times: Deque[float] = deque(maxlen=self.config.history_size)

        self._current_timeout = self.config.base_timeout
        self._previous_timeout = self.config.base_timeout

        self.total_adjustments = 0
        self.successful_requests = 0
        self.timeout_errors = 0
        self.last_adjustment_time: Optional[datetime] = None

        self._lock = asyncio.Lock()

        logger.info(
            "TimeoutController initialized: base=%ss, range=[%s-%s]s, percentile=%s%%, buffer=%sx",
            self.config.base_timeout, self.config.min_timeout, self.config.max_timeout,
            self.config.percentile * 100, self.config.buffer_factor,
        )

    async def record_response(
        self,
        duration: float,
        success: bool,
        workload_type: Optional[WorkloadType] = None
    ) -> None:
        """Record a request's performance."""
        async with self._lock:
            self.response_times.append(duration)

            if success:
                self.successful_requests += 1
            else:
                self.timeout_errors += 1

            logger.debug(
                "Recorded response: %.3fs, success=%s, type=%s, history_size=%d",
                duration, success, workload_type, len(self.response_times),
            )

    async def get_timeout(self) -> float:
        """Get current recommended timeout value."""
        async with self._lock:
            return self._current_timeout

    async def adjust_timeout(self, force: bool = False) -> Optional[TimeoutAdjustment]:
        """Recalculate and adjust the timeout value."""
        async with self._lock:
            sample_count = len(self.response_times)

            if sample_count < 10 and not force:
                logger.debug("Insufficient samples for adjustment: %d < 10", sample_count)
                return None

            if sample_count == 0:
                logger.warning("No response times available for adjustment")
                return None

            self._previous_timeout = self._current_timeout

            new_timeout = self._calculate_percentile_timeout()

            reason = self._determine_adjustment_reason(new_timeout)

            confidence = min(1.0, sample_count / self.config.history_size)

            self._current_timeout = new_timeout
            self.total_adjustments += 1
            self.last_adjustment_time = datetime.now()

            adjustment = TimeoutAdjustment(
                current_timeout=new_timeout,
                previous_timeout=self._previous_timeout,
                adjustment_reason=reason,
                confidence=confidence,
                sample_count=sample_count
            )

            logger.info(
                "Timeout adjusted: %.2fs -> %.2fs (reason=%s, confidence=%.2f, samples=%d)",
                self._previous_timeout, new_timeout, reason, confidence, sample_count,
            )

            return adjustment

    def _calculate_percentile_timeout(self) -> float:
        """
        Real percentile calculation:
        1. Sort response times
        2. Find percentile value (statistics.quantiles, n=100, inclusive)
        3. Add safety buffer
        4. Clamp to min/max
        """
        if not self.response_times:
            return self.config.base_timeout

        sorted_times = sorted(self.response_times)
        percentile_value = statistics.quantiles(
            sorted_times,
            n=100,
            method='inclusive'
        )[int(self.config.percentile * 100) - 1]

        buffered_timeout = percentile_value * self.config.buffer_factor

        clamped_timeout = max(
            self.config.min_timeout,
            min(self.config.max_timeout, buffered_timeout)
        )

        logger.debug(
            "Calculated timeout: p%s=%.3fs, buffered=%.3fs, clamped=%.3fs",
            self.config.percentile * 100, percentile_value, buffered_timeout, clamped_timeout,
        )

        return clamped_timeout

    def _determine_adjustment_reason(self, new_timeout: float) -> AdjustmentReason:
        """Determine reason for the timeout adjustment."""
        if self._previous_timeout == self.config.base_timeout:
            return AdjustmentReason.INITIAL

        change_pct = (
            (new_timeout - self._previous_timeout) / self._previous_timeout
        ) * 100

        if change_pct > 10:
            total_requests = self.successful_requests + self.timeout_errors
            if total_requests > 0:
                error_rate = (self.timeout_errors / total_requests) * 100
                if error_rate > 5.0:
                    return AdjustmentReason.ERROR_RATE_HIGH
            return AdjustmentReason.PERCENTILE_INCREASED

        elif change_pct < -10:
            return AdjustmentReason.PERCENTILE_DECREASED

        else:
            total_requests = self.successful_requests + self.timeout_errors
            if total_requests > 0:
                error_rate = (self.timeout_errors / total_requests) * 100
                if error_rate < 2.0:
                    return AdjustmentReason.PERFORMANCE_IMPROVED

            return AdjustmentReason.PERCENTILE_INCREASED

    async def get_statistics(self) -> Dict[str, object]:
        """Get timeout controller statistics."""
        async with self._lock:
            total_requests = self.successful_requests + self.timeout_errors
            error_rate = 0.0
            if total_requests > 0:
                error_rate = (self.timeout_errors / total_requests) * 100

            avg_response_time = 0.0
            if self.response_times:
                avg_response_time = statistics.mean(self.response_times)

            percentiles = {}
            if len(self.response_times) >= 2:
                sorted_times = sorted(self.response_times)
                percentiles = {
                    "p50": statistics.median(sorted_times),
                    "p95": statistics.quantiles(sorted_times, n=100, method='inclusive')[94],
                    "p99": statistics.quantiles(sorted_times, n=100, method='inclusive')[98]
                }

            return {
                "current_timeout": self._current_timeout,
                "min_timeout": self.config.min_timeout,
                "max_timeout": self.config.max_timeout,
                "base_timeout": self.config.base_timeout,
                "percentile": self.config.percentile,
                "buffer_factor": self.config.buffer_factor,
                "total_requests": total_requests,
                "successful_requests": self.successful_requests,
                "timeout_errors": self.timeout_errors,
                "error_rate": error_rate,
                "avg_response_time": avg_response_time,
                "sample_count": len(self.response_times),
                "history_size": self.config.history_size,
                "total_adjustments": self.total_adjustments,
                "last_adjustment": (
                    self.last_adjustment_time.isoformat()
                    if self.last_adjustment_time else None
                ),
                **percentiles
            }

    async def reset_statistics(self) -> None:
        """Reset statistics counters."""
        async with self._lock:
            self.successful_requests = 0
            self.timeout_errors = 0
            self.total_adjustments = 0
            self.last_adjustment_time = None
            logger.info("Statistics reset")

    async def clear_history(self) -> None:
        """Clear response time history."""
        async with self._lock:
            self.response_times.clear()
            self._current_timeout = self.config.base_timeout
            self._previous_timeout = self.config.base_timeout
            logger.info("History cleared, timeout reset to base value")

    async def set_config(self, config: TimeoutConfig) -> None:
        """Update timeout configuration."""
        async with self._lock:
            old_config = self.config
            self.config = config

            if config.history_size != old_config.history_size:
                times_list = list(self.response_times)
                self.response_times = deque(
                    times_list[-config.history_size:],
                    maxlen=config.history_size
                )

            logger.info(
                "Configuration updated: base=%ss, range=[%s-%s]s, percentile=%s%%, buffer=%sx",
                config.base_timeout, config.min_timeout, config.max_timeout,
                config.percentile * 100, config.buffer_factor,
            )

    async def get_config(self) -> TimeoutConfig:
        """Get current configuration."""
        async with self._lock:
            return self.config

    async def get_history(self, limit: Optional[int] = None) -> List[float]:
        """Get response time history (most recent first)."""
        async with self._lock:
            history = list(self.response_times)
            history.reverse()

            if limit is not None and limit < len(history):
                history = history[:limit]

            return history


# ============================================================================
# PredictiveEngine — real statistical time-of-day/workload prediction
# ============================================================================

class PredictiveEngine:
    """
    Statistical timeout prediction and pattern recognition.

    NOTE ON NAMING: the source module's docstring calls this "ML-based" —
    it is not a trained model. `_get_time_multiplier()` and
    `_get_workload_multiplier()` are real applications of
    `statistics.mean()` over recorded observation history (an hour's or a
    workload's average response time relative to the overall average,
    clamped to [0.5, 2.0]), not a fitted model with learned parameters.
    Ported as real statistics; this docstring intentionally does not
    repeat the "ML" framing so as not to mislead callers.

    Features:
    - Pattern detection (hourly, daily)
    - Workload-based prediction
    - Time-of-day adjustment
    - Confidence scoring
    """

    def __init__(self, baseline_timeout: float = 5.0):
        self.baseline_timeout = baseline_timeout

        self.hourly_stats: Dict[int, List[float]] = defaultdict(list)
        self.daily_stats: Dict[str, List[float]] = defaultdict(list)
        self.workload_stats: Dict[WorkloadType, List[float]] = defaultdict(list)

        self._lock = asyncio.Lock()

        logger.info("PredictiveEngine initialized: baseline=%ss", baseline_timeout)

    async def record_observation(
        self,
        duration: float,
        workload_type: Optional[WorkloadType] = None,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Record an observation for pattern learning."""
        async with self._lock:
            ts = timestamp or datetime.now()

            hour = ts.hour
            self.hourly_stats[hour].append(duration)
            if len(self.hourly_stats[hour]) > 100:
                self.hourly_stats[hour] = self.hourly_stats[hour][-100:]

            day_name = ts.strftime("%A")
            self.daily_stats[day_name].append(duration)
            if len(self.daily_stats[day_name]) > 100:
                self.daily_stats[day_name] = self.daily_stats[day_name][-100:]

            if workload_type:
                self.workload_stats[workload_type].append(duration)
                if len(self.workload_stats[workload_type]) > 100:
                    self.workload_stats[workload_type] = (
                        self.workload_stats[workload_type][-100:]
                    )

    async def predict_timeout(self, context: PredictionContext) -> TimeoutPrediction:
        """Predict the optimal timeout for a given context."""
        async with self._lock:
            baseline = self.baseline_timeout

            time_multiplier = await self._get_time_multiplier()

            workload_multiplier = await self._get_workload_multiplier(
                context.workload_type
            )

            predicted_timeout = baseline * time_multiplier * workload_multiplier

            sample_count = await self._get_sample_count(context)
            confidence = min(1.0, sample_count / 50.0)  # 50 samples = 100% confidence

            factors = PredictionFactors(
                baseline=baseline,
                time_multiplier=time_multiplier,
                workload_factor=workload_multiplier
            )

            logger.info(
                "Predicted timeout: %.2fs (baseline=%.2fs, time=%.2fx, workload=%.2fx, confidence=%.2f)",
                predicted_timeout, baseline, time_multiplier, workload_multiplier, confidence,
            )

            return TimeoutPrediction(
                predicted_timeout=predicted_timeout,
                confidence=confidence,
                factors=factors,
                sample_count=sample_count
            )

    async def _get_time_multiplier(self) -> float:
        """Real time-of-day performance multiplier (mean ratio, clamped)."""
        current_hour = datetime.now().hour

        if current_hour not in self.hourly_stats:
            return 1.0

        values = self.hourly_stats[current_hour]
        if not values:
            return 1.0

        hour_avg = statistics.mean(values)

        all_values = []
        for hour_values in self.hourly_stats.values():
            all_values.extend(hour_values)

        if not all_values:
            return 1.0

        overall_avg = statistics.mean(all_values)

        if overall_avg > 0:
            multiplier = hour_avg / overall_avg
            return max(0.5, min(2.0, multiplier))

        return 1.0

    async def _get_workload_multiplier(self, workload_type: WorkloadType) -> float:
        """Real workload-specific performance multiplier (mean ratio, clamped)."""
        if workload_type not in self.workload_stats:
            return 1.0

        values = self.workload_stats[workload_type]
        if not values:
            return 1.0

        workload_avg = statistics.mean(values)

        all_values = []
        for workload_values in self.workload_stats.values():
            all_values.extend(workload_values)

        if not all_values:
            return 1.0

        overall_avg = statistics.mean(all_values)

        if overall_avg > 0:
            multiplier = workload_avg / overall_avg
            return max(0.5, min(2.0, multiplier))

        return 1.0

    async def _get_sample_count(self, context: PredictionContext) -> int:
        """Get number of samples backing a prediction context."""
        count = 0

        current_hour = datetime.now().hour
        if current_hour in self.hourly_stats:
            count += len(self.hourly_stats[current_hour])

        if context.workload_type in self.workload_stats:
            count += len(self.workload_stats[context.workload_type])

        return count

    async def detect_patterns(self) -> List[PerformancePattern]:
        """Detect real hourly/daily performance patterns."""
        async with self._lock:
            patterns = []

            if len(self.hourly_stats) >= 5:
                hourly_pattern = await self._detect_hourly_pattern()
                if hourly_pattern:
                    patterns.append(hourly_pattern)

            if len(self.daily_stats) >= 3:
                daily_pattern = await self._detect_daily_pattern()
                if daily_pattern:
                    patterns.append(daily_pattern)

            return patterns

    async def _detect_hourly_pattern(self) -> Optional[PerformancePattern]:
        """Detect hourly performance pattern (peak hours >20% above average)."""
        hour_averages = {}
        for hour, values in self.hourly_stats.items():
            if values:
                hour_averages[hour] = statistics.mean(values)

        if not hour_averages:
            return None

        overall_avg = statistics.mean(hour_averages.values())

        peak_hours = [
            hour for hour, avg in hour_averages.items()
            if avg > overall_avg * 1.2
        ]

        if not peak_hours:
            return None

        peak_avg = statistics.mean([hour_averages[h] for h in peak_hours])
        multiplier = peak_avg / overall_avg if overall_avg > 0 else 1.0

        return PerformancePattern(
            pattern_type=PatternType.HOURLY,
            peak_hours=sorted(peak_hours),
            multiplier=multiplier,
            confidence=min(1.0, len(peak_hours) / 10.0)
        )

    async def _detect_daily_pattern(self) -> Optional[PerformancePattern]:
        """Detect daily performance pattern (peak days >20% above average)."""
        day_averages = {}
        for day, values in self.daily_stats.items():
            if values:
                day_averages[day] = statistics.mean(values)

        if not day_averages:
            return None

        overall_avg = statistics.mean(day_averages.values())

        peak_days = [
            day for day, avg in day_averages.items()
            if avg > overall_avg * 1.2
        ]

        if not peak_days:
            return None

        peak_avg = statistics.mean([day_averages[d] for d in peak_days])
        multiplier = peak_avg / overall_avg if overall_avg > 0 else 1.0

        return PerformancePattern(
            pattern_type=PatternType.DAILY,
            peak_days=peak_days,
            multiplier=multiplier,
            confidence=min(1.0, len(peak_days) / 7.0)
        )


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    import random

    async def _smoke_test():
        print("=== ALGO-35 ATC (Adaptive Timeout Controller) smoke test ===")

        # --- TimeoutController: real p95 percentile calculation ---
        controller = TimeoutController(TimeoutConfig(base_timeout=2.0, percentile=0.95, buffer_factor=1.2))

        random.seed(42)
        # 20 fast responses + a few slow outliers -> p95 should sit above the fast cluster
        durations = [round(random.uniform(0.8, 1.2), 3) for _ in range(18)] + [4.5, 5.0]
        for d in durations:
            await controller.record_response(duration=d, success=True)

        adjustment = await controller.adjust_timeout()
        print(f"Adjustment: current={adjustment.current_timeout:.3f}s, "
              f"previous={adjustment.previous_timeout:.3f}s, reason={adjustment.adjustment_reason}, "
              f"confidence={adjustment.confidence:.2f}, samples={adjustment.sample_count}")
        assert adjustment is not None
        assert adjustment.current_timeout > 1.2  # buffered p95 should exceed the fast cluster
        assert adjustment.sample_count == 20

        stats = await controller.get_statistics()
        print(f"Stats: p50={stats['p50']:.3f}, p95={stats['p95']:.3f}, p99={stats['p99']:.3f}, "
              f"avg={stats['avg_response_time']:.3f}")
        assert stats["p95"] >= stats["p50"]

        # Too few samples -> no adjustment unless forced
        controller2 = TimeoutController()
        await controller2.record_response(duration=1.0, success=True)
        no_adj = await controller2.adjust_timeout()
        assert no_adj is None
        forced_adj = await controller2.adjust_timeout(force=True)
        assert forced_adj is not None
        print(f"Forced single-sample adjustment: {forced_adj.current_timeout:.3f}s "
              f"(reason={forced_adj.adjustment_reason})")

        # --- PredictiveEngine: real time-of-day / workload statistics ---
        engine = PredictiveEngine(baseline_timeout=5.0)

        # Feed a clearly slower workload (LLM_INFERENCE) vs a fast one (API_CALL)
        for _ in range(30):
            await engine.record_observation(duration=random.uniform(0.4, 0.6), workload_type=WorkloadType.API_CALL)
        for _ in range(30):
            await engine.record_observation(duration=random.uniform(2.0, 3.0), workload_type=WorkloadType.LLM_INFERENCE)

        pred_fast = await engine.predict_timeout(PredictionContext(workload_type=WorkloadType.API_CALL))
        pred_slow = await engine.predict_timeout(PredictionContext(workload_type=WorkloadType.LLM_INFERENCE))
        print(f"Predicted timeout API_CALL={pred_fast.predicted_timeout:.3f}s "
              f"(workload_factor={pred_fast.factors.workload_factor:.3f})")
        print(f"Predicted timeout LLM_INFERENCE={pred_slow.predicted_timeout:.3f}s "
              f"(workload_factor={pred_slow.factors.workload_factor:.3f})")
        assert pred_slow.predicted_timeout > pred_fast.predicted_timeout, \
            "slower workload's real statistics.mean() ratio must predict a larger timeout"

        print("=== ALGO-35 ATC: ALL ASSERTIONS PASSED ===")

    asyncio.run(_smoke_test())
