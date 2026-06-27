def test_windows_toast_starts_hidden_listener_with_target(monkeypatch, tmp_path):
    import notifier

    hub = tmp_path / "news.html"
    hub.write_text("<h1>News</h1>", encoding="utf-8")
    calls = []

    def fake_popen(cmd, **kwargs):
        calls.append((cmd, kwargs))

        class Proc:
            pass

        return Proc()

    monkeypatch.setattr(notifier.subprocess, "Popen", fake_popen)
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
    assert kwargs["env"]["ZDN_TOAST_TARGET"] == str(hub.resolve())
    assert kwargs["env"]["ZDN_TOAST_TITLE"] == "Title"
    assert kwargs["env"]["ZDN_TOAST_SUBTITLE"] == "Paper title"
    assert kwargs["env"]["ZDN_TOAST_MESSAGE"] == "Briefing body"
