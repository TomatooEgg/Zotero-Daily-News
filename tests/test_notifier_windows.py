from types import SimpleNamespace


def test_windows_toast_runs_hidden_and_reports_success(monkeypatch, tmp_path):
    import notifier

    hub = tmp_path / "news.html"
    hub.write_text("<h1>News</h1>", encoding="utf-8")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(notifier.subprocess, "run", fake_run)
    monkeypatch.setattr(notifier, "no_window_subprocess_kwargs", lambda: {"creationflags": 123})

    ok = notifier._notify_windows_toast(
        "Title",
        "Briefing body",
        "Paper title",
        True,
        note_id="20260627_ITEM123_news",
        hub_path=hub,
    )

    assert ok
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd[:2] == ["powershell.exe", "-NoProfile"]
    assert "-WindowStyle" in cmd
    assert "Hidden" in cmd
    assert kwargs["creationflags"] == 123
    assert kwargs["timeout"] == 15
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["env"]["ZDN_TOAST_TITLE"] == "Title"
    assert kwargs["env"]["ZDN_TOAST_SUBTITLE"] == "Paper title"
    assert kwargs["env"]["ZDN_TOAST_MESSAGE"] == "Briefing body"
    assert "ZDN_TOAST_TARGET" not in kwargs["env"]


def test_windows_toast_reports_failure(monkeypatch):
    import notifier

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="toast failed")

    monkeypatch.setattr(notifier.subprocess, "run", fake_run)

    assert not notifier._notify_windows_toast("Title", "Body", "", False)
