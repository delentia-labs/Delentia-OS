"""
Tests for MEEEngine / MEESession — MEE v2 Production Runtime
rct_control_plane/mee_engine.py

MEE v2 formula: G(t+1) = max(G_FLOOR, G(t) × (1 + M × Δ) × R_t)
"""

import json
import os

import pytest
from rct_control_plane.mee_engine import (
    MEEEngine,
    MEESession,
    MEEStepRecord,
    MEE_VERSION,
    DEFAULT_META_RATE,
    DEFAULT_STATE_FILE,
    G_FLOOR,
    G_CAP,
    RESILIENCE_PENALTY,
)


# ─── Tests: MEESession single-session behaviour ───────────────────────────────

class TestMEESessionBasics:
    def test_initial_g_is_one(self):
        sess = MEESession(session_id="test-init")
        assert sess.g == 1.0

    def test_version_constant(self):
        assert MEE_VERSION == "2.0"

    def test_default_meta_rate(self):
        assert DEFAULT_META_RATE == pytest.approx(0.10)

    def test_g_floor_constant(self):
        assert G_FLOOR == pytest.approx(0.10)

    def test_g_cap_constant(self):
        assert G_CAP == pytest.approx(1000.0)

    def test_resilience_penalty_constant(self):
        assert RESILIENCE_PENALTY == pytest.approx(0.02)


class TestMEESessionStep:
    def test_positive_delta_increases_g(self):
        sess = MEESession(session_id="pos")
        record = sess.step(delta=0.5)
        assert record.g_after > record.g_before

    def test_negative_delta_decreases_g(self):
        sess = MEESession(session_id="neg")
        record = sess.step(delta=-0.5)
        assert record.g_after < record.g_before

    def test_zero_delta_leaves_g_near_initial(self):
        sess = MEESession(session_id="zero")
        record = sess.step(delta=0.0)
        # G × (1 + M × 0) × R_t = G × R_t ≤ G (resilience ≤ 1)
        assert record.g_after <= record.g_before + 1e-9

    def test_g_never_below_floor(self):
        sess = MEESession(session_id="floor")
        for _ in range(20):
            sess.step(delta=-1.0, governance_violation=True)
        assert sess.g >= G_FLOOR

    def test_g_never_above_cap(self):
        sess = MEESession(session_id="cap")
        for _ in range(50):
            sess.step(delta=1.0)
        assert sess.g <= G_CAP

    def test_step_returns_mee_step_record(self):
        sess = MEESession(session_id="rec")
        record = sess.step(delta=0.1)
        assert isinstance(record, MEEStepRecord)

    def test_step_record_fields_populated(self):
        sess = MEESession(session_id="fields")
        record = sess.step(delta=0.2)
        assert record.step_number >= 1
        assert record.g_before == pytest.approx(1.0)
        assert record.g_after > 0
        assert record.delta == pytest.approx(0.2)
        assert record.meta_rate == pytest.approx(DEFAULT_META_RATE)
        assert record.resilience > 0
        assert record.timestamp != ""

    def test_step_count_increments(self):
        sess = MEESession(session_id="count")
        assert sess.step_count == 0
        sess.step(delta=0.1)
        assert sess.step_count == 1
        sess.step(delta=0.1)
        assert sess.step_count == 2


class TestMEEFormula:
    def test_formula_exact_calculation(self):
        """Verify G(t+1) = G(t) × (1 + M × Δ) × R_t for clean step."""
        sess = MEESession(session_id="formula", meta_rate=0.10)
        g0 = sess.g  # 1.0
        delta = 0.5
        record = sess.step(delta=delta)

        # R_t = 1.0 (no violation, resilience starts at 1.0)
        expected = max(G_FLOOR, min(G_CAP, g0 * (1 + 0.10 * delta) * 1.0))
        assert record.g_after == pytest.approx(expected, rel=1e-6)

    def test_formula_with_governance_violation(self):
        """Governance violation reduces R_t by RESILIENCE_PENALTY."""
        sess = MEESession(session_id="gov", meta_rate=0.10)
        g0 = sess.g  # 1.0
        delta = 0.5
        record = sess.step(delta=delta, governance_violation=True)

        # R_t = 1.0 - RESILIENCE_PENALTY = 0.98
        r_t = 1.0 - RESILIENCE_PENALTY
        expected = max(G_FLOOR, min(G_CAP, g0 * (1 + 0.10 * delta) * r_t))
        assert record.g_after == pytest.approx(expected, rel=1e-6)

    def test_resilience_penalised_on_violation(self):
        sess = MEESession(session_id="res-pen")
        record = sess.step(delta=0.1, governance_violation=True)
        assert record.resilience == pytest.approx(1.0 - RESILIENCE_PENALTY, rel=1e-6)

    def test_resilience_recovers_without_violation(self):
        sess = MEESession(session_id="res-rec")
        # First penalise
        sess.step(delta=0.1, governance_violation=True)
        r_after_violation = sess.resilience
        # Then recover (multiple clean steps)
        sess.step(delta=0.1, governance_violation=False)
        assert sess.resilience > r_after_violation

    def test_consecutive_steps_chain_correctly(self):
        sess = MEESession(session_id="chain", meta_rate=0.10)
        sess.step(delta=0.2)
        g1 = sess.g
        sess.step(delta=0.3)
        g2 = sess.g
        assert g2 > g1  # two positive deltas should grow G


class TestMEESessionSerialization:
    def test_to_dict_returns_dict(self):
        sess = MEESession(session_id="ser")
        sess.step(delta=0.1)
        d = sess.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_required_keys(self):
        sess = MEESession(session_id="keys")
        sess.step(delta=0.05)
        d = sess.to_dict()
        # to_dict() uses g_current (not g)
        for key in ("session_id", "g_current", "step_count", "meta_rate", "resilience"):
            assert key in d, f"Missing key: {key}"

    def test_from_dict_restores_g(self):
        sess = MEESession(session_id="restore")
        for _ in range(3):
            sess.step(delta=0.1)
        g_before = sess.g
        d = sess.to_dict()
        restored = MEESession.from_dict(d)
        assert restored.g == pytest.approx(g_before, rel=1e-9)

    def test_from_dict_restores_g_current(self):
        """from_dict restores G but not full history (steps not replayed)."""
        sess = MEESession(session_id="cnt")
        for _ in range(5):
            sess.step(delta=0.05)
        g_expected = sess.g
        d = sess.to_dict()
        restored = MEESession.from_dict(d)
        assert restored.g == pytest.approx(g_expected, rel=1e-6)

    def test_summary_dict(self):
        sess = MEESession(session_id="sum")
        for _ in range(3):
            sess.step(delta=0.1)
        s = sess.summary()
        assert "g" in s or "g_current" in s or "session_id" in s


# ─── Tests: MEEEngine multi-session ──────────────────────────────────────────

class TestMEEEngine:
    def test_create_session(self):
        engine = MEEEngine()
        sess = engine.create_session("agent-alpha")
        assert isinstance(sess, MEESession)

    def test_get_or_create_returns_same_session(self):
        engine = MEEEngine()
        s1 = engine.get_or_create("agent-beta")
        s2 = engine.get_or_create("agent-beta")
        assert s1 is s2

    def test_step_via_engine(self):
        engine = MEEEngine()
        engine.get_or_create("agent-gamma")
        record = engine.step("agent-gamma", delta=0.2)
        assert isinstance(record, MEEStepRecord)
        assert record.g_after != record.g_before

    def test_step_raises_for_missing_session(self):
        """engine.step() raises KeyError if session not created first."""
        engine = MEEEngine()
        with pytest.raises(KeyError, match="not found"):
            engine.step("nonexistent-agent", delta=0.1)

    def test_all_summaries_returns_list(self):
        """all_summaries() returns a list of dicts (one per session)."""
        engine = MEEEngine()
        engine.get_or_create("a1")
        engine.get_or_create("a2")
        summaries = engine.all_summaries()
        assert isinstance(summaries, list)
        assert len(summaries) == 2
        ids = {s["session_id"] for s in summaries}
        assert "a1" in ids
        assert "a2" in ids

    def test_restore_session(self):
        """restore_session(data) takes only one arg (no session_id param)."""
        engine = MEEEngine()
        sess = engine.get_or_create("restore-agent")
        for _ in range(3):
            sess.step(delta=0.1)
        state = sess.to_dict()
        g_expected = sess.g

        engine2 = MEEEngine()
        restored = engine2.restore_session(state)  # single-arg call
        assert restored.g == pytest.approx(g_expected, rel=1e-6)

    def test_multiple_agents_independent(self):
        engine = MEEEngine()
        sa = engine.get_or_create("agent-x")
        sb = engine.get_or_create("agent-y")
        sa.step(delta=0.9)
        sb.step(delta=-0.5)
        assert sa.g != sb.g


# ─── Tests: Thread safety ─────────────────────────────────────────────────────

class TestMEEThreadSafety:
    def test_concurrent_steps_do_not_corrupt(self):
        """Multiple threads stepping the same session should not raise."""
        import threading
        sess = MEESession(session_id="thread-safe")
        errors = []

        def worker():
            try:
                for _ in range(10):
                    sess.step(delta=0.01)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert sess.step_count == 50
        assert sess.g >= G_FLOOR


# ─── Tests: Edge cases ───────────────────────────────────────────────────────

class TestMEEEdgeCases:
    def test_very_large_positive_delta(self):
        sess = MEESession(session_id="big-delta")
        record = sess.step(delta=100.0)
        assert record.g_after <= G_CAP

    def test_very_large_negative_delta(self):
        sess = MEESession(session_id="big-neg")
        record = sess.step(delta=-100.0)
        assert record.g_after >= G_FLOOR

    def test_many_violations_resilience_floor(self):
        sess = MEESession(session_id="many-vio")
        for _ in range(100):
            sess.step(delta=0.0, governance_violation=True)
        assert sess.resilience >= 0.0

    def test_g_monotonically_grows_with_positive_delta_no_violations(self):
        sess = MEESession(session_id="mono")
        prev = sess.g
        for _ in range(10):
            sess.step(delta=0.1)
            assert sess.g >= prev
            prev = sess.g

    def test_g_can_shrink_despite_positive_delta_when_resilience_is_low(self):
        """
        Regression test for an overclaim caught during the 2026-09-12 audit:
        the module docstring stated unconditional "monotonic growth when
        Δ > 0 and M > 0", but G(t+1) = G(t) × (1+MΔ) × R_t multiplies by R_t
        unconditionally — a resilience factor suppressed by prior governance
        violations can still shrink G even with a positive delta. This test
        proves the counter-example the original claim missed, corrected in
        the docstring rather than silently left inaccurate.
        """
        sess = MEESession(session_id="low-resilience-counterexample")
        # Drive resilience down with repeated violations — deliberately NOT
        # enough steps to also push G down to G_FLOOR (checked empirically:
        # 8 steps suppresses resilience to ~0.84 while G stays well above
        # the 0.10 floor, so the shrinkage below isn't masked by clamping).
        for _ in range(8):
            sess.step(delta=0.0, governance_violation=True)
        low_resilience = sess.resilience
        assert low_resilience < 0.9, "setup assumption: resilience must be meaningfully suppressed"

        g_before = sess.g
        assert g_before > G_FLOOR * 2, "setup assumption: must not already be at/near the floor"
        # A small positive delta: (1 + 0.1*0.05) * low_resilience < 1 when
        # low_resilience is low enough, so G shrinks despite delta > 0.
        record = sess.step(delta=0.05)
        assert record.delta > 0
        assert record.g_after < g_before, "G shrank despite a positive delta, because R_t < 1 — the real, documented behavior"


# ─── Tests: real file persistence (save_to_file / load_from_file) ────────────

class TestMEEPersistence:
    """
    Regression tests for a real bug found in the 2026-09-12 audit: this
    module's docstring always claimed sessions were "saved to .rct.json",
    but no method anywhere ever wrote a file — to_dict()/from_dict() only
    did in-memory (de)serialization. save_to_file()/load_from_file() below
    make the documented claim actually true.
    """

    def test_save_to_file_actually_writes_a_real_file(self, tmp_path):
        path = str(tmp_path / "test.rct.json")
        sess = MEESession(session_id="persist-1")
        sess.step(0.2)
        sess.step(-0.1, governance_violation=True)

        returned_path = sess.save_to_file(path)
        assert returned_path == path
        assert os.path.exists(path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "mee_state" in data
        assert "persist-1" in data["mee_state"]
        assert data["mee_state"]["persist-1"]["g_current"] == pytest.approx(sess.g)

    def test_save_to_file_merges_rather_than_overwrites_existing_content(self, tmp_path):
        """`.rct.json` is a shared control-plane state file, not MEE-exclusive — saving must not clobber other keys already there."""
        path = str(tmp_path / "test.rct.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"some_other_control_plane_key": {"unrelated": True}}, f)

        sess = MEESession(session_id="persist-2")
        sess.step(0.1)
        sess.save_to_file(path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["some_other_control_plane_key"] == {"unrelated": True}
        assert "persist-2" in data["mee_state"]

    def test_load_from_file_round_trips_g_and_resilience(self, tmp_path):
        path = str(tmp_path / "test.rct.json")
        original = MEESession(session_id="persist-3")
        original.step(0.15)
        original.step(-0.08, governance_violation=True)
        original.save_to_file(path)

        restored = MEESession.load_from_file("persist-3", path)
        assert restored.g == pytest.approx(original.g)
        assert restored.resilience == pytest.approx(original.resilience)

    def test_load_from_file_raises_key_error_for_unknown_session(self, tmp_path):
        path = str(tmp_path / "test.rct.json")
        MEESession(session_id="known").save_to_file(path)
        with pytest.raises(KeyError):
            MEESession.load_from_file("unknown-session-id", path)

    def test_default_state_file_constant_matches_documented_filename(self):
        assert DEFAULT_STATE_FILE == ".rct.json"


class TestMEEEnginePersistence:
    def test_engine_save_and_load_session_round_trip(self, tmp_path):
        path = str(tmp_path / "test.rct.json")
        engine = MEEEngine()
        engine.create_session("agent-x")
        engine.step("agent-x", delta=0.3)
        expected_g = engine.summary("agent-x")["g_current"]

        engine.save_session("agent-x", path)

        fresh_engine = MEEEngine()
        restored = fresh_engine.load_session("agent-x", path)
        assert restored.session_id == "agent-x"
        assert fresh_engine.summary("agent-x")["g_current"] == pytest.approx(expected_g)

    def test_save_session_raises_for_unknown_session(self, tmp_path):
        path = str(tmp_path / "test.rct.json")
        engine = MEEEngine()
        with pytest.raises(KeyError):
            engine.save_session("does-not-exist", path)
