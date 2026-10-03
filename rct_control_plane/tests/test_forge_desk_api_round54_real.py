"""Round 54: the Desk endpoints for the Tool Forge, through the real FastAPI app with real approvals and real subprocesses."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from fastapi.testclient import TestClient

from rct_control_plane import approvals
from rct_control_plane.api import create_app
from scripted_model import ScriptedModel

CODE = 'import re\n\ndef shout(text):\n    return re.sub(r"\s+", " ", text).strip().upper() + "!"\n'
SMOKE = 'assert shout("hi") == "HI!"\nassert shout("  a   b ") == "A B!"'


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("DELENTIA_API_TOKEN", raising=False)
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv("DELENTIA_API_TOKENS_FILE", str(tmp_path / "none.json"))
    with TestClient(create_app()) as c:
        yield c


def name():
    return "shout_" + os.urandom(3).hex()


def sign(approval_id, tmp_path, monkeypatch):
    from rct_control_plane.mcp_server import _kernel
    key = tmp_path / "keys" / f"k{os.urandom(2).hex()}.pem"
    public = approvals.generate_approver_key(str(key))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public)
    store = approvals.PendingActionStore(_kernel._persistence)
    record = store.get(approval_id)
    signed = approvals.sign_decision(str(key), approval_id, record.action_sha256, "APPROVED")
    store.decide(approval_id, "APPROVED", signed["public_key_hex"], signed["signature_hex"])


def test_state_lists_gaps_proposals_tools_and_the_limits(client):
    data = client.get("/v1/desk/forge").json()
    assert set(data) == {"gaps", "proposals", "tools", "limits"} and "math" in data["limits"]["allowed_imports"] and data["limits"]["min_asserts"] == 2


def test_the_whole_story_over_http_propose_request_sign_activate_run_off(client, tmp_path, monkeypatch):
    tool = name()
    code, smoke = CODE.replace("shout", tool), SMOKE.replace("shout", tool)
    proposed = client.post("/v1/desk/forge/propose", json={"name": tool, "spec": "upper-case and squeeze spaces", "smoke_test": smoke, "code": code})
    assert proposed.status_code == 200 and proposed.json()["status"] == "VERIFIED" and "code" not in proposed.json()
    detail = client.get(f"/v1/desk/forge/proposals/{proposed.json()['id']}").json()
    assert detail["code"] == code and detail["smoke_test"] == smoke and detail["approval"] is None
    requested = client.post(f"/v1/desk/forge/proposals/{proposed.json()['id']}/request").json()
    approval_id = requested["approval_id"]
    assert client.get(f"/v1/desk/forge/proposals/{proposed.json()['id']}").json()["approval"]["status"] == "PENDING"
    early = client.post("/v1/desk/forge/activate", json={"approval_id": approval_id})
    assert early.status_code == 403 and "not APPROVED" in early.json()["detail"]
    sign(approval_id, tmp_path, monkeypatch)
    done = client.post("/v1/desk/forge/activate", json={"approval_id": approval_id})
    assert done.status_code == 200 and done.json()["name"] == tool
    ran = client.post(f"/v1/desk/forge/tools/{tool}/run", json={"args": {"text": "  hello   there "}}).json()
    assert ran == {"ok": True, "result": "HELLO THERE!"}
    state = client.get("/v1/desk/forge").json()
    assert [t["name"] for t in state["tools"]] == [t["name"] for t in state["tools"] if t["active"]] and any(t["name"] == tool for t in state["tools"])
    assert client.post(f"/v1/desk/forge/tools/{tool}/off").status_code == 200
    assert client.post(f"/v1/desk/forge/tools/{tool}/off").status_code == 404
    assert client.post(f"/v1/desk/forge/tools/{tool}/run", json={"args": {}}).json()["ok"] is False


def test_a_bad_proposal_is_reported_and_cannot_be_put_forward(client):
    tool = name()
    bad = client.post("/v1/desk/forge/propose", json={"name": tool, "spec": "read secrets", "smoke_test": "assert x(1) == 1\nassert x(2) == 2",
                                                       "code": "import os\ndef " + tool + "(x):\n    return os.environ"}).json()
    assert bad["status"] == "REJECTED_STATIC_CHECK" and bad["verification"]["problems"]
    refused = client.post(f"/v1/desk/forge/proposals/{bad['id']}/request")
    assert refused.status_code == 400 and "only a VERIFIED proposal" in refused.json()["detail"]


@pytest.mark.parametrize("body,fragment", [
    ({"name": "No", "spec": "x", "smoke_test": "assert 1"}, "tool name"),
    ({"name": "good_name", "spec": "", "smoke_test": "assert 1", "code": "def good_name(): pass"}, "spec"),
])
def test_bad_input_is_a_400_with_a_reason(client, body, fragment):
    response = client.post("/v1/desk/forge/propose", json=body)
    assert response.status_code == 400 and fragment in response.json()["detail"]


def test_the_model_writes_the_code_when_none_is_given(client, monkeypatch, tmp_path):
    from rct_control_plane.model_config import save_model_selection
    tool = name()
    with ScriptedModel(lambda request: CODE.replace("shout", tool), model_id="writer-1") as server:
        config = tmp_path / "model.json"
        save_model_selection("openai-compat", "writer-1", path=config, endpoint={"base_url": server.base_url, "kind": "local", "region": "", "operator": "t"})
        monkeypatch.setenv("DELENTIA_MODEL_CONFIG", str(config))
        monkeypatch.setenv("DELENTIA_LLM_PROVIDER", "openai-compat")
        monkeypatch.setenv("DELENTIA_LLM_MODEL", "writer-1")
        proposed = client.post("/v1/desk/forge/propose", json={"name": tool, "spec": "upper-case and squeeze spaces", "smoke_test": SMOKE.replace("shout", tool)})
        assert proposed.status_code == 200 and proposed.json()["verification"]["code_source"] == "model" and proposed.json()["status"] == "VERIFIED"


def test_unknown_proposal_and_bad_run_args(client):
    assert client.get("/v1/desk/forge/proposals/fp-nothing").status_code == 404
    assert client.post("/v1/desk/forge/tools/x/run", json={"args": [1]}).status_code == 400
