import importlib


def test_relative_output_dirs_resolve_under_runtime_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("ZOTERO_DAILY_NEWS_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ZOTERO_DAILY_NEWS_CONFIG_DIR", str(tmp_path / "config"))

    import config_manager

    importlib.reload(config_manager)
    cfg = config_manager.load_config()
    summaries_dir, hubs_dir = config_manager.resolve_output_dirs(cfg)

    assert summaries_dir == (tmp_path / "runtime" / "summaries").resolve()
    assert hubs_dir == (tmp_path / "runtime" / "hubs").resolve()
    assert summaries_dir.is_dir()
    assert hubs_dir.is_dir()

    config_manager.save_config(cfg)
    assert (tmp_path / "config" / "config.yaml").is_file()
