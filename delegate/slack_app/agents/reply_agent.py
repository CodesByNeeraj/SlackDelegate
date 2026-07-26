import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from langfuse.openai import OpenAI

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are interpreting a reply from a team member about a task they were assigned.

Today's date is {today}.

Based on their reply, call exactly one tool:
- mark_done: they are saying the task is complete ("done", "finished", "sent", "completed", etc.)
- request_reschedule: they need more time and explicitly mention a specific future date to reschedule to
- request_reassignment: they think someone else should own this task
- ask_for_date: they want more time but have not mentioned a specific date — ask them to provide one
- cancel_request: they are withdrawing or cancelling a previous request ("nevermind", "its okay", "forget it", "don't worry about it")
- no_action_needed: the reply is a question, casual acknowledgement, or not an actionable update

When calling request_reschedule or request_reassignment, extract the reason directly from the person's reply. Use their own words as closely as possible — do not invent or infer a reason that isn't stated. If they give no reason, set reason to an empty string.

For dates, always use {today}'s year unless the person specifies otherwise. If only a date is mentioned with no time, default to 18:00:00+08:00.
"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "mark_done",
            "description": "Mark the task as completed.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_reschedule",
            "description": "Request a new due date for the task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "requested_due_date": {
                        "type": "string",
                        "description": "New due date in ISO 8601 format with timezone, e.g. 2026-06-30T18:00:00+08:00",
                    },
                    "reason": {"type": "string", "description": "Reason for needing more time."},
                },
                "required": ["requested_due_date", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_reassignment",
            "description": "Request the task be reassigned to someone else.",
            "parameters": {
                "type": "object",
                "properties": {
                    "suggested_owner_name": {
                        "type": "string",
                        "description": "Name of the person suggested as the new owner.",
                    },
                    "reason": {"type": "string", "description": "Reason for requesting reassignment."},
                },
                "required": ["suggested_owner_name", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_for_date",
            "description": "The person wants more time but did not mention a specific date. Ask them to provide one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "A short, friendly message asking the person for a specific date.",
                    }
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_request",
            "description": "The person is withdrawing or cancelling a previous request they made (e.g. 'nevermind', 'its okay', 'forget it').",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "no_action_needed",
            "description": "The reply is not an actionable status update.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def interpret_reply(task_description: str, reply_text: str, today: str = None) -> dict:
    """
    Returns {"action": "<tool_name>", "args": {...}}.
    Always calls exactly one tool thanks to tool_choice="required".
    """
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    response = _client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(today=today)},
            {"role": "user", "content": f"Task: {task_description}\n\nReply: {reply_text}"},
        ],
        tools=_TOOLS,
        tool_choice="required",
        temperature=0,
        name="interpret-reply",
    )

    tool_call = response.choices[0].message.tool_calls[0]
    return {
        "action": tool_call.function.name,
        "args": json.loads(tool_call.function.arguments),
    }
