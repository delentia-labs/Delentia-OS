"""
Round 61: trajectories - opt-in, local, redacted records of what episodes did.

Real episodes through the real governed loop write real files in a temp data home; the redaction is checked on realistic secrets; the export filters and the CLI are the real ones.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import json

import pytest
from click.testing import CliRunner

import measure_injection_defence as mid
import rct_control_plane.autonomous_loop as al
from rct_control_plane import trajectories
from rct_control_plane.cli import cli
from rct_control_plane.governed_autonomous_loop import GovernedAutonomousLoop
from rct_control_plane.persistence import ControlPlanePersistence
from rct_control_plane.skill_library import SkillLibrary
from test_governed_autonomous_loop_real import _FakeKernel

run = asyncio.run


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(trajectories.ENV, raising=False)


class TestRedaction:
    @pytest.mark.parametrize("secret", [
        "sk-or-v1-abcdef1234567890abcdef", "ghp_abcdefghijklmnopqrstuvwxyz0123", "xoxb-1234567890-abcdefghij", "AKIAABCDEFGHIJKLMNOP", "Bearer abcdefghijklmnop1234567890",
        'api_key = "hunter2hunter2"', "password: correcthorsebattery", "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----",
    ])
    def test_secrets_are_replaced(self, secret):
        out = trajectories.redact(f"the config says {secret} and that is all")
        assert "[secret]" in out and secret.split()[-1] not in out

    def test_emails_phones_and_long_numbers_are_replaced_and_short_numbers_are_not(self):
        out = trajectories.redact("mail bob@example.org or call +66 81 234 5678, card 4111 1111 1111 1111, we sold 42 items in 2026")
        assert "[email]" in out and "bob@" not in out and "234 5678" not in out and "4111" not in out and "42 items in 2026" in out

    def test_long_text_is_clipped_and_says_so(self):
        out = trajectories.redact("word " * 3000, limit=100)
        assert len(out) < 200 and "cut" in out

    def test_a_structure_is_redacted_as_text(self):
        assert "[secret]" in trajectories.redact({"headers": {"Authorization": "Bearer abcdefghijklmnop1234567890"}})


def one_episode(tmp_path, monkeypatch, goal, calls=(), results=None, namespace="telegram-42", answer="Here is the answer."):
    script = list(calls)

    async def model(g, history, available_tools, llm_provider=None, extra_context=""):
        i = len(history)
        if i < len(script):
            return {"action": "call_tool", "tool_name": script[i][0], "tool_args": script[i][1], "reasoning": "step"}
        return {"action": "finish", "reasoning": "done", "final_answer": answer, "tool_name": None, "tool_args": {}}
    monkeypatch.setattr(al, "decide_next_action", model)
    persistence = ControlPlanePersistence(db_path=str(tmp_path / "t.db"))
    mcp = mid.RecordingMCP(lambda n, a: (results or {}).get(n, json.dumps({"ok": True})))
    loop = GovernedAutonomousLoop(mcp_server=mcp, persistence=persistence, kernel=_FakeKernel(), max_iterations=4, namespace=namespace, route=False,
                                  skill_library=SkillLibrary(db_path=str(tmp_path / "sk.db")))
    return run(loop.run(goal))


class TestRecording:
    def test_off_by_default_nothing_is_written(self, tmp_path, monkeypatch):
        one_episode(tmp_path, monkeypatch, "Read the notes")
        assert not list((tmp_path / "home").glob("trajectories/*.jsonl"))

    def test_on_each_episode_is_one_redacted_line_with_its_steps(self, tmp_path, monkeypatch):
        monkeypatch.setenv(trajectories.ENV, "1")
        one_episode(tmp_path, monkeypatch, "Read notes.txt, my email is ann@example.org", calls=[("delentia_read_repo_file", {"relative_path": "notes.txt"})],
                    results={"delentia_read_repo_file": json.dumps({"content": "deploy key: api_key=abcDEF1234567 and call 0812345678"})})
        files = list((tmp_path / "home").glob("trajectories/*.jsonl"))
        assert len(files) == 1
        rows = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        row = rows[0]
        text = json.dumps(row)
        assert "ann@example.org" not in text and "abcDEF1234567" not in text and "0812345678" not in text
        assert row["steps"][0]["tool"] == "delentia_read_repo_file" and row["stopped_reason"] == "llm_finished" and row["tainted"] is False
        assert row["person"].startswith("p-") and "telegram-42" not in text

    def test_a_tainted_episode_is_marked(self, tmp_path, monkeypatch):
        monkeypatch.setenv(trajectories.ENV, "1")
        one_episode(tmp_path, monkeypatch, "Summarise https://example.org/x", calls=[("delentia_crawl_url", {"url": "https://example.org/x"})],
                    results={"delentia_crawl_url": json.dumps({"text": "a harmless page about gardening"})})
        row = next(trajectories._rows())
        assert row["tainted"] is True

    def test_a_recording_failure_never_changes_the_episode(self, tmp_path, monkeypatch):
        monkeypatch.setenv(trajectories.ENV, "1")
        monkeypatch.setattr(trajectories, "directory", lambda: (_ for _ in ()).throw(OSError("disk full")))
        out = one_episode(tmp_path, monkeypatch, "Read the notes")
        assert out["stopped_reason"] == "llm_finished"


class TestExport:
    def _record_three(self, tmp_path, monkeypatch):
        monkeypatch.setenv(trajectories.ENV, "1")
        one_episode(tmp_path, monkeypatch, "Read notes.txt and tell me what it says about the project", calls=[("delentia_read_repo_file", {"relative_path": "notes.txt"})],
                    results={"delentia_read_repo_file": json.dumps({"content": "The project is called Atlas and ships in May."})}, answer="The project is called Atlas and ships in May.")
        one_episode(tmp_path, monkeypatch, "Summarise https://example.org/x", calls=[("delentia_crawl_url", {"url": "https://example.org/x"})],
                    results={"delentia_crawl_url": json.dumps({"text": "a harmless page about gardening"})})
        one_episode(tmp_path, monkeypatch, "Create a file a.txt", answer="Created a.txt successfully.", namespace="telegram-43")      # an invented action: not verified (another person: taint travels with a conversation)

    def test_filters(self, tmp_path, monkeypatch):
        self._record_three(tmp_path, monkeypatch)
        stats = trajectories.stats()
        assert stats["episodes"] == 3 and stats["tainted"] == 1 and stats["verified"] == 1
        everything = trajectories.export(str(tmp_path / "all.jsonl"))
        verified = trajectories.export(str(tmp_path / "ok.jsonl"), verified_only=True)
        clean = trajectories.export(str(tmp_path / "clean.jsonl"), exclude_tainted=True)
        assert (everything["written"], verified["written"], clean["written"]) == (3, 1, 2)

    def test_it_will_not_overwrite_a_file(self, tmp_path, monkeypatch):
        self._record_three(tmp_path, monkeypatch)
        trajectories.export(str(tmp_path / "x.jsonl"))
        with pytest.raises(FileExistsError):
            trajectories.export(str(tmp_path / "x.jsonl"))

    def test_cli(self, tmp_path, monkeypatch):
        self._record_three(tmp_path, monkeypatch)
        r = CliRunner()
        shown = r.invoke(cli, ["trajectories", "stats"]).output
        assert "3 episode(s)" in shown and "delentia_read_repo_file" in shown
        done = r.invoke(cli, ["trajectories", "export", str(tmp_path / "out.jsonl"), "--exclude-tainted", "--verified-only"])
        assert done.exit_code == 0 and "wrote 1 episode(s)" in done.output
        again = r.invoke(cli, ["trajectories", "export", str(tmp_path / "out.jsonl")])
        assert again.exit_code == 1 and "already exists" in again.output
