import uuid
from datetime import datetime, timezone
from shared.db.dynamo_client import get_table

TABLE_NAME = "Transcripts"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_transcript(
    workspace_id: str,
    raw_text: str,
    uploaded_by: str,
    channel_id: str,
) -> dict:
    """
    Called right after a docx/pdf is parsed, before sending the text
    to the extraction agent. Storing it first means task.source_transcript_id
    always has something real to point back to, and the reply agent's
    get_task_context tool can pull the original wording later.
    """
    table = get_table(TABLE_NAME)
    transcript_id = str(uuid.uuid4())
    now = _now_iso()

    item = {
        "workspace_id": workspace_id,
        "transcript_id": transcript_id,
        "raw_text": raw_text,
        "uploaded_by": uploaded_by,
        "channel_id": channel_id,
        "created_at": now,
    }

    table.put_item(Item=item)
    return item


def get_transcript(workspace_id: str, transcript_id: str) -> dict | None:
    table = get_table(TABLE_NAME)
    response = table.get_item(
        Key={"workspace_id": workspace_id, "transcript_id": transcript_id}
    )
    return response.get("Item")


def get_transcripts_for_workspace(workspace_id: str) -> list[dict]:
    """
    Mostly useful for an eventual frontend view, 'history of meetings
    processed', not used by the core Slack flow day to day.
    """
    table = get_table(TABLE_NAME)
    response = table.query(
        KeyConditionExpression="workspace_id = :wid",
        ExpressionAttributeValues={":wid": workspace_id},
    )
    return response.get("Items", [])


def delete_transcript(workspace_id: str, transcript_id: str) -> None:
    table = get_table(TABLE_NAME)
    table.delete_item(
        Key={"workspace_id": workspace_id, "transcript_id": transcript_id}
    )