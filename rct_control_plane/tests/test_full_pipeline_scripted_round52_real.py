"""
Round 52: the whole system against a model that behaves exactly as scripted
(scripts/full_pipeline_cases.py). The harness runs once in a fresh process (real kernel, real
tools on a temporary git repo, real SQLite, real subprocess subagents in real git worktrees,
a real HTTP model endpoint); each case is then asserted here by name, so a failure says which
part of the Constitutional Cycle broke.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from rct_control_plane.autonomous_loop import _describe_llm_error, _is_transient_llm_error

ROOT = Path(__file__).resolve().parent.parent.parent

CASE_CODES = ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11", "C12", "C13", "C14", "C15", "C16"]


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    out = tmp_path_factory.mktemp("pipeline") / "report.json"
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "full_pipeline_cases.py"), "--json", str(out)],
                          cwd=ROOT, capture_output=True, text=True, timeout=1500,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(ROOT)})
    assert out.exists(), f"the harness did not finish:\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}"
    return {r["case"]: r for r in json.loads(out.read_text(encoding="utf-8"))}


@pytest.mark.parametrize("code", CASE_CODES)
def test_pipeline_case(report, code):
    result = report[code]
    failed = [f"{c['check']}: {c['detail']}" for c in result["checks"] if not c["ok"]]
    assert result["ok"], f"{code} {result['title']}\n  " + "\n  ".join(failed)
    assert len(result["checks"]) >= 2


# ------------------------------------------------------------ the pieces the harness leans on

def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://example.test/v1/chat/completions")
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(code, request=request))


@pytest.mark.parametrize("code,transient", [(429, True), (500, True), (502, True), (503, True), (504, True),
                                             (400, False), (401, False), (403, False), (404, False)])
def test_only_transient_http_statuses_are_retried(code, transient):
    assert _is_transient_llm_error(_status_error(code)) is transient


def test_connection_problems_are_retried_but_programming_errors_are_not():
    assert _is_transient_llm_error(httpx.ConnectError("refused"))
    assert _is_transient_llm_error(httpx.ReadTimeout("slow"))
    assert not _is_transient_llm_error(KeyError("choices"))
    assert not _is_transient_llm_error(ValueError("bad"))


def test_the_error_note_never_contains_the_request():
    text = _describe_llm_error(_status_error(503))
    assert text == "model endpoint answered HTTP 503"
    assert "example.test" not in text
    assert "KeyError" in _describe_llm_error(KeyError("choices"))
