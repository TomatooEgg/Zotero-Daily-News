def test_load_dotenv_prefers_user_env_file(monkeypatch, tmp_path):
    from zotero_daily_news.digest import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-key")

    load_dotenv(env_file)

    assert __import__("os").environ["DEEPSEEK_API_KEY"] == "file-key"


def test_zotero_credentials_prefer_user_env_file(monkeypatch, tmp_path):
    from zotero_daily_news import zotero_credentials

    env_file = tmp_path / ".env"
    env_file.write_text("ZOTERO_API_KEY=file-zotero\nZOTERO_LIBRARY_ID=42\n", encoding="utf-8")
    monkeypatch.setattr(zotero_credentials, "ENV_PATH", env_file)
    monkeypatch.setenv("ZOTERO_API_KEY", "process-zotero")
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)

    assert zotero_credentials.get_zotero_credentials() == {
        "api_key": "file-zotero",
        "library_id": "42",
    }
