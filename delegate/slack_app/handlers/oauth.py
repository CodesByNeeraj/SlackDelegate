import os
import requests
from shared.models import workspace as workspace_model
from slack_app.services.encryption import encrypt_token


def build_install_url() -> str:
    """
    The URL your 'Add to Slack' button points to. Sends the company
    to Slack's authorization screen with the scopes your manifest defines.
    """
    client_id = os.environ["SLACK_CLIENT_ID"]
    redirect_uri = os.environ["SLACK_REDIRECT_URI"]
    scopes = "channels:history,chat:write,im:history,im:write,im:read,files:read,users:read,commands,reactions:write"

    return (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={redirect_uri}"
    )


def handle_oauth_callback(code: str) -> dict:
    """
    Called by your redirect endpoint when Slack sends back the
    authorization code. Exchanges it for a real bot token, encrypts it,
    and creates the workspace row. This is the only place a plaintext
    bot token exists outside of Slack's own systems, and it never
    touches disk in that form.
    """
    response = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": os.environ["SLACK_CLIENT_ID"],
            "client_secret": os.environ["SLACK_CLIENT_SECRET"],
            "code": code,
            "redirect_uri": os.environ["SLACK_REDIRECT_URI"],
        },
    )
    data = response.json()

    if not data.get("ok"):
        raise ValueError(f"OAuth exchange failed: {data.get('error')}")

    plaintext_bot_token = data["access_token"]
    workspace_id = data["team"]["id"]
    team_name = data["team"]["name"]
    installer_user_id = data["authed_user"]["id"]

    encrypted_token = encrypt_token(plaintext_bot_token)

    existing = workspace_model.get_workspace(workspace_id)
    if existing:
        # reinstall, e.g. they uninstalled and came back, or scopes changed
        workspace = workspace_model.update_bot_token(workspace_id, encrypted_token)
    else:
        workspace = workspace_model.create_workspace(
            workspace_id=workspace_id,
            bot_token_encrypted=encrypted_token,
            team_name=team_name,
            installed_by=installer_user_id,
        )

    return workspace


def handle_app_uninstalled(workspace_id: str) -> None:
    """
    Called from events.py when Slack sends an app_uninstalled event.
    Soft-deletes so task history survives in case they reinstall.
    """
    workspace_model.mark_uninstalled(workspace_id)