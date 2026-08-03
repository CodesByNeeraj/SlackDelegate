from boto3.dynamodb.conditions import Key
from shared.db.dynamo_client import get_table

TABLE_NAME = "TranscriptChunks"


def save_chunks(workspace_id: str, transcript_id: str, chunks: list[dict]) -> None:
    table = get_table(TABLE_NAME)
    with table.batch_writer() as batch:
        for chunk in chunks:
            batch.put_item(Item={
                "workspace_id": workspace_id,
                "chunk_key": f"{transcript_id}#{chunk['chunk_index']}",
                "transcript_id": transcript_id,
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "embedding_json": chunk["embedding_json"],
            })


def get_chunks_for_workspace(workspace_id: str) -> list[dict]:
    table = get_table(TABLE_NAME)
    response = table.query(KeyConditionExpression=Key("workspace_id").eq(workspace_id))
    items = response.get("Items", [])
    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("workspace_id").eq(workspace_id),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))
    return items


def delete_chunks_for_transcript(workspace_id: str, transcript_id: str) -> None:
    table = get_table(TABLE_NAME)
    response = table.query(
        KeyConditionExpression=Key("workspace_id").eq(workspace_id) & Key("chunk_key").begins_with(transcript_id)
    )
    items = response.get("Items", [])
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"workspace_id": workspace_id, "chunk_key": item["chunk_key"]})
