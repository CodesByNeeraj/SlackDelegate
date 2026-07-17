from datetime import datetime


def _format_due_date(due_date: str | None) -> str:
    if not due_date or due_date == "NONE":
        return "No due date set"
    try:
        dt = datetime.fromisoformat(due_date)
        return dt.strftime("%b %d, %Y at %I:%M %p (SGT)")
    except ValueError:
        return due_date


def build_task_dm_blocks(task: dict, assigned_by_slack_id: str) -> list:
    due_str = _format_due_date(task.get("due_date"))
    owner_slack_id = task.get("owner_slack_id")
    self_assigned = owner_slack_id and owner_slack_id == assigned_by_slack_id

    header = (
        f"You have assigned yourself a task:\n\n"
        f"*{task['task_description']}*\n"
        f":calendar: Due: {due_str}"
    ) if self_assigned else (
        f"<@{assigned_by_slack_id}> has assigned you a task:\n\n"
        f"*{task['task_description']}*\n"
        f":calendar: Due: {due_str}"
    )

    instructions = (
        "Reply in this thread to update your status:\n"
        "• *done* — mark it complete"
    ) if self_assigned else (
        "Reply in this thread to update your status:\n"
        "• *done* — mark it complete\n"
        "• *need more time until [date]* — request a new due date\n"
        "• *this should go to [name]* — request reassignment"
    )

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": instructions},
        },
    ]
