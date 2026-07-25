import json
import math
import uuid
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
from shared.db.dynamo_client import get_table

TABLE_NAME = "Transcripts"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x ** 2 for x in a))
    norm_b = math.sqrt(sum(x ** 2 for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def create_transcript(
    workspace_id: str,
    raw_text: str,
    uploaded_by: str,
    channel_id: str,
    chunks: list[dict] | None = None,
    filename: str | None = None,
    file_permalink: str | None = None,
    embedding_tokens: int | None = None,
    extraction_prompt_tokens: int | None = None,
    extraction_completion_tokens: int | None = None,
    extraction_latency_ms: int | None = None,
    task_count: int | None = None,
) -> dict:
    table = get_table(TABLE_NAME)
    transcript_id = str(uuid.uuid4())
    now = _now_iso()

    item = {
        "workspace_id": workspace_id,
        "transcript_id": transcript_id,
        "raw_text": raw_text,
        "uploaded_by": uploaded_by,
        "channel_id": channel_id,
        "created_at": now,
        "filename": filename or "unknown",
        "file_permalink": file_permalink or "",
        "embedding_tokens": embedding_tokens or 0,
        "extraction_prompt_tokens": extraction_prompt_tokens or 0,
        "extraction_completion_tokens": extraction_completion_tokens or 0,
        "extraction_latency_ms": extraction_latency_ms or 0,
        "task_count": task_count or 0,
    }
    if chunks:
        item["chunks"] = chunks

    table.put_item(Item=item)
    return item


def get_transcript(workspace_id: str, transcript_id: str) -> dict | None:
    table = get_table(TABLE_NAME)
    response = table.get_item(Key={"workspace_id": workspace_id, "transcript_id": transcript_id})
    return response.get("Item")


def get_transcripts_for_workspace(workspace_id: str) -> list[dict]:
    table = get_table(TABLE_NAME)
    response = table.query(KeyConditionExpression=Key("workspace_id").eq(workspace_id))
    return response.get("Items", [])


def search_transcripts(
    workspace_id: str,
    query_embedding: list[float],
    top_n: int = 3,
    max_transcripts: int | None = None,
) -> list[dict]:
    """
    Scores every chunk across all transcripts by cosine similarity.
    Returns the top_n chunks as dicts with transcript metadata attached.
    Transcripts without chunks (uploaded before this feature) are skipped.
    If max_transcripts is set, only the most recent N transcripts are searched.
    """
    transcripts = get_transcripts_for_workspace(workspace_id)
    if max_transcripts is not None:
        transcripts = sorted(transcripts, key=lambda t: t.get("created_at", ""), reverse=True)[:max_transcripts]
    scored = []

    for t in transcripts:
        for chunk in t.get("chunks", []):
            stored = json.loads(chunk["embedding_json"])
            score = _cosine_similarity(query_embedding, stored)
            scored.append((score, {
                "chunk_text": chunk["text"],
                "chunk_index": chunk["chunk_index"],
                "transcript_id": t["transcript_id"],
                "workspace_id": t["workspace_id"],
                "created_at": t.get("created_at", ""),
                "uploaded_by": t.get("uploaded_by", ""),
            }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk_info for _, chunk_info in scored[:top_n]]


def delete_transcript(workspace_id: str, transcript_id: str) -> None:
    table = get_table(TABLE_NAME)
    table.delete_item(Key={"workspace_id": workspace_id, "transcript_id": transcript_id})
