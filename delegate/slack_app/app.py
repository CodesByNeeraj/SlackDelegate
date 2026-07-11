import os
import logging

logging.basicConfig(level=logging.INFO)

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.authorization import AuthorizeResult
from dotenv import load_dotenv
from shared.models import workspace as workspace_model
from slack_app.services.encryption import decrypt_token
from slack_app.handlers.events import register_event_handlers
from slack_app.handlers.actions import register_action_handlers
from slack_app.handlers.commands import register_command_handlers

load_dotenv()


def authorize(enterprise_id, team_id, logger):
    workspace_key = enterprise_id or team_id
    if not workspace_key:
        raise ValueError("No team_id or enterprise_id in request — cannot authorize")
    workspace = workspace_model.get_workspace(workspace_key)
    if not workspace or workspace.get("status") != "active":
        raise ValueError(f"Workspace {workspace_key} not found or inactive")
    bot_token = decrypt_token(workspace["bot_token"])
    return AuthorizeResult(
        enterprise_id=enterprise_id,
        team_id=team_id,
        bot_token=bot_token,
    )


app = App(authorize=authorize)

register_event_handlers(app)
register_action_handlers(app)
register_command_handlers(app)


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
