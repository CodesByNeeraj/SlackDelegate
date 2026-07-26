import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from shared.models import task as task_model
from shared.models import transcript as transcript_model
from shared.models import search_log
from slack_app.agents.tools.embeddings import generate_embedding
from slack_app.agents.tools.task_filter import apply_task_filter

load_dotenv()

from langfuse import observe, get_client
from langfuse.openai import OpenAI

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


def _extract_query_participants(query: str, user_name: str | None) -> list[str] | None:
    """
    Extracts person names mentioned in the query.
    Adds user_name if first-person pronouns are detected.
    Returns None if no names found (no participant filter needed).
    """
    try:
        response = _client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": 'Extract person names explicitly mentioned in this query. Return a JSON object: {"names": [...]}. If no person names appear, return {"names": []}. Do not include pronouns like "I" or "me".'},
                {"role": "user", "content": query},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            name="extract-query-participants",
        )
        names = json.loads(response.choices[0].message.content).get("names", [])
    except Exception:
        names = []

    if user_name:
        names.append(user_name)

    return names if names else None


_RERANK_SYSTEM_PROMPT = """You evaluate whether retrieved text chunks are relevant to answering a user's query.

Label each chunk as "relevant" or "not" based on:
- "relevant": directly answers the query OR provides necessary supporting context
- "not": loosely related, tangential, or does not help answer the query

Return only valid JSON with no explanation.

---
Example 1:
Query: "What is Docker?"
Chunks: {"c1": "Docker is a container platform that packages applications and their dependencies.", "c2": "Kubernetes manages containerized workloads across clusters.", "c3": "Containers allow apps to run in isolated environments."}
Output: {"c1": "relevant", "c2": "not", "c3": "relevant"}

---
Example 2:
Query: "What budget was approved for Q3?"
Chunks: {"c1": "The team discussed marketing strategies for the product launch.", "c2": "Finance approved $50k for Q3 operations during the board meeting.", "c3": "Project timelines were reviewed and milestones are on track."}
Output: {"c1": "not", "c2": "relevant", "c3": "not"}

---
Example 3:
Query: "Who is responsible for the API integration?"
Chunks: {"c1": "John was assigned the API integration task due end of month.", "c2": "The frontend team is building the new dashboard.", "c3": "Sarah said she would support John on the API work if needed."}
Output: {"c1": "relevant", "c2": "not", "c3": "relevant"}
"""


def _rerank_chunks(query: str, chunks: list[dict]) -> list[dict]:
    """
    Labels each chunk relevant/not in one LLM call.
    Returns relevant chunks in lost-in-the-middle order (best first, second best last).
    Falls back to top cosine chunk if all are labeled not relevant.
    """
    if len(chunks) <= 1:
        return chunks

    chunk_map = {f"c{i + 1}": chunk for i, chunk in enumerate(chunks)}
    chunks_payload = json.dumps({k: v["chunk_text"] for k, v in chunk_map.items()})

    try:
        response = _client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": _RERANK_SYSTEM_PROMPT},
                {"role": "user", "content": f'Query: "{query}"\nChunks: {chunks_payload}'},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            name="rerank-chunks",
        )
        labels = json.loads(response.choices[0].message.content)
    except Exception:
        return chunks

    relevant = [chunk_map[k] for k in sorted(chunk_map) if labels.get(k) == "relevant"]

    if not relevant:
        return [chunks[0]]

    return relevant


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
        name="answer-transcript-query",
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
        name="answer-tasks-query",
    )
    return response.choices[0].message.content



@observe(name="search-agent", as_type="agent", capture_input=False, capture_output=False)
def run(query: str, user_id: str, workspace_id: str, user_name: str | None = None) -> tuple[str, list]:
    """
    Search agent entry point — invoked by master orchestrator via invoke_search_agent.
    Embeds the query, searches transcript chunks, fetches their tasks, and synthesizes an answer.
    Returns (answer_text, slack_blocks).
    """
    get_client().update_current_span(input=query)
    query_embedding = generate_embedding(query)
    max_transcripts = 1 if _has_specific_past_intent(query) else None
    participant_filter = _extract_query_participants(query, user_name)
    get_client().update_current_span(metadata={
        "max_transcripts": str(max_transcripts),
        "participant_filter": ",".join(participant_filter) if participant_filter else "",
    })
    top_chunks = transcript_model.search_transcripts(
        workspace_id, query_embedding, top_n=10,
        max_transcripts=max_transcripts,
        participant_filter=participant_filter,
    )

    if not top_chunks:
        if user_name and not transcript_model.user_has_transcripts(workspace_id, user_name):
            answer = "Sorry, I'm not allowed to answer about meetings you were not part of."
        else:
            answer = "Sorry, I could not find anything matching your query. Please try rephrasing or providing more context."
        snippets = []
        source_blocks = []
    else:
        top_chunks = _rerank_chunks(query, top_chunks)
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

    get_client().update_current_span(output=answer)

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f":mag: *Search results for:* _{query}_"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": answer}},
        *source_blocks,
    ]
    return answer, blocks
