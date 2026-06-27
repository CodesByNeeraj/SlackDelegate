import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_SYSTEM_PROMPT = """You are a helpful assistant answering questions about past meeting transcripts and their delegated tasks.

Answer the question using only the transcript excerpts and task information provided below. Be concise and specific.
If the answer cannot be found in the provided context, say so clearly and do not guess or make up information.
"""


def _format_date(iso_str: str) -> str:
    try:
        return datetime.fromisoformat(iso_str).strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return "Unknown date"


def _format_tasks(tasks: list) -> str:
    if not tasks:
        return "  No tasks were delegated from this meeting."
    lines = []
    for t in tasks:
        owner = t.get("owner_name_raw", "Unknown")
        due = t.get("due_date") or "no due date"
        status = t.get("status", "unknown")
        lines.append(f"  • {owner}: {t['task_description']} (due: {due}, status: {status})")
    return "\n".join(lines)


def answer_search_query(query: str, chunks_with_tasks: list[tuple[dict, list]], user_name: str | None = None) -> str:
    """
    chunks_with_tasks: list of (chunk_info, tasks) ordered by relevance.
    chunk_info has: chunk_text, transcript_id, created_at, chunk_index.
    tasks are all tasks from the same transcript as the chunk.
    """
    context_parts = []
    for i, (chunk, tasks) in enumerate(chunks_with_tasks, 1):
        date_str = _format_date(chunk.get("created_at", ""))
        context_parts.append(
            f"[Excerpt {i} — from meeting on {date_str}]\n"
            f"{chunk['chunk_text']}\n\n"
            f"Tasks delegated from this meeting:\n{_format_tasks(tasks)}"
        )

    context = "\n\n---\n\n".join(context_parts)

    user_line = f"The person asking is: {user_name}\n" if user_name else ""

    response = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"{user_line}Question: {query}\n\nContext:\n{context}"},
        ],
        temperature=0.3,
    )

    return response.choices[0].message.content
