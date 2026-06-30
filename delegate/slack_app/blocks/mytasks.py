from datetime import datetime, timezone


def _format_due_date(due_date: str | None) -> str:
    if not due_date or due_date == "NONE":
        return "No due date"
    try:
        return datetime.fromisoformat(due_date).strftime("%b %d, %Y")
    except ValueError:
        return due_date


def _is_overdue(due_date: str | None) -> bool:
    if not due_date or due_date == "NONE":
        return False
    try:
        dt = datetime.fromisoformat(due_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < datetime.now(tz=timezone.utc)
    except ValueError:
        return False


def _status_badge(status: str, due_date: str | None = None) -> str:
    if status == "pending" and _is_overdue(due_date):
        return ":red_circle: Pending (Late)"
    return {"pending": ":hourglass: Pending"}.get(status, status)


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

        block = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{task['task_description']}*\n"
                    f":calendar: {due_str}   {_status_badge(task.get('status', 'pending'), task.get('due_date'))}\n"
                    f"_Assigned by {assigned_by}_"
                ),
            },
        }

        dm_channel_id = task.get("dm_channel_id")
        dm_message_ts = task.get("dm_message_ts")
        if dm_channel_id and dm_message_ts:
            ts_slug = dm_message_ts.replace(".", "")
            block["accessory"] = {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Task"},
                "url": f"https://slack.com/archives/{dm_channel_id}/p{ts_slug}",
                "action_id": "view_task_link",
            }

        blocks.append(block)
        blocks.append({"type": "divider"})

    return blocks
