"""
Round 55: the host kit (deploy/host), the notary token file, and the address-encoding cases for the agent's fetch.

The container files could not be built or run here (Docker Desktop was not running), so what is checked is what can be: they parse, they
say what the runbook says, and they cannot leak what the Round 55 review found the old Dockerfile could (databases, git history, .env).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import fnmatch
from pathlib import Path

import pytest
import yaml

from rct_control_plane import notary, url_safety

ROOT = Path(__file__).resolve().parent.parent.parent
HOST = ROOT / "deploy" / "host"


def compose():
    return yaml.safe_load((HOST / "docker-compose.yml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ .dockerignore

def ignored(path: str) -> bool:
    patterns = [line.strip() for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    for pattern in patterns:
        pat = pattern.rstrip("/")
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, f"**/{pat}") or path == pat or path.startswith(pat + "/"):
            return True
        if pat.startswith("**/") and fnmatch.fnmatch(path.split("/")[-1], pat[3:]):
            return True
    return False


@pytest.mark.parametrize("path", [".git", ".git/config", "rct_control_plane.db", "rct_control_plane_agentic.db-wal", "ground_truth_store.db", ".env", ".env.local",
                                  "deploy/host/secrets/audit.pem", "workspace_output", "apps/gui/node_modules", "some/dir/credentials.json", "vault_master.key"])
def test_nothing_private_can_end_up_in_an_image(path):
    assert ignored(path), f"{path} would be copied into the image by `COPY . .`"


@pytest.mark.parametrize("path", ["pyproject.toml", "requirements.txt", "rct_control_plane/api.py", "core/delta_engine/memory_delta.py", "signedai/api.py"])
def test_what_the_runtime_needs_is_still_copied(path):
    assert not ignored(path)


# ------------------------------------------------------------------ the compose file

def test_only_the_proxy_publishes_ports_and_it_publishes_only_80_and_443():
    services = compose()["services"]
    published = {name: svc.get("ports") for name, svc in services.items() if svc.get("ports")}
    assert set(published) == {"caddy"} and sorted(published["caddy"]) == ["443:443", "80:80"]


def test_the_notary_is_another_user_with_its_own_volume_and_a_locked_down_container():
    services = compose()["services"]
    notary_svc, agent = services["notary"], services["delentia"]
    assert notary_svc["user"] != agent["user"] and notary_svc["user"].split(":")[0] != "0"
    assert notary_svc["volumes"] != agent["volumes"] and not set(notary_svc["volumes"]) & set(agent["volumes"])
    assert notary_svc["read_only"] is True and notary_svc["cap_drop"] == ["ALL"] and "no-new-privileges:true" in notary_svc["security_opt"]
    assert "notary_key" in notary_svc["secrets"] and "notary_key" not in agent["secrets"]          # the agent never holds the notary's key


def test_the_agent_reaches_the_loopback_only_notary_through_a_shared_network_namespace():
    services = compose()["services"]
    assert services["notary"]["network_mode"] == "service:net" and services["delentia"]["network_mode"] == "service:net"
    assert services["delentia"]["environment"]["DELENTIA_NOTARY_URL"] == "http://127.0.0.1:8765"
    assert "8765" in " ".join(services["notary"]["command"])


def test_no_secret_value_is_written_into_the_compose_file_or_the_dockerfile():
    text = (HOST / "docker-compose.yml").read_text(encoding="utf-8") + (HOST / "Dockerfile").read_text(encoding="utf-8")
    from rct_control_plane.host_check import KEY_LOOKING
    assert not KEY_LOOKING.search(text)
    env = compose()["services"]["delentia"]["environment"]
    assert "DELENTIA_API_TOKEN" not in env and all("TOKEN" not in k or k.endswith(("_FILE", "MAX_TOKENS")) for k in env)      # tokens come from files / the secrets folder


def test_the_runtime_data_and_config_live_on_a_volume_so_a_restart_keeps_them():
    agent = compose()["services"]["delentia"]
    assert any(v.endswith(":/data") for v in agent["volumes"]) and agent["environment"]["HOME"].startswith("/data")
    assert agent["environment"]["DELENTIA_REPO_ROOT"].startswith("/data") and agent["environment"]["DELENTIA_HOME"] == "/data"
    assert agent["environment"]["DELENTIA_EPISODE_MAX_TOKENS"] and agent["environment"]["DELENTIA_EPISODE_BUDGET_USD"]        # a per-episode cap by default


def test_the_domain_is_required_and_the_secrets_folder_is_never_committed():
    assert "?" in compose()["services"]["caddy"]["environment"]["DELENTIA_DOMAIN"]                  # ${VAR:?message}: refuses to start without it
    assert "secrets/" in (HOST / ".gitignore").read_text(encoding="utf-8")
    assert all(Path(spec["file"]).parts[:2] == (".", "secrets") or str(spec["file"]).startswith("./secrets/") for spec in compose()["secrets"].values())


def test_the_dockerfile_runs_serve_as_a_non_root_user_with_a_healthcheck():
    text = (HOST / "Dockerfile").read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    assert "USER delentia" in lines and "--uid 10001" in text
    assert any(line.startswith("HEALTHCHECK") for line in lines) and 'CMD ["delentia", "serve", "--host", "0.0.0.0", "--port", "8000"]' in lines
    assert lines.index("USER delentia") > max(i for i, line in enumerate(lines) if line.startswith("RUN"))      # installs as root, runs as the user


def test_the_runbook_names_every_file_and_command_it_depends_on():
    runbook = (HOST / "HOST_RUNBOOK.md").read_text(encoding="utf-8")
    for needle in ("host-check", "host_sizing.py", "delentia tokens create", "approvals keygen --out", "bootstrap.sh", "tokens create",
                   "docker compose up -d", "Known gaps"):
        assert needle.lower() in runbook.lower(), needle
    assert "built and run for real" in runbook.lower() and "not run:" in runbook.lower()      # says what was run AND what was not


# ------------------------------------------------------------------ the notary token can be a secret file

def test_the_notary_token_comes_from_the_environment_or_a_secret_file(tmp_path, monkeypatch):
    monkeypatch.delenv(notary.NOTARY_TOKEN_ENV, raising=False)
    monkeypatch.delenv(notary.NOTARY_TOKEN_ENV + "_FILE", raising=False)
    assert notary.token_from_env() is None
    secret = tmp_path / "token"
    secret.write_text("file-token-123\n", encoding="utf-8")
    monkeypatch.setenv(notary.NOTARY_TOKEN_ENV + "_FILE", str(secret))
    assert notary.token_from_env() == "file-token-123"
    monkeypatch.setenv(notary.NOTARY_TOKEN_ENV, "env-token-456")
    assert notary.token_from_env() == "env-token-456"                       # the environment variable wins
    monkeypatch.delenv(notary.NOTARY_TOKEN_ENV)
    monkeypatch.setenv(notary.NOTARY_URL_ENV, "http://127.0.0.1:8765")
    assert notary.NotaryClient.from_env().token == "file-token-123"          # the agent side reads it the same way
    secret.write_text("\n", encoding="utf-8")
    assert notary.token_from_env() is None                                  # an empty file is no token, not an empty token


# ------------------------------------------------------------------ the address check against encoded forms

@pytest.mark.parametrize("url", [
    "http://2130706433/", "http://0x7f000001/", "http://017700000001/", "http://127.1/", "http://[::ffff:7f00:1]/", "http://localhost./",
    "http://0/", "http://[::]/", "http://[fe80::1%25eth0]/", "http://[::1]:8000/", "HTTP://LOCALHOST/", "http://1.1.1.1@127.0.0.1/",
    "http://127.0.0.1#@example.com/", "http://metadata/", "http://100.64.0.1/",
])
def test_encoded_and_tricky_forms_of_internal_addresses_are_refused(url, monkeypatch):
    monkeypatch.delenv(url_safety.ALLOW_PRIVATE_ENV, raising=False)
    with pytest.raises(url_safety.UnsafeURLError):
        url_safety.check_public_url(url)


# ------------------------------------------------------------------ things found by actually running the kit in containers

def test_the_ffmpeg_copy_at_import_time_survives_an_unwritable_site_packages():
    """Found in the container: algo_27 copied a binary into site-packages at IMPORT time, so as an unprivileged user the whole kernel died."""
    source = (ROOT / "rct_control_plane" / "algo_27_tvra.py").read_text(encoding="utf-8")
    body = source[source.index("import imageio_ffmpeg"):source.index("except ImportError")]
    assert "except OSError" in body and "gettempdir" in body


def test_the_exchange_folder_follows_the_data_home_instead_of_the_filesystem_root(tmp_path, monkeypatch):
    """Found in the container: the default was two folders above the package, i.e. /exchange at the root of the image."""
    from rct_control_plane.exchange_bridge import NeuralExchangeBridge
    monkeypatch.delenv("DELENTIA_EXCHANGE_DIR", raising=False)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    assert Path(NeuralExchangeBridge().root_dir) == tmp_path / "home" / "exchange"
    monkeypatch.setenv("DELENTIA_EXCHANGE_DIR", str(tmp_path / "elsewhere"))
    assert Path(NeuralExchangeBridge().root_dir) == tmp_path / "elsewhere"
    assert Path(NeuralExchangeBridge(str(tmp_path / "explicit")).root_dir) == tmp_path / "explicit"


def test_the_kit_creates_the_notary_folder_for_the_notary_uid_and_ships_a_bootstrap_script():
    dockerfile = (HOST / "Dockerfile").read_text(encoding="utf-8")
    assert "/notary" in dockerfile and "chown 10002:10002 /notary" in dockerfile and "--mount=type=cache" in dockerfile
    script = (HOST / "bootstrap.sh").read_text(encoding="utf-8")
    assert "--user 10001:10001" in script and "--user 10002:10002" in script and "tokens create" in script and "MSYS_NO_PATHCONV" in script
    assert compose()["services"]["delentia"]["image"] == compose()["services"]["notary"]["image"] == "delentia-host:latest"


def test_the_ollama_address_can_be_set_by_environment_and_an_explicit_address_still_wins(monkeypatch):
    from rct_control_plane.llm_provider import DEFAULT_OLLAMA_URL, OllamaProvider
    monkeypatch.delenv("DELENTIA_OLLAMA_URL", raising=False)
    assert OllamaProvider().llm_url == DEFAULT_OLLAMA_URL
    monkeypatch.setenv("DELENTIA_OLLAMA_URL", "http://ollama.internal:11434/")
    assert OllamaProvider().llm_url == "http://ollama.internal:11434"
    assert OllamaProvider(llm_url="http://127.0.0.1:9").llm_url == "http://127.0.0.1:9"


def test_the_dependency_layer_does_not_depend_on_the_source_tree():
    """Round 56: the 9-10 minute install must only be invalidated by pyproject.toml / requirements.txt, not by any .py edit."""
    lines = [line.strip() for line in (HOST / "Dockerfile").read_text(encoding="utf-8").splitlines()]
    deps_copy = next(i for i, line in enumerate(lines) if line.startswith("COPY pyproject.toml requirements.txt"))
    source_copy = next(i for i, line in enumerate(lines) if line.startswith("COPY --chown=delentia:delentia . ."))
    install = next(i for i, line in enumerate(lines) if "pip install -r requirements.txt" in line)
    project_install = next(i for i, line in enumerate(lines) if line.startswith("RUN pip install --no-deps -e ."))
    assert deps_copy < install < source_copy < project_install


def test_export_deps_lists_every_runtime_dependency_and_the_full_extra():
    import subprocess
    root = HOST.parent.parent
    out = subprocess.run([sys.executable, str(HOST / "export_deps.py"), str(root / "pyproject.toml")], capture_output=True, text=True, check=True).stdout.splitlines()
    names = {line.split(">")[0].split("[")[0].strip().lower() for line in out}
    assert {"fastapi", "cryptography", "mcp", "torch", "spacy", "faiss-cpu", "ultralytics"} <= names
    assert len(out) == len(set(out))


# ------------------------------------------------------------------ Round 56: A3 anchoring as a setting, and registering a key at the witness

def test_compose_turns_anchoring_on_by_environment_for_both_the_notary_and_the_runtime_and_off_by_default():
    compose = yaml.safe_load((HOST / "docker-compose.yml").read_text(encoding="utf-8"))
    notary_env = compose["services"]["notary"]["environment"]
    runtime_env = compose["services"]["delentia"]["environment"]
    assert notary_env["DELENTIA_NOTARY_ANCHOR_URL"].startswith("${DELENTIA_AUDIT_ANCHOR_URL:-") and notary_env["DELENTIA_NOTARY_ANCHOR_KEY_ID"].endswith(":-}")
    assert runtime_env["DELENTIA_AUDIT_ANCHOR_URL"].endswith(":-}") and runtime_env["DELENTIA_AUDIT_ANCHOR_KEY_ID"].endswith(":-}")
    assert "DELENTIA_AUDIT_ANCHOR_INTERVAL_S" in runtime_env


def test_the_notary_reads_its_anchor_settings_from_the_environment_and_refuses_a_url_without_a_key_id(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from rct_control_plane.cli import cli
    key = tmp_path / "notary.pem"
    notary.generate_key(str(key))
    monkeypatch.setenv("DELENTIA_NOTARY_ANCHOR_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("DELENTIA_NOTARY_ANCHOR_KEY_ID", raising=False)
    result = CliRunner().invoke(cli, ["notary", "serve", "--db", str(tmp_path / "n.db"), "--key", str(key), "--port", "0"])
    assert result.exit_code == 1 and "--anchor-url needs --anchor-key-id" in result.output
    monkeypatch.setenv("DELENTIA_NOTARY_ANCHOR_URL", "")                      # what the compose file passes when anchoring is off
    monkeypatch.delenv("DELENTIA_NOTARY_ANCHOR_URL")


def test_witness_entry_prints_the_exact_object_the_witness_registry_expects(tmp_path, monkeypatch):
    import json
    from click.testing import CliRunner
    from rct_control_plane import audit_chain
    from rct_control_plane.cli import cli
    runner = CliRunner()
    notary_key = tmp_path / "notary.pem"
    public = notary.generate_key(str(notary_key))
    out = runner.invoke(cli, ["notary", "witness-entry", "--key-id", "delentia-notary-2", "--key", str(notary_key)])
    assert out.exit_code == 0, out.output
    entry = json.loads([line for line in out.output.splitlines() if line.startswith("{")][0])
    assert entry == {"key_id": "delentia-notary-2", "public_key_hex": public}
    assert "BEFORE its first anchor" in out.output

    audit_key = tmp_path / "audit.pem"
    audit_public = audit_chain.generate_signing_key(str(audit_key))
    monkeypatch.setenv(audit_chain.SIGNING_KEY_ENV, str(audit_key))
    out = runner.invoke(cli, ["audit-chain", "witness-entry", "--key-id", "host-1"])
    assert json.loads([line for line in out.output.splitlines() if line.startswith("{")][0]) == {"key_id": "host-1", "public_key_hex": audit_public}
    monkeypatch.delenv(audit_chain.SIGNING_KEY_ENV)
    assert runner.invoke(cli, ["audit-chain", "witness-entry", "--key-id", "host-1"]).exit_code == 1
