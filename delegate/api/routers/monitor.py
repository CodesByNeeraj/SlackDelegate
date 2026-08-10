from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from shared.models import transcript as transcript_model, search_log
from shared.db.dynamo_client import get_table

router = APIRouter(prefix="/monitor", tags=["monitor"])

#text-embedding-3-small
EMBEDDING_COST_PER_1M = 0.020      
#gpt-5.4 mini
EXTRACTION_INPUT_COST_PER_1M = 0.75
EXTRACTION_OUTPUT_COST_PER_1M = 4.50


def _extraction_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1_000_000 * EXTRACTION_INPUT_COST_PER_1M) + \
           (completion_tokens / 1_000_000 * EXTRACTION_OUTPUT_COST_PER_1M)


def _embedding_cost(tokens: int) -> float:
    return tokens / 1_000_000 * EMBEDDING_COST_PER_1M


def _get_all_transcripts() -> list[dict]:
    table = get_table("Transcripts")
    response = table.scan(ProjectionExpression=(
        "workspace_id, transcript_id, filename, task_count, "
        "embedding_tokens, extraction_prompt_tokens, extraction_completion_tokens, "
        "extraction_latency_ms, created_at, uploaded_by"
    ))
    items = response.get("Items", [])
    return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)


@router.get("/", response_class=HTMLResponse)
def dashboard():
    transcripts = _get_all_transcripts()
    logs = search_log.get_all_logs()

    transcript_rows = ""
    for t in transcripts:
        pt = int(t.get("extraction_prompt_tokens", 0))
        ct = int(t.get("extraction_completion_tokens", 0))
        et = int(t.get("embedding_tokens", 0))
        ext_cost = _extraction_cost(pt, ct)
        emb_cost = _embedding_cost(et)
        latency = int(t.get("extraction_latency_ms", 0))
        task_count = int(t.get("task_count", 0))
        created = t.get("created_at", "")[:19].replace("T", " ")

        transcript_rows += f"""
        <tr>
            <td>{t.get("filename", "unknown")}</td>
            <td>{task_count}</td>
            <td>{latency:,} ms</td>
            <td>{pt:,}</td>
            <td>{ct:,}</td>
            <td>${ext_cost:.5f}</td>
            <td>{et:,}</td>
            <td>${emb_cost:.5f}</td>
            <td>${ext_cost + emb_cost:.5f}</td>
            <td>{created}</td>
            <td style="font-size:11px;color:#666">{t.get("workspace_id", "")}</td>
        </tr>"""

    search_rows = ""
    for log in logs:
        snippets = log.get("snippets", [])
        snippet_html = ""
        for i, s in enumerate(snippets, 1):
            preview = s.replace("<", "&lt;").replace(">", "&gt;")
            snippet_html += f'<details style="margin-bottom:6px"><summary style="cursor:pointer;font-size:12px;font-weight:600">Snippet {i}</summary><pre style="white-space:pre-wrap;font-size:11px;background:#f5f5f5;padding:6px;border-radius:4px;margin-top:4px">{preview}</pre></details>'

        answer_preview = log.get("answer", "").replace("<", "&lt;").replace(">", "&gt;")
        ts = log.get("timestamp", "")[:19].replace("T", " ")

        search_rows += f"""
        <tr>
            <td>{ts}</td>
            <td><b>{log.get("query","").replace("<","&lt;")}</b></td>
            <td>{snippet_html}</td>
            <td><pre style="white-space:pre-wrap;font-size:11px">{answer_preview}</pre></td>
            <td style="font-size:11px;color:#666">{log.get("workspace_id","")}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<title>Delegate Monitor</title>
<style>
  body {{ font-family: -apple-system, sans-serif; padding: 24px; background: #fafafa; color: #111; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; margin-top: 40px; margin-bottom: 12px; color: #333; }}
  table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  th {{ background: #1a1a1a; color: white; padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 13px; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f9f9f9; }}
</style>
</head>
<body>
<h1>Delegate Internal Monitor</h1>

<h2>Transcripts ({len(transcripts)})</h2>
<table>
  <thead>
    <tr>
      <th>Filename</th>
      <th>Tasks</th>
      <th>Extraction Latency</th>
      <th>Input Tokens</th>
      <th>Output Tokens</th>
      <th>Extraction Cost</th>
      <th>Embedding Tokens</th>
      <th>Embedding Cost</th>
      <th>Total Cost</th>
      <th>Uploaded At</th>
      <th>Workspace</th>
    </tr>
  </thead>
  <tbody>
    {transcript_rows or '<tr><td colspan="11" style="text-align:center;color:#999">No transcripts yet</td></tr>'}
  </tbody>
</table>

<h2>Search Logs — Faithfulness Review ({len(logs)})</h2>
<table>
  <thead>
    <tr>
      <th>Time</th>
      <th>Query</th>
      <th>Source Snippets</th>
      <th>Answer</th>
      <th>Workspace</th>
    </tr>
  </thead>
  <tbody>
    {search_rows or '<tr><td colspan="5" style="text-align:center;color:#999">No searches yet</td></tr>'}
  </tbody>
</table>

</body>
</html>"""

    return HTMLResponse(content=html)
