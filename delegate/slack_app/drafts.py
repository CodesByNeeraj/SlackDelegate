_drafts = {}


def save_draft(draft_id: str, tasks: list, transcript_id: str, channel_id: str):
    _drafts[draft_id] = {
        "tasks": tasks,
        "transcript_id": transcript_id,
        "channel_id": channel_id,
        "message_ts": None,
    }


def get_draft(draft_id: str) -> dict | None:
    return _drafts.get(draft_id)


def set_message_ts(draft_id: str, message_ts: str):
    if draft_id in _drafts:
        _drafts[draft_id]["message_ts"] = message_ts


def update_task(draft_id: str, task_index: int, updated_task: dict):
    _drafts[draft_id]["tasks"][task_index] = updated_task


def remove_task(draft_id: str, task_index: int):
    _drafts[draft_id]["tasks"].pop(task_index)


def delete_draft(draft_id: str):
    _drafts.pop(draft_id, None)
