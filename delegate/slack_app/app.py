import os
import logging

logging.basicConfig(level=logging.INFO)

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from slack_app.handlers.events import register_event_handlers
from slack_app.handlers.actions import register_action_handlers
from slack_app.handlers.commands import register_command_handlers

load_dotenv()

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

register_event_handlers(app)
register_action_handlers(app)
register_command_handlers(app)



if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
