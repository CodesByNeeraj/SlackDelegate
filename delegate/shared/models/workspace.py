from datetime import datetime, timezone
from shared.db.dynamo_client import get_table

TABLE_NAME = "Workspaces"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_workspace(
    workspace_id: str,
    bot_token_encrypted: bytes,
    team_name: str,
    installed_by: str,
    default_reminder_threshold: int = 2,
) -> dict:
    """
    Called once, at the end of the OAuth install flow, right after
    exchanging the code for a bot token and encrypting it via KMS.
    """
    table = get_table(TABLE_NAME)
    now = _now_iso()

    item = {
        "workspace_id": workspace_id,
        "bot_token": bot_token_encrypted,
        "team_name": team_name,
        "installed_by": installed_by,
        "installed_at": now,
        "default_reminder_threshold": default_reminder_threshold,
        "status": "active",
        "updated_at": now,
    }

    table.put_item(Item=item)
    return item


def get_workspace(workspace_id: str) -> dict | None:
    """
    The most frequently called function in the whole system, every
    single Slack API call needs the bot token for the right workspace
    first. Keep this fast, it's a plain key lookup, no query needed.
    """
    table = get_table(TABLE_NAME)
    response = table.get_item(Key={"workspace_id": workspace_id})
    return response.get("Item")


def update_bot_token(workspace_id: str, new_bot_token_encrypted: bytes) -> dict:
    """
    Used if a workspace reinstalls the app or Slack rotates the token.
    """
    table = get_table(TABLE_NAME)
    response = table.update_item(
        Key={"workspace_id": workspace_id},
        UpdateExpression="SET bot_token = :token, #s = :status, updated_at = :updated_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":token": new_bot_token_encrypted,
            ":status": "active",
            ":updated_at": _now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def update_reminder_threshold(workspace_id: str, new_threshold: int) -> dict:
    table = get_table(TABLE_NAME)
    response = table.update_item(
        Key={"workspace_id": workspace_id},
        UpdateExpression="SET default_reminder_threshold = :threshold, updated_at = :updated_at",
        ExpressionAttributeValues={
            ":threshold": new_threshold,
            ":updated_at": _now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def mark_uninstalled(workspace_id: str) -> dict:
    """
    Called when Slack sends an app_uninstalled event. Soft-delete,
    keeps the row and task history intact instead of deleting outright,
    in case they reinstall later or you need it for analytics.
    """
    table = get_table(TABLE_NAME)
    response = table.update_item(
        Key={"workspace_id": workspace_id},
        UpdateExpression="SET #s = :status, updated_at = :updated_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": "uninstalled",
            ":updated_at": _now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def is_active(workspace_id: str) -> bool:
    """
    Quick guard to call before doing any work on behalf of a workspace,
    in case it was uninstalled but a stale event still comes through.
    """
    workspace = get_workspace(workspace_id)
    return workspace is not None and workspace.get("status") == "active"