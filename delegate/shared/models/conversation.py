from shared.db.dynamo_client import get_table

TABLE_NAME = "ConversationHistory"
_WINDOW = 3  # exchanges kept (= 6 messages)


def get_history(workspace_id: str, user_id: str) -> list[dict]:
    table = get_table(TABLE_NAME)
    response = table.get_item(Key={"workspace_id": workspace_id, "user_id": user_id})
    return response.get("Item", {}).get("messages", [])


def append_exchange(workspace_id: str, user_id: str, user_message: str, assistant_message: str) -> None:
    history = get_history(workspace_id, user_id)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_message})
    trimmed = history[-(_WINDOW * 2):]
    get_table(TABLE_NAME).put_item(Item={
        "workspace_id": workspace_id,
        "user_id": user_id,
        "messages": trimmed,
    })
