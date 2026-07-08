from datetime import datetime, timezone


def apply_task_filter(tasks: list, args: dict) -> list:
    status_filter = args.get("status_filter", "all")
    owner_name = (args.get("owner_name") or "").strip().lower()
    now = datetime.now(timezone.utc).isoformat()

    if status_filter == "pending":
        tasks = [t for t in tasks if t.get("status") == "pending"]
    elif status_filter == "done":
        tasks = [t for t in tasks if t.get("status") == "done"]
    elif status_filter == "cancelled":
        tasks = [t for t in tasks if t.get("status") == "cancelled"]
    elif status_filter == "overdue":
        tasks = [
            t for t in tasks
            if t.get("status") == "pending"
            and t.get("due_date")
            and t["due_date"] != "NONE"
            and t["due_date"] < now
        ]

    if owner_name:
        tasks = [t for t in tasks if owner_name in (t.get("owner_name_raw") or "").lower()]

    return tasks
