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
