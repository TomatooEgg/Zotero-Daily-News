"""根据通知用户操作，决定发布简报或推迟到下次推送。"""

from __future__ import annotations

from .digest import load_history, record_pushed
from .notifier import is_publish_action
from .pending_publish import publish_note
from .queue_manager import STATUS_PUSHED, load_queue, save_queue


def apply_push_action(
    *,
    item_key: str | None,
    note_id: str | None,
    action: str | None,
    update_queue: bool = True,
) -> bool:
    """用户选择「查看总结」时发布并记入推送历史；否则保持待发布。返回是否已发布。"""
    if not is_publish_action(action):
        return False
    if note_id:
        publish_note(note_id)
    if item_key:
        record_pushed(load_history(), [item_key])
        if update_queue:
            _mark_queue_pushed(item_key)
    return True


def apply_push_results(results: list[dict]) -> int:
    published = 0
    for row in results:
        if apply_push_action(
            item_key=row.get("item_key"),
            note_id=row.get("note_id"),
            action=row.get("action"),
            update_queue=bool(row.get("update_queue", True)),
        ):
            published += 1
    return published


def _mark_queue_pushed(item_key: str) -> None:
    queue = load_queue()
    if not queue:
        return
    changed = False
    for entry in queue.get("items", []):
        if entry.get("item_key") == item_key and entry.get("status") != STATUS_PUSHED:
            entry["status"] = STATUS_PUSHED
            changed = True
    if changed:
        save_queue(queue)
