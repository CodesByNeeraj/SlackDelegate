from shared.models import task as task_model
from slack_app.blocks.mytasks import build_mytasks_blocks

ACTIVE_STATUSES = {"pending", "blocked"}


def register_command_handlers(app):

    @app.command("/mytasks")
    def handle_mytasks(ack, body, client, respond, logger):
        ack()
        user_id = body["user_id"]

        # If used outside the bot DM, redirect them there
        if body.get("channel_name") != "directmessage":
            respond(text="Use `/mytasks` in your DM with Delegate to see your tasks privately.")
            return

        try:
            all_tasks = task_model.get_tasks_for_owner(user_id)
        except Exception as e:
            logger.error(f"/mytasks query failed: {e}")
            respond(text="Something went wrong fetching your tasks, please try again.")
            return

        open_tasks = [t for t in all_tasks if t.get("status") in ACTIVE_STATUSES]
        # GSI already sorts by due_date, but filter may have disrupted order
        open_tasks.sort(key=lambda t: t.get("due_date") or "9999")

        client.chat_postMessage(
            channel=body["channel_id"],
            blocks=build_mytasks_blocks(open_tasks),
            text=f"You have {len(open_tasks)} open task(s).",
        )
