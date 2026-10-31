"""
Round 73: `delentia setup` - the first ten minutes of a new person, in one guided command (Hermes: `hermes setup`).

Until now a new person had to know about a dozen separate things (a model, an audit key, an approver key, the owner's policy, recall by meaning, the host check). This looks at the machine, says what it
found, proposes the steps, and does them only when asked. It writes ONLY under the Delentia home folder (default ~/.delentia), never into the repository, never a key into a place the agent can read:

  * model: keeps the model already chosen; otherwise takes the best local Ollama model that is installed (PREFERRED_LOCAL_MODELS), else OpenRouter when OPENROUTER_API_KEY is set, else nothing and says so;
  * audit signing key: created once under <home>/keys when missing (`delentia audit-chain keygen` does the same);
  * approver key: NOT created by default. The key that approves risky actions belongs on ANOTHER device (a signature from a key the agent can read proves nothing). `--approver-key-here` creates one on this machine for a
    single-person trial and says plainly that it is only a trial;
  * recall by meaning: reports which embedding model `auto` will use, changes nothing;
  * ends with `host-check --local` style findings and the exact commands that are still left.
It is idempotent: a second run changes nothing that already exists. `--dry-run` shows the plan and writes nothing.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Local models in the order they are preferred as the agent's brain. Measured on this runtime's own probe (scripts/real_model_tool_probe.py, five simple goals, one run each, CPU only):
# qwen3:8b 4/5 (the right tool every time; one episode ran out of its time, 90-443 s per goal), qwen2.5:7b 3/5 (70-190 s per goal). A difference of one goal is noise; the larger model is also much slower.
PREFERRED_LOCAL_MODELS = ("qwen3:8b", "qwen2.5:7b")
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-5"


@dataclass
class Step:
    id: str
    title: str
    action: str                      # "do" | "skip" | "info" | "needs-you"
    detail: str
    done: bool = False
    result: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


def delentia_home(override: Optional[str] = None) -> Path:
    from rct_control_plane.data_home import data_home
    return Path(override).expanduser() if override else (data_home() or Path.home() / ".delentia")


def inspect_machine(home: Path) -> Dict[str, Any]:
    """Facts only; nothing is changed."""
    from rct_control_plane import memory_embeddings
    url = memory_embeddings.base_url()
    installed = memory_embeddings._installed_models(url) if memory_embeddings._address_allowed(url) else []
    model_file = home / "model.json"
    return {
        "home": str(home), "home_exists": home.exists(),
        "ollama_models": installed, "ollama_reachable": bool(installed),
        "openrouter_key_set": bool(os.environ.get("OPENROUTER_API_KEY")),
        "model_config_exists": model_file.exists(),
        "audit_key_exists": (home / "keys" / "audit-signer.pem").exists(),
        "approvers_file_exists": (home / "approvers.json").exists(),
        "embedding_auto_would_use": next((m for m in memory_embeddings.PREFERRED_MODELS if memory_embeddings._has(installed, m)), None),
    }


def _pick_local(models: List[str]) -> Optional[str]:
    for wanted in PREFERRED_LOCAL_MODELS:
        if wanted in models or f"{wanted}:latest" in models:
            return wanted
    return None


def make_plan(facts: Dict[str, Any], *, provider: Optional[str] = None, model: Optional[str] = None, approver_here: bool = False) -> List[Step]:
    steps: List[Step] = []
    # 1 model
    if facts["model_config_exists"] and not (provider or model):
        steps.append(Step("model", "Which model drives the agent", "skip", "a choice is already saved (change it with `delentia model set`)"))
    else:
        chosen_provider, chosen_model = provider, model
        if not chosen_provider:
            local = _pick_local(facts["ollama_models"])
            if local:
                chosen_provider, chosen_model = "ollama", model or local
            elif facts["openrouter_key_set"]:
                chosen_provider, chosen_model = "openrouter", model or DEFAULT_OPENROUTER_MODEL
        if chosen_provider and (chosen_model or chosen_provider == "openrouter"):
            steps.append(Step("model", "Which model drives the agent", "do", f"use {chosen_provider}:{chosen_model}", payload={"provider": chosen_provider, "model": chosen_model or DEFAULT_OPENROUTER_MODEL}))
        else:
            steps.append(Step("model", "Which model drives the agent", "needs-you", "no preferred local model is installed and OPENROUTER_API_KEY is not set: install one (`ollama pull qwen2.5:7b`) "
                              "or set the key in the environment where the server starts, then run `delentia model set <model> --provider <ollama|openrouter>`"))
    # 2 audit key
    if facts["audit_key_exists"]:
        steps.append(Step("audit_key", "Audit signing key", "skip", "already created"))
    else:
        steps.append(Step("audit_key", "Audit signing key", "do", "create <home>/keys/audit-signer.pem so every audit row is signed; point DELENTIA_AUDIT_SIGNING_KEY at it where the server starts"))
    # 3 approver key
    if facts["approvers_file_exists"]:
        steps.append(Step("approver_key", "Who may sign risky actions", "skip", "an approvers file exists (`delentia approvals list`)"))
    elif approver_here:
        steps.append(Step("approver_key", "Who may sign risky actions", "do", "create an approver key ON THIS MACHINE (a single-person trial only: the agent runs as the same user and could read it)"))
    else:
        steps.append(Step("approver_key", "Who may sign risky actions", "needs-you", "create the approver key on ANOTHER device (`delentia approvals keygen`) and put its public key on this machine's approvers list; "
                          "until then nothing that needs a signature can run (fail closed). For a one-person trial, re-run with --approver-key-here. "
                          "Or, with the Desk open, add this computer's Windows Hello as the first approver with a one-time code: `delentia approvals first-device-code`"))
    # 4 recall
    steps.append(Step("embedding", "Recall by meaning", "info", (f"`auto` will use {facts['embedding_auto_would_use']}" if facts["embedding_auto_would_use"]
                      else "no embedding model is installed, so memories are found by shared words (`ollama pull bge-m3` reads Thai; `ollama pull nomic-embed-text` is smaller and better on English)")))
    return steps


def apply_plan(steps: List[Step], home: Path, *, dry_run: bool = False) -> List[Step]:
    for step in steps:
        if step.action != "do":
            continue
        if dry_run:
            step.result = "would do"
            continue
        try:
            if step.id == "model":
                from rct_control_plane import model_config
                path = model_config.save_model_selection(step.payload["provider"], step.payload["model"], path=home / "model.json")
                step.result, step.done = f"saved to {path}", True
            elif step.id == "audit_key":
                from rct_control_plane import audit_chain
                key = home / "keys" / "audit-signer.pem"
                key.parent.mkdir(parents=True, exist_ok=True)
                public = audit_chain.generate_signing_key(str(key))
                step.result, step.done = f"created {key}; public key {public}", True
            elif step.id == "approver_key":
                from rct_control_plane import approvals
                key = home / "keys" / "approver-trial.pem"
                key.parent.mkdir(parents=True, exist_ok=True)
                public = approvals.generate_approver_key(str(key))
                registry = home / "approvers.json"
                entries = json.loads(registry.read_text(encoding="utf-8")) if registry.exists() else []
                entries.append({"name": "trial-approver (same machine)", "public_key_hex": public, "role": ""})
                registry.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
                step.result, step.done = f"created {key} and listed it in {registry} - for a trial only", True
        except Exception as exc:                                              # noqa: BLE001 - say what failed; the other steps still run
            step.result = f"FAILED: {type(exc).__name__}: {str(exc)[:160]}"
    return steps


def render(facts: Dict[str, Any], steps: List[Step]) -> str:
    marks = {"do": "[do]   ", "skip": "[ok]   ", "info": "[info] ", "needs-you": "[YOU]  "}
    lines = [f"Delentia setup - home folder {facts['home']}", ""]
    for s in steps:
        lines.append(f"{marks[s.action]}{s.title}: {s.detail}")
        if s.result:
            lines.append(f"         -> {s.result}")
    if Path(facts["home"]) != Path.home() / ".delentia":
        lines += ["", f"This home folder is not ~/.delentia, so tell the server where things are: DELENTIA_MODEL_CONFIG={facts['home']}/model.json  DELENTIA_APPROVERS_FILE={facts['home']}/approvers.json  "
                      f"DELENTIA_AUDIT_SIGNING_KEY={facts['home']}/keys/audit-signer.pem"]
    left = [s for s in steps if s.action == "needs-you"]
    lines += ["", ("Still for you: " + ", ".join(s.title.lower() for s in left)) if left else "Nothing is waiting for you in this list.",
              "Then: `delentia serve` starts the agent, and in a second window `delentia desk` opens it in your browser (or `delentia demo init` for a guided first task). "
              "`delentia host-check --local` lists what else to look at."]
    return "\n".join(lines)


def as_json(facts: Dict[str, Any], steps: List[Step]) -> str:
    return json.dumps({"facts": facts, "steps": [asdict(s) for s in steps]}, indent=2, ensure_ascii=False)
