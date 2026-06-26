from pathlib import Path


def test_python_cmd_uses_frozen_executable_for_digest(monkeypatch):
    import app

    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "executable", r"C:\Apps\Zotero Daily News\Zotero Daily News.exe")
    monkeypatch.setattr(app, "is_apple_silicon", lambda: False)

    cmd = app.python_cmd(str(Path("C:/Apps/Zotero Daily News/digest.py")), "--push-queue")

    assert cmd == [r"C:\Apps\Zotero Daily News\Zotero Daily News.exe", "--push-queue"]


def test_python_bin_prefers_windows_venv_python(monkeypatch, tmp_path):
    import app

    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    monkeypatch.setattr(app.sys, "frozen", False, raising=False)
    monkeypatch.setattr(app, "SCRIPT_DIR", tmp_path)

    assert app.python_bin() == str(venv_python)
