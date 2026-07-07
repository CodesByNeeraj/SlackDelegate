import os
from datetime import datetime, timezone
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_TRANSCRIPT_SYSTEM_PROMPT = """You are Delegate, an intelligent meeting intelligence agent. You surface insights from past meeting transcripts and their delegated tasks.

Answer the question using only the transcript excerpts and task information provided below. Be concise and specific.
If the answer cannot be found in the provided context, say so clearly and do not guess or make up information.
"""

_TASKS_SYSTEM_PROMPT = """You are Delegate, an intelligent task intelligence agent. You have real-time visibility into delegated tasks and their current status.

Answer the question using only the task data provided. Be concise and specific.
If the answer cannot be determined from the task data, say so clearly.
"""

_COMBINED_SYSTEM_PROMPT = """You are Delegate, an intelligent meeting and task intelligence agent. You cross-reference live task data with meeting transcript context to surface accurate insights.

You have access to both transcript excerpts and live task data. Use both to answer accurately.
Prefer current task status data over what the transcript says when they conflict.
Be concise and specific. Do not guess or make up information.
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


def _format_flat_tasks(tasks: list) -> str:
    if not tasks:
        return "No tasks found."
    lines = []
    for t in tasks:
        owner = t.get("owner_name_raw", "Unknown")
        due = t.get("due_date") or "no due date"
        status = t.get("status", "unknown")
        lines.append(f"• {owner}: {t['task_description']} (due: {due}, status: {status})")
    return "\n".join(lines)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def answer_search_query(query: str, chunks_with_tasks: list[tuple[dict, list]], user_name: str | None = None) -> str:
    """
    Route 2: Semantic search only.
    chunks_with_tasks: list of (chunk_info, tasks) ordered by relevance.
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
            {"role": "system", "content": _TRANSCRIPT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Today's date: {_today()}\n{user_line}Question: {query}\n\nContext:\n{context}"},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


def answer_from_tasks(query: str, tasks: list, user_name: str | None = None) -> str:
    """Route 1: Tasks DB only — no transcript context."""
    tasks_context = _format_flat_tasks(tasks)
    user_line = f"The person asking is: {user_name}\n" if user_name else ""

    response = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _TASKS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Today's date: {_today()}\n{user_line}Question: {query}\n\nTasks:\n{tasks_context}"},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


def answer_combined(
    query: str,
    tasks: list,
    chunks_with_tasks: list[tuple[dict, list]],
    user_name: str | None = None,
) -> str:
    """Route 3: Tasks DB + semantic search combined."""
    tasks_section = f"Current task data:\n{_format_flat_tasks(tasks)}"

    transcript_parts = []
    for i, (chunk, chunk_tasks) in enumerate(chunks_with_tasks, 1):
        date_str = _format_date(chunk.get("created_at", ""))
        transcript_parts.append(
            f"[Excerpt {i} — from meeting on {date_str}]\n"
            f"{chunk['chunk_text']}\n\n"
            f"Tasks from this meeting (may be stale):\n{_format_tasks(chunk_tasks)}"
        )

    transcript_section = "\n\n---\n\n".join(transcript_parts) if transcript_parts else "No relevant transcript excerpts found."
    context = f"{tasks_section}\n\n===\n\nTranscript excerpts:\n{transcript_section}"
    user_line = f"The person asking is: {user_name}\n" if user_name else ""

    response = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _COMBINED_SYSTEM_PROMPT},
            {"role": "user", "content": f"Today's date: {_today()}\n{user_line}Question: {query}\n\nContext:\n{context}"},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content
