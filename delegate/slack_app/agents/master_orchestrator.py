import json
import os
from dotenv import load_dotenv

load_dotenv()

from langfuse.openai import OpenAI

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

#agent as a tool pattern
_SYSTEM_PROMPT = """You are the orchestrator agent for Delegate, a meeting task management assistant.
Based on the user's message, decide whether to delegate to the search agent or invoke a tool directly.

Search agent (handles transcript content — embed + search + LLM synthesis):
- invoke_search_agent: any question about meeting discussions, decisions, transcript content, or queries needing both transcript and task context

Tools (direct data retrieval):
- tasks_db_search: query is about task ownership, status, assignments, or overdue tasks — answered from live task data only, no transcript needed
- invoke_status_tool: user wants to see the status of tasks from their most recently delegated meeting
- invoke_digest_tool: user wants a full digest or summary of all their delegated tasks
- out_of_scope: message is clearly unrelated to task management or meetings

Be conservative with out_of_scope — when in doubt, prefer invoke_search_agent.
"""

# openai function calling schema
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "invoke_search_agent",
            "description": "Delegate to the search agent — query is about meeting discussions, decisions, transcript content, or needs both transcript and live task context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Copy the user's exact message verbatim. Do not rephrase, expand, or add anything."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tasks_db_search",
            "description": "Query is about task ownership, status, assignments, overdue tasks, or completions — answerable from live task data only, no transcript needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The user's question."},
                    "status_filter": {
                        "type": "string",
                        "enum": ["all", "pending", "done", "cancelled", "overdue"],
                        "description": "Filter tasks by status. Use 'all' if no specific status is asked for.",
                    },
                    "owner_name": {
                        "type": "string",
                        "description": "Filter by this person's name if mentioned. Empty string otherwise.",
                    },
                },
                "required": ["query", "status_filter", "owner_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_status_tool",
            "description": "User wants to see the status of tasks from their most recently delegated meeting.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_digest_tool",
            "description": "User wants a full digest or summary of all their delegated tasks.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "out_of_scope",
            "description": "Message is clearly unrelated to task management or meetings — e.g. general knowledge, jokes, coding help. Do NOT use for vague questions that could relate to meetings or people.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def classify(text: str, history: list[dict] | None = None) -> dict:
    """
    Returns {"route": str, "args": dict}
    route is one of: invoke_search_agent, tasks_db_search,
                     invoke_status_tool, invoke_digest_tool, out_of_scope
    """
    response = _client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            *(history or []),
            {"role": "user", "content": text},
        ],
        tools=_TOOLS,
        tool_choice="required",
        temperature=0,
        name="classify-intent",
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return {
        "route": tool_call.function.name,
        "args": json.loads(tool_call.function.arguments),
    }
