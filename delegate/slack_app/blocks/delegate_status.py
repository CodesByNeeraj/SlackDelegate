from datetime import datetime


def _format_due_date(due_date: str | None) -> str:
    if not due_date or due_date == "NONE":
        return "No due date"
    try:
        return datetime.fromisoformat(due_date).strftime("%b %d, %Y")
    except ValueError:
        return due_date


def _status_emoji(status: str) -> str:
    return {"pending": ":hourglass:", "done": ":white_check_mark:", "cancelled": ":x:"}.get(status, ":grey_question:")


def _owner_ref(task: dict) -> str:
    if task.get("owner_slack_id") and task["owner_slack_id"] != "UNASSIGNED":
        return f"<@{task['owner_slack_id']}>"
    return task.get("owner_name_raw", "Unassigned")


def _group_by_transcript(tasks: list) -> list[tuple[str, list]]:
    """Returns list of (transcript_id, tasks) sorted by most recent first."""
    groups: dict[str, list] = {}
    for t in tasks:
        tid = t.get("source_transcript_id", "unknown")
        groups.setdefault(tid, []).append(t)
    # Sort groups by the most recent created_at within each group
    return sorted(
        groups.items(),
        key=lambda g: max(t.get("created_at", "") for t in g[1]),
        reverse=True,
    )


def _task_row(task: dict) -> dict:
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"{_status_emoji(task.get('status', 'pending'))} *{task['task_description']}*\n"
                f":bust_in_silhouette: {_owner_ref(task)}   :calendar: {_format_due_date(task.get('due_date'))}"
            ),
        },
    }


def build_delegate_status_blocks(all_tasks: list) -> list:
    """Shows only the most recent delegation batch."""
    if not all_tasks:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": "You haven't delegated any tasks yet."}}]

    groups = _group_by_transcript(all_tasks)
    _, latest_tasks = groups[0]

    pending = sum(1 for t in latest_tasks if t.get("status") == "pending")
    done = sum(1 for t in latest_tasks if t.get("status") == "done")

    date_str = datetime.fromisoformat(latest_tasks[0]["created_at"]).strftime("%b %d, %Y") if latest_tasks[0].get("created_at") else "recent"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Last delegation — {date_str}"}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":hourglass: *{pending} pending*   :white_check_mark: *{done} done*"},
        },
        {"type": "divider"},
    ]

    for task in sorted(latest_tasks, key=lambda t: t.get("due_date") or "9999"):
        blocks.append(_task_row(task))

    return blocks


def build_delegate_digest_blocks(all_tasks: list) -> list:
    """Shows all delegations grouped by meeting."""
    if not all_tasks:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": "You haven't delegated any tasks yet."}}]

    groups = _group_by_transcript(all_tasks)

    total_pending = sum(1 for t in all_tasks if t.get("status") == "pending")
    total_done = sum(1 for t in all_tasks if t.get("status") == "done")

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Delegation Digest"}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":hourglass: *{total_pending} pending across all meetings*   :white_check_mark: *{total_done} done*"},
        },
        {"type": "divider"},
    ]

    for i, (transcript_id, tasks) in enumerate(groups):
        date_str = datetime.fromisoformat(tasks[0]["created_at"]).strftime("%b %d, %Y") if tasks[0].get("created_at") else f"Meeting {i + 1}"
        pending = sum(1 for t in tasks if t.get("status") == "pending")
        done = sum(1 for t in tasks if t.get("status") == "done")

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{date_str}* — {len(tasks)} task(s)   :hourglass: {pending} pending   :white_check_mark: {done} done"},
        })
        for task in tasks:
            blocks.append(_task_row(task))
        blocks.append({"type": "divider"})

    return blocks
