import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_SYSTEM_PROMPT = """You are a query router for a task management system.
Classify the user's query into the correct search route.

- tasks_db_search: query is about task ownership, status, assignments, overdue tasks, completions — answerable from live task data
- semantic_search: query is about meeting discussions, decisions, or transcript content
- combined_search: query needs both meeting transcript content AND current task state
- out_of_scope: query is unrelated to tasks, meetings, or delegated work (e.g. general knowledge, coding help, jokes)

Be conservative with combined_search — only use it when both are clearly needed.
Reject anything that is not genuinely about the user's tasks or meeting transcripts.
"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tasks_db_search",
            "description": "Query is about task ownership, completion status, assignments, or due dates. Answered from the live tasks database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "enum": ["all", "pending", "done", "cancelled", "overdue"],
                        "description": "Filter tasks by status. Use 'all' if no specific status is asked for.",
                    },
                    "owner_name": {
                        "type": "string",
                        "description": "Filter by this person's name if a specific person is mentioned. Empty string otherwise.",
                    },
                },
                "required": ["status_filter", "owner_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "Query is about meeting discussions, decisions, context, or content from transcripts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "combined_search",
            "description": "Query needs both transcript content AND current task status or ownership.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "enum": ["all", "pending", "done", "cancelled", "overdue"],
                        "description": "Filter tasks by status.",
                    },
                    "owner_name": {
                        "type": "string",
                        "description": "Filter by this person's name if mentioned. Empty string otherwise.",
                    },
                },
                "required": ["status_filter", "owner_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "out_of_scope",
            "description": "Query is unrelated to tasks, meetings, or delegated work.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def classify_query(query: str) -> dict:
    """
    Returns {"route": "tasks_db_search"|"semantic_search"|"combined_search", "args": {...}}
    """
    response = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        tools=_TOOLS,
        tool_choice="required",
        temperature=0,
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return {
        "route": tool_call.function.name,
        "args": json.loads(tool_call.function.arguments),
    }
