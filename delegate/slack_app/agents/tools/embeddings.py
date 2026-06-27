import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
_MODEL = "text-embedding-3-small"


def generate_embedding(text: str) -> list[float]:
    text = text.replace("\n", " ").strip()
    response = _client.embeddings.create(input=text, model=_MODEL)
    return response.data[0].embedding


def chunk_text(text: str, max_words: int = 400) -> list[str]:
    """
    Splits text into chunks of ~max_words, respecting paragraph boundaries.
    Keeps chunks under text-embedding-3-small's 8191 token limit.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_words + para_words > max_words and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_words = para_words
        else:
            current.append(para)
            current_words += para_words

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def embed_transcript_chunks(text: str) -> list[dict]:
    """
    Splits the transcript into ~400-word chunks and embeds each one.
    Returns list of {chunk_index, text, embedding_json}.
    """
    chunks = chunk_text(text)
    return [
        {
            "chunk_index": i,
            "text": chunk,
            "embedding_json": json.dumps(generate_embedding(chunk)),
        }
        for i, chunk in enumerate(chunks)
    ]
