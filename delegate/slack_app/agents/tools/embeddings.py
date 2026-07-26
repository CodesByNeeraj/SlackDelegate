import json
import os
from dotenv import load_dotenv

load_dotenv()

from langfuse.openai import OpenAI

_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
_MODEL = "text-embedding-3-small"


def generate_embedding(text: str) -> list[float]:
    text = text.replace("\n", " ").strip()
    response = _client.embeddings.create(input=text, model=_MODEL, name="generate-embedding")
    return response.data[0].embedding


_SEPARATORS = ["\n\n", "\n", ". ", " "]


def _split_recursive(text: str, max_words: int, depth: int = 0) -> list[str]:
    if len(text.split()) <= max_words:
        return [text.strip()]

    if depth >= len(_SEPARATORS):
        words = text.split()
        return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]

    sep = _SEPARATORS[depth]
    parts = [p.strip() for p in text.split(sep) if p.strip()]

    chunks = []
    current: list[str] = []
    current_words = 0

    for part in parts:
        part_words = len(part.split())
        if part_words > max_words:
            if current:
                chunks.append("\n\n".join(current))
                current, current_words = [], 0
            chunks.extend(_split_recursive(part, max_words, depth + 1))
        elif current_words + part_words > max_words and current:
            chunks.append("\n\n".join(current))
            current, current_words = [part], part_words
        else:
            current.append(part)
            current_words += part_words

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_text(text: str, max_words: int = 400, overlap_words: int = 50) -> list[str]:
    raw = _split_recursive(text, max_words)
    if len(raw) <= 1:
        return raw

    result = [raw[0]]
    for i in range(1, len(raw)):
        prev_words = raw[i - 1].split()
        overlap = " ".join(prev_words[-overlap_words:])
        result.append(overlap + "\n\n" + raw[i])

    return result


def embed_transcript_chunks(text: str) -> tuple[list[dict], int]:
    """
    Splits the transcript into ~400-word chunks and embeds each one.
    Returns (chunks, total_tokens) where chunks is list of {chunk_index, text, embedding_json}.
    """
    raw_chunks = chunk_text(text)
    chunks = []
    total_tokens = 0
    for i, chunk in enumerate(raw_chunks):
        chunk_clean = chunk.replace("\n", " ").strip()
        response = _client.embeddings.create(input=chunk_clean, model=_MODEL, name="embed-transcript-chunk")
        total_tokens += response.usage.total_tokens
        chunks.append({
            "chunk_index": i,
            "text": chunk,
            "embedding_json": json.dumps(response.data[0].embedding),
        })
    return chunks, total_tokens
