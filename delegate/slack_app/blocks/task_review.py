import json
from datetime import datetime


def _format_due_date(due_date: str | None) -> str:
    if not due_date or due_date == "NONE":
        return "No due date"
    try:
        dt = datetime.fromisoformat(due_date)
        return dt.strftime("%b %d, %Y")
    except ValueError:
        return due_date


def build_review_blocks(tasks: list, draft_id: str, channel_id: str, transcript_id: str) -> list:
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Found {len(tasks)} action item(s)"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Review and edit before sending. Nothing is saved until you click *Send All*.",
                }
            ],
        },
        {"type": "divider"},
    ]

    for i, task in enumerate(tasks):
        due_str = _format_due_date(task.get("due_date"))
        owner_slack_id = task.get("owner_slack_id")
        if owner_slack_id:
            owner_display = f"<@{owner_slack_id}>"
        else:
            owner_display = f"*{task['owner_name']}* ⚠️ _unmatched — click Edit to assign_"
        button_value = json.dumps({"draft_id": draft_id, "task_index": i})
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{owner_display}\n{task['task_description']}\n:calendar: {due_str}",
                },
            }
        )
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Edit"},
                        "action_id": "edit_task",
                        "value": button_value,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Remove"},
                        "style": "danger",
                        "action_id": "remove_task",
                        "value": button_value,
                    },
                ],
            }
        )
        blocks.append({"type": "divider"})

    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Delegate Tasks"},
                    "style": "primary",
                    "action_id": "send_tasks",
                    "value": json.dumps(
                        {
                            "draft_id": draft_id,
                            "channel_id": channel_id,
                            "transcript_id": transcript_id,
                        }
                    ),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "style": "danger",
                    "action_id": "cancel_tasks",
                    "value": json.dumps({"draft_id": draft_id}),
                },
            ],
        }
    )

    return blocks