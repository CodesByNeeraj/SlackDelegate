import os
from datetime import datetime, timezone
from openai import OpenAI
from dotenv import load_dotenv
from shared.models import task as task_model
from shared.models import transcript as transcript_model
from shared.models import search_log
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
Ensure your response uses correct grammar and clear sentence structure throughout.
If the name of the person asking appears anywhere in the transcript or your answer, replace it with "you" or "your" — never refer to them by name.
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


_SPECIFIC_PAST_KEYWORDS = {"previous", "last", "most recent", "latest", "yesterday", "prior", "last meeting", "previous meeting"}

def _has_specific_past_intent(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _SPECIFIC_PAST_KEYWORDS)


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

    name_instruction = f'The person asking is "{user_name}". If "{user_name}" appears anywhere in the transcript or your answer, replace it with "you" or "your".' if user_name else ""
    system_prompt = _TRANSCRIPT_SYSTEM_PROMPT + (f"\n{name_instruction}" if name_instruction else "")

    response = _client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Today's date: {_today()}\nQuestion: {query}\n\nContext:\n{context}"},
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
    max_transcripts = 1 if _has_specific_past_intent(query) else None
    top_chunks = transcript_model.search_transcripts(workspace_id, query_embedding, top_n=3, max_transcripts=max_transcripts)

    if not top_chunks:
        answer = "Sorry, I could not find anything matching your query. Please try rephrasing or providing more context."
        snippets = []
        source_blocks = []
    else:
        chunks_with_tasks = [
            (chunk, task_model.get_tasks_for_transcript(chunk["workspace_id"], chunk["transcript_id"]))
            for chunk in top_chunks
        ]
        answer = answer_search_query(query, chunks_with_tasks, user_name=user_name)
        snippets = [chunk["chunk_text"] for chunk in top_chunks]

        seen = {}
        for chunk in top_chunks:
            tid = chunk["transcript_id"]
            if tid not in seen:
                t = transcript_model.get_transcript(chunk["workspace_id"], tid)
                if t:
                    seen[tid] = t

        source_lines = []
        for t in seen.values():
            permalink = t.get("file_permalink", "")
            fname = t.get("filename", "unknown")
            if permalink:
                source_lines.append(f"• <{permalink}|{fname}>")
            else:
                source_lines.append(f"• {fname}")

        source_blocks = [
            {"type": "context", "elements": [{"type": "mrkdwn", "text": ":page_facing_up: *Sources:* " + "  ".join(source_lines)}]}
        ] if source_lines else []

    try:
        search_log.log_search(workspace_id=workspace_id, user_id=user_id, query=query, snippets=snippets, answer=answer)
    except Exception:
        pass

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f":mag: *Search results for:* _{query}_"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": answer}},
        *source_blocks,
    ]
    return answer, blocks
