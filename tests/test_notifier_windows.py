from types import SimpleNamespace


def test_windows_toast_uses_protocol_activation(monkeypatch, tmp_path):
    from zotero_daily_news import notifier

    hub = tmp_path / "news.html"
    hub.write_text("<h1>News</h1>", encoding="utf-8")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(notifier.subprocess, "run", fake_run)
    monkeypatch.setattr(notifier, "no_window_subprocess_kwargs", lambda: {"creationflags": 123})
    monkeypatch.setattr(notifier, "_register_windows_protocol_handler", lambda: None)

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
    assert kwargs["creationflags"] == 123
    assert kwargs["timeout"] == 15
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["env"]["ZDN_TOAST_APP_ID"] == notifier.WINDOWS_TOAST_APP_ID
    assert kwargs["env"]["ZDN_TOAST_TITLE"] == "Title"
    assert kwargs["env"]["ZDN_TOAST_SUBTITLE"] == "Paper title"
    assert kwargs["env"]["ZDN_TOAST_MESSAGE"] == "Briefing body"
    assert kwargs["env"]["ZDN_TOAST_TARGET"] == "zotero-digest://note/20260627_ITEM123_news?activate=1"
    assert "ToastText02" in cmd[-1]
    assert "ToastGeneric" not in cmd[-1]
    assert 'SetAttribute("activationType", "protocol")' in cmd[-1]
    assert 'SetAttribute("launch", $env:ZDN_TOAST_TARGET)' in cmd[-1]
    assert 'SetAttribute("content", "Open News")' in cmd[-1]
    assert 'SetAttribute("arguments", $env:ZDN_TOAST_TARGET)' in cmd[-1]
    assert "add_Activated" not in cmd[-1]


def test_windows_toast_target_falls_back_to_hub_file(tmp_path):
    from zotero_daily_news import notifier

    hub = tmp_path / "news.html"
    hub.write_text("<h1>News</h1>", encoding="utf-8")

    assert notifier._windows_toast_target(None, hub) == hub.resolve().as_uri()


def test_windows_toast_reports_failure(monkeypatch):
    from zotero_daily_news import notifier

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="toast failed")

    monkeypatch.setattr(notifier.subprocess, "run", fake_run)
    monkeypatch.setattr(notifier, "_register_windows_protocol_handler", lambda: None)

    assert not notifier._notify_windows_toast("Title", "Body", "", False, note_id="NEWS")
