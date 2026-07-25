import uuid
import time
from dotenv import load_dotenv
from slack_app.agents.tools.parsetext import (
    extract_text_from_docx,
    extract_text_from_pdf,
)
from slack_app.agents.tools.task_extractor import extract_tasks
from slack_app.agents.tools.embeddings import embed_transcript_chunks
from slack_app.agents.reply_agent import interpret_reply
from slack_app.agents import master_orchestrator, search_agent
from slack_app.agents.tools import status_tool, digest_tool
from slack_app.agents.tools.participant_extractor import extract_participants
from slack_app.agents.tools.task_filter import apply_task_filter
from slack_app.services.slack_client import download_file_content
from slack_app.blocks.task_review import build_review_blocks
from slack_app.blocks.approval_request import build_approval_request_blocks
from slack_app.services.name_matcher import match_name_to_slack_user
from slack_app import drafts
from slack_app.handlers.oauth import handle_app_uninstalled
from shared.models import transcript as transcript_model
from shared.models import task as task_model

load_dotenv()


def register_event_handlers(app):

    @app.event("message")
    def handle_message_events(body, event, client, say, logger):
        # Ignore bot messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        workspace_id = body.get("enterprise_id") or body.get("team_id", "")

        # DM reply to a task thread
        if event.get("channel_type") == "im" and event.get("thread_ts"):
            _handle_dm_reply(event, client, logger, workspace_id)
            return

        # File upload in a channel
        if event.get("subtype") == "file_share":
            _handle_file_upload(body, event, client, say, logger, workspace_id)
            return

        # Free-form DM message (no thread, no file) — route through master orchestrator
        if event.get("channel_type") == "im" and event.get("text"):
            _handle_general_dm(event, client, logger, workspace_id)
            return

    @app.event("file_shared")
    def handle_file_shared_noop(body, logger):
        # message event with subtype file_share already handles this,
        # this just silences Slack's duplicate event for the same upload
        pass

    @app.event("app_uninstalled")
    def handle_app_uninstalled_event(body, logger):
        workspace_id = body.get("enterprise_id") or body.get("team_id", "")
        if workspace_id:
            handle_app_uninstalled(workspace_id)
            logger.info(f"Workspace {workspace_id} marked as uninstalled")


def _handle_file_upload(body, event, client, say, logger, workspace_id: str):
    files = event.get("files", [])
    if not files:
        return

    file_data = files[0]
    file_url = file_data["url_private_download"]
    file_type = file_data["filetype"]
    filename = file_data.get("name", "unknown")
    file_permalink = file_data.get("permalink", "")
    channel_id = event["channel"]
    uploaded_by = event["user"]

    if file_type not in ("docx", "pdf"):
        say(text="Please upload a docx or pdf file.", channel=channel_id)
        return

    say(text="Got it, reading your transcript now...", channel=channel_id)

    try:
        file_bytes = download_file_content(workspace_id, file_url)
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
        say(text="That file appears to be empty, nothing for me to extract. Please upload a non-empty meeting transcript file.", channel=channel_id)
        return

    embedding_tokens = 0
    try:
        chunks, embedding_tokens = embed_transcript_chunks(transcript_text)
    except Exception as e:
        logger.warning(f"Chunk embedding failed, transcript will not be searchable: {e}")
        chunks = None

    participants = extract_participants(transcript_text)

    say(text="Extracting action items, this'll take a few seconds...", channel=channel_id)

    extraction_usage = {}
    try:
        t0 = time.time()
        tasks, extraction_usage = extract_tasks(transcript_text)
        extraction_latency_ms = int((time.time() - t0) * 1000)
    except Exception as e:
        logger.error(f"Task extraction failed: {e}")
        say(text="Something went wrong while extracting tasks, mind trying again?", channel=channel_id)
        return

    transcript_record = transcript_model.create_transcript(
        workspace_id=workspace_id,
        raw_text=transcript_text,
        uploaded_by=uploaded_by,
        channel_id=channel_id,
        chunks=chunks,
        filename=filename,
        file_permalink=file_permalink,
        participants=participants,
        embedding_tokens=embedding_tokens,
        extraction_prompt_tokens=extraction_usage.get("prompt_tokens", 0),
        extraction_completion_tokens=extraction_usage.get("completion_tokens", 0),
        extraction_latency_ms=extraction_latency_ms,
        task_count=len(tasks),
    )

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
        workspace_id=workspace_id,
    )

    blocks = build_review_blocks(tasks, draft_id, channel_id, transcript_id)

    response = client.chat_postMessage(
        channel=channel_id,
        text=f"Found {len(tasks)} action item(s) — review below.",
        blocks=blocks,
    )
    drafts.set_message_ts(draft_id, response["ts"])


def _handle_dm_reply(event, client, logger, workspace_id: str):
    thread_ts = event["thread_ts"]
    reply_text = event.get("text", "").strip()
    replying_user = event["user"]
    dm_channel = event["channel"]

    if not reply_text:
        return

    task = task_model.get_task_by_dm_ts(workspace_id, thread_ts)
    if not task:
        logger.warning(f"No task found for DM thread ts={thread_ts}")
        return

    if task.get("status") == "done":
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":white_check_mark: This task has already been marked as complete.",
        )
        return

    if task.get("status") == "cancelled":
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":x: This task has been cancelled and is no longer active.",
        )
        return

    if task.get("owner_slack_id") and task["owner_slack_id"] != replying_user:
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":information_source: This task has been reassigned and is no longer assigned to you.",
        )
        return

    try:
        result = interpret_reply(task["task_description"], reply_text)
    except Exception as e:
        logger.error(f"Reply agent failed: {e}")
        return

    action = result["action"]
    args = result["args"]
    workspace_id = task["workspace_id"]

    if action in ("request_reschedule", "request_reassignment") and task.get("pending_request"):
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":hourglass: You already have a pending request waiting for the organizer's response. Please wait for them to approve or deny it before submitting a new one.",
        )
        return

    if action == "mark_done":
        task_model.update_task_status(workspace_id, task["task_id"], "done")
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":white_check_mark: Got it, I've marked that as done!",
        )
        if task.get("channel_id") and task.get("created_by"):
            client.chat_postMessage(
                channel=task["channel_id"],
                thread_ts=task.get("summary_message_ts"),
                text=f"<@{task['created_by']}> <@{replying_user}> has completed the task: *{task['task_description']}*",
            )

    elif action == "request_reschedule":
        updated_task = task_model.request_reschedule(
            workspace_id=workspace_id,
            task_id=task["task_id"],
            requested_due_date=args["requested_due_date"],
            reason=args.get("reason", ""),
        )
        client.chat_postMessage(
            channel=task["channel_id"],
            thread_ts=task.get("summary_message_ts"),
            text=f"<@{task['created_by']}> — <@{replying_user}> is requesting a deadline extension.",
            blocks=build_approval_request_blocks(updated_task, "reschedule", organizer_slack_id=task.get("created_by")),
        )
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":hourglass: Got it, I've sent your request to the organizer for approval.",
        )

    elif action == "request_reassignment":
        try:
            slack_users = client.users_list().get("members", [])
            suggested_slack_id = match_name_to_slack_user(args["suggested_owner_name"], slack_users)
        except Exception:
            suggested_slack_id = None

        updated_task = task_model.request_reassignment(
            workspace_id=workspace_id,
            task_id=task["task_id"],
            suggested_owner_name=args["suggested_owner_name"],
            reason=args.get("reason", ""),
            suggested_owner_slack_id=suggested_slack_id,
        )
        client.chat_postMessage(
            channel=task["channel_id"],
            thread_ts=task.get("summary_message_ts"),
            text=f"<@{task['created_by']}> — <@{replying_user}> is requesting task reassignment.",
            blocks=build_approval_request_blocks(updated_task, "reassignment", organizer_slack_id=task.get("created_by")),
        )
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":eyes: Got it, I've flagged this to the organizer for review.",
        )

    elif action == "ask_for_date":
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=args.get("message", "Could you share a specific date you'd like to request?"),
        )

    elif action == "cancel_request":
        client.chat_postMessage(
            channel=dm_channel,
            thread_ts=thread_ts,
            text=":thumbsup: No problem! Your task remains unchanged.",
        )

    elif action == "no_action_needed":
        pass


def _handle_general_dm(event, client, logger, workspace_id: str):
    text = event.get("text", "").strip()
    user_id = event["user"]
    channel_id = event["channel"]

    try:
        classification = master_orchestrator.classify(text)
    except Exception as e:
        logger.error(f"Master orchestrator failed: {e}")
        return

    route = classification["route"]
    args = classification["args"]
    logger.info(f"Master orchestrator: route={route} args={args}")

    if route == "out_of_scope":
        client.chat_postMessage(
            channel=channel_id,
            text=":no_entry: Sorry, I can only help with delegated tasks and meeting transcripts.",
        )
        return

    try:
        try:
            user_info = client.users_info(user=user_id)
            user_name = user_info["user"].get("real_name") or user_info["user"].get("name")
        except Exception:
            user_name = None

        if route == "invoke_search_agent":
            query = args.get("query", text)
            searching_msg = client.chat_postMessage(channel=channel_id, text=":mag: Searching...")
            answer, blocks = search_agent.run(query, user_id, workspace_id, user_name=user_name)
            client.chat_update(channel=channel_id, ts=searching_msg["ts"], text=answer, blocks=blocks)

        elif route == "tasks_db_search":
            query = args.get("query", text)
            searching_msg = client.chat_postMessage(channel=channel_id, text=":mag: Searching...")
            all_tasks = task_model.get_tasks_created_by(workspace_id, user_id)
            filtered = apply_task_filter(all_tasks, args)
            answer = search_agent.answer_from_tasks(query, filtered, user_name=user_name)
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": f":mag: *Search results for:* _{query}_"}},
                {"type": "divider"},
                {"type": "section", "text": {"type": "mrkdwn", "text": answer}},
            ]
            client.chat_update(channel=channel_id, ts=searching_msg["ts"], text=answer, blocks=blocks)

        elif route == "invoke_status_tool":
            blocks, text_summary = status_tool.run(user_id, workspace_id)
            client.chat_postMessage(channel=channel_id, blocks=blocks, text=text_summary)

        elif route == "invoke_digest_tool":
            blocks, text_summary = digest_tool.run(user_id, workspace_id)
            client.chat_postMessage(channel=channel_id, blocks=blocks, text=text_summary)

    except Exception as e:
        logger.error(f"Sub-agent failed (route={route}): {e}")
        client.chat_postMessage(channel=channel_id, text="Something went wrong. Please try again.")
