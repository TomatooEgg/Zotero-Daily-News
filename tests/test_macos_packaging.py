from pathlib import Path


def test_terminal_notifier_execute_uses_frozen_executable(monkeypatch, tmp_path):
    from zotero_daily_news import notifier

    exe = "/Applications/Zotero 简报.app/Contents/Resources/runtime/launcher"
    monkeypatch.setattr(notifier.sys, "frozen", True, raising=False)
    monkeypatch.setattr(notifier.sys, "executable", exe)
    monkeypatch.setattr(notifier, "SCRIPT_DIR", tmp_path)

    command = notifier._terminal_notifier_execute_cmd("NEWS1")

    assert exe in command
    assert "--open-target NEWS1" in command
    assert ".venv" not in command
    assert "python3" not in command


def test_launchd_uses_frozen_executable(monkeypatch, tmp_path):
    from zotero_daily_news import launchd_mgr

    exe = "/Applications/Zotero 简报.app/Contents/Resources/runtime/launcher"
    monkeypatch.setattr(launchd_mgr.sys, "frozen", True, raising=False)
    monkeypatch.setattr(launchd_mgr.sys, "executable", exe)
    monkeypatch.setattr(launchd_mgr, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(launchd_mgr, "logs_dir", lambda: tmp_path / "logs")

    push = launchd_mgr.build_plist({"schedule": [{"hour": 10, "minute": 0}]})
    prepare = launchd_mgr.build_prepare_plist({"schedule": [{"hour": 10, "minute": 0}]})

    assert push["ProgramArguments"] == [exe, "--push-queue"]
    assert prepare["ProgramArguments"] == [exe, "--refresh-queue", "--prepare-queue"]


def test_macos_window_detects_frozen_app_bundle(monkeypatch):
    from zotero_daily_news import macos_window

    exe = "/Applications/Zotero 简报.app/Contents/Resources/runtime/launcher"
    monkeypatch.setattr(macos_window.sys, "frozen", True, raising=False)
    monkeypatch.setattr(macos_window.sys, "executable", exe)

    bundle = macos_window.digest_app_bundle_path()

    assert bundle.name == "Zotero 简报.app"
    assert bundle.parts[-2:] == ("Applications", "Zotero 简报.app")


def test_dmg_script_uses_frozen_runtime_not_bundled_venv():
    script = Path("build_dmg.sh").read_text(encoding="utf-8")

    assert "Contents/Resources/runtime" in script
    assert "Contents/Resources/app/.venv" not in script
    assert 'exec "$EXECUTABLE" "$@"' in script


def test_packaged_entry_routes_smoke_test(monkeypatch):
    from zotero_daily_news import launcher, zotero_daily

    calls = []
    monkeypatch.setattr(launcher, "smoke_test", lambda: calls.append("smoke"))
    monkeypatch.setattr(zotero_daily.sys, "argv", ["launcher", "--smoke-test"])

    zotero_daily.main()

    assert calls == ["smoke"]
