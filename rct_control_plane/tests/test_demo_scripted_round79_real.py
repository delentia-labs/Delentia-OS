"""
Round 79: `delentia demo run compare --scripted` - the demo a newcomer can run with NO model at all (no Ollama, no key).

Real: separate CLI processes, the governed loop, the real file tools confined to the demo folder, the FDIA gate and the untrusted-folder taint, Ed25519 approval, the signed audit chain.
Scripted: only the model. No model is configured for these processes, so if the script were not used the run could not succeed.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def cli(args, env, timeout=600):
    return subprocess.run([sys.executable, "-m", "rct_control_plane.cli", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, env=env, timeout=timeout)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("scripted_demo")
    root = base / "delentia-demo"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "USERPROFILE": str(base / "home"), "HOME": str(base / "home"),
           "DELENTIA_MODEL_CONFIG": str(base / "no-model.json"), "DELENTIA_LLM_PROVIDER": "openai-compat", "DELENTIA_LLM_MODEL": "nothing-is-listening",
           "DELENTIA_LLM_RETRY_BACKOFF": "0.01", "DELENTIA_LLM_RETRIES": "0"}
    for name in ("DELENTIA_HOME", "DELENTIA_REPO_ROOT", "DELENTIA_UNTRUSTED_PATHS", "DELENTIA_APPROVERS_FILE", "DELENTIA_AUDIT_SIGNING_KEY", "DELENTIA_WARM_RECALL", "RCT_DB_PATH",
                 "RCT_AGENTIC_DB_PATH", "DELENTIA_API_TOKEN", "DELENTIA_OPENAI_COMPAT_BASE_URL"):
        env.pop(name, None)
    init = cli(["demo", "init", "--dir", str(root)], env)
    assert init.returncode == 0, init.stderr[-600:]
    return {"root": root, "env": env, "init": init}


@pytest.fixture(scope="module")
def compare_run(world):
    return cli(["demo", "run", "compare", "--scripted", "--dir", str(world["root"])], world["env"])


class TestScriptedDemo:
    def test_init_points_a_newcomer_at_the_model_free_path(self, world):
        assert "--scripted" in world["init"].stdout

    def test_compare_runs_without_any_model_and_every_check_passes(self, world, compare_run):
        out = compare_run.stdout
        assert compare_run.returncode == 0, (out[-1500:], compare_run.stderr[-600:])
        assert out.count("- `delentia_read_repo_file` {") == 3
        assert "ไม่ผ่าน" not in out and out.count("ผ่าน:") >= 5
        assert "ครบสมบูรณ์" in out and "บางกอกเทคนิค" in out and "เกินงบ" in out

    def test_the_report_says_the_model_is_scripted(self, world, compare_run):
        text = sorted((world["root"] / "results").glob("*compare*.md"))[-1].read_text(encoding="utf-8")
        assert "สคริปต์ (ไม่ใช่โมเดลจริง)" in text and "ไม่ได้บอกอะไรเกี่ยวกับความสามารถของโมเดลใด" in text

    def test_reading_the_quotes_still_counts_as_reading_outside_text(self, world, compare_run):
        text = sorted((world["root"] / "results").glob("*compare*.md"))[-1].read_text(encoding="utf-8")
        assert "อ่านข้อความจากภายนอก" in text

    def test_without_scripted_and_with_a_model_that_is_not_running_the_run_fails_and_suggests_the_scripted_path(self, world):
        env = {k: v for k, v in world["env"].items() if k not in ("DELENTIA_LLM_PROVIDER", "DELENTIA_LLM_MODEL")}
        env.update({"DELENTIA_LLM_PROVIDER": "ollama", "DELENTIA_OLLAMA_URL": "http://127.0.0.1:9"})
        run = cli(["demo", "run", "compare", "--dir", str(world["root"])], env)
        assert "llm_error" in run.stdout and "--scripted" in run.stdout

    def test_a_half_configured_model_gives_a_message_not_a_traceback(self, world):
        run = cli(["demo", "run", "compare", "--dir", str(world["root"])], world["env"])          # provider openai-compat without an endpoint
        assert run.returncode == 2 and "Traceback" not in run.stdout + run.stderr and "--scripted" in run.stdout

    def test_goals_that_need_a_real_model_are_refused_not_faked(self, world):
        run = cli(["demo", "run", "remember", "--scripted", "--dir", str(world["root"])], world["env"])
        assert run.returncode != 0 and "compare, budget, edit" in (run.stdout + run.stderr)


class TestScriptedEditStopsForASignature:
    def test_edit_waits_then_changes_the_file_only_after_the_signature(self, world):
        root, env = world["root"], world["env"]
        quote = root / "workspace/quotes/vendor_a.md"
        before = quote.read_text(encoding="utf-8")
        run = cli(["demo", "run", "edit", "--scripted", "--dir", str(root)], env)
        assert "pending_approval" in run.stdout, (run.stdout[-1200:], run.stderr[-600:])
        assert quote.read_text(encoding="utf-8") == before                                   # nothing written before a person signs
        approval = [line for line in run.stdout.splitlines() if "demo approve" in line and "--scripted" in line][-1].split("approve")[1].split()[0]
        done = cli(["demo", "approve", approval, "--scripted", "--dir", str(root)], env)
        assert done.returncode == 0, (done.stdout[-1200:], done.stderr[-600:])
        assert "ราคารวม: 14,000 บาท" in quote.read_text(encoding="utf-8")
        assert "quotes/vendor_a.md" in done.stdout and "ครบสมบูรณ์" in done.stdout and "None — None" not in done.stdout
        again = cli(["demo", "approve", approval, "--scripted", "--dir", str(root)], env)    # at most once
        assert again.returncode != 0 or "ไม่พบ" in (again.stdout + again.stderr) or "already" in (again.stdout + again.stderr).lower() or "ใช้ไปแล้ว" in (again.stdout + again.stderr)
        # Round 92: the refusal is a plain message, not a Python traceback, and the file was not written a second time
        assert "Traceback" not in again.stderr and "EXECUTED" in again.stderr and "ครั้งเดียว" in again.stderr, again.stderr[-600:]
        assert "None USD" not in done.stdout
