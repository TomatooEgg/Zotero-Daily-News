def test_list_notes_can_include_pending(monkeypatch, tmp_path):
    import notes_index

    summaries = tmp_path / "summaries"
    hubs = tmp_path / "hubs"
    summaries.mkdir()
    hubs.mkdir()
    note_id = "20260627_ITEM123_pending-news"
    (summaries / f"{note_id}.md").write_text(
        "# Pending News\n\n> **头条简报**：Generated but not clicked yet.\n",
        encoding="utf-8",
    )
    (hubs / f"{note_id}.html").write_text("<h1>Pending News</h1>", encoding="utf-8")

    monkeypatch.setattr(notes_index, "load_config", lambda: {})
    monkeypatch.setattr(notes_index, "resolve_output_dirs", lambda _cfg: (summaries, hubs))
    monkeypatch.setattr(notes_index, "is_pending", lambda stem: stem == note_id)

    assert notes_index.list_notes() == []

    entries = notes_index.list_notes(include_pending=True)
    assert len(entries) == 1
    assert entries[0].id == note_id
    assert entries[0].pending is True
    assert entries[0].to_dict()["pending"] is True
