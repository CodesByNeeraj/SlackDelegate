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
        return due_date < datetime.now(timezone.utc).isoformat()
    except Exception:
        return False


def _status_emoji(status: str, due_date: str | None = None) -> str:
    if status == "pending" and _is_overdue(due_date):
        return ":red_circle:"
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
    status = task.get("status", "pending")
    due_date = task.get("due_date")
    overdue = status == "pending" and _is_overdue(due_date)
    label = " *(Late)*" if overdue else ""
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"{_status_emoji(status, due_date)} *{task['task_description']}*{label}\n"
                f":bust_in_silhouette: {_owner_ref(task)}   :calendar: {_format_due_date(due_date)}"
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
    overdue = sum(1 for t in latest_tasks if t.get("status") == "pending" and _is_overdue(t.get("due_date")))

    date_str = datetime.fromisoformat(latest_tasks[0]["created_at"]).strftime("%b %d, %Y") if latest_tasks[0].get("created_at") else "recent"
    overdue_str = f"   :red_circle: *{overdue} overdue*" if overdue else ""

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Last delegation — {date_str}"}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":hourglass: *{pending} pending*   :white_check_mark: *{done} done*{overdue_str}"},
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
    total_overdue = sum(1 for t in all_tasks if t.get("status") == "pending" and _is_overdue(t.get("due_date")))
    overdue_str = f"   :red_circle: *{total_overdue} overdue*" if total_overdue else ""

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Delegation Digest"}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":hourglass: *{total_pending} pending across all meetings*   :white_check_mark: *{total_done} done*{overdue_str}"},
        },
        {"type": "divider"},
    ]

    for i, (transcript_id, tasks) in enumerate(groups):
        date_str = datetime.fromisoformat(tasks[0]["created_at"]).strftime("%b %d, %Y") if tasks[0].get("created_at") else f"Meeting {i + 1}"
        pending = sum(1 for t in tasks if t.get("status") == "pending")
        done = sum(1 for t in tasks if t.get("status") == "done")
        overdue = sum(1 for t in tasks if t.get("status") == "pending" and _is_overdue(t.get("due_date")))
        overdue_str = f"   :red_circle: {overdue} overdue" if overdue else ""

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{date_str}* — {len(tasks)} task(s)   :hourglass: {pending} pending   :white_check_mark: {done} done{overdue_str}"},
        })
        for task in tasks:
            blocks.append(_task_row(task))
        blocks.append({"type": "divider"})

    return blocks
