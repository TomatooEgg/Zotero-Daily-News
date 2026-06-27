def test_push_queue_does_not_retry_failed_deep_read(monkeypatch, tmp_path):
    from zotero_daily_news import digest, queue_manager

    hub = tmp_path / "news.html"
    hub.write_text("<h1>News</h1>", encoding="utf-8")
    queue = {
        "items": [
            {
                "item_key": "ITEM1",
                "title": "Paper",
                "authors": "Author",
                "has_pdf": True,
                "status": queue_manager.STATUS_READY,
                "deep_read": queue_manager.DEEP_ERROR,
                "note_id": "20260628_ITEM1_news",
                "hub_path": str(hub),
                "briefing": "Briefing",
            }
        ]
    }
    notifications = []

    monkeypatch.setattr(
        queue_manager,
        "queue_settings",
        lambda config=None: {"push_count": 1, "pre_generate_deep_read": True},
    )
    monkeypatch.setattr(queue_manager, "load_config", lambda: {})
    monkeypatch.setattr(queue_manager, "load_queue", lambda: queue)
    monkeypatch.setattr(queue_manager, "save_queue", lambda q: None)
    monkeypatch.setattr(
        queue_manager,
        "_prepare_deep_read_only",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected retry")),
    )
    monkeypatch.setattr(digest, "load_history", lambda: {})
    monkeypatch.setattr(digest, "record_pushed", lambda *args, **kwargs: None)
    monkeypatch.setattr(digest, "emit_notification", lambda **kwargs: notifications.append(kwargs))

    assert queue_manager.push_from_queue(no_notify=True) == 0
    assert notifications
