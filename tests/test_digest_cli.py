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


def test_cli_runtime_error_is_user_facing_and_logged(monkeypatch, capsys, tmp_path):
    from zotero_daily_news import digest, queue_manager

    message = "无法连接 Zotero 本地 API。请确认 Zotero 已启动"

    def fail_refresh(*args, **kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(digest.sys, "argv", ["digest.py", "--refresh-queue"])
    monkeypatch.setattr(queue_manager, "refresh_queue", fail_refresh)
    monkeypatch.setenv("ZOTERO_DAILY_NEWS_RUNTIME_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exc:
        digest.main()

    captured = capsys.readouterr()
    log_path = tmp_path / "logs" / "stderr.log"
    assert exc.value.code == 1
    assert f"错误: {message}" in captured.err
    assert f"详细日志: {log_path}" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" in log_path.read_text(encoding="utf-8")
    assert message in log_path.read_text(encoding="utf-8")
