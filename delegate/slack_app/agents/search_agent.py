import os
from datetime import datetime, timezone
from openai import OpenAI
from dotenv import load_dotenv
from shared.models import task as task_model
from shared.models import transcript as transcript_model
from slack_app.agents.tools.embeddings import generate_embedding
from slack_app.agents.tools.task_filter import apply_task_filter

load_dotenv()

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_FORMATTING_RULES = """
Format your response for Slack:
- Use *bold* (single asterisk) for emphasis, never **double asterisk**
- Use _italic_ (underscore) for italics
- Use • for bullet points, never - or *
- Keep responses concise
"""

_TRANSCRIPT_SYSTEM_PROMPT = """You are Delegate, an intelligent meeting intelligence agent. You surface insights from past meeting transcripts and their delegated tasks.

Answer the question using only the transcript excerpts and task information provided below. Be concise and specific.
If the answer cannot be found in the provided context, say so clearly and do not guess or make up information.
""" + _FORMATTING_RULES

_TASKS_SYSTEM_PROMPT = """You are Delegate, an intelligent task intelligence agent. You have real-time visibility into delegated tasks and their current status.

Answer the question using only the task data provided. Be concise and specific.
If the answer cannot be determined from the task data, say so clearly.
""" + _FORMATTING_RULES


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
        model="gpt-5.4-mini",
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
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": _TASKS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Today's date: {_today()}\n{user_line}Question: {query}\n\nTasks:\n{tasks_context}"},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content



def run(query: str, user_id: str, workspace_id: str, user_name: str | None = None) -> tuple[str, list]:
    """
    Search agent entry point — invoked by master orchestrator via invoke_search_agent.
    Embeds the query, searches transcript chunks, fetches their tasks, and synthesizes an answer.
    Returns (answer_text, slack_blocks).
    """
    query_embedding = generate_embedding(query)
    top_chunks = transcript_model.search_transcripts(workspace_id, query_embedding, top_n=3)

    if not top_chunks:
        answer = "Sorry, I could not find anything matching your query. Please try rephrasing or providing more context."
    else:
        chunks_with_tasks = [
            (chunk, task_model.get_tasks_for_transcript(chunk["workspace_id"], chunk["transcript_id"]))
            for chunk in top_chunks
        ]
        answer = answer_search_query(query, chunks_with_tasks, user_name=user_name)

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f":mag: *Search results for:* _{query}_"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": answer}},
    ]
    return answer, blocks
