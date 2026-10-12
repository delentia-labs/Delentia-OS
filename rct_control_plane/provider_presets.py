"""
Starting points for "plug in your own AI" (Round 52): well-known OpenAI-compatible endpoints,
grouped by the country of the company that runs them, so the Desk can offer
country -> provider -> model with an "Other" option at every step.

Read this before trusting a preset:

* These are CONVENIENCES, not facts about your contract. A base URL and model id can change;
  the Desk's "Test connection" asks the endpoint itself which models it serves, and that answer
  wins over this list.
* The company's country is NOT where your data is processed. A provider headquartered in
  Korea may serve from elsewhere, and one headquartered abroad may offer an in-country region.
  So no preset claims a processing location: `data_location` is always chosen by the operator
  (this machine / inside a named country / unknown), and a remote preset starts as "unknown"
  (cross-border, the strict reading) until the operator says otherwise. The residency policy
  trusts that declaration (see core/regional_adapter/sovereignty.py).
* Credentials are never stored here or in the model config: a preset only suggests the NAME of
  the environment variable that holds the key.

Adding a provider is one entry below. Nothing else needs to change.
"""
from __future__ import annotations

from typing import Any, Dict, List

LOCAL = "LOCAL"
GLOBAL = "XX"       # no single home country (or: "other")

COUNTRIES: Dict[str, str] = {
    LOCAL: "My own machine or network (self-hosted)",
    "TH": "Thailand", "JP": "Japan", "KR": "South Korea", "CN": "China", "SG": "Singapore", "IN": "India",
    "FR": "France / EU", "US": "United States",
}

# id, name, country, base_url, credential_env, models (examples only), docs, note
_P = [
    # ---- self-hosted: data stays on the operator's own machine or network
    dict(id="ollama-openai", name="Ollama (OpenAI-compatible mode)", country=LOCAL, base_url="http://127.0.0.1:11434/v1",
         credential_env="", models=["qwen2.5:7b", "llama3.2:3b"], docs="https://ollama.com",
         note="Runs on this machine. Needs no key. For plain Ollama, the 'Ollama' provider on the Models page works too."),
    dict(id="vllm", name="vLLM server", country=LOCAL, base_url="http://localhost:8000/v1", credential_env="VLLM_API_KEY",
         models=[], docs="https://docs.vllm.ai", note="Your own GPU server. Use the model name you started it with."),
    dict(id="llamacpp", name="llama.cpp server", country=LOCAL, base_url="http://localhost:8080/v1", credential_env="",
         models=[], docs="https://github.com/ggml-org/llama.cpp", note="Your own machine. Use the model name you loaded."),
    dict(id="lmstudio", name="LM Studio", country=LOCAL, base_url="http://localhost:1234/v1", credential_env="",
         models=[], docs="https://lmstudio.ai", note="Your own machine."),
    # ---- national / regional providers
    dict(id="typhoon", name="Typhoon (OpenTyphoon.ai)", country="TH", base_url="https://api.opentyphoon.ai/v1",
         credential_env="TYPHOON_API_KEY", models=["typhoon-v2.5-30b-a3b-instruct", "typhoon-v2.1-12b-instruct"],
         docs="https://opentyphoon.ai", note="Thai-focused models. Confirm with the provider where requests are processed before declaring it in-country."),
    dict(id="upstage", name="Upstage Solar", country="KR", base_url="https://api.upstage.ai/v1", credential_env="UPSTAGE_API_KEY",
         models=["solar-pro2", "solar-mini"], docs="https://console.upstage.ai", note="Korean company; confirm the processing location."),
    dict(id="clova", name="Naver HyperCLOVA X", country="KR", base_url="https://clovastudio.stream.ntruss.com/v1/openai",
         credential_env="CLOVASTUDIO_API_KEY", models=["HCX-005"], docs="https://api.ncloud-docs.com/docs/clovastudio-overview",
         note="OpenAI-compatible mode of CLOVA Studio. Check the current model ids in your console."),
    dict(id="deepseek", name="DeepSeek", country="CN", base_url="https://api.deepseek.com/v1", credential_env="DEEPSEEK_API_KEY",
         models=["deepseek-chat", "deepseek-reasoner"], docs="https://api-docs.deepseek.com", note="Servers are in China."),
    dict(id="moonshot", name="Moonshot (Kimi)", country="CN", base_url="https://api.moonshot.cn/v1", credential_env="MOONSHOT_API_KEY",
         models=["kimi-k2-0905-preview"], docs="https://platform.moonshot.cn/docs", note="Servers are in China."),
    dict(id="zhipu", name="Zhipu AI (GLM)", country="CN", base_url="https://open.bigmodel.cn/api/paas/v4", credential_env="ZHIPUAI_API_KEY",
         models=["glm-4.5"], docs="https://docs.bigmodel.cn", note="Servers are in China."),
    dict(id="dashscope", name="Alibaba Cloud Model Studio (Qwen)", country="CN",
         base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", credential_env="DASHSCOPE_API_KEY",
         models=["qwen-plus", "qwen-max"], docs="https://www.alibabacloud.com/help/en/model-studio",
         note="The mainland endpoint. The international endpoint has a different host; use Other for it."),
    dict(id="sealion", name="SEA-LION (AI Singapore)", country="SG", base_url="https://api.sea-lion.ai/v1", credential_env="SEALION_API_KEY",
         models=[], docs="https://sea-lion.ai", note="South-East-Asian languages. Use 'Test connection' to list the model ids."),
    dict(id="sarvam", name="Sarvam AI", country="IN", base_url="https://api.sarvam.ai/v1", credential_env="SARVAM_API_KEY",
         models=["sarvam-m"], docs="https://docs.sarvam.ai", note="Indian-language models."),
    dict(id="mistral", name="Mistral AI", country="FR", base_url="https://api.mistral.ai/v1", credential_env="MISTRAL_API_KEY",
         models=["mistral-large-latest", "mistral-small-latest"], docs="https://docs.mistral.ai", note="EU company; confirm the region you use."),
    # ---- global providers
    dict(id="openai", name="OpenAI", country="US", base_url="https://api.openai.com/v1", credential_env="OPENAI_API_KEY",
         models=["gpt-4o-mini"], docs="https://platform.openai.com/docs", note="Data is processed outside most countries unless you have a regional agreement."),
    dict(id="groq", name="Groq", country="US", base_url="https://api.groq.com/openai/v1", credential_env="GROQ_API_KEY",
         models=["llama-3.3-70b-versatile"], docs="https://console.groq.com/docs", note=""),
    dict(id="together", name="Together AI", country="US", base_url="https://api.together.xyz/v1", credential_env="TOGETHER_API_KEY",
         models=[], docs="https://docs.together.ai", note=""),
    dict(id="fireworks", name="Fireworks AI", country="US", base_url="https://api.fireworks.ai/inference/v1",
         credential_env="FIREWORKS_API_KEY", models=[], docs="https://docs.fireworks.ai", note=""),
]


def _normalise(p: Dict[str, Any]) -> Dict[str, Any]:
    local = p["country"] == LOCAL
    return {
        **p,
        # What the Desk pre-selects for "where is data processed". Local servers: this machine.
        # Anything remote: unknown (cross-border) until the operator confirms otherwise.
        "suggested_data_location": "local" if local else "cross_border",
        "needs_key": bool(p["credential_env"]),
        "company_country": None if local else p["country"],
    }


PRESETS: List[Dict[str, Any]] = [_normalise(p) for p in _P]


def catalog() -> Dict[str, Any]:
    used = {p["country"] for p in PRESETS}
    return {
        "countries": [{"code": code, "name": name} for code, name in COUNTRIES.items() if code in used],
        "providers": PRESETS,
        "notice": ("These are starting points, not statements about your contract. The company's country is not where your data "
                   "is processed, so the data location is always your declaration. 'Test connection' lists the models the "
                   "endpoint really serves."),
    }


def by_id(preset_id: str) -> Dict[str, Any]:
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    raise KeyError(preset_id)
