def test_actions_panel_does_not_render_queue_note_table(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "scheduler_status", lambda: {"loaded": False, "name": "TestTask"})

    response = app_module.app.test_client().get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "打开笔记库" in html
    assert "queue_list" not in html
    assert "queue-table" not in html
    assert "打开 News" not in html
    assert "定位文件" not in html
