"""
Round 52: data sovereignty for the Regional Adapter and the runtime.

The idea: any country can plug in its own AI and the data stays inside it. Real code
throughout: the national-ID checksums, the policy decisions, the router, the provider
guard (with a real local HTTP server standing in for a national model endpoint), the
audit trail, the CLI. The only stand-ins are fake model classes that record what they
were sent, because the point is to prove what was NOT sent.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from click.testing import CliRunner

from core.regional_adapter import regional_adapter as ra
from core.regional_adapter import sovereignty as sv
from rct_control_plane import model_config, residency
from rct_control_plane.cli import cli
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.llm_provider import (
    LLMProvider, OllamaProvider, OpenAICompatibleProvider, OpenRouterProvider, ResidencyViolation,
)
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary


# ------------------------------------------------------------ valid national numbers
def thai_id(first12: str) -> str:
    total = sum(int(first12[i]) * (13 - i) for i in range(12))
    return first12 + str((11 - total % 11) % 10)


def jp_my_number(first11: str) -> str:
    total = 0
    for n in range(1, 12):
        p = int(first11[11 - n])
        total += p * (n + 1 if n <= 6 else n - 5)
    r = total % 11
    return first11 + str(0 if r <= 1 else 11 - r)


def cn_id(first17: str) -> str:
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    return first17 + "10X98765432"[sum(int(first17[i]) * weights[i] for i in range(17)) % 11]


def kr_rrn(first12: str) -> str:
    weights = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)
    return first12 + str((11 - sum(int(first12[i]) * weights[i] for i in range(12)) % 11) % 10)


THAI = thai_id("110170203451")
JP = jp_my_number("12345678901")
CN = cn_id("11010519491231002")
KR = kr_rrn("900101123456")
CARD = "4111111111111111"


class TestPersonalDataScanner:
    scanner = sv.PIIScanner()

    @pytest.mark.parametrize("text, kind", [
        (f"รหัสบัตรประชาชน {THAI}", "th_national_id"),
        (f"id {THAI[0]}-{THAI[1:5]}-{THAI[5:10]}-{THAI[10:12]}-{THAI[12]}", "th_national_id"),
        (f"My Number {JP}", "jp_my_number"),
        (f"resident id {CN}", "cn_resident_id"),
        (f"rrn {KR[:6]}-{KR[6:]}", "kr_resident_registration_number"),
        (f"card {CARD[:4]} {CARD[4:8]} {CARD[8:12]} {CARD[12:]}", "payment_card"),
        ("write to somchai.j@example.co.th please", "email_address"),
        ("call +66 81 234 5678 tomorrow", "phone_number"),
        ("โทร 0812345678 ด่วน", "th_mobile_number"),
    ])
    def test_each_kind_is_found(self, text, kind):
        assert kind in {f.kind for f in self.scanner.scan(text)}

    @pytest.mark.parametrize("text", [
        "order 1234567890123 shipped",            # 13 digits, wrong Thai checksum
        "tracking 4111111111111112 failed",       # 16 digits, fails Luhn
        "version 2.5.1 build 20260930",
        "total 1,234,567 baht",
        "no personal data in this sentence at all",
        "user@ example",                           # not an address
    ])
    def test_ordinary_numbers_and_text_are_not_flagged(self, text):
        assert self.scanner.scan(text) == []

    def test_redaction_removes_the_values_and_names_the_kind(self):
        text = f"Customer {THAI} paid with {CARD} and wrote from a@b.org"
        redacted, findings = self.scanner.redact(text)
        for secret in (THAI, CARD, "a@b.org"):
            assert secret not in redacted
        assert "[REDACTED:th_national_id]" in redacted and "[REDACTED:payment_card]" in redacted and "[REDACTED:email_address]" in redacted
        assert redacted.startswith("Customer ") and len(findings) == 3

    def test_the_summary_keeps_counts_only(self):
        s = sv.pii_summary(self.scanner.scan(f"{THAI} {THAI} {CARD}"))
        assert s == {"th_national_id": 2, "payment_card": 1}

    def test_hostile_input_is_scanned_in_linear_time(self):
        nasty = "0" * 300000 + "@" + "a." * 100000 + " " + "1-" * 100000
        started = time.perf_counter()
        self.scanner.scan(nasty)
        assert time.perf_counter() - started < 3.0


class TestPolicyDecisions:
    TH = sv.SovereigntyPolicy(home_region="TH")
    LOCAL = sv.HostingProfile(sv.KIND_LOCAL, "LOCAL", "my server")
    IN_TH = sv.HostingProfile(sv.KIND_IN_REGION, "TH", "a Thai provider")
    US = sv.HostingProfile(sv.KIND_CROSS_BORDER, "US", "a US provider")
    CLOUD = sv.HostingProfile(sv.KIND_CROSS_BORDER, sv.GLOBAL, "OpenRouter")

    def test_local_and_in_country_endpoints_are_allowed_with_personal_data(self):
        text = f"id {THAI}"
        assert sv.evaluate_call(self.TH, self.LOCAL, text).action == "allow"
        d = sv.evaluate_call(self.TH, self.IN_TH, text)
        assert d.action == "allow" and not d.cross_border

    def test_a_cross_border_endpoint_is_blocked_unless_the_policy_allows_it(self):
        for hosting in (self.US, self.CLOUD):
            d = sv.evaluate_call(self.TH, hosting, "hello")
            assert d.action == "block" and d.cross_border and "no cross-border" in d.reason

    def test_an_unpinned_global_endpoint_is_never_inside_an_allowed_region(self):
        policy = sv.SovereigntyPolicy(home_region="TH", allowed_regions=["TH", "SG"])
        assert not sv.hosting_is_allowed(policy, self.CLOUD)
        assert sv.hosting_is_allowed(policy, sv.HostingProfile(sv.KIND_IN_REGION, "SG", "x"))

    @pytest.mark.parametrize("pii_policy, action", [("block", "block"), ("redact", "redact"), ("allow", "allow")])
    def test_personal_data_in_an_allowed_cross_border_call_follows_the_pii_policy(self, pii_policy, action):
        policy = sv.SovereigntyPolicy(home_region="TH", allow_cross_border=True, pii_policy=pii_policy)
        d = sv.evaluate_call(policy, self.US, f"id {THAI}")
        assert d.action == action and d.pii == {"th_national_id": 1}

    def test_a_cross_border_call_without_personal_data_passes_when_allowed(self):
        policy = sv.SovereigntyPolicy(home_region="TH", allow_cross_border=True)
        d = sv.evaluate_call(policy, self.US, "what is the capital of France")
        assert d.action == "allow" and d.cross_border and d.pii == {}

    def test_bad_input_is_refused(self):
        with pytest.raises(ValueError):
            sv.SovereigntyPolicy(home_region="TH", pii_policy="maybe")
        with pytest.raises(ValueError):
            sv.validate_region("THA")

    def test_a_policy_survives_a_round_trip(self):
        policy = sv.SovereigntyPolicy(home_region="jp", allowed_regions=["jp", "sg"], allow_cross_border=True,
                                      pii_policy="redact", legal_basis="APPI art.28", tenant_id="t")
        assert sv.SovereigntyPolicy.from_dict(policy.to_dict()).to_dict() == policy.to_dict()


class TestRegionalRouterEnforcesThePolicy:
    def _router(self):
        return ra.RegionalModelRouter()

    def test_without_a_policy_the_old_behaviour_is_unchanged(self):
        assert self._router().resolve("th", "TH").model_id == "scb10x/typhoon-v2-70b-instruct"

    def test_every_default_entry_says_it_is_cross_border(self):
        assert all(e.hosting_kind == sv.KIND_CROSS_BORDER and e.hosting_region == sv.GLOBAL for e in ra._REGIONAL_MODELS)

    def test_the_default_table_has_no_model_a_closed_border_tenant_may_use(self):
        with pytest.raises(ra.RegionalPolicyViolation) as err:
            self._router().resolve("th", "TH", policy=sv.SovereigntyPolicy(home_region="TH"))
        assert "register_regional_llm" in str(err.value)

    def test_a_country_plugs_in_its_own_ai_and_it_is_chosen(self):
        router = self._router()
        router.add_model(ra.RegionalModelEntry(
            language="th", region="TH", model_id="typhoon-local", model_name="Typhoon (our server)", proficiency=0.9,
            cost_input=0.0, cost_output=0.0, hosting_kind=sv.KIND_IN_REGION, hosting_region="TH", operator="our datacentre",
            base_url="https://llm.example.th/v1", on_openrouter=False))
        chosen = router.resolve("th", "TH", policy=sv.SovereigntyPolicy(home_region="TH"))
        assert chosen.model_id == "typhoon-local" and chosen.hosting.region == "TH"

    def test_fallback_never_leaves_the_policy(self):
        router = self._router()
        router.add_model(ra.RegionalModelEntry(language="en", region="TH", model_id="english-local", model_name="e", proficiency=0.5,
                                               cost_input=0.0, cost_output=0.0, hosting_kind=sv.KIND_LOCAL, hosting_region="TH"))
        policy = sv.SovereigntyPolicy(home_region="TH")
        assert router.resolve("ja", "JP", policy=policy).model_id == "english-local"          # fell back to the local English model
        with pytest.raises(ra.RegionalPolicyViolation):
            self._router().resolve("ja", "JP", policy=policy)                                  # the cloud English model is not allowed

    def test_a_tenant_that_allows_cross_border_may_use_the_cloud_table(self):
        policy = sv.SovereigntyPolicy(home_region="JP", allow_cross_border=True)
        assert self._router().resolve("ja", "JP", policy=policy).language == "ja"

    def test_tenants_carry_a_policy_that_defaults_to_closed(self):
        policy = ra.PILOT_TENANTS["jp_techcorp"].sovereignty_policy()
        assert policy.home_region == "JP" and policy.allowed_regions == ["JP"] and not policy.allow_cross_border

    def test_resolve_for_tenant_enforces_it(self):
        with pytest.raises(ra.RegionalPolicyViolation):
            ra.resolve_for_tenant("こんにちは、今日の予定を教えてください", "jp_techcorp")
        with pytest.raises(KeyError):
            ra.resolve_for_tenant("hello", "nobody")

    def test_register_regional_llm_declares_where_the_model_runs(self):
        before = ra.get_regional_router().get_metrics()["total_models"]
        try:
            ra.register_regional_llm("id", "ID", "garuda-local", "Garuda", 0.9, 0.0, 0.0, hosting_kind="in_region",
                                     hosting_region="id", base_url="http://10.0.0.5:8000/v1", api_key_env="GARUDA_TOKEN")
            entry = [e for e in ra.get_regional_router().get_models_for_language("id") if e.model_id == "garuda-local"][0]
            assert entry.hosting_region == "ID" and not entry.on_openrouter and entry.api_key_env == "GARUDA_TOKEN"
            with pytest.raises(ValueError):
                ra.register_regional_llm("id", "ID", "x", "x", 0.5, 0, 0, hosting_kind="in_region")        # no region
            with pytest.raises(ValueError):
                ra.register_regional_llm("id", "ID", "x", "x", 0.5, 0, 0, hosting_kind="orbital")
        finally:
            router = ra.get_regional_router()
            router._models = [e for e in router._models if e.model_id != "garuda-local"]
            router._lang_index["id"] = [e for e in router._lang_index["id"] if e.model_id != "garuda-local"]
            router._index.pop(("id", "ID"), None)
            for e in router._models:
                router._index[(e.language, e.region)] = e
            router._cache.clear()
            assert router.get_metrics()["total_models"] == before

    def test_the_default_model_ids_exist_where_they_claim_to(self):
        """Four of the seven distinct ids in the earlier table were not in OpenRouter's catalog
        (qwen was `alibaba/qwen-2.5-*`, a Sonnet that no longer exists). A model that is not on
        OpenRouter must say so instead of looking routable."""
        for e in ra._REGIONAL_MODELS:
            assert not e.model_id.startswith("alibaba/") and "claude-3.5" not in e.model_id
        typhoon = [e for e in ra._REGIONAL_MODELS if "typhoon" in e.model_id][0]
        assert typhoon.on_openrouter is False


# ------------------------------------------------------------------ the runtime guard
class RecordingProvider(LLMProvider):
    """Records what it is sent. Used as the 'inside' of the guard."""
    def __init__(self):
        self.sent = []
        self.model = "recorder"

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.sent.append((prompt, system_prompt))
        return "ok"


class FakeOpenRouter(OpenRouterProvider):
    def __init__(self):
        super().__init__(api_key="not-a-real-key", model="vendor/model")
        self.sent = []

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.sent.append(prompt)
        return json.dumps({"action": "finish", "reasoning": "r", "final_answer": "done"})


class FakeLocalOllama(OllamaProvider):
    def __init__(self):
        super().__init__(llm_url="http://127.0.0.1:11434", model="local-model")
        self.sent = []

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048, json_mode=False):
        self.sent.append(prompt)
        return json.dumps({"action": "finish", "reasoning": "r", "final_answer": "answered locally"})


class TestHostingOfProviders:
    def test_each_provider_kind_is_described_honestly(self, monkeypatch):
        monkeypatch.delenv(residency.LLM_REGION_ENV, raising=False)
        assert residency.hosting_for_provider(OllamaProvider()).kind == "local"
        assert residency.hosting_for_provider(OllamaProvider(llm_url="http://192.168.1.20:11434")).kind == "local"
        remote = residency.hosting_for_provider(OllamaProvider(llm_url="https://gpu.example.com:11434"))
        assert remote.kind == "cross_border" and remote.region == "GLOBAL"
        monkeypatch.setenv(residency.LLM_REGION_ENV, "th")
        assert residency.hosting_for_provider(OllamaProvider(llm_url="https://gpu.example.com:11434")).region == "TH"
        assert residency.hosting_for_provider(FakeOpenRouter()).region == "GLOBAL"
        national = OpenAICompatibleProvider("https://llm.example.th/v1", "m", kind="in_region", region="th", operator="Thai host")
        assert residency.hosting_for_provider(national).region == "TH"
        assert residency.hosting_for_provider(RecordingProvider()).kind == "cross_border"     # unknown = cross-border

    def test_wrappers_are_unwrapped(self):
        from rct_control_plane.llm_provider import MeteredProvider
        assert residency.hosting_for_provider(MeteredProvider(FakeLocalOllama())).kind == "local"


@pytest.fixture
def audit(tmp_path):
    return ControlPlanePersistence(db_path=str(tmp_path / "res.db"))


class TestResidencyCheckedProvider:
    def _guard(self, inner, audit, **policy):
        return residency.ResidencyCheckedProvider(inner, sv.SovereigntyPolicy(**{"home_region": "TH", **policy}), audit, "ns")

    def test_a_blocked_call_is_never_sent_and_the_audit_row_holds_no_personal_data(self, audit):
        inner = FakeOpenRouter()
        guard = self._guard(inner, audit)
        with pytest.raises(ResidencyViolation):
            asyncio.run(guard.complete(f"customer {THAI} asked about {CARD}"))
        assert inner.sent == [] and guard.blocked == 1
        rows = [r for r in audit.recent_audit(20) if r["entity_type"] == "residency_decision"]
        assert len(rows) == 1 and rows[0]["action"] == "block"
        stored = json.dumps(rows[0])
        assert THAI not in stored and CARD not in stored and "text_sha256" in stored

    def test_a_local_model_gets_the_text_untouched(self, audit):
        inner = FakeLocalOllama()
        guard = self._guard(inner, audit)
        text = f"customer {THAI}"
        assert asyncio.run(guard.complete(text))
        assert inner.sent == [text] and guard.blocked == 0 and guard.cross_border_calls == 0

    def test_redaction_replaces_personal_data_before_a_permitted_cross_border_call(self, audit):
        inner = RecordingProvider()
        guard = self._guard(inner, audit, allow_cross_border=True, pii_policy="redact")
        asyncio.run(guard.complete(f"summarise the file of {THAI}", system_prompt=f"you are helping {CARD}"))
        prompt, system = inner.sent[0]
        assert THAI not in prompt and CARD not in system and "[REDACTED:th_national_id]" in prompt
        assert guard.redacted_calls == 1 and guard.cross_border_calls == 1

    def test_usage_and_model_pass_through_so_budgets_keep_working(self, audit):
        inner = RecordingProvider()
        guard = self._guard(inner, audit, allow_cross_border=True)
        from rct_control_plane.llm_provider import LLMUsage
        guard.last_usage = LLMUsage(3, 4, None)
        assert inner.last_usage.prompt_tokens == 3 and guard.model == "recorder"

    def test_no_policy_means_the_provider_is_returned_unchanged(self, monkeypatch, tmp_path):
        monkeypatch.delenv(residency.HOME_REGION_ENV, raising=False)
        monkeypatch.setenv(residency.CONFIG_ENV, str(tmp_path / "none.json"))
        inner = FakeOpenRouter()
        assert residency.guard_provider(inner) is inner


class TestPolicyConfiguration:
    def test_environment_turns_enforcement_on(self, monkeypatch, tmp_path):
        monkeypatch.setenv(residency.CONFIG_ENV, str(tmp_path / "none.json"))
        monkeypatch.setenv(residency.HOME_REGION_ENV, "th")
        monkeypatch.setenv(residency.ALLOWED_REGIONS_ENV, "SG, JP")
        monkeypatch.setenv(residency.PII_POLICY_ENV, "redact")
        policy = residency.load_policy()
        assert policy.home_region == "TH" and policy.allowed_regions == ["SG", "JP"] and policy.pii_policy == "redact"
        assert policy.allow_cross_border is False

    def test_a_policy_file_round_trips_and_a_broken_one_does_not_silently_disable_enforcement(self, monkeypatch, tmp_path):
        monkeypatch.delenv(residency.HOME_REGION_ENV, raising=False)
        path = tmp_path / "sovereignty.json"
        monkeypatch.setenv(residency.CONFIG_ENV, str(path))
        assert residency.load_policy() is None
        residency.save_policy(sv.SovereigntyPolicy(home_region="KR", legal_basis="PIPA"))
        assert residency.load_policy().legal_basis == "PIPA"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError):
            residency.load_policy()

    def test_describe_warns_when_nothing_is_configured_and_says_what_would_be_blocked_when_it_is(self, monkeypatch, tmp_path):
        monkeypatch.delenv(residency.HOME_REGION_ENV, raising=False)
        monkeypatch.setenv(residency.CONFIG_ENV, str(tmp_path / "none.json"))
        none = residency.describe(FakeOpenRouter())
        assert none["enforced"] is False and "leaving this machine" in none["warning"]
        monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
        closed = residency.describe(FakeOpenRouter())
        assert closed["enforced"] and closed["would_be_allowed"] is False
        assert residency.describe(FakeLocalOllama())["would_be_allowed"] is True


# ------------------------------------------------------------------ in the agent loop
def _loop(tmp_path, provider):
    from rct_control_plane.algorithm_kernel_41 import AlgorithmKernel41
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "loop.db"))
    return GovernedAutonomousLoop(
        mcp_server=type("M", (), {"list_tools": staticmethod(lambda: asyncio.sleep(0, result=[]))})(),
        persistence=persistence, kernel=AlgorithmKernel41(), skill_library=SkillLibrary(db_path=str(tmp_path / "s.db")),
        max_iterations=3, namespace="sov", llm_provider=provider, route=False, compress_tool_outputs=False)


class TestInTheAgentLoop:
    GOAL = "Tell me the capital of France"

    def test_a_closed_border_policy_stops_the_episode_before_any_call_to_a_cloud_model(self, tmp_path, monkeypatch):
        monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
        provider = FakeOpenRouter()
        loop = _loop(tmp_path, provider)
        result = asyncio.run(loop.run(self.GOAL))
        assert result["stopped_reason"] == "residency_blocked" and provider.sent == []
        assert "residency_blocked" in result["steps"][-1]["tool_result"]
        assert result["residency"]["blocked"] == 1 and result["growth"]["delta"] == 0.0
        assert any(r["entity_type"] == "residency_decision" and r["action"] == "block" for r in loop._persistence.recent_audit(50))

    def test_the_same_goal_runs_when_the_model_is_local(self, tmp_path, monkeypatch):
        monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
        provider = FakeLocalOllama()
        result = asyncio.run(_loop(tmp_path, provider).run(self.GOAL))
        assert result["stopped_reason"] == "llm_finished" and result["final_answer"] == "answered locally"
        assert provider.sent and result["residency"]["cross_border_calls"] == 0

    def test_an_explicit_cross_border_policy_lets_the_cloud_model_answer(self, tmp_path, monkeypatch):
        monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
        monkeypatch.setenv(residency.ALLOW_CROSS_BORDER_ENV, "1")
        provider = FakeOpenRouter()
        result = asyncio.run(_loop(tmp_path, provider).run(self.GOAL))
        assert result["stopped_reason"] == "llm_finished" and result["residency"]["cross_border_calls"] >= 1

    def test_personal_data_in_the_goal_is_stopped_even_with_cross_border_allowed(self, tmp_path, monkeypatch):
        monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
        monkeypatch.setenv(residency.ALLOW_CROSS_BORDER_ENV, "1")      # pii policy defaults to block
        provider = FakeOpenRouter()
        result = asyncio.run(_loop(tmp_path, provider).run(f"Look up the customer with national id {THAI}"))
        assert result["stopped_reason"] == "residency_blocked" and provider.sent == []

    def test_without_a_policy_nothing_changes(self, tmp_path, monkeypatch):
        monkeypatch.delenv(residency.HOME_REGION_ENV, raising=False)
        monkeypatch.setenv(residency.CONFIG_ENV, str(tmp_path / "none.json"))
        provider = FakeOpenRouter()
        result = asyncio.run(_loop(tmp_path, provider).run(self.GOAL))
        assert result["stopped_reason"] == "llm_finished" and "residency" not in result


# ------------------------------------------------------ plug in your own national AI
class _NationalModel(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _NationalModel.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        answer = json.dumps({"action": "finish", "reasoning": "r", "final_answer": "ตอบจากโมเดลในประเทศ"})
        payload = json.dumps({"choices": [{"message": {"content": answer}}], "usage": {"prompt_tokens": 11, "completion_tokens": 7}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def national_endpoint():
    server = HTTPServer(("127.0.0.1", 0), _NationalModel)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _NationalModel.seen.clear()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


class TestPlugInYourOwnAI:
    def test_the_provider_speaks_the_openai_protocol_and_reads_its_key_from_the_named_variable(self, national_endpoint, monkeypatch):
        monkeypatch.setenv("NATIONAL_AI_TOKEN", "secret-from-env")
        provider = OpenAICompatibleProvider(national_endpoint, "typhoon-v2", credential_env="NATIONAL_AI_TOKEN", kind="in_region", region="TH")
        answer = asyncio.run(provider.complete("สวัสดี", system_prompt="be brief", json_mode=True))
        call = _NationalModel.seen[0]
        assert call["path"] == "/v1/chat/completions" and call["auth"] == "Bearer secret-from-env"
        assert call["body"]["model"] == "typhoon-v2" and call["body"]["response_format"] == {"type": "json_object"}
        assert json.loads(answer)["final_answer"] == "ตอบจากโมเดลในประเทศ"
        assert provider.last_usage.prompt_tokens == 11 and provider.last_usage.cost_usd is None

    def test_a_governed_episode_runs_end_to_end_on_the_national_model_under_a_closed_policy(self, national_endpoint, tmp_path, monkeypatch):
        monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
        provider = OpenAICompatibleProvider(national_endpoint, "typhoon-v2", kind="in_region", region="TH", operator="Thai host")
        result = asyncio.run(_loop(tmp_path, provider).run("สรุปนโยบายคุ้มครองข้อมูลส่วนบุคคลให้หน่อย"))
        assert result["stopped_reason"] == "llm_finished" and "ในประเทศ" in result["final_answer"]
        assert len(_NationalModel.seen) >= 1 and result["residency"]["blocked"] == 0

    def test_declared_in_another_country_the_same_endpoint_is_blocked(self, national_endpoint, tmp_path, monkeypatch):
        monkeypatch.setenv(residency.HOME_REGION_ENV, "TH")
        provider = OpenAICompatibleProvider(national_endpoint, "m", kind="in_region", region="US")
        result = asyncio.run(_loop(tmp_path, provider).run("hello"))
        assert result["stopped_reason"] == "residency_blocked" and _NationalModel.seen == []


class TestModelConfigForOwnEndpoints:
    def test_a_pasted_key_is_refused_as_the_credential_name(self):
        with pytest.raises(model_config.ModelConfigError):
            model_config.validate_endpoint({"base_url": "http://x/v1", "kind": "local", "credential_env": "sk-or-v1-abcdef"})
        with pytest.raises(model_config.ModelConfigError):
            model_config.validate_endpoint({"base_url": "ftp://x", "kind": "local"})
        with pytest.raises(model_config.ModelConfigError):
            model_config.validate_endpoint({"base_url": "http://x/v1", "kind": "in_region"})            # no region
        ok = model_config.validate_endpoint({"base_url": "http://x/v1/", "kind": "in_region", "region": "th", "credential_env": "TYPHOON_TOKEN"})
        assert ok["base_url"] == "http://x/v1" and ok["region"] == "TH"

    def test_selection_is_saved_and_the_default_provider_is_built_from_it(self, tmp_path, monkeypatch):
        cfg = tmp_path / "model.json"
        monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(cfg))
        monkeypatch.delenv("DELENTIA_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("DELENTIA_LLM_MODEL", raising=False)
        model_config.save_model_selection("openai-compat", "typhoon-v2", endpoint={
            "base_url": "https://llm.example.th/v1", "kind": "in_region", "region": "TH", "operator": "Thai host", "credential_env": "TYPHOON_TOKEN"})
        from rct_control_plane.llm_provider import get_default_provider
        provider = get_default_provider()
        assert isinstance(provider, OpenAICompatibleProvider) and provider.model == "typhoon-v2" and provider.region == "TH"
        assert "TYPHOON_TOKEN" in cfg.read_text(encoding="utf-8") and "sk-" not in cfg.read_text(encoding="utf-8")

    def test_openai_compat_without_an_endpoint_is_refused(self, tmp_path):
        with pytest.raises(model_config.ModelConfigError):
            model_config.save_model_selection("openai-compat", "m", path=tmp_path / "m.json")


class TestSovereigntyCLI:
    def test_set_show_check_and_model_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv(residency.CONFIG_ENV, str(tmp_path / "sov.json"))
        monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(tmp_path / "model.json"))
        monkeypatch.delenv(residency.HOME_REGION_ENV, raising=False)
        monkeypatch.delenv("DELENTIA_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("DELENTIA_LLM_MODEL", raising=False)
        run = CliRunner().invoke
        assert "No policy is set" in run(cli, ["sovereignty", "check", "hello"]).output
        out = run(cli, ["sovereignty", "set", "--region", "TH", "--pii", "redact", "--legal-basis", "PDPA s.28"]).output
        assert "Enforcement is on" in out and "no call may leave" in out
        shown = run(cli, ["sovereignty", "show"]).output
        assert "home=TH" in shown and "pii=redact" in shown and "PDPA s.28" in shown
        saved = run(cli, ["model", "set", "typhoon-v2", "--provider", "openai-compat", "--base-url", "http://10.0.0.5:8000/v1",
                          "--kind", "in_region", "--region", "TH", "--credential-env", "TYPHOON_TOKEN"])
        assert saved.exit_code == 0 and "in_region TH" in saved.output
        assert "ALLOWED" in run(cli, ["sovereignty", "show"]).output
        refused = run(cli, ["model", "set", "x", "--provider", "openai-compat", "--base-url", "http://h/v1", "--kind", "local",
                            "--credential-env", "sk-live-abc"])
        assert refused.exit_code == 1 and "NAME of an environment variable" in refused.output + (refused.stderr or "")
        checked = run(cli, ["sovereignty", "check", f"customer {THAI}"]).output
        assert "th_national_id" in checked and "ALLOW" in checked          # the national model is in-country
