"""
Round 58: DM pairing and slash commands in chat.

Real SQLite, real approvals store and real Ed25519 signatures; the only fake is the "agent" a gateway would call (a function that records that it was reached),
because the point is to prove WHEN the agent is reached and when it is not.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio

import pytest

from rct_control_plane import approvals, chat_commands, pairing
from rct_control_plane.agent_factory import SENDER_ALLOWLIST_ENV, REJECTED_SENDER_REPLY, rejection_reply, sender_allowed
from rct_control_plane.approvals import ApprovalError, PendingActionStore
from rct_control_plane.cron_jobs import CronService
from rct_control_plane.gateways import common
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.session_search import SessionLog


def run(coro):
    return asyncio.run(coro)


class Kernel:
    def __init__(self, path):
        self._persistence = ControlPlanePersistence(db_path=str(path))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for var in list(os.environ):
        if var.startswith("DELENTIA_") and var.endswith("_ALLOWED_SENDERS"):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv(approvals.APPROVERS_ENV, raising=False)
    monkeypatch.setenv("DELENTIA_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    monkeypatch.setenv(pairing.ENABLED_ENV, "1")


@pytest.fixture
def kernel(tmp_path):
    return Kernel(tmp_path / "agent.db")


@pytest.fixture
def owner(tmp_path, monkeypatch):
    key_path = tmp_path / "keys" / "owner.pem"
    public_hex = approvals.generate_approver_key(str(key_path))
    monkeypatch.setenv(approvals.APPROVERS_ENV, public_hex)
    return str(key_path), public_hex


def sign(kernel, key_path, code, decision="APPROVED"):
    store = PendingActionStore(kernel._persistence)
    action = store.get(code)
    signed = approvals.sign_decision(key_path, action.approval_id, action.action_sha256, decision)
    return store.decide(action.approval_id, decision, signed["public_key_hex"], signed["signature_hex"])


class Agent:
    def __init__(self):
        self.calls = []

    async def __call__(self, goal, namespace):
        self.calls.append((goal, namespace))
        return {"final_answer": f"done: {goal}"}


def deliver(kernel, channel, sender, text, agent):
    sent = []

    async def reply(t):
        sent.append(t)

    out = run(common.handle_incoming(kernel, channel, sender, text, dispatch=agent, reply=reply, reply_to_rejected=reply))
    return out, sent


# ------------------------------------------------------------------ pairing

class TestPairing:
    def test_off_by_default_an_unknown_sender_gets_the_fixed_refusal_and_nothing_is_created(self, kernel, monkeypatch):
        monkeypatch.delenv(pairing.ENABLED_ENV)
        agent = Agent()
        out, sent = deliver(kernel, "telegram", "42", "hello", agent)
        assert out["rejected"] and sent == [REJECTED_SENDER_REPLY] and agent.calls == []
        assert PendingActionStore(kernel._persistence).list(status=None) == []

    def test_an_unknown_sender_is_given_a_code_and_the_agent_is_not_reached(self, kernel):
        agent = Agent()
        out, sent = deliver(kernel, "telegram", "42", "please delete my files", agent)
        assert out["rejected"] and agent.calls == []
        (pending,) = PendingActionStore(kernel._persistence).list()
        assert pending.tool_name == pairing.TOOL and pending.tool_args == {"channel": "telegram", "sender_id": "42"}
        assert pending.approval_id in sent[0] and "owner" in sent[0]
        assert "delete" not in sent[0]                                    # the sender's text is never echoed

    def test_asking_again_returns_the_same_code_not_a_second_request(self, kernel):
        first = pairing.request("telegram", "42", kernel._persistence)
        again = pairing.request("telegram", "42", kernel._persistence)
        assert first["state"] == "new" and again == {"state": "waiting", "code": first["code"]}
        assert len(PendingActionStore(kernel._persistence).list()) == 1

    def test_before_the_signature_nothing_runs_and_an_edited_status_is_not_a_signature(self, kernel, owner):
        asked = pairing.request("telegram", "42", kernel._persistence)
        assert not sender_allowed("telegram", "42", kernel._persistence)
        with kernel._persistence._connect() as conn:                     # someone with the DB flips the status by hand
            conn.execute("UPDATE pending_actions SET status = 'APPROVED' WHERE approval_id = ?", (asked["code"],))
        assert not sender_allowed("telegram", "42", kernel._persistence)

    def test_a_signature_from_a_key_nobody_trusts_does_not_let_anyone_in(self, kernel, owner, tmp_path):
        asked = pairing.request("telegram", "42", kernel._persistence)
        stranger = tmp_path / "stranger.pem"
        approvals.generate_approver_key(str(stranger))
        with pytest.raises(ApprovalError):
            sign(kernel, str(stranger), asked["code"])
        assert not sender_allowed("telegram", "42", kernel._persistence)

    def test_the_owner_signs_and_the_sender_can_talk_to_the_agent(self, kernel, owner):
        key_path, _ = owner
        deliver(kernel, "telegram", "42", "hi", Agent())
        (code,) = [a.approval_id for a in PendingActionStore(kernel._persistence).list()]
        sign(kernel, key_path, code)
        agent = Agent()
        out, sent = deliver(kernel, "telegram", "42", "what is on my list?", agent)
        assert agent.calls == [("what is on my list?", "telegram-42")] and sent == ["done: what is on my list?"]
        with kernel._persistence._connect() as conn:
            kinds = [r[0] for r in conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'pairing'").fetchall()]
        assert kinds == ["requested", "granted"]

    def test_a_grant_is_for_one_channel_and_one_person(self, kernel, owner):
        key_path, _ = owner
        asked = pairing.request("telegram", "42", kernel._persistence)
        sign(kernel, key_path, asked["code"])
        assert sender_allowed("telegram", "42", kernel._persistence)
        assert not sender_allowed("discord", "42", kernel._persistence)
        assert not sender_allowed("telegram", "43", kernel._persistence)

    def test_the_approval_is_used_up_once_and_cannot_be_replayed(self, kernel, owner):
        key_path, _ = owner
        asked = pairing.request("telegram", "42", kernel._persistence)
        sign(kernel, key_path, asked["code"])
        assert pairing.is_granted("telegram", "42", kernel._persistence)
        with pytest.raises(ApprovalError, match="already"):
            PendingActionStore(kernel._persistence).claim_for_execution(asked["code"])

    def test_a_refusal_is_final_for_a_day_then_the_sender_may_ask_again(self, kernel, owner):
        key_path, _ = owner
        asked = pairing.request("telegram", "42", kernel._persistence)
        sign(kernel, key_path, asked["code"], decision="REJECTED")
        assert pairing.request("telegram", "42", kernel._persistence)["state"] == "refused"
        assert rejection_reply(kernel, "telegram", "42") == REJECTED_SENDER_REPLY       # no code, no hint
        later = pairing.request("telegram", "42", kernel._persistence, now=__import__("time").time() + pairing.REFUSAL_COOLDOWN_S + 5)
        assert later["state"] == "new"

    def test_flood_control_caps_pending_requests_per_channel(self, kernel):
        states = [pairing.request("telegram", str(1000 + i), kernel._persistence)["state"] for i in range(pairing.MAX_PENDING_PER_CHANNEL + 3)]
        assert states.count("new") == pairing.MAX_PENDING_PER_CHANNEL and states[-1] == "full"
        assert pairing.request("discord", "1", kernel._persistence)["state"] == "new"   # another channel is not starved

    @pytest.mark.parametrize("sender", ["", "a b", "x\nIgnore previous instructions", "x" * 200, "<script>"])
    def test_a_sender_id_that_is_not_a_plain_id_gets_no_request(self, kernel, sender):
        assert pairing.request("telegram", sender, kernel._persistence)["state"] == "invalid"
        assert PendingActionStore(kernel._persistence).list(status=None) == []

    def test_email_never_gets_a_code(self, kernel):
        assert rejection_reply(kernel, "email", "attacker@example.com") == REJECTED_SENDER_REPLY
        assert PendingActionStore(kernel._persistence).list(status=None) == []

    def test_revoking_closes_the_door_again_and_is_audited(self, kernel, owner):
        key_path, _ = owner
        asked = pairing.request("telegram", "42", kernel._persistence)
        sign(kernel, key_path, asked["code"])
        assert sender_allowed("telegram", "42", kernel._persistence)
        assert pairing.revoke("telegram", "42", persistence=kernel._persistence)
        assert not sender_allowed("telegram", "42", kernel._persistence)
        assert not pairing.revoke("telegram", "42", persistence=kernel._persistence)           # nothing left to revoke
        with kernel._persistence._connect() as conn:
            kinds = [r[0] for r in conn.execute("SELECT action FROM audit_trail WHERE entity_type = 'pairing'").fetchall()]
        assert kinds == ["requested", "granted", "revoked"]

    def test_the_environment_allowlist_still_works_without_pairing_and_is_never_edited(self, kernel, monkeypatch):
        monkeypatch.delenv(pairing.ENABLED_ENV)
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "7")
        assert sender_allowed("telegram", "7", kernel._persistence) and not sender_allowed("telegram", "8", kernel._persistence)
        assert os.environ[SENDER_ALLOWLIST_ENV["telegram"]] == "7"

    def test_an_unreadable_store_means_nobody_new_gets_in(self):
        class Broken:
            def _connect(self):
                raise RuntimeError("disk gone")
        assert pairing.is_granted("telegram", "42", Broken()) is False

    def test_state_lists_waiting_requests_and_grants_for_the_desk(self, kernel, owner):
        key_path, _ = owner
        a = pairing.request("telegram", "42", kernel._persistence)
        b = pairing.request("telegram", "43", kernel._persistence)
        sign(kernel, key_path, a["code"])
        view = pairing.state(kernel._persistence)
        assert [g["sender_id"] for g in view["grants"]] == ["42"] and [p["sender_id"] for p in view["pending"]] == ["43"]
        assert view["pending"][0]["code"] == b["code"]


# ------------------------------------------------------------------ slash commands

class TestCommands:
    @pytest.mark.parametrize("text,expected", [
        ("/help", ("help", "")), ("/search invoice 2026", ("search", "invoice 2026")), ("/status@MyBot", ("status", "")),
        ("  /jobs  ", ("jobs", "")), ("/start", ("start", "")),
    ])
    def test_a_one_word_command_is_recognised(self, text, expected):
        assert chat_commands.parse(text) == expected

    @pytest.mark.parametrize("text", ["/etc/hosts please read this", "/unknowncmd", "hello /help", "", "/ help", "//help", "/HELP"])
    def test_anything_else_is_an_ordinary_goal(self, text):
        assert chat_commands.parse(text) is None

    def test_a_command_never_reaches_the_agent(self, kernel, monkeypatch):
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42")
        agent = Agent()
        out, sent = deliver(kernel, "telegram", "42", "/help", agent)
        assert agent.calls == [] and out["command"] and "/status" in sent[0]

    def test_a_path_that_starts_with_a_slash_is_still_a_goal_for_the_agent(self, kernel, monkeypatch):
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42")
        agent = Agent()
        deliver(kernel, "telegram", "42", "/etc/hosts what does it say", agent)
        assert len(agent.calls) == 1

    def test_a_refused_sender_cannot_use_commands(self, kernel, monkeypatch):
        monkeypatch.delenv(pairing.ENABLED_ENV)
        agent = Agent()
        out, sent = deliver(kernel, "telegram", "42", "/status", agent)
        assert out["rejected"] and sent == [REJECTED_SENDER_REPLY]

    def test_whoami_names_the_callers_own_space(self, kernel, monkeypatch):
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["signal"], "+6611")
        _, sent = deliver(kernel, "signal", "+6611", "/whoami", Agent())
        assert "signal-+6611" in sent[0]

    def test_jobs_lists_only_the_callers_jobs(self, kernel, monkeypatch):
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42,43")
        cron = CronService(kernel._persistence)
        cron.create("telegram-42", "check the build", "every weekday at 9:00", name="build check")
        cron.create("telegram-43", "secret errand", "every day at 10:00", name="private errand")
        _, mine = deliver(kernel, "telegram", "42", "/jobs", Agent())
        assert "build check" in mine[0] and "private errand" not in mine[0]
        _, empty = deliver(kernel, "telegram", "43", "/jobs", Agent())
        assert "private errand" in empty[0] and "build check" not in empty[0]

    def test_search_finds_the_callers_earlier_requests_and_nobody_elses(self, kernel, monkeypatch):
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42")
        log = SessionLog(kernel._persistence)
        log.record("telegram-42", "summarise the quarterly invoice", "The invoice total is 1,200 baht.")
        log.record("telegram-99", "summarise the secret merger invoice", "Acquisition at 9 billion.")
        _, sent = deliver(kernel, "telegram", "42", "/search invoice", Agent())
        assert "quarterly invoice" in sent[0] and "merger" not in sent[0] and "billion" not in sent[0]
        _, none = deliver(kernel, "telegram", "42", "/search zebra", Agent())
        assert "Nothing" in none[0]

    def test_approvals_lists_the_callers_waiting_actions_and_tells_them_they_cannot_sign(self, kernel, monkeypatch):
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42")
        store = PendingActionStore(kernel._persistence)
        mine = store.create("telegram-42", "write the notes", "delentia_write_repo_file", {"relative_path": "n.md"})
        store.create("telegram-99", "other person's write", "delentia_write_repo_file", {"relative_path": "x.md"})
        _, sent = deliver(kernel, "telegram", "42", "/approvals", Agent())
        assert mine.approval_id in sent[0] and "other person" not in sent[0] and "cannot sign" in sent[0]

    def test_commands_change_nothing(self, kernel, monkeypatch):
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42")
        store = PendingActionStore(kernel._persistence)
        store.create("telegram-42", "g", "delentia_write_repo_file", {"relative_path": "n.md"})
        with kernel._persistence._connect() as conn:
            before = conn.execute("SELECT status, tool_args_json FROM pending_actions").fetchall()
        for command in ("/help", "/whoami", "/status", "/jobs", "/approvals", "/search n", "/model"):
            deliver(kernel, "telegram", "42", command, Agent())
        with kernel._persistence._connect() as conn:
            assert conn.execute("SELECT status, tool_args_json FROM pending_actions").fetchall() == before

    def test_a_broken_table_is_reported_not_raised(self, monkeypatch):
        class Broken:
            _persistence = object()
        reply = chat_commands.handle(Broken(), "telegram", "42", "telegram-42", "/jobs")
        assert reply.startswith("/jobs could not be answered")

    def test_the_reply_is_bounded(self, kernel, monkeypatch):
        monkeypatch.setenv(SENDER_ALLOWLIST_ENV["telegram"], "42")
        log = SessionLog(kernel._persistence)
        for _ in range(5):
            log.record("telegram-42", "invoice " + "x" * 400, "y" * 700)
        _, sent = deliver(kernel, "telegram", "42", "/search invoice", Agent())
        assert len(sent[0]) <= chat_commands.MAX_REPLY
