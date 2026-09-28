"""
Round 48: Delentia-OS can sign delentia-mcp-ecosystem Architect tokens with the
same Ed25519 approver key it uses for approvals. Ed25519 is deterministic, so
a fixed key and input must give exactly the token the TypeScript signer gives
(tests/architect_token.test.mjs pins the same string).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

import pytest
from click.testing import CliRunner

from rct_control_plane import approvals

FIXED_PEM = "-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f\n-----END PRIVATE KEY-----\n"
TS_VECTOR = "dat1.k1.1800000600.5u3u69tP7CeFJkU_MLNUU0fzDg0blNyNeBhPEbq7naqbw_BimKQXgUDa7rTvGI13QVWtZh26Y9dpxIsp0RB6CA"


@pytest.fixture
def fixed_key(tmp_path):
    p = tmp_path / "fixed.pem"
    p.write_text(FIXED_PEM)
    return str(p)


def test_python_signs_byte_identical_to_typescript(fixed_key):
    token = approvals.sign_architect_token(fixed_key, "k1", "delete_repo", '{"repo":"a"}', 600, now_seconds=1_800_000_000)
    assert token == TS_VECTOR


def test_ttl_is_capped_at_24h_and_key_id_cannot_contain_dots(fixed_key):
    t = approvals.sign_architect_token(fixed_key, "k1", "x", "", 10**9, now_seconds=1_000)
    assert int(t.split(".")[2]) == 1_000 + 86_400
    with pytest.raises(approvals.ApprovalError):
        approvals.sign_architect_token(fixed_key, "a.b", "x")


def test_cli_prints_token_and_key_entry(fixed_key):
    from rct_control_plane.cli import cli
    runner = CliRunner()
    r = runner.invoke(cli, ["approvals", "architect-token", "--key", fixed_key, "--key-id", "k1", "--action", "delete_repo"])
    assert r.exit_code == 0 and r.output.strip().startswith("dat1.k1.")
    r = runner.invoke(cli, ["approvals", "architect-key-entry", "--key", fixed_key, "--key-id", "k1"])
    entry = json.loads(r.output)
    assert entry["key_id"] == "k1" and entry["role"] == "Chief_Architect" and len(entry["public_key_hex"]) == 64
