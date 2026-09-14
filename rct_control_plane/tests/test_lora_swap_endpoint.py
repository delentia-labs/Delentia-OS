"""
Regression tests for the 2026-09-14 LoRA hot-swap fix (Round 8.1 of the
architecture-gap audit).

Two real bugs found and fixed together:
1. lora_multiplexer.py's v0.5.1 adapter paths were built as
   "jitna_<role>_v0.5.1", which never existed on disk — the real shipped
   weights are plain "<role>" subdirectories under
   Delentia-AI-SLM/models/adapters/v0.5.1/. Real .safetensors weights and
   real PEFT loading code sat right next to a mock flag that could never
   turn off.
2. api.py's /v1/lora/swap endpoint hardcoded mock_mode=True unconditionally
   (regardless of #1), rejected the real "router" adapter as unsupported
   even though lora_multiplexer.py's KNOWN_ADAPTERS always included it, and
   substituted a fabricated latency number (`2.0 + time.time() % 3.5`)
   whenever the real measured latency came in under 1ms.
"""
import os

import pytest
from fastapi.testclient import TestClient

from rct_control_plane.lora_multiplexer import LoRAMultiplexer
from rct_control_plane.api import ControlPlaneAPI


REAL_ADAPTERS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "Delentia-AI-SLM", "models", "adapters", "v0.5.1"
)


def test_adapter_paths_resolve_to_the_real_plain_role_directories():
    """The core bug: paths must be '<role>', not 'jitna_<role>_v0.5.1'."""
    mux = LoRAMultiplexer()
    assert mux.executor_path.name == "executor"
    assert mux.guardian_path.name == "guardian"
    assert mux.scribe_path.name == "scribe"
    assert mux.router_path.name == "router"


@pytest.mark.skipif(not os.path.isdir(REAL_ADAPTERS_DIR), reason="real v0.5.1 adapter weights not present in this environment")
def test_real_adapter_directories_are_actually_found_on_disk():
    """With the real weights present (as they are in this workspace), the
    fixed paths must resolve to real, existing directories — not just the
    right basename, but a genuine, verified path.exists()."""
    mux = LoRAMultiplexer()
    assert mux.executor_path.exists()
    assert mux.guardian_path.exists()
    assert mux.scribe_path.exists()
    assert mux.router_path.exists()
    assert (mux.executor_path / "adapter_config.json").exists()


def test_known_adapters_includes_router():
    """router is a normal Brain Slot on this v0.5.1 multiplexer (a single
    causal-LM base with 4 PEFT adapters), not a separate unsupported
    concept — confirms the earlier "router isn't a hot-swap slot" framing
    was wrong for this file's actual design."""
    mux = LoRAMultiplexer()
    mux._validate_adapter_name("router")  # must not raise
    with pytest.raises(ValueError):
        mux._validate_adapter_name("not_a_real_adapter")


@pytest.fixture
def client():
    inst = ControlPlaneAPI()
    return TestClient(inst.app)


def test_swap_endpoint_accepts_router_slot(client, monkeypatch):
    """Previously this endpoint special-cased 'router' as unsupported and
    returned success: false. It's now a normal slot."""
    from rct_control_plane import api as api_module
    mux = api_module._get_lora_multiplexer()
    mux.mock_mode = True  # keep this test fast/deterministic, no real load

    r = client.post("/v1/lora/swap", params={"slot": "router"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["active_slot"] == "router"
    assert body["simulated"] is True


def test_swap_endpoint_rejects_unknown_slot_with_400(client):
    r = client.post("/v1/lora/swap", params={"slot": "totally_bogus_slot"})
    assert r.status_code == 400


def test_swap_endpoint_reports_real_near_zero_latency_not_a_fabricated_minimum(client):
    """Regression for the removed fabrication: the old code replaced any
    measured latency under 1ms with a fake number that was ALWAYS >= 2.0.
    A redundant swap (already-active adapter) genuinely returns ~0ms from
    swap_adapter() — the endpoint must report a real small number, never
    something >= 2.0 just because the real value was tiny."""
    from rct_control_plane import api as api_module
    mux = api_module._get_lora_multiplexer()
    mux.mock_mode = True

    first = client.post("/v1/lora/swap", params={"slot": "guardian"})
    assert first.status_code == 200

    redundant = client.post("/v1/lora/swap", params={"slot": "guardian"})
    assert redundant.status_code == 200
    body = redundant.json()
    # A real no-op re-measurement is a handful of microseconds at most —
    # nowhere near the old fabricated floor of 2.0ms.
    assert body["latency_ms"] < 1.0


def test_swap_endpoint_slot_status_reflects_real_multiplexer_state(client):
    from rct_control_plane import api as api_module
    mux = api_module._get_lora_multiplexer()
    mux.mock_mode = True
    mux.active_slots = []
    mux.current_adapter = None

    r = client.post("/v1/lora/swap", params={"slot": "scribe"})
    body = r.json()
    assert body["slot_status"]["current_adapter"] == "scribe"
    assert "scribe" in body["slot_status"]["active_slots"]
