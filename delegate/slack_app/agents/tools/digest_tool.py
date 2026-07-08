from shared.models import task as task_model
from slack_app.blocks.delegate_status import build_delegate_digest_blocks


def run(user_id: str) -> tuple[list, str]:
    tasks = task_model.get_tasks_created_by(user_id)
    blocks = build_delegate_digest_blocks(tasks)
    text = "Your delegation digest."
    return blocks, text
