import os
import uuid
from datetime import datetime, timezone
from shared.db.dynamo_client import get_table

def _table_name() -> str:
    return os.environ["SEARCH_LOGS_TABLE"]


def log_search(workspace_id: str, user_id: str, query: str, snippets: list[str], answer: str):
    table = get_table(_table_name())
    table.put_item(Item={
        "log_id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "user_id": user_id,
        "query": query,
        "snippets": snippets,
        "answer": answer,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def get_all_logs() -> list[dict]:
    table = get_table(_table_name())
    response = table.scan(ProjectionExpression="log_id, workspace_id, #q, snippets, #ans, #ts",
                          ExpressionAttributeNames={"#q": "query", "#ans": "answer", "#ts": "timestamp"})
    items = response.get("Items", [])
    return sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)
