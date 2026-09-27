"""
Round 45 item C (group 4): real tests for swarm_hr_engine.py - 0% coverage
before this file. Confirmed genuinely used: rct_control_plane/api.py imports
SWARM_HR_ENGINE. ALGORITHM_KERNEL.process_intent_full_pipeline is mocked
(confirmed disk side effect - scaffolds files under workspace_output/genesis/
- unrelated to this module's own behavior). generate_promptpay_emvco is real
(pure, already covered by test_billing_service.py) - left unmocked here.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

import rct_control_plane.swarm_hr_engine as swarm_module
from rct_control_plane.swarm_hr_engine import SwarmHREngine, SwarmTeam, SubagentProfile


class _FakeKernel:
    def process_intent_full_pipeline(self, intent):
        return {"fdia_score": 1.0}


@pytest.fixture(autouse=True)
def patched_kernel(monkeypatch):
    monkeypatch.setattr(swarm_module, "ALGORITHM_KERNEL", _FakeKernel())


@pytest.fixture
def engine():
    return SwarmHREngine()


class TestSubagentProfile:
    def test_starts_idle(self):
        agent = SubagentProfile("a1", "Role", "executor", "prompt text", ["cap1", "cap2"])
        assert agent.status == "IDLE"

    def test_to_dict_shape(self):
        agent = SubagentProfile("a1", "Role", "executor", "prompt text", ["cap1"])
        d = agent.to_dict()
        assert d == {
            "agent_id": "a1", "role_title": "Role", "lora_slot": "executor",
            "system_prompt": "prompt text", "capabilities": ["cap1"], "status": "IDLE",
        }


class TestSwarmTeam:
    def test_indexes_subagents_by_id(self):
        agents = [SubagentProfile("a1", "R1", "router", "p", []), SubagentProfile("a2", "R2", "scribe", "p", [])]
        team = SwarmTeam("t1", "Team One", "objective", agents)
        assert set(team.subagents.keys()) == {"a1", "a2"}

    def test_to_dict_includes_all_subagents_and_starts_with_empty_history(self):
        agents = [SubagentProfile("a1", "R1", "router", "p", [])]
        team = SwarmTeam("t1", "Team One", "objective", agents)
        d = team.to_dict()
        assert len(d["subagents"]) == 1
        assert d["execution_history"] == []
        assert d["pending_approvals"] == []


class TestGoldenSmeTemplates:
    def test_all_three_templates_exist(self, engine):
        assert set(engine.templates.keys()) == {"ECOMMERCE_SOLO", "LEGAL_TAX_SME", "CREATOR_MODDER"}

    def test_ecommerce_template_has_three_subagents(self, engine):
        assert len(engine.templates["ECOMMERCE_SOLO"].subagents) == 3

    def test_legal_tax_template_has_three_subagents(self, engine):
        assert len(engine.templates["LEGAL_TAX_SME"].subagents) == 3

    def test_creator_modder_template_has_three_subagents(self, engine):
        assert len(engine.templates["CREATOR_MODDER"].subagents) == 3


class TestProvisionTeamFromBrief:
    def test_ecommerce_keywords_select_the_ecommerce_template(self, engine):
        team = engine.provision_team_from_brief("ช่วยตอบแชทลูกค้าร้านขายเสื้อผ้า")
        assert set(team.subagents.keys()) == set(engine.templates["ECOMMERCE_SOLO"].subagents.keys())

    def test_legal_keywords_select_the_legal_tax_template(self, engine):
        team = engine.provision_team_from_brief("ช่วยตรวจสัญญาและคำนวณภาษี")
        assert set(team.subagents.keys()) == set(engine.templates["LEGAL_TAX_SME"].subagents.keys())

    def test_unmatched_brief_falls_back_to_creator_modder_template(self, engine):
        team = engine.provision_team_from_brief("อยากทำคอนเทนต์เกม Stardew Valley")
        assert set(team.subagents.keys()) == set(engine.templates["CREATOR_MODDER"].subagents.keys())

    def test_ecommerce_keywords_take_priority_over_legal_when_both_present(self, engine):
        # "ร้าน" (ecommerce) checked before the legal branch in the source.
        team = engine.provision_team_from_brief("ร้านขายของกับเรื่องภาษี")
        assert set(team.subagents.keys()) == set(engine.templates["ECOMMERCE_SOLO"].subagents.keys())

    def test_provisioned_team_is_stored_and_retrievable(self, engine):
        team = engine.provision_team_from_brief("ร้านขายของออนไลน์")
        assert engine.teams[team.team_id] is team

    def test_team_ids_are_unique_across_calls(self, engine):
        team1 = engine.provision_team_from_brief("ร้านขายของ")
        team2 = engine.provision_team_from_brief("ร้านขายของ")
        assert team1.team_id != team2.team_id

    def test_objective_is_set_to_the_real_brief_text(self, engine):
        team = engine.provision_team_from_brief("ร้านขายของออนไลน์")
        assert team.objective == "ร้านขายของออนไลน์"


class TestFindTeam:
    def test_finds_a_provisioned_team_by_its_real_id(self, engine):
        team = engine.provision_team_from_brief("ร้านขายของ")
        assert engine._find_team(team.team_id) is team

    def test_finds_a_golden_template_by_its_dict_key(self, engine):
        assert engine._find_team("ECOMMERCE_SOLO") is engine.templates["ECOMMERCE_SOLO"]

    def test_finds_a_golden_template_by_its_own_team_id_attribute(self, engine):
        assert engine._find_team("tpl_legal_tax_sme") is engine.templates["LEGAL_TAX_SME"]

    def test_unknown_id_returns_none(self, engine):
        assert engine._find_team("no-such-team") is None


class TestExecuteSwarmPipeline:
    def test_unknown_team_raises(self, engine):
        with pytest.raises(ValueError, match="not found"):
            engine.execute_swarm_pipeline("no-such-team", "do something")

    def test_runs_against_a_golden_template_and_returns_success(self, engine):
        result = engine.execute_swarm_pipeline("ECOMMERCE_SOLO", "สรุปยอดขายวันนี้")
        assert result["status"] == "SUCCESS"
        assert result["fdia_score"] == 1.0
        assert len(result["outputs"]) == 3

    def test_billing_agent_output_includes_a_real_qr_payload(self, engine):
        result = engine.execute_swarm_pipeline("ECOMMERCE_SOLO", "ออกบิล")
        billing_output = result["outputs"]["bot_sales_accounting"]
        assert "qr_payload" in billing_output
        assert billing_output["qr_payload"].startswith("00020101")  # real EMVCo payload prefix

    def test_chat_and_content_agents_do_not_include_qr_payload(self, engine):
        result = engine.execute_swarm_pipeline("ECOMMERCE_SOLO", "ตอบแชท")
        assert "qr_payload" not in result["outputs"]["bot_chat_support"]
        assert "qr_payload" not in result["outputs"]["bot_caption_writer"]

    def test_all_agents_return_to_idle_after_execution(self, engine):
        team = engine.templates["ECOMMERCE_SOLO"]
        engine.execute_swarm_pipeline("ECOMMERCE_SOLO", "x")
        assert all(a.status == "IDLE" for a in team.subagents.values())

    def test_creates_a_pending_approval_item(self, engine):
        result = engine.execute_swarm_pipeline("ECOMMERCE_SOLO", "x")
        team = engine.templates["ECOMMERCE_SOLO"]
        assert len(team.pending_approvals) == 1
        assert team.pending_approvals[0]["status"] == "PENDING_APPROVAL"
        assert result["pending_approval"]["approval_id"] == team.pending_approvals[0]["approval_id"]

    def test_appends_to_execution_history(self, engine):
        team = engine.templates["LEGAL_TAX_SME"]
        engine.execute_swarm_pipeline("LEGAL_TAX_SME", "task one")
        engine.execute_swarm_pipeline("LEGAL_TAX_SME", "task two")
        assert len(team.execution_history) == 2
        assert team.execution_history[0]["task_input"] == "task one"


class TestApprovePendingAction:
    def test_unknown_team_raises(self, engine):
        with pytest.raises(ValueError, match="not found"):
            engine.approve_pending_action("no-such-team", "APP-1")

    def test_unknown_approval_id_returns_not_found(self, engine):
        engine.execute_swarm_pipeline("CREATOR_MODDER", "x")
        result = engine.approve_pending_action("CREATOR_MODDER", "no-such-approval")
        assert result == {"status": "NOT_FOUND"}

    def test_real_approval_id_is_approved_and_sealed(self, engine):
        exec_result = engine.execute_swarm_pipeline("CREATOR_MODDER", "x")
        approval_id = exec_result["pending_approval"]["approval_id"]

        result = engine.approve_pending_action("CREATOR_MODDER", approval_id)
        assert result["status"] == "APPROVED"
        assert result["a_invariant"] == 1.0
        assert result["signedai_seal"] == exec_result["pending_approval"]["signedai_seal"]

        team = engine.templates["CREATOR_MODDER"]
        stored_item = next(i for i in team.pending_approvals if i["approval_id"] == approval_id)
        assert stored_item["status"] == "APPROVED (A = 1.0)"
        assert "approved_at" in stored_item
