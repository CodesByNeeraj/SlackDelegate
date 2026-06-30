import json
from datetime import datetime


def _format_due_date(due_date: str | None) -> str:
    if not due_date or due_date == "NONE":
        return "no due date"
    try:
        return datetime.fromisoformat(due_date).strftime("%b %d, %Y")
    except ValueError:
        return due_date


def build_approval_request_blocks(task: dict, request_type: str, organizer_slack_id: str | None = None) -> list:
    pending = task.get("pending_request", {})
    owner_ref = f"<@{task['owner_slack_id']}>" if task.get("owner_slack_id") else task["owner_name_raw"]
    organizer_mention = f"<@{organizer_slack_id}> " if organizer_slack_id else ""

    if request_type == "reschedule":
        new_date = _format_due_date(pending.get("requested_due_date"))
        reason = pending.get("reason") or "No reason given."
        detail_text = (
            f"{owner_ref} is requesting a deadline extension.\n"
            f"*New date:* {new_date}\n"
            f"*Reason:* {reason}"
        )
    else:
        suggested_slack_id = pending.get("suggested_owner_slack_id")
        suggested = f"<@{suggested_slack_id}>" if suggested_slack_id else pending.get("suggested_owner_name", "someone else")
        reason = pending.get("reason") or "No reason given."
        detail_text = (
            f"{owner_ref} is requesting reassignment.\n"
            f"*Suggested owner:* {suggested}\n"
            f"*Reason:* {reason}"
        )

    button_value = json.dumps(
        {"workspace_id": task["workspace_id"], "task_id": task["task_id"]}
    )

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{organizer_mention}:bell: *Approval needed*\n"
                    f"{detail_text}\n"
                    f"*Task:* {task['task_description']}"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "action_id": "approve_request",
                    "value": button_value,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Deny"},
                    "style": "danger",
                    "action_id": "deny_request",
                    "value": button_value,
                },
            ],
        },
    ]
