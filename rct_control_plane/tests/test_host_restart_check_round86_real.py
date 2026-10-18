"""
Round 86, H25 of `delentia host-check`: is "restart" a real restart on this machine?

Found on the Architect's PC: after "rebooting" on the 18th the kernel's boot time still said the 16th. Windows' Fast startup turns "Shut down" into a hibernate, so a task set to run at startup does not
run again and a recovery test done with "Shut down" proves nothing. The check reads the one registry value that decides it.
"""
from __future__ import annotations

from rct_control_plane import host_check


def test_fast_startup_on_is_a_warning_that_says_how_to_test_properly(monkeypatch):
    monkeypatch.setattr(host_check, "_fast_startup_enabled", lambda: True)
    (check,) = host_check.check_restart_behaviour()
    assert check.id == "H25" and check.status == host_check.WARN
    assert "Restart" in check.fix and "powercfg" in check.fix and "does not restart the kernel" in check.detail


def test_fast_startup_off_passes(monkeypatch):
    monkeypatch.setattr(host_check, "_fast_startup_enabled", lambda: False)
    (check,) = host_check.check_restart_behaviour()
    assert check.status == host_check.PASS


def test_a_machine_where_it_cannot_be_read_says_nothing(monkeypatch):
    monkeypatch.setattr(host_check, "_fast_startup_enabled", lambda: None)
    assert host_check.check_restart_behaviour() == []


def test_the_check_is_part_of_the_run(monkeypatch):
    monkeypatch.setattr(host_check, "_fast_startup_enabled", lambda: True)
    ids = {c.id for c in host_check.run_checks(public=False)}
    assert "H25" in ids


def test_the_real_registry_read_does_not_raise():
    assert host_check._fast_startup_enabled() in (True, False, None)
