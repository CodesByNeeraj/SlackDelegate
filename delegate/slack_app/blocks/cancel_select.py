from datetime import datetime


def _format_due_date(due_date: str | None) -> str:
    if not due_date or due_date == "NONE":
        return "No due date"
    try:
        return datetime.fromisoformat(due_date).strftime("%b %d, %Y")
    except ValueError:
        return due_date


def build_cancel_select_blocks(tasks: list, selected_task: dict = None) -> list:
    if not tasks:
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "You have no active tasks to cancel."},
            }
        ]

    options = []
    for t in tasks:
        owner = t.get("owner_name_raw", "Unknown")
        desc = t["task_description"]
        label = f"{owner}: {desc}"
        if len(label) > 75:
            label = label[:72] + "..."
        options.append(
            {
                "text": {"type": "plain_text", "text": label},
                "value": f"{t['workspace_id']}:{t['task_id']}",
            }
        )

    select_element = {
        "type": "static_select",
        "action_id": "select_task_to_cancel",
        "placeholder": {"type": "plain_text", "text": "Choose a task..."},
        "options": options,
    }
    if selected_task:
        select_element["initial_option"] = {
            "text": {"type": "plain_text", "text": next(
                (o["text"]["text"] for o in options if o["value"] == f"{selected_task['workspace_id']}:{selected_task['task_id']}"),
                "Selected"
            )},
            "value": f"{selected_task['workspace_id']}:{selected_task['task_id']}",
        }

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Select a task to cancel:"},
        },
        {
            "type": "actions",
            "block_id": "cancel_select_block",
            "elements": [
                select_element,
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel Task"},
                    "style": "danger",
                    "action_id": "confirm_cancel_task",
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Cancel this task?"},
                        "text": {
                            "type": "mrkdwn",
                            "text": "The assignee will be notified in their task thread that this has been cancelled.",
                        },
                        "confirm": {"type": "plain_text", "text": "Yes, cancel it"},
                        "deny": {"type": "plain_text", "text": "Never mind"},
                    },
                },
            ],
        },
    ]

    if selected_task:
        owner_ref = f"<@{selected_task['owner_slack_id']}>" if selected_task.get("owner_slack_id") and selected_task["owner_slack_id"] != "UNASSIGNED" else selected_task.get("owner_name_raw", "Unknown")
        due_str = _format_due_date(selected_task.get("due_date"))
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":clipboard: *Full task details*\n"
                        f"{selected_task['task_description']}\n"
                        f":bust_in_silhouette: {owner_ref}   :calendar: {due_str}"
                    ),
                },
            }
        )

    return blocks
