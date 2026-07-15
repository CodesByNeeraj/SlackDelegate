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


_PAGE_SIZE = 15


def build_review_blocks(tasks: list, draft_id: str, channel_id: str, transcript_id: str, page: int = 0) -> list:
    total = len(tasks)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _PAGE_SIZE
    end = min(start + _PAGE_SIZE, total)
    displayed = tasks[start:end]

    header_text = f"Found {total} action item(s)"
    if total_pages > 1:
        header_text += f" — page {page + 1} of {total_pages}"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Review and edit before sending. Nothing is saved until you click *Delegate Tasks*.",
                }
            ],
        },
        {"type": "divider"},
    ]

    for i, task in enumerate(displayed):
        abs_index = start + i
        due_str = _format_due_date(task.get("due_date"))
        owner_slack_id = task.get("owner_slack_id")
        if owner_slack_id:
            owner_display = f"<@{owner_slack_id}>"
        else:
            owner_display = f"*{task['owner_name']}* ⚠️ _unmatched — click Edit to assign_"
        button_value = json.dumps({"draft_id": draft_id, "task_index": abs_index, "page": page})
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

    if total_pages > 1:
        nav_elements = []
        if page > 0:
            nav_elements.append({
                "type": "button",
                "text": {"type": "plain_text", "text": "← Prev"},
                "action_id": "prev_page_tasks",
                "value": json.dumps({"draft_id": draft_id, "page": page - 1}),
            })
        if end < total:
            nav_elements.append({
                "type": "button",
                "text": {"type": "plain_text", "text": "Next →"},
                "action_id": "next_page_tasks",
                "value": json.dumps({"draft_id": draft_id, "page": page + 1}),
            })
        if nav_elements:
            blocks.append({"type": "actions", "elements": nav_elements})

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