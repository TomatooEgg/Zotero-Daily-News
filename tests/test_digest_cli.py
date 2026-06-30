import pytest


def test_push_queue_cli_uses_package_queue_manager(monkeypatch):
    from zotero_daily_news import digest, queue_manager

    calls: list[str] = []

    monkeypatch.setattr(digest.sys, "argv", ["digest.py", "--no-notify", "--push-queue"])
    monkeypatch.setattr(queue_manager, "load_queue", lambda: {"items": [{"status": "ready"}]})
    monkeypatch.setattr(queue_manager, "refresh_queue", lambda *args, **kwargs: calls.append("refresh"))
    monkeypatch.setattr(queue_manager, "prepare_queue", lambda *args, **kwargs: calls.append("prepare"))
    monkeypatch.setattr(queue_manager, "push_from_queue", lambda *args, **kwargs: 0)

    with pytest.raises(SystemExit) as exc:
        digest.main()

    assert exc.value.code == 0
    assert calls == []


def test_cli_runtime_error_is_user_facing(monkeypatch, capsys):
    from zotero_daily_news import digest, queue_manager

    message = "无法连接 Zotero 本地 API。请确认 Zotero 已启动"

    def fail_refresh(*args, **kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(digest.sys, "argv", ["digest.py", "--refresh-queue"])
    monkeypatch.setattr(queue_manager, "refresh_queue", fail_refresh)

    with pytest.raises(SystemExit) as exc:
        digest.main()

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert f"错误: {message}" in captured.err
    assert "Traceback" not in captured.err
