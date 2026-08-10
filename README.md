# Delegate - AI-Powered Task Delegation for Slack

## What is Delegate?

Meetings are where decisions get made but without a structured handoff, the tasks that come out of them fall through the cracks. Follow-ups get forgotten, deadlines slip, and the organizer is left chasing people down manually.

Delegate fixes this entirely within Slack. An organizer uploads a meeting transcript (PDF or DOCX) directly into the Delegate bot DM. The app uses AI to extract action items, identify who owns each task, and send individualised task DMs to the right people. Task owners reply in-thread to mark things done, request deadline extensions, or request reassignment, all of which route back to the organizer for approval. Organizers can also ask the bot questions regarding the past meetings they attended and get answers synthesised directly from their past meeting transcripts.

## Why These Technologies?

**Slack Bolt (Python)** - Delegate lives inside Slack, so building natively on Bolt gave us the full event handling, block kit, and OAuth surface without abstraction layers. Socket Mode allowed rapid local development without exposing a public endpoint during iteration.

**OpenAI GPT-4o-mini** - Task extraction, reply interpretation, and semantic search answers all require language understanding. GPT-4o-mini hits the right balance of capability and cost for high-frequency operations like per-transcript extraction and per-query answering.

**OpenAI text-embedding-3-small** - Fast, cheap, and accurate enough for semantic similarity over meeting transcript chunks. Used to embed both transcript chunks at upload time and user queries at search time.

**AWS DynamoDB** - Serverless, pay-per-request, and schema-flexible. Since each workspace has its own isolated data and load patterns vary significantly, DynamoDB's on-demand billing avoids over-provisioning. The multi-tenant model - scoped entirely by `workspace_id` - maps cleanly onto DynamoDB's partition key design.

**AWS KMS** - Bot tokens are sensitive credentials. KMS ensures they are never stored in plaintext, with encryption and decryption happening server-side without the key ever touching application memory.

**FastAPI** - Handles the OAuth install flow (the `/slack/install` and `/slack/oauth/callback` endpoints). Thin, fast, and easy to deploy alongside the Bolt app.

**Langfuse** - LLM observability. Every extraction, embedding, search, and reranking call is traced with token counts and latency, which feeds directly into the internal cost monitor.

## What's Next?

- **Jira Integration** - push delegated tasks directly to Jira as tickets, keeping Slack and project management in sync without manual re-entry.
- **Deadline Reminders** - proactive DMs to task owners as deadlines approach, and escalation alerts to organizers when tasks are overdue.

---

## Table of Contents

1. [Product Walkthrough](#product-walkthrough)
2. [Tech Stack Used](#tech-stack-used)
3. [Why These Technologies?](#why-these-technologies)
4. [System Architecture Diagram](#system-architecture-diagram)
5. [Evaluations](#evaluations)
6. [Challenges Faced](#challenges-faced)
7. [View PRD](#view-prd)
