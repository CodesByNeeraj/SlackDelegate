import uuid
from datetime import datetime, timezone
from shared.db.dynamo_client import get_table

TABLE_NAME = "Tasks"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_task(
    workspace_id: str,
    task_description: str,
    owner_name_raw: str,
    created_by: str,
    channel_id: str,
    source_transcript_id: str,
    owner_slack_id: str | None = None,
    due_date: str | None = None,
) -> dict:
    """
    Creates a new task in DynamoDB. Only called AFTER the organizer has
    confirmed the task list and clicked send. The extraction + editing
    loop before this point lives entirely in Slack's Block Kit
    private_metadata, nothing is written to the DB until confirmation,
    so abandoned or heavily-edited drafts never touch the table.
    Status starts as 'pending' since by definition the task is being
    sent out the moment this runs.
    """
    table = get_table(TABLE_NAME)
    task_id = str(uuid.uuid4())
    now = _now_iso()

    item = {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "task_description": task_description,
        "owner_name_raw": owner_name_raw,
        "owner_slack_id": owner_slack_id or "UNASSIGNED",
        "due_date": due_date or "NONE",
        "status": "pending",
        "source_transcript_id": source_transcript_id,
        "created_by": created_by,
        "channel_id": channel_id,
        "summary_message_ts": None,
        "dm_message_ts": None,
        "pending_request": None,
        "created_at": now,
        "updated_at": now,
    }

    table.put_item(Item=item)
    return item


def get_task(workspace_id: str, task_id: str) -> dict | None:
    table = get_table(TABLE_NAME)
    response = table.get_item(Key={"workspace_id": workspace_id, "task_id": task_id})
    return response.get("Item")


def get_tasks_for_workspace(workspace_id: str) -> list[dict]:
    """Used for the summary card, all tasks tied to one meeting/workspace pull."""
    table = get_table(TABLE_NAME)
    response = table.query(
        KeyConditionExpression="workspace_id = :wid",
        ExpressionAttributeValues={":wid": workspace_id},
    )
    return response.get("Items", [])


def get_tasks_for_owner(owner_slack_id: str) -> list[dict]:
    """
    Used by /mytasks. Queries the GSI instead of scanning the table,
    sorted by due_date automatically since that's the GSI sort key.
    """
    table = get_table(TABLE_NAME)
    response = table.query(
        IndexName="owner_slack_id-index",
        KeyConditionExpression="owner_slack_id = :oid",
        ExpressionAttributeValues={":oid": owner_slack_id},
    )
    return response.get("Items", [])


def update_task_status(workspace_id: str, task_id: str, new_status: str) -> dict:
    table = get_table(TABLE_NAME)
    response = table.update_item(
        Key={"workspace_id": workspace_id, "task_id": task_id},
        UpdateExpression="SET #s = :status, updated_at = :updated_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": new_status,
            ":updated_at": _now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def request_reschedule(workspace_id: str, task_id: str, requested_due_date: str, reason: str = "") -> dict:
    """
    Recipient asked to change the due date. Does NOT update due_date yet,
    stores the request for the organizer to approve or deny first.
    """
    table = get_table(TABLE_NAME)
    pending_request = {
        "type": "reschedule",
        "requested_due_date": requested_due_date,
        "reason": reason,
        "requested_at": _now_iso(),
    }
    response = table.update_item(
        Key={"workspace_id": workspace_id, "task_id": task_id},
        UpdateExpression="SET pending_request = :pr, updated_at = :updated_at",
        ExpressionAttributeValues={
            ":pr": pending_request,
            ":updated_at": _now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def request_reassignment(workspace_id: str, task_id: str, suggested_owner_name: str, reason: str = "") -> dict:
    """
    Recipient asked for the task to go to someone else, or disputed
    ownership entirely. Stored as a pending request, not applied directly.
    """
    table = get_table(TABLE_NAME)
    pending_request = {
        "type": "reassignment",
        "suggested_owner_name": suggested_owner_name,
        "reason": reason,
        "requested_at": _now_iso(),
    }
    response = table.update_item(
        Key={"workspace_id": workspace_id, "task_id": task_id},
        UpdateExpression="SET pending_request = :pr, updated_at = :updated_at",
        ExpressionAttributeValues={
            ":pr": pending_request,
            ":updated_at": _now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def approve_pending_request(workspace_id: str, task_id: str) -> dict:
    """
    Organizer approved the pending request. Applies the actual change
    (reschedule or reassignment) and clears pending_request.
    """
    task = get_task(workspace_id, task_id)
    if not task or not task.get("pending_request"):
        raise ValueError("No pending request on this task")

    request = task["pending_request"]
    table = get_table(TABLE_NAME)

    if request["type"] == "reschedule":
        response = table.update_item(
            Key={"workspace_id": workspace_id, "task_id": task_id},
            UpdateExpression="SET due_date = :due_date, pending_request = :null_val, updated_at = :updated_at",
            ExpressionAttributeValues={
                ":due_date": request["requested_due_date"],
                ":null_val": None,
                ":updated_at": _now_iso(),
            },
            ReturnValues="ALL_NEW",
        )
    elif request["type"] == "reassignment":
        response = table.update_item(
            Key={"workspace_id": workspace_id, "task_id": task_id},
            UpdateExpression="SET owner_name_raw = :oname, pending_request = :null_val, updated_at = :updated_at",
            ExpressionAttributeValues={
                ":oname": request["suggested_owner_name"],
                ":null_val": None,
                ":updated_at": _now_iso(),
            },
            ReturnValues="ALL_NEW",
        )
    else:
        raise ValueError(f"Unknown request type: {request['type']}")

    return response.get("Attributes")


def deny_pending_request(workspace_id: str, task_id: str) -> dict:
    """Organizer denied the request. Task stays exactly as it was, just clears the flag."""
    table = get_table(TABLE_NAME)
    response = table.update_item(
        Key={"workspace_id": workspace_id, "task_id": task_id},
        UpdateExpression="SET pending_request = :null_val, updated_at = :updated_at",
        ExpressionAttributeValues={
            ":null_val": None,
            ":updated_at": _now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def attach_message_refs(workspace_id: str, task_id: str, summary_message_ts: str = None, dm_message_ts: str = None) -> dict:
    """
    Called after the organizer sends tasks out. Stores the Slack message
    timestamps so we can later edit the summary card or find the DM thread.
    """
    table = get_table(TABLE_NAME)
    update_parts = []
    values = {":updated_at": _now_iso()}

    if summary_message_ts is not None:
        update_parts.append("summary_message_ts = :smts")
        values[":smts"] = summary_message_ts
    if dm_message_ts is not None:
        update_parts.append("dm_message_ts = :dmts")
        values[":dmts"] = dm_message_ts

    update_parts.append("updated_at = :updated_at")
    update_expression = "SET " + ", ".join(update_parts)

    response = table.update_item(
        Key={"workspace_id": workspace_id, "task_id": task_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def get_tasks_created_by(creator_slack_id: str) -> list[dict]:
    """Returns all tasks created by this user across all workspaces, sorted by created_at desc."""
    from boto3.dynamodb.conditions import Attr
    table = get_table(TABLE_NAME)
    response = table.scan(FilterExpression=Attr("created_by").eq(creator_slack_id))
    items = response.get("Items", [])
    return sorted(items, key=lambda t: t.get("created_at", ""), reverse=True)


def get_tasks_for_transcript(workspace_id: str, transcript_id: str) -> list[dict]:
    from boto3.dynamodb.conditions import Key, Attr
    table = get_table(TABLE_NAME)
    response = table.query(
        KeyConditionExpression=Key("workspace_id").eq(workspace_id),
        FilterExpression=Attr("source_transcript_id").eq(transcript_id),
    )
    return response.get("Items", [])


def get_task_by_dm_ts(dm_message_ts: str) -> dict | None:
    """
    Scans for the task whose DM thread matches this ts. Called on every DM reply
    so it's intentionally a scan — add a GSI on dm_message_ts if volume demands it.
    """
    from boto3.dynamodb.conditions import Attr
    table = get_table(TABLE_NAME)
    response = table.scan(FilterExpression=Attr("dm_message_ts").eq(dm_message_ts))
    items = response.get("Items", [])
    return items[0] if items else None


def delete_task(workspace_id: str, task_id: str) -> None:
    table = get_table(TABLE_NAME)
    table.delete_item(Key={"workspace_id": workspace_id, "task_id": task_id})