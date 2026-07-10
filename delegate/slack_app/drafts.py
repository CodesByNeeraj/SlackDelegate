import time
from shared.db.dynamo_client import get_table

TABLE_NAME = "Drafts"


def save_draft(draft_id: str, tasks: list, transcript_id: str, channel_id: str, workspace_id: str = ""):
    table = get_table(TABLE_NAME)
    table.put_item(Item={
        "draft_id": draft_id,
        "workspace_id": workspace_id,
        "tasks": tasks,
        "transcript_id": transcript_id,
        "channel_id": channel_id,
        "message_ts": None,
        "ttl": int(time.time()) + 86400,
    })


def get_draft(draft_id: str) -> dict | None:
    table = get_table(TABLE_NAME)
    response = table.get_item(Key={"draft_id": draft_id})
    return response.get("Item")


def set_message_ts(draft_id: str, message_ts: str):
    table = get_table(TABLE_NAME)
    table.update_item(
        Key={"draft_id": draft_id},
        UpdateExpression="SET message_ts = :ts",
        ExpressionAttributeValues={":ts": message_ts},
    )


def update_task(draft_id: str, task_index: int, updated_task: dict):
    draft = get_draft(draft_id)
    if not draft:
        return
    tasks = list(draft["tasks"])
    tasks[task_index] = updated_task
    table = get_table(TABLE_NAME)
    table.update_item(
        Key={"draft_id": draft_id},
        UpdateExpression="SET tasks = :tasks",
        ExpressionAttributeValues={":tasks": tasks},
    )


def remove_task(draft_id: str, task_index: int):
    draft = get_draft(draft_id)
    if not draft:
        return
    tasks = list(draft["tasks"])
    tasks.pop(task_index)
    table = get_table(TABLE_NAME)
    table.update_item(
        Key={"draft_id": draft_id},
        UpdateExpression="SET tasks = :tasks",
        ExpressionAttributeValues={":tasks": tasks},
    )


def delete_draft(draft_id: str):
    table = get_table(TABLE_NAME)
    table.delete_item(Key={"draft_id": draft_id})
