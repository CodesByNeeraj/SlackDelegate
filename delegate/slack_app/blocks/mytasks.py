from datetime import datetime


def _format_due_date(due_date: str | None) -> str:
    if not due_date or due_date == "NONE":
        return "No due date"
    try:
        return datetime.fromisoformat(due_date).strftime("%b %d, %Y")
    except ValueError:
        return due_date


def _status_badge(status: str) -> str:
    return {"pending": ":hourglass: Pending", "blocked": ":warning: Blocked"}.get(status, status)


def build_mytasks_blocks(tasks: list) -> list:
    if not tasks:
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": ":white_check_mark: You have no open tasks right now."},
            }
        ]

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Your open tasks ({len(tasks)})"},
        },
        {"type": "divider"},
    ]

    for task in tasks:
        due_str = _format_due_date(task.get("due_date"))
        assigned_by = f"<@{task['created_by']}>" if task.get("created_by") else "someone"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{task['task_description']}*\n"
                        f":calendar: {due_str}   {_status_badge(task.get('status', 'pending'))}\n"
                        f"_Assigned by {assigned_by}_"
                    ),
                },
            }
        )
        blocks.append({"type": "divider"})

    return blocks
