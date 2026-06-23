import os
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

EXTRACTION_PROMPT = """You are extracting action items from a meeting transcript.

Rules for due_date:
- If a specific date and time are both mentioned, use them exactly.
- If only a date is mentioned with no time (e.g. "by Friday", "before the 25th"),
  default the time to 18:00 in the +08:00 (Singapore) timezone.
- If a relative date is mentioned (e.g. "next week", "in two days"), calculate the
  actual date based on the meeting date provided below, still defaulting to 18:00
  if no time is given.
- If no due date is mentioned at all for a task, due_date must be null.

Only extract genuine action items, things a specific person committed to do or was
assigned to do. Do not extract general discussion points, decisions with no owner,
or vague statements. If a task has no clear owner, skip it entirely, don't guess.

Meeting date for relative date calculations: {meeting_date}

Transcript:
{transcript_text}
"""

TASK_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "owner_name": {"type": "string"},
                    "task_description": {"type": "string"},
                    "due_date": {"type": ["string", "null"]},
                },
                "required": ["owner_name", "task_description", "due_date"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tasks"],
    "additionalProperties": False,
}


def extract_tasks(transcript_text: str, meeting_date: str = None) -> list[dict]:
    """
    Sends transcript text to OpenAI using Structured Outputs, which
    enforces the response shape at the API level via JSON schema.
    """
    if meeting_date is None:
        meeting_date = datetime.now().strftime("%Y-%m-%d")

    prompt = EXTRACTION_PROMPT.format(
        meeting_date=meeting_date,
        transcript_text=transcript_text,
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "task_extraction",
                "schema": TASK_LIST_SCHEMA,
                "strict": True,
            },
        },
    )

    raw_content = response.choices[0].message.content
    parsed = json.loads(raw_content)  # guaranteed valid JSON matching the schema

    return parsed["tasks"]