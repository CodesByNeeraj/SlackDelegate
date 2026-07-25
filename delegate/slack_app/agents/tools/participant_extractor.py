import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_SYSTEM_PROMPT = """Extract all speaker and participant names from this meeting transcript.
Return a JSON object with a single key "names" containing an array of name strings.
Include only actual person names as they appear in the transcript. Do not include roles, titles, or generic labels.
If no names are found, return {"names": []}.

Example output: {"names": ["Alice", "Bob Chen", "Neeraj"]}
"""


def extract_participants(transcript_text: str) -> list[str]:
    try:
        response = _client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": transcript_text[:6000]},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        names = json.loads(response.choices[0].message.content).get("names", [])
    except Exception:
        return []

    # Deduplicate: drop any name that is a substring of a longer name (case-insensitive)
    names = sorted(set(n.strip() for n in names if n.strip()), key=len, reverse=True)
    deduped = []
    for name in names:
        if not any(name.lower() in kept.lower() for kept in deduped):
            deduped.append(name)
    return deduped
