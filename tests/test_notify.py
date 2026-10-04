import subprocess

from sort_sys_alpha import notify as notify_module
from sort_sys_alpha.notify import notify


def test_notify_is_a_noop_on_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(notify_module.platform, "system", lambda: "Linux")
    calls = []
    monkeypatch.setattr(notify_module.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    notify("title", "message")
    assert calls == []


def test_notify_invokes_powershell_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(notify_module.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(notify_module.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    notify("sort-sys-alpha", "moved 3, held 1")

    assert len(calls) == 1
    args, kwargs = calls[0]
    command = args[0]
    assert command[0] == "powershell.exe"
    assert str(notify_module.NOTIFY_SCRIPT) in command
    assert "sort-sys-alpha" in command
    assert "moved 3, held 1" in command
    assert kwargs["timeout"] == 10


def test_notify_swallows_failures(monkeypatch) -> None:
    monkeypatch.setattr(notify_module.platform, "system", lambda: "Windows")

    def _boom(*_a, **_k):
        raise FileNotFoundError("powershell.exe not found")

    monkeypatch.setattr(notify_module.subprocess, "run", _boom)

    notify("title", "message")  # must not raise


def test_notify_swallows_timeout(monkeypatch) -> None:
    monkeypatch.setattr(notify_module.platform, "system", lambda: "Windows")

    def _timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="powershell.exe", timeout=10)

    monkeypatch.setattr(notify_module.subprocess, "run", _timeout)

    notify("title", "message")  # must not raise
