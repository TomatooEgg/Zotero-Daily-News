from pathlib import Path


def test_python_cmd_uses_frozen_executable_for_digest(monkeypatch):
    from zotero_daily_news import app

    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "executable", r"C:\Apps\Zotero Daily News\Zotero Daily News.exe")
    monkeypatch.setattr(app, "is_apple_silicon", lambda: False)

    cmd = app.python_cmd(str(Path("C:/Apps/Zotero Daily News/digest.py")), "--push-queue")

    assert cmd == [r"C:\Apps\Zotero Daily News\Zotero Daily News.exe", "--push-queue"]


def test_python_bin_prefers_windows_venv_python(monkeypatch, tmp_path):
    from zotero_daily_news import app

    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    monkeypatch.setattr(app.sys, "frozen", False, raising=False)
    monkeypatch.setattr(app, "SCRIPT_DIR", tmp_path)

    assert app.python_bin() == str(venv_python)


def test_python_module_cmd_uses_module_in_source(monkeypatch):
    from zotero_daily_news import app

    monkeypatch.setattr(app.sys, "frozen", False, raising=False)
    monkeypatch.setattr(app, "is_apple_silicon", lambda: False)
    monkeypatch.setattr(app, "python_bin", lambda: "python")

    cmd = app.python_module_cmd("zotero_daily_news.digest", "--push-queue")

    assert cmd == ["python", "-m", "zotero_daily_news.digest", "--push-queue"]


def test_python_subprocess_env_forces_utf8(monkeypatch):
    from zotero_daily_news import app

    monkeypatch.setattr(app, "load_env", lambda: {})
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("PYTHONUTF8", raising=False)

    env = app.python_subprocess_env()

    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"


def test_display_subprocess_stdout_hides_notify_protocol():
    from zotero_daily_news import app

    stdout = '@@NOTIFY@@{"title":"x"}\n待确认: 中文标题\n'

    assert app.display_subprocess_stdout(stdout) == "待确认: 中文标题"
