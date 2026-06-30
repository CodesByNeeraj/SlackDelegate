import json
import os
from datetime import datetime, date as date_type, timezone, timedelta
from dotenv import load_dotenv

SGT = timezone(timedelta(hours=8))
from shared.models import task as task_model
from slack_app import drafts
from slack_app.blocks.task_review import build_review_blocks
from slack_app.blocks.task_dm import build_task_dm_blocks
from slack_app.services import slack_client
from slack_app.blocks.cancel_select import build_cancel_select_blocks

load_dotenv()
SANDBOX_WORKSPACE_ID = os.environ["WORKSPACE_ID"]

TIME_OPTIONS = [
    ("09:00", "9:00 AM"),
    ("12:00", "12:00 PM"),
    ("15:00", "3:00 PM"),
    ("17:00", "5:00 PM"),
    ("18:00", "6:00 PM"),
    ("23:59", "End of day"),
]

_TIME_OPTION_BLOCKS = [
    {
        "text": {"type": "plain_text", "text": label},
        "value": value,
    }
    for value, label in TIME_OPTIONS
]

DEFAULT_TIME = "18:00"


def _parse_iso_due_date(due_date: str | None) -> tuple[str | None, str]:
    """Returns (YYYY-MM-DD, HH:MM) from an ISO due_date string. Defaults time to 18:00."""
    if not due_date or due_date == "NONE":
        return None, DEFAULT_TIME
    try:
        dt = datetime.fromisoformat(due_date)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = f"{dt.hour:02d}:{dt.minute:02d}"
        if time_str not in {v for v, _ in TIME_OPTIONS}:
            time_str = DEFAULT_TIME
        return date_str, time_str
    except ValueError:
        return None, DEFAULT_TIME


def _build_iso_due_date(date_str: str | None, time_str: str) -> str | None:
    if not date_str:
        return None
    return f"{date_str}T{time_str}:00+08:00"


def register_action_handlers(app):

    @app.action("view_task_link")
    def handle_view_task_link(ack):
        ack()

    @app.action("edit_task")
    def handle_edit_task(ack, body, client, logger):
        ack()
        payload = json.loads(body["actions"][0]["value"])
        draft_id = payload["draft_id"]
        task_index = payload["task_index"]

        draft = drafts.get_draft(draft_id)
        if not draft:
            logger.error(f"Draft {draft_id} not found")
            return

        task = draft["tasks"][task_index]
        initial_date, initial_time = _parse_iso_due_date(task.get("due_date"))

        due_date_block = {
            "type": "input",
            "block_id": "due_date_block",
            "label": {"type": "plain_text", "text": "Due Date"},
            "optional": True,
            "element": {
                "type": "datepicker",
                "action_id": "due_date_input",
                "placeholder": {"type": "plain_text", "text": "Pick a date"},
            },
        }
        if initial_date:
            due_date_block["element"]["initial_date"] = initial_date

        initial_time_option = next(
            (opt for opt in _TIME_OPTION_BLOCKS if opt["value"] == initial_time),
            _TIME_OPTION_BLOCKS[-2],  # default to 6:00 PM
        )

        private_metadata = json.dumps(
            {
                "draft_id": draft_id,
                "task_index": task_index,
                "channel_id": draft["channel_id"],
                "message_ts": draft["message_ts"],
                "transcript_id": draft["transcript_id"],
            }
        )

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "edit_task_modal",
                "title": {"type": "plain_text", "text": "Edit Task"},
                "submit": {"type": "plain_text", "text": "Save"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "private_metadata": private_metadata,
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "owner_block",
                        "label": {"type": "plain_text", "text": "Owner"},
                        "element": {
                            **{
                                "type": "users_select",
                                "action_id": "owner_input",
                                "placeholder": {"type": "plain_text", "text": "Search for a team member"},
                            },
                            **({"initial_user": task["owner_slack_id"]} if task.get("owner_slack_id") else {}),
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "task_block",
                        "label": {"type": "plain_text", "text": "Task"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "task_input",
                            "multiline": True,
                            "initial_value": task["task_description"],
                        },
                    },
                    due_date_block,
                    {
                        "type": "input",
                        "block_id": "due_time_block",
                        "label": {"type": "plain_text", "text": "Due Time (SGT, UTC+8)"},
                        "element": {
                            "type": "static_select",
                            "action_id": "due_time_input",
                            "options": _TIME_OPTION_BLOCKS,
                            "initial_option": initial_time_option,
                        },
                    },
                ],
            },
        )

    @app.view("edit_task_modal")
    def handle_edit_task_modal(ack, body, client, logger):
        values = body["view"]["state"]["values"]
        date_str = values["due_date_block"]["due_date_input"].get("selected_date")
        time_str = values["due_time_block"]["due_time_input"]["selected_option"]["value"]

        if date_str:
            try:
                full_dt = datetime.fromisoformat(f"{date_str}T{time_str}:00+08:00")
                if full_dt <= datetime.now(tz=SGT):
                    ack(
                        response_action="errors",
                        errors={"due_date_block": "Due date and time must be in the future."},
                    )
                    return
            except ValueError:
                ack(
                    response_action="errors",
                    errors={"due_date_block": "Invalid date."},
                )
                return

        ack()

        metadata = json.loads(body["view"]["private_metadata"])
        draft_id = metadata["draft_id"]
        task_index = metadata["task_index"]
        channel_id = metadata["channel_id"]
        message_ts = metadata["message_ts"]
        transcript_id = metadata["transcript_id"]

        owner_slack_id = values["owner_block"]["owner_input"]["selected_user"]
        task_description = values["task_block"]["task_input"]["value"]
        due_date = _build_iso_due_date(date_str, time_str)

        existing_task = drafts.get_draft(draft_id)["tasks"][task_index]
        drafts.update_task(
            draft_id,
            task_index,
            {
                "owner_name": existing_task["owner_name"],
                "owner_slack_id": owner_slack_id,
                "task_description": task_description,
                "due_date": due_date,
            },
        )

        draft = drafts.get_draft(draft_id)
        updated_blocks = build_review_blocks(
            draft["tasks"], draft_id, channel_id, transcript_id
        )

        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=f"Review {len(draft['tasks'])} action item(s)",
            blocks=updated_blocks,
        )

    @app.action("remove_task")
    def handle_remove_task(ack, body, client, logger):
        ack()
        payload = json.loads(body["actions"][0]["value"])
        draft_id = payload["draft_id"]
        task_index = payload["task_index"]

        draft = drafts.get_draft(draft_id)
        if not draft:
            logger.error(f"Draft {draft_id} not found")
            return

        drafts.remove_task(draft_id, task_index)
        draft = drafts.get_draft(draft_id)

        if not draft["tasks"]:
            drafts.delete_draft(draft_id)
            client.chat_update(
                channel=draft["channel_id"],
                ts=draft["message_ts"],
                text="All tasks removed.",
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": ":x: All tasks removed. Upload a new transcript to start again."},
                    }
                ],
            )
            return

        updated_blocks = build_review_blocks(
            draft["tasks"], draft_id, draft["channel_id"], draft["transcript_id"]
        )
        client.chat_update(
            channel=draft["channel_id"],
            ts=draft["message_ts"],
            text=f"Review {len(draft['tasks'])} action item(s)",
            blocks=updated_blocks,
        )

    @app.action("send_tasks")
    def handle_send_tasks(ack, body, client, logger):
        ack()
        payload = json.loads(body["actions"][0]["value"])
        draft_id = payload["draft_id"]
        channel_id = payload["channel_id"]
        transcript_id = payload["transcript_id"]
        uploaded_by = body["user"]["id"]

        draft = drafts.get_draft(draft_id)
        if not draft:
            logger.error(f"Draft {draft_id} not found on send")
            return

        unassigned = [t for t in draft["tasks"] if not t.get("owner_slack_id")]
        if unassigned:
            names = ", ".join(t["owner_name"] for t in unassigned)
            client.chat_postMessage(
                channel=channel_id,
                text=f":warning: {len(unassigned)} task(s) still unassigned ({names}). Please assign an owner for each before delegating.",
            )
            return

        summary_message_ts = draft["message_ts"]
        created = []

        for task in draft["tasks"]:
            t = task_model.create_task(
                workspace_id=SANDBOX_WORKSPACE_ID,
                task_description=task["task_description"],
                owner_name_raw=task["owner_name"],
                created_by=uploaded_by,
                channel_id=channel_id,
                source_transcript_id=transcript_id,
                due_date=task.get("due_date"),
                owner_slack_id=task.get("owner_slack_id"),
            )

            dm_response = slack_client.send_dm(
                workspace_id=SANDBOX_WORKSPACE_ID,
                user_id=task["owner_slack_id"],
                text=f"You've been assigned a task: {task['task_description']}",
                blocks=build_task_dm_blocks(t, uploaded_by),
            )

            task_model.attach_message_refs(
                workspace_id=SANDBOX_WORKSPACE_ID,
                task_id=t["task_id"],
                summary_message_ts=summary_message_ts,
                dm_message_ts=dm_response["ts"],
                dm_channel_id=dm_response["channel"],
            )

            created.append(t)

        drafts.delete_draft(draft_id)
        logger.info(f"Delegated {len(created)} task(s) and sent DMs")

        lines = [f":white_check_mark: *{len(created)} task(s) delegated.*"]
        for t in created:
            lines.append(f"• <@{t['owner_slack_id']}> — {t['task_description']}")

        client.chat_update(
            channel=channel_id,
            ts=summary_message_ts,
            text=f"{len(created)} task(s) delegated.",
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(lines)},
                }
            ],
        )

    @app.action("cancel_tasks")
    def handle_cancel_tasks(ack, body, client, logger):
        ack()
        payload = json.loads(body["actions"][0]["value"])
        draft_id = payload["draft_id"]

        draft = drafts.get_draft(draft_id)
        drafts.delete_draft(draft_id)

        if draft and draft.get("message_ts"):
            client.chat_update(
                channel=draft["channel_id"],
                ts=draft["message_ts"],
                text="Task delegation cancelled.",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ":x: Task delegation cancelled. Upload a new transcript to start again.",
                        },
                    }
                ],
            )

    @app.action("select_task_to_cancel")
    def handle_select_task_to_cancel(ack, body, client, logger):
        ack()
        selected_option = body["actions"][0].get("selected_option")
        if not selected_option:
            return

        workspace_id, task_id = selected_option["value"].split(":", 1)
        task = task_model.get_task(workspace_id, task_id)
        if not task:
            return

        organizer_id = body["user"]["id"]
        all_tasks = task_model.get_tasks_created_by(organizer_id)
        active_tasks = [t for t in all_tasks if t.get("status") == "pending"]

        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text="Select a task to cancel.",
            blocks=build_cancel_select_blocks(active_tasks, selected_task=task),
        )

    @app.action("confirm_cancel_task")
    def handle_confirm_cancel_task(ack, body, client, logger):
        ack()
        state = body["state"]["values"]
        selected = state.get("cancel_select_block", {}).get("select_task_to_cancel", {}).get("selected_option")

        if not selected:
            client.chat_postMessage(
                channel=body["channel"]["id"],
                text="Please select a task first.",
            )
            return

        workspace_id, task_id = selected["value"].split(":", 1)

        task = task_model.get_task(workspace_id, task_id)
        if not task:
            logger.error(f"Task {task_id} not found for cancellation")
            return

        if task.get("owner_slack_id") and task["owner_slack_id"] != "UNASSIGNED" and task.get("dm_message_ts"):
            try:
                dm_channel = client.conversations_open(users=[task["owner_slack_id"]])["channel"]["id"]
                client.chat_postMessage(
                    channel=dm_channel,
                    thread_ts=task["dm_message_ts"],
                    text=":x: This task has been cancelled by the organiser.",
                )
            except Exception as e:
                logger.error(f"Failed to notify owner of cancellation: {e}")

        task_model.delete_task(workspace_id, task_id)

        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text="Task cancelled.",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":white_check_mark: Cancelled: _{task['task_description']}_",
                    },
                }
            ],
        )

    @app.action("approve_request")
    def handle_approve_request(ack, body, client, logger):
        ack()
        payload = json.loads(body["actions"][0]["value"])
        workspace_id = payload["workspace_id"]
        task_id = payload["task_id"]

        task_before = task_model.get_task(workspace_id, task_id)
        if not task_before:
            logger.error(f"Task {task_id} not found")
            return
        pending = task_before.get("pending_request", {})

        # For reassignment: resolve the suggested name to a Slack ID before approving
        if pending.get("type") == "reassignment":
            try:
                team_id = body.get("team_id") or body.get("team", {}).get("id")
                slack_users = client.users_list(team_id=team_id).get("members", [])
            except Exception:
                slack_users = []
            from slack_app.services.name_matcher import match_name_to_slack_user
            new_slack_id = match_name_to_slack_user(pending.get("suggested_owner_name", ""), slack_users)
            pending["new_owner_slack_id"] = new_slack_id

            # Patch the pending_request on the task so approve_pending_request can read it
            task_model.update_task_field(workspace_id, task_id, "pending_request", pending)

        try:
            task = task_model.approve_pending_request(workspace_id, task_id)
        except ValueError as e:
            logger.error(f"Approve failed: {e}")
            return

        original_owner_slack_id = task_before.get("owner_slack_id")
        owner_ref = f"<@{original_owner_slack_id}>" if original_owner_slack_id and original_owner_slack_id != "UNASSIGNED" else task_before["owner_name_raw"]

        if pending.get("type") == "reschedule":
            summary = f"{owner_ref} requested a deadline extension to *{pending.get('requested_due_date', '?')}*\nReason: {pending.get('reason') or 'none given'}"
        else:
            new_owner_display = f"<@{pending['new_owner_slack_id']}>" if pending.get("new_owner_slack_id") else pending.get("suggested_owner_name", "?")
            summary = f"{owner_ref} requested reassignment to *{new_owner_display}*\nReason: {pending.get('reason') or 'none given'}"

        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text="Request approved.",
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f":bell: *Request*\n{summary}\n_Task: {task_before['task_description']}_"},
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":white_check_mark: *Approved.* The task has been updated."},
                },
            ],
        )

        # Notify original owner in their thread
        if original_owner_slack_id and original_owner_slack_id != "UNASSIGNED" and task_before.get("dm_message_ts"):
            orig_dm_channel = client.conversations_open(users=[original_owner_slack_id])["channel"]["id"]
            if pending.get("type") == "reschedule":
                orig_msg = f":white_check_mark: Your deadline extension request was approved. New due date: *{pending.get('requested_due_date', '?')}*"
            else:
                orig_msg = ":white_check_mark: Your reassignment request was approved. The task has been reassigned."
            client.chat_postMessage(
                channel=orig_dm_channel,
                thread_ts=task_before["dm_message_ts"],
                text=orig_msg,
            )

        # For reassignment: send a fresh task DM to the new owner
        if pending.get("type") == "reassignment":
            new_slack_id = pending.get("new_owner_slack_id")
            if new_slack_id and new_slack_id != "UNASSIGNED":
                from slack_app.blocks.task_dm import build_task_dm_blocks
                dm_response = slack_client.send_dm(
                    workspace_id=workspace_id,
                    user_id=new_slack_id,
                    text=f"You've been assigned a task: {task['task_description']}",
                    blocks=build_task_dm_blocks(task, task_before["created_by"]),
                )
                task_model.attach_message_refs(
                    workspace_id=workspace_id,
                    task_id=task_id,
                    dm_message_ts=dm_response["ts"],
                    dm_channel_id=dm_response["channel"],
                )
            else:
                logger.warning(f"Reassignment approved but could not match '{pending.get('suggested_owner_name')}' to a Slack user — no DM sent.")

    @app.action("deny_request")
    def handle_deny_request(ack, body, client, logger):
        ack()
        payload = json.loads(body["actions"][0]["value"])

        private_metadata = json.dumps({
            "workspace_id": payload["workspace_id"],
            "task_id": payload["task_id"],
            "channel_id": body["channel"]["id"],
            "message_ts": body["message"]["ts"],
        })

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "deny_request_modal",
                "title": {"type": "plain_text", "text": "Deny Request"},
                "submit": {"type": "plain_text", "text": "Deny"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "private_metadata": private_metadata,
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "reason_block",
                        "label": {"type": "plain_text", "text": "Reason for denial"},
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "reason_input",
                            "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "Let them know why their request is being denied..."},
                        },
                    }
                ],
            },
        )

    @app.view("deny_request_modal")
    def handle_deny_request_modal(ack, body, client, logger):
        ack()
        metadata = json.loads(body["view"]["private_metadata"])
        workspace_id = metadata["workspace_id"]
        task_id = metadata["task_id"]
        channel_id = metadata["channel_id"]
        message_ts = metadata["message_ts"]

        reason = body["view"]["state"]["values"]["reason_block"]["reason_input"]["value"]

        task_before = task_model.get_task(workspace_id, task_id)
        if not task_before:
            logger.error(f"Task {task_id} not found on deny modal submit")
            return
        pending = task_before.get("pending_request", {})

        try:
            task = task_model.deny_pending_request(workspace_id, task_id)
        except Exception as e:
            logger.error(f"Deny failed: {e}")
            return

        owner_ref = f"<@{task_before['owner_slack_id']}>" if task_before.get("owner_slack_id") else task_before["owner_name_raw"]
        if pending.get("type") == "reschedule":
            summary = f"{owner_ref} requested a deadline extension to *{pending.get('requested_due_date', '?')}*\nReason: {pending.get('reason') or 'none given'}"
        else:
            summary = f"{owner_ref} requested reassignment to *{pending.get('suggested_owner_name', '?')}*\nReason: {pending.get('reason') or 'none given'}"

        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text="Request denied.",
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f":bell: *Request*\n{summary}\n_Task: {task_before['task_description']}_"},
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f":x: *Denied.*" + (f"\nReason: {reason}" if reason else "")},
                },
            ],
        )

        if task.get("owner_slack_id") and task["owner_slack_id"] != "UNASSIGNED" and task.get("dm_message_ts"):
            dm_channel = client.conversations_open(users=[task["owner_slack_id"]])["channel"]["id"]
            client.chat_postMessage(
                channel=dm_channel,
                thread_ts=task["dm_message_ts"],
                text=":x: Your request was denied." + (f"\n*Reason:* {reason}" if reason else ""),
            )
