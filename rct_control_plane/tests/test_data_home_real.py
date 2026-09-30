"""
Round 50: where the runtime keeps its data. Tests must never write to a real
runtime's databases (a Desk run showed 271 "learned" skills that were all
test artefacts), and one DELENTIA_HOME must give one audit chain no matter
where the process starts.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import subprocess
from pathlib import Path

from rct_control_plane import data_home


def test_the_test_session_runs_with_an_isolated_home():
    home = data_home.data_home()
    assert home is not None and "delentia-test-home-" in str(home)


def test_legacy_defaults_when_nothing_is_set(monkeypatch):
    for name in ("DELENTIA_HOME", "RCT_DB_PATH", "RCT_AGENTIC_DB_PATH"):
        monkeypatch.delenv(name, raising=False)
    assert data_home.agentic_db_path() == "rct_control_plane_agentic.db"
    assert data_home.control_plane_db_path().endswith("rct_control_plane.db")
    assert data_home.describe()["home"] is None


def test_home_gives_one_place_and_explicit_paths_win(monkeypatch, tmp_path):
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("RCT_DB_PATH", raising=False)
    monkeypatch.delenv("RCT_AGENTIC_DB_PATH", raising=False)
    assert data_home.agentic_db_path() == str(tmp_path / "home" / "agentic.db")
    assert data_home.control_plane_db_path() == str(tmp_path / "home" / "control_plane.db")
    monkeypatch.setenv("RCT_AGENTIC_DB_PATH", str(tmp_path / "x.db"))
    assert data_home.agentic_db_path() == str(tmp_path / "x.db")


def test_a_fresh_process_started_elsewhere_uses_the_same_databases(tmp_path):
    """Two working directories, one DELENTIA_HOME: one file, not two."""
    root = Path(__file__).resolve().parents[2]
    code = ("import logging; logging.disable(logging.CRITICAL);"
            "from rct_control_plane.data_home import agentic_db_path, control_plane_db_path;"
            "import os; print(os.path.abspath(agentic_db_path())); print(os.path.abspath(control_plane_db_path()))")
    outs = []
    for cwd in (tmp_path / "a", tmp_path / "b"):
        cwd.mkdir()
        env = {**os.environ, "DELENTIA_HOME": str(tmp_path / "home"), "PYTHONPATH": str(root)}
        env.pop("RCT_DB_PATH", None)
        env.pop("RCT_AGENTIC_DB_PATH", None)
        outs.append(subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True).stdout.split())
    assert outs[0] == outs[1] and len(outs[0]) == 2 and all(str(tmp_path / "home") in p for p in outs[0])


def test_skill_library_and_persistence_follow_the_home(tmp_path):
    """Checked in a fresh process: reloading the modules in this one would
    replace classes other tests already hold."""
    root = Path(__file__).resolve().parents[2]
    code = ("import logging; logging.disable(logging.CRITICAL);"
            "import rct_control_plane.persistence as p, rct_control_plane.skill_library as s;"
            "print(p._DEFAULT_DB_PATH); print(s._DEFAULT_DB_PATH)")
    env = {**os.environ, "DELENTIA_HOME": str(tmp_path / "h2"), "PYTHONPATH": str(root)}
    env.pop("RCT_DB_PATH", None)
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True).stdout.split()
    assert out == [str(tmp_path / "h2" / "control_plane.db")] * 2
