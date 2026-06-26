from pathlib import Path


def test_windows_scheduler_uses_powershell_scripts(monkeypatch, tmp_path):
    import scheduler

    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **_kwargs):
        calls.append([str(part) for part in cmd])
        return Result()

    monkeypatch.setattr(scheduler.sys, "platform", "win32")
    monkeypatch.setattr(scheduler, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)

    ok, message = scheduler.reload_scheduler(
        {
            "count": 2,
            "schedule": [{"hour": 12, "minute": 1}],
            "queue": {"prepare_before_minutes": 30},
        }
    )

    assert ok, message
    create_calls = [cmd for cmd in calls if "/Create" in cmd]
    assert any("run.ps1" in " ".join(cmd) and "--push-queue" in " ".join(cmd) for cmd in create_calls)
    assert any("prepare_queue.ps1" in " ".join(cmd) for cmd in create_calls)
    assert any("12:01" in cmd for cmd in create_calls)
    assert any("11:31" in cmd for cmd in create_calls)


def test_windows_scheduler_uses_frozen_executable(monkeypatch, tmp_path):
    import scheduler

    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **_kwargs):
        calls.append([str(part) for part in cmd])
        return Result()

    monkeypatch.setattr(scheduler.sys, "platform", "win32")
    monkeypatch.setattr(scheduler.sys, "frozen", True, raising=False)
    monkeypatch.setattr(scheduler.sys, "executable", str(Path("C:/Apps/Zotero Daily News/Zotero Daily News.exe")))
    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)

    ok, message = scheduler.reload_scheduler(
        {
            "count": 1,
            "schedule": [{"hour": 9, "minute": 0}],
            "queue": {"prepare_before_minutes": 120},
        }
    )

    assert ok, message
    create_commands = [" ".join(cmd) for cmd in calls if "/Create" in cmd]
    assert any("Zotero Daily News.exe" in cmd and "--push-queue" in cmd for cmd in create_commands)
    assert any("Zotero Daily News.exe" in cmd and "--prepare-queue" in cmd for cmd in create_commands)
