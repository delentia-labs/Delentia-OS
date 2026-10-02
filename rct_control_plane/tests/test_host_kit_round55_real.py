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
    for needle in ("host-check", "host_sizing.py", "delentia tokens create", "approvals keygen --out", "audit-chain keygen", "notary keygen",
                   "docker compose up -d", "Known gaps"):
        assert needle.lower() in runbook.lower(), needle
    assert "not built or run" in runbook.lower()


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
