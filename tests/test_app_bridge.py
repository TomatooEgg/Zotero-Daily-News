def test_navigate_to_note_passes_activate_as_keyword():
    from zotero_daily_news import app_bridge

    calls = []

    def callback(note_id: str, *, activate: bool = True) -> bool:
        calls.append((note_id, activate))
        return True

    app_bridge.set_navigate_to_note(callback)
    try:
        assert app_bridge.navigate_to_note("NOTE1", activate=False) == (True, False)
        assert calls == [("NOTE1", False)]
    finally:
        app_bridge.set_navigate_to_note(None)


def test_navigate_to_note_keeps_tuple_result():
    from zotero_daily_news import app_bridge

    def callback(note_id: str, *, activate: bool = True) -> tuple[bool, bool]:
        return False, True

    app_bridge.set_navigate_to_note(callback)
    try:
        assert app_bridge.navigate_to_note("NOTE1") == (False, True)
    finally:
        app_bridge.set_navigate_to_note(None)
