def test_queue_refresh_error_is_logged(monkeypatch):
    from zotero_daily_news import app as app_module
    from zotero_daily_news import queue_manager

    logged: list[str] = []

    def fail_refresh(*args, **kwargs):
        raise RuntimeError("无法连接 Zotero 本地 API")

    monkeypatch.setattr(queue_manager, "refresh_queue", fail_refresh)
    monkeypatch.setattr(app_module.app.logger, "exception", lambda msg: logged.append(msg))

    response = app_module.app.test_client().post("/api/queue/refresh", json={"force": True})

    assert response.status_code == 500
    assert response.get_json() == {"error": "无法连接 Zotero 本地 API"}
    assert logged == ["刷新待推清单失败"]
