from scripts.watchdog import pid_alive


def test_pid_alive_treats_stale_windows_pid_as_dead():
    assert pid_alive(2147483647) is False


def test_pid_alive_handles_windows_system_error(monkeypatch):
    import os

    def fail_kill(_pid, _sig):
        raise SystemError("simulated Windows pid lookup failure")

    monkeypatch.setattr(os, "kill", fail_kill)
    assert pid_alive(12345) is False
