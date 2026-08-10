from datetime import datetime, timezone


def apply_task_filter(tasks: list, args: dict) -> list:
    status_filter = args.get("status_filter", "all")
    owner_names = [n.strip().lower() for n in (args.get("owner_names") or []) if n.strip()]
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

    if owner_names:
        tasks = [t for t in tasks if any(n in (t.get("owner_name_raw") or "").lower() for n in owner_names)]

    return tasks
