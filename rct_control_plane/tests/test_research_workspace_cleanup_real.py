"""A finished research run must not redirect later file tools or grounding."""
import asyncio
import os

import pytest

from research.runner import Harness
from rct_control_plane import data_evidence, mcp_server


@pytest.mark.parametrize("existing_env", [False, True])
@pytest.mark.parametrize("cleanup_error", [False, True])
def test_closed_harness_restores_real_file_access(tmp_path, monkeypatch, existing_env, cleanup_error):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    original = tmp_path / "original"
    original.mkdir()
    (original / "pyproject.toml").write_text('[project]\nname = "original-project"\n')
    monkeypatch.setattr(mcp_server, "REPO_ROOT", original)
    if existing_env:
        monkeypatch.setenv("DELENTIA_REPO_ROOT", str(original))
    else:
        monkeypatch.delenv("DELENTIA_REPO_ROOT", raising=False)
    before = dict(os.environ)

    harness = Harness(tmp_path / "run", "diligent")
    harness.start()
    assert mcp_server.REPO_ROOT == (tmp_path / "run/repo").resolve()
    if cleanup_error:
        real_exit = harness.model.__exit__

        def close_then_raise(*args):
            real_exit(*args)
            raise RuntimeError("model cleanup failed")

        monkeypatch.setattr(harness.model, "__exit__", close_then_raise)
        with pytest.raises(RuntimeError, match="model cleanup failed"):
            harness.close()
    else:
        harness.close()

    # Exercise the real file tool and the actual grounding estimator: later
    # episodes must see the original workspace rather than the run's fixtures.
    content = asyncio.run(mcp_server.delentia_read_repo_file("pyproject.toml"))
    assert "original-project" in str(content)
    evidence = data_evidence.assess(
        "Read the file pyproject.toml in the repository", clarity=1.0,
        workspace_root=mcp_server.REPO_ROOT,
    )
    assert evidence.parts["grounding"] == 1.0
    assert os.environ.get("DELENTIA_REPO_ROOT") == (str(original) if existing_env else None)
    # Report names only if cleanup leaks a setting; never expose credential values.
    changed_names = sorted(name for name in set(before) | set(os.environ)
                           if before.get(name) != os.environ.get(name))
    assert not changed_names
