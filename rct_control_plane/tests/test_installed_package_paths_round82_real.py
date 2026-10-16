"""
Round 82: an installed package never keeps its data inside site-packages.

Found by the install-contract check on Linux (a read-only package folder): `GroundTruthStore()` opened `<site-packages>/ground_truth_store.db` and failed with
"attempt to write a readonly database"; `topic_cache` and the control-plane store defaulted to the repository root, which for an installed package is the same folder (a writable
install would have kept the person's data where an upgrade or uninstall deletes it). From a source checkout nothing moves.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pathlib import Path

import pytest

from rct_control_plane import data_home


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    for name in ("DELENTIA_HOME", "RCT_DB_PATH", "RCT_AGENTIC_DB_PATH", "GROUND_TRUTH_DB_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))


def installed(monkeypatch, tmp_path):
    site = tmp_path / "site-packages"
    site.mkdir()
    monkeypatch.setattr(data_home, "_REPO_ROOT", site)            # no pyproject.toml beside the package: this is what an installed package looks like
    return site


def test_a_source_checkout_keeps_its_legacy_paths(monkeypatch):
    assert data_home.is_source_checkout()
    assert data_home.control_plane_db_path().endswith("rct_control_plane.db") and Path(data_home.control_plane_db_path()).parent == data_home._REPO_ROOT
    assert data_home.agentic_db_path() == "rct_control_plane_agentic.db"


def test_an_installed_package_keeps_everything_out_of_its_own_folder(monkeypatch, tmp_path):
    site = installed(monkeypatch, tmp_path)
    assert not data_home.is_source_checkout()
    for path in (data_home.control_plane_db_path(), data_home.agentic_db_path(), data_home.legacy_default("ground_truth_store.db")):
        resolved = Path(path).resolve()
        assert not resolved.is_relative_to(site.resolve()), path
        assert resolved.is_relative_to((tmp_path / "user").resolve()), path


def test_delentia_home_and_explicit_paths_still_win(monkeypatch, tmp_path):
    installed(monkeypatch, tmp_path)
    monkeypatch.setenv("DELENTIA_HOME", str(tmp_path / "home"))
    assert data_home.control_plane_db_path() == str(tmp_path / "home" / "control_plane.db")
    monkeypatch.setenv("RCT_DB_PATH", str(tmp_path / "x.db"))
    assert data_home.control_plane_db_path() == str(tmp_path / "x.db")


def test_the_ground_truth_store_and_topic_cache_resolve_through_the_same_rules(monkeypatch, tmp_path):
    import importlib

    from rct_control_plane import ground_truth_store, topic_cache
    site = installed(monkeypatch, tmp_path)
    try:
        importlib.reload(ground_truth_store)
        importlib.reload(topic_cache)
        for path in (ground_truth_store._DEFAULT_DB_PATH, topic_cache._DEFAULT_DB_PATH):
            assert not Path(path).resolve().is_relative_to(site.resolve()), path
    finally:
        monkeypatch.undo()
        importlib.reload(ground_truth_store)
        importlib.reload(topic_cache)


def test_a_store_in_a_readonly_package_folder_still_works(monkeypatch, tmp_path):
    """The failure the CI check saw, reproduced without needing Linux: the package folder cannot be written, the store must not try."""
    import importlib

    from rct_control_plane import ground_truth_store
    installed(monkeypatch, tmp_path)
    try:
        importlib.reload(ground_truth_store)
        store = ground_truth_store.GroundTruthStore()
        assert store.check_claim("eiffel tower", "construction_completed_year", "1889")
        assert Path(store.db_path).is_relative_to((tmp_path / "user").resolve()) or Path(store.db_path).resolve().is_relative_to((tmp_path / "user").resolve())
    finally:
        monkeypatch.undo()
        importlib.reload(ground_truth_store)
