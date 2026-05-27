"""
Tests for Helix-TTD — Topological Trend Drift Detector
"""

from __future__ import annotations

import math
import unittest

from rct_control_plane.helix_ttd import (
    HELIX_TTD_VERSION,
    HELIX_STATE_DIM,
    HELIX_DIM_NAMES,
    DRIFT_VELOCITY_ALERT,
    DRIFT_VELOCITY_CRITICAL,
    HelixStateVector,
    TopologicalDriftDetector,
    HelixHistory,
    DriftAlert,
    drift_velocity,
    euclidean_distance,
)


# ============================================================
# Helpers
# ============================================================

def _stable(**kwargs) -> HelixStateVector:
    """Return a healthy default state vector with optional overrides."""
    defaults = dict(
        fdia=0.85,
        cord_score=0.90,
        mee_g=0.80,
        violation_rate=0.05,
        entropy=2.5,
        latency_norm=0.30,
        throughput_norm=0.70,
        governance_ratio=0.75,
    )
    defaults.update(kwargs)
    return HelixStateVector(**defaults)


# ============================================================
# 1. Constants
# ============================================================

class TestConstants(unittest.TestCase):
    def test_version(self):
        self.assertEqual(HELIX_TTD_VERSION, "1.0")

    def test_state_dim(self):
        self.assertEqual(HELIX_STATE_DIM, 8)

    def test_dim_names_count(self):
        self.assertEqual(len(HELIX_DIM_NAMES), 8)

    def test_alert_threshold(self):
        self.assertEqual(DRIFT_VELOCITY_ALERT, 0.15)

    def test_critical_threshold(self):
        self.assertEqual(DRIFT_VELOCITY_CRITICAL, 0.35)


# ============================================================
# 2. HelixStateVector
# ============================================================

class TestHelixStateVector(unittest.TestCase):
    def test_valid_state_no_errors(self):
        sv = _stable()
        self.assertEqual(sv.validate(), [])

    def test_as_tuple_has_8_elements(self):
        sv = _stable()
        self.assertEqual(len(sv.as_tuple()), 8)

    def test_entropy_normalised_in_tuple(self):
        sv = _stable(entropy=4.0)
        t = sv.as_tuple()
        # entropy 4.0 / 8.0 = 0.5
        self.assertAlmostEqual(t[4], 0.5)

    def test_to_dict_has_all_fields(self):
        sv = _stable()
        d = sv.to_dict()
        for name in HELIX_DIM_NAMES:
            self.assertIn(name, d)
        self.assertIn("recorded_at", d)

    def test_invalid_fdia_raises_error(self):
        errors = HelixStateVector(
            fdia=1.5, cord_score=0.8, mee_g=0.8, violation_rate=0.1,
            entropy=2.0, latency_norm=0.3, throughput_norm=0.7, governance_ratio=0.8
        ).validate()
        self.assertTrue(any("fdia" in e for e in errors))

    def test_invalid_entropy_raises_error(self):
        errors = _stable(entropy=9.0).validate()
        self.assertTrue(any("entropy" in e for e in errors))


# ============================================================
# 3. euclidean_distance / drift_velocity
# ============================================================

class TestDriftVelocity(unittest.TestCase):
    def test_zero_drift_identical_states(self):
        sv = _stable()
        v = drift_velocity(sv, sv)
        self.assertAlmostEqual(v, 0.0, places=10)

    def test_single_dimension_jump(self):
        sv1 = _stable(fdia=0.0)
        sv2 = _stable(fdia=1.0)
        v = drift_velocity(sv1, sv2)
        # distance = 1.0; normalised = 1 / sqrt(8) ≈ 0.354
        expected = 1.0 / math.sqrt(8)
        self.assertAlmostEqual(v, expected, places=5)

    def test_large_multi_dim_drift_above_alert(self):
        sv1 = _stable(fdia=0.9, cord_score=0.9, mee_g=0.9)
        sv2 = _stable(fdia=0.3, cord_score=0.3, mee_g=0.3)
        v = drift_velocity(sv1, sv2)
        self.assertGreater(v, DRIFT_VELOCITY_ALERT)

    def test_small_drift_below_alert(self):
        sv1 = _stable(fdia=0.85)
        sv2 = _stable(fdia=0.86)
        v = drift_velocity(sv1, sv2)
        self.assertLess(v, DRIFT_VELOCITY_ALERT)

    def test_dimension_mismatch_raises(self):
        with self.assertRaises(ValueError):
            euclidean_distance((1.0, 2.0), (1.0, 2.0, 3.0))


# ============================================================
# 4. TopologicalDriftDetector
# ============================================================

class TestTopologicalDriftDetector(unittest.TestCase):
    def test_first_observation_no_alert(self):
        det = TopologicalDriftDetector()
        alert = det.observe(_stable())
        self.assertIsNone(alert)

    def test_stable_sequence_no_alert(self):
        det = TopologicalDriftDetector()
        det.observe(_stable())
        for _ in range(5):
            alert = det.observe(_stable(fdia=0.85 + 0.001))
            self.assertIsNone(alert)

    def test_large_jump_triggers_warning(self):
        det = TopologicalDriftDetector()
        det.observe(_stable(fdia=0.9))
        alert = det.observe(_stable(fdia=0.3, cord_score=0.3))
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "warning")

    def test_very_large_jump_triggers_critical(self):
        det = TopologicalDriftDetector()
        det.observe(_stable(fdia=1.0, cord_score=1.0, mee_g=1.0))
        alert = det.observe(_stable(
            fdia=0.0, cord_score=0.0, mee_g=0.0,
            violation_rate=1.0, latency_norm=1.0,
        ))
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "critical")

    def test_alert_contains_from_to_states(self):
        det = TopologicalDriftDetector()
        sv1 = _stable(fdia=0.9)
        sv2 = _stable(fdia=0.1, cord_score=0.1)
        det.observe(sv1)
        alert = det.observe(sv2)
        self.assertIsNotNone(alert)
        self.assertIsInstance(alert.from_state, HelixStateVector)
        self.assertIsInstance(alert.to_state, HelixStateVector)

    def test_alert_count_increments(self):
        det = TopologicalDriftDetector()
        det.observe(_stable(fdia=1.0))
        det.observe(_stable(fdia=0.1, cord_score=0.1))
        self.assertEqual(det.alert_count, 1)

    def test_reset_clears_state(self):
        det = TopologicalDriftDetector()
        det.observe(_stable())
        det.reset()
        alert = det.observe(_stable())
        self.assertIsNone(alert)
        self.assertEqual(det.alert_count, 0)

    def test_invalid_state_raises(self):
        det = TopologicalDriftDetector()
        bad = HelixStateVector(
            fdia=2.0, cord_score=0.8, mee_g=0.8, violation_rate=0.1,
            entropy=2.0, latency_norm=0.3, throughput_norm=0.7, governance_ratio=0.8,
        )
        with self.assertRaises(ValueError):
            det.observe(bad)

    def test_drift_alert_to_dict(self):
        det = TopologicalDriftDetector()
        det.observe(_stable(fdia=1.0))
        alert = det.observe(_stable(fdia=0.1, cord_score=0.1))
        d = alert.to_dict()
        self.assertIn("severity", d)
        self.assertIn("velocity", d)
        self.assertIn("threshold", d)

    def test_is_critical_property(self):
        det = TopologicalDriftDetector(critical_threshold=0.01)
        det.observe(_stable(fdia=1.0))
        alert = det.observe(_stable(fdia=0.5))
        self.assertTrue(alert.is_critical)


# ============================================================
# 5. HelixHistory
# ============================================================

class TestHelixHistory(unittest.TestCase):
    def test_push_returns_none_when_stable(self):
        h = HelixHistory()
        for _ in range(3):
            result = h.push(_stable(fdia=0.8))
            self.assertIsNone(result)

    def test_push_returns_alert_on_drift(self):
        h = HelixHistory()
        h.push(_stable(fdia=1.0))
        alert = h.push(_stable(fdia=0.1, cord_score=0.1))
        self.assertIsNotNone(alert)

    def test_states_list_grows(self):
        h = HelixHistory()
        for i in range(5):
            h.push(_stable(fdia=0.8))
        self.assertEqual(len(h.states), 5)

    def test_alert_recorded_in_history(self):
        h = HelixHistory()
        h.push(_stable(fdia=1.0))
        h.push(_stable(fdia=0.0, cord_score=0.0))
        self.assertEqual(h.alert_count, 1)

    def test_mean_vector_none_when_empty(self):
        h = HelixHistory()
        self.assertIsNone(h.mean_vector())

    def test_mean_vector_correct(self):
        h = HelixHistory()
        h.push(_stable(fdia=0.6))
        h.push(_stable(fdia=0.8))
        mean = h.mean_vector()
        self.assertIsInstance(mean, HelixStateVector)
        self.assertAlmostEqual(mean.fdia, 0.7, places=5)

    def test_clear_resets_everything(self):
        h = HelixHistory()
        h.push(_stable(fdia=1.0))
        h.push(_stable(fdia=0.0, cord_score=0.0))
        h.clear()
        self.assertEqual(len(h.states), 0)
        self.assertEqual(h.alert_count, 0)

    def test_max_size_enforced(self):
        h = HelixHistory(max_size=5)
        for _ in range(10):
            h.push(_stable())
        self.assertLessEqual(len(h.states), 5)


if __name__ == "__main__":
    unittest.main()
