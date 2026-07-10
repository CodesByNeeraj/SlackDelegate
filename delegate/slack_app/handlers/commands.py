from dotenv import load_dotenv
from shared.models import task as task_model
from slack_app.agents import search_agent, master_orchestrator
from slack_app.agents.tools.task_filter import apply_task_filter
from slack_app.blocks.mytasks import build_mytasks_blocks
from slack_app.blocks.delegate_status import build_delegate_status_blocks, build_delegate_digest_blocks
from slack_app.blocks.cancel_select import build_cancel_select_blocks

load_dotenv()
ACTIVE_STATUSES = {"pending"}
_DM_ONLY_MSG = "DM the Delegate bot to use this command."


def _is_dm(body: dict) -> bool:
    return body.get("channel_name") == "directmessage"


def register_command_handlers(app):

    @app.command("/delegate")
    def handle_delegate(ack, body, client, respond, logger):
        ack()
        if not _is_dm(body):
            respond(text=_DM_ONLY_MSG)
            return

        subcommand = body.get("text", "").strip().lower()
        user_id = body["user_id"]
        channel_id = body["channel_id"]
        workspace_id = body.get("team_id", "")

        if subcommand.startswith("search"):
            query = body.get("text", "")[len("search"):].strip()
            if not query:
                client.chat_postMessage(
                    channel=channel_id,
                    text='Please include a search query. Example: `/delegate search who was assigned the API docs task?`',
                )
                return

            searching_msg = client.chat_postMessage(channel=channel_id, text=":mag: Searching...")

            try:
                user_info = client.users_info(user=user_id)
                user_name = user_info["user"].get("real_name") or user_info["user"].get("name")
            except Exception:
                user_name = None

            try:
                classification = master_orchestrator.classify(query)
                route = classification["route"]
                args = classification["args"]
                if route == "invoke_search_agent":
                    answer, blocks = search_agent.run(args.get("query", query), user_id, workspace_id, user_name=user_name)
                elif route == "tasks_db_search":
                    all_tasks = task_model.get_tasks_created_by(workspace_id, user_id)
                    filtered = apply_task_filter(all_tasks, args)
                    answer = search_agent.answer_from_tasks(args.get("query", query), filtered, user_name=user_name)
                    blocks = [
                        {"type": "section", "text": {"type": "mrkdwn", "text": f":mag: *Search results for:* _{query}_"}},
                        {"type": "divider"},
                        {"type": "section", "text": {"type": "mrkdwn", "text": answer}},
                    ]
                else:
                    answer, blocks = search_agent.run(query, user_id, workspace_id, user_name=user_name)
            except Exception as e:
                logger.error(f"/delegate search failed: {e}")
                client.chat_update(channel=channel_id, ts=searching_msg["ts"], text="Something went wrong. Please try again.")
                return

            client.chat_update(channel=channel_id, ts=searching_msg["ts"], text=answer, blocks=blocks)

        elif subcommand == "cancel":
            try:
                all_tasks = task_model.get_tasks_created_by(workspace_id, user_id)
            except Exception as e:
                logger.error(f"/delegate cancel failed: {e}")
                client.chat_postMessage(channel=channel_id, text="Something went wrong fetching your tasks.")
                return

            active_tasks = [t for t in all_tasks if t.get("status") in ACTIVE_STATUSES]
            client.chat_postMessage(
                channel=channel_id,
                blocks=build_cancel_select_blocks(active_tasks),
                text="Select a task to cancel.",
            )

        elif subcommand == "digest":
            try:
                tasks = task_model.get_tasks_created_by(workspace_id, user_id)
            except Exception as e:
                logger.error(f"/delegate digest failed: {e}")
                client.chat_postMessage(channel=channel_id, text="Something went wrong fetching your tasks.")
                return

            client.chat_postMessage(
                channel=channel_id,
                blocks=build_delegate_digest_blocks(tasks),
                text="Your delegation digest.",
            )

        elif subcommand == "status":
            try:
                tasks = task_model.get_tasks_created_by(workspace_id, user_id)
            except Exception as e:
                logger.error(f"/delegate status failed: {e}")
                client.chat_postMessage(channel=channel_id, text="Something went wrong fetching your task statuses.")
                return

            client.chat_postMessage(
                channel=channel_id,
                blocks=build_delegate_status_blocks(tasks),
                text=f"You have {len(tasks)} delegated task(s).",
            )
        else:
            client.chat_postMessage(
                channel=channel_id,
                text="Upload a meeting transcript (docx or pdf) here and I'll extract the action items.",
            )

    @app.command("/mytasks")
    def handle_mytasks(ack, body, client, respond, logger):
        ack()
        if not _is_dm(body):
            respond(text=_DM_ONLY_MSG)
            return

        user_id = body["user_id"]
        channel_id = body["channel_id"]

        try:
            all_tasks = task_model.get_tasks_for_owner(user_id)
        except Exception as e:
            logger.error(f"/mytasks query failed: {e}")
            client.chat_postMessage(channel=channel_id, text="Something went wrong fetching your tasks, please try again.")
            return

        open_tasks = [t for t in all_tasks if t.get("status") in ACTIVE_STATUSES]
        open_tasks.sort(key=lambda t: t.get("due_date") or "9999")

        client.chat_postMessage(
            channel=channel_id,
            blocks=build_mytasks_blocks(open_tasks),
            text=f"You have {len(open_tasks)} open task(s).",
        )
