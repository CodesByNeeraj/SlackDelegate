from slack_sdk import WebClient
import requests
from shared.models import workspace as workspace_model
from slack_app.services.encryption import decrypt_token


def get_client_for_workspace(workspace_id: str) -> WebClient:
    """
    Every handler should call this instead of holding a single global
    bot token. This is what makes multi-tenancy actually work, every
    Slack API call is explicit about which company it's acting for.
    """
    workspace = workspace_model.get_workspace(workspace_id)
    if workspace is None:
        raise ValueError(f"No workspace found for workspace_id={workspace_id}")
    if workspace.get("status") != "active":
        raise ValueError(f"Workspace {workspace_id} is not active (status={workspace.get('status')})")

    bot_token = decrypt_token(workspace["bot_token"])
    return WebClient(token=bot_token)


def send_dm(workspace_id: str, user_id: str, text: str = None, blocks: list = None) -> dict:
    """
    Opens a DM (if one doesn't already exist) and sends a message.
    Returns the Slack API response, which includes the message ts,
    useful for callers that need to call task.attach_message_refs() after.
    """
    client = get_client_for_workspace(workspace_id)
    conversation = client.conversations_open(users=[user_id])
    channel_id = conversation["channel"]["id"]

    response = client.chat_postMessage(
        channel=channel_id,
        text=text or "You have a new task",
        blocks=blocks,
    )
    return response


def post_message(workspace_id: str, channel_id: str, text: str = None, blocks: list = None) -> dict:
    client = get_client_for_workspace(workspace_id)
    return client.chat_postMessage(channel=channel_id, text=text or "", blocks=blocks)


def update_message(workspace_id: str, channel_id: str, message_ts: str, text: str = None, blocks: list = None) -> dict:
    """
    Used to edit the summary card in place as task statuses change,
    instead of posting a new message every time.
    """
    client = get_client_for_workspace(workspace_id)
    return client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text=text or "",
        blocks=blocks,
    )


def get_user_list(workspace_id: str) -> list[dict]:
    """Used by name_matcher.py to fuzzy match transcript names to real Slack users."""
    client = get_client_for_workspace(workspace_id)
    response = client.users_list()
    return response.get("members", [])


def download_file_content(workspace_id: str, file_url: str) -> bytes:
    """
    Slack file URLs are private, this fetches the raw bytes using
    the correct workspace's bot token in the Authorization header.
    """
    workspace = workspace_model.get_workspace(workspace_id)
    bot_token = decrypt_token(workspace["bot_token"])

    headers = {"Authorization": f"Bearer {bot_token}"}
    response = requests.get(file_url, headers=headers)
    return response.content