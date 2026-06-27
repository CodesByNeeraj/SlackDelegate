import os
import uuid
from dotenv import load_dotenv
from slack_app.agents.tools.parsetext import (
    extract_text_from_docx,
    extract_text_from_pdf,
)
from slack_app.agents.tools.task_extractor import extract_tasks
from slack_app.agents.tools.embeddings import embed_transcript_chunks
from slack_app.agents.reply_agent import interpret_reply
from slack_app.services.slack_client import download_file_content
from slack_app.services import slack_client
from slack_app.blocks.task_review import build_review_blocks
from slack_app.blocks.approval_request import build_approval_request_blocks
from slack_app.services.name_matcher import match_name_to_slack_user
from slack_app import drafts
from shared.models import transcript as transcript_model
from shared.models import task as task_model

load_dotenv()
SANDBOX_WORKSPACE_ID = os.environ["WORKSPACE_ID"]


def register_event_handlers(app):

    @app.event("message")
    def handle_message_events(body, event, client, say, logger):
        # Ignore bot messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        # DM reply to a task thread
        if event.get("channel_type") == "im" and event.get("thread_ts"):
            _handle_dm_reply(event, client, logger)
            return

        # File upload in a channel
        if event.get("subtype") == "file_share":
            _handle_file_upload(body, event, client, say, logger)
            return

    @app.event("file_shared")
    def handle_file_shared_noop(body, logger):
        # message event with subtype file_share already handles this,
        # this just silences Slack's duplicate event for the same upload
        pass


def _handle_file_upload(body, event, client, say, logger):
    files = event.get("files", [])
    if not files:
        return

    file_data = files[0]
    file_url = file_data["url_private_download"]
    file_type = file_data["filetype"]
    channel_id = event["channel"]
    uploaded_by = event["user"]

    if file_type not in ("docx", "pdf"):
        say(text="Please upload a docx or pdf file.", channel=channel_id)
        return

    say(text="Got it, reading your transcript now...", channel=channel_id)

    try:
        file_bytes = download_file_content(SANDBOX_WORKSPACE_ID, file_url)
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        say(text="I had trouble downloading that file, can you try uploading it again?", channel=channel_id)
        return

    try:
        if file_type == "docx":
            transcript_text = extract_text_from_docx(file_bytes)
        else:
            transcript_text = extract_text_from_pdf(file_bytes)
    except Exception as e:
        logger.error(f"Failed to extract text: {e}")
        say(text="I couldn't read the contents of that file, it might be corrupted or password protected.", channel=channel_id)
        return

    if not transcript_text or not transcript_text.strip():
        say(text="That file appears to be empty, nothing for me to extract.", channel=channel_id)
        return

    try:
        chunks = embed_transcript_chunks(transcript_text)
    except Exception as e:
        logger.warning(f"Chunk embedding failed, transcript will not be searchable: {e}")
        chunks = None

    transcript_record = transcript_model.create_transcript(
        workspace_id=SANDBOX_WORKSPACE_ID,
        raw_text=transcript_text,
        uploaded_by=uploaded_by,
        channel_id=channel_id,
        chunks=chunks,
    )

    say(text="Extracting action items, this'll take a few seconds...", channel=channel_id)

    try:
        tasks = extract_tasks(transcript_text)
    except Exception as e:
        logger.error(f"Task extraction failed: {e}")
        say(text="Something went wrong while extracting tasks, mind trying again?", channel=channel_id)
        return

    if len(tasks) == 0:
        say(
            text=(
                "I read through the file but didn't find any clear action items "
                "with an assigned owner. This might not be a meeting transcript, "
                "or no one was assigned specific tasks. Feel free to upload a "
                "different file."
            ),
            channel=channel_id,
        )
        return

    try:
        team_id = body.get("team_id")
        slack_users = client.users_list(team_id=team_id).get("members", [])
    except Exception as e:
        logger.warning(f"Could not fetch Slack users for name matching: {e}")
        slack_users = []

    for task in tasks:
        task["owner_slack_id"] = match_name_to_slack_user(task["owner_name"], slack_users)

    draft_id = str(uuid.uuid4())
    transcript_id = transcript_record["transcript_id"]

    drafts.save_draft(
        draft_id=draft_id,
        tasks=tasks,
        transcript_id=transcript_id,
        channel_id=channel_id,
    )

    blocks = build_review_blocks(tasks, draft_id, channel_id, transcript_id)

    response = client.chat_postMessage(
        channel=channel_id,
        text=f"Found {len(tasks)} action item(s) — review below.",
        blocks=blocks,
    )
    drafts.set_message_ts(draft_id, response["ts"])


def _handle_dm_reply(event, client, logger):
    thread_ts = event["thread_ts"]
    reply_text = event.get("text", "").strip()
    replying_user = event["user"]
    dm_channel = event["channel"]

    if not reply_text:
        return

    task = task_model.get_task_by_dm_ts(thread_ts)
    if not task:
        logger.warning(f"No task found for DM thread ts={thread_ts}")
        return

    try:
        result = interpret_reply(task["task_description"], reply_text)
    except Exception as e:
        logger.error(f"Reply agent failed: {e}")
        return

    action = result["action"]
    args = result["args"]
    workspace_id = task["workspace_id"]

    if action == "mark_done":
        task_model.update_task_status(workspace_id, task["task_id"], "done")
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":white_check_mark: Got it, I've marked that as done!",
        )

    elif action == "request_reschedule":
        updated_task = task_model.request_reschedule(
            workspace_id=workspace_id,
            task_id=task["task_id"],
            requested_due_date=args["requested_due_date"],
            reason=args.get("reason", ""),
        )
        slack_client.send_dm(
            workspace_id=workspace_id,
            user_id=task["created_by"],
            text=f"<@{replying_user}> is requesting a deadline extension.",
            blocks=build_approval_request_blocks(updated_task, "reschedule"),
        )
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":hourglass: Got it, I've sent your request to the organizer for approval.",
        )

    elif action == "request_reassignment":
        updated_task = task_model.request_reassignment(
            workspace_id=workspace_id,
            task_id=task["task_id"],
            suggested_owner_name=args["suggested_owner_name"],
            reason=args.get("reason", ""),
        )
        slack_client.send_dm(
            workspace_id=workspace_id,
            user_id=task["created_by"],
            text=f"<@{replying_user}> is requesting task reassignment.",
            blocks=build_approval_request_blocks(updated_task, "reassignment"),
        )
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":eyes: Got it, I've flagged this to the organizer for review.",
        )

    elif action == "no_action_needed":
        pass
