from shared.models import task as task_model
from slack_app.blocks.delegate_status import build_delegate_status_blocks


def run(user_id: str, workspace_id: str) -> tuple[list, str]:
    tasks = task_model.get_tasks_created_by(workspace_id, user_id)
    blocks = build_delegate_status_blocks(tasks)
    text = f"You have {len(tasks)} delegated task(s)."
    return blocks, text
