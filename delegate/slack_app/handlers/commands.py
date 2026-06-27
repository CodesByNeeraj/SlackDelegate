import os
from dotenv import load_dotenv
from shared.models import task as task_model
from shared.models import transcript as transcript_model
from slack_app.agents.tools.embeddings import generate_embedding
from slack_app.agents import search_agent
from slack_app.blocks.mytasks import build_mytasks_blocks
from slack_app.blocks.delegate_status import build_delegate_status_blocks, build_delegate_digest_blocks
from slack_app.blocks.cancel_select import build_cancel_select_blocks

load_dotenv()
ACTIVE_STATUSES = {"pending"}
SANDBOX_WORKSPACE_ID = os.environ["WORKSPACE_ID"]
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

        if subcommand.startswith("search"):
            query = body.get("text", "")[len("search"):].strip()
            if not query:
                client.chat_postMessage(
                    channel=channel_id,
                    text='Please include a search query. Example: `/delegate search who was assigned the API docs task?`',
                )
                return

            searching_msg = client.chat_postMessage(channel=channel_id, text=":mag: Searching your transcripts...")

            try:
                query_embedding = generate_embedding(query)
                top_transcripts = transcript_model.search_transcripts(SANDBOX_WORKSPACE_ID, query_embedding, top_n=3)
            except Exception as e:
                logger.error(f"/delegate search embedding failed: {e}")
                client.chat_update(channel=channel_id, ts=searching_msg["ts"], text="Something went wrong during search. Please try again.")
                return

            if not top_transcripts:
                client.chat_update(
                    channel=channel_id,
                    ts=searching_msg["ts"],
                    text="No searchable transcripts found. Upload a meeting transcript first.",
                )
                return

            chunks_with_tasks = []
            for chunk in top_transcripts:
                tasks = task_model.get_tasks_for_transcript(chunk["workspace_id"], chunk["transcript_id"])
                chunks_with_tasks.append((chunk, tasks))

            try:
                user_info = client.users_info(user=user_id)
                user_name = user_info["user"].get("real_name") or user_info["user"].get("name")
            except Exception:
                user_name = None

            try:
                answer = search_agent.answer_search_query(query, chunks_with_tasks, user_name=user_name)
            except Exception as e:
                logger.error(f"/delegate search LLM failed: {e}")
                client.chat_update(channel=channel_id, ts=searching_msg["ts"], text="Something went wrong generating the answer. Please try again.")
                return

            client.chat_update(
                channel=channel_id,
                ts=searching_msg["ts"],
                text=answer,
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f":mag: *Search results for:* _{query}_"},
                    },
                    {"type": "divider"},
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": answer},
                    },
                ],
            )

        elif subcommand == "cancel":
            try:
                all_tasks = task_model.get_tasks_created_by(user_id)
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
                tasks = task_model.get_tasks_created_by(user_id)
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
                tasks = task_model.get_tasks_created_by(user_id)
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
