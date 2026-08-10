# Delegate - AI-Powered Task Delegation for Slack

## What is Delegate?

Meetings are where decisions get made but without a structured handoff, the tasks that come out of them fall through the cracks. Follow-ups get forgotten, deadlines slip, and the organizer is left chasing people down manually.

Delegate fixes this entirely within Slack. An organizer uploads a meeting transcript (PDF or DOCX) directly into the Delegate bot DM. The app uses AI to extract action items, identify who owns each task, and send individualised task DMs to the right people. Task owners reply in-thread to mark things done, request deadline extensions, or request reassignment, all of which route back to the organizer for approval. Organizers can also ask the bot questions regarding the past meetings they attended and get answers synthesised directly from their past meeting transcripts.

## What's Next?

- **Jira Integration** - push delegated tasks directly to Jira as tickets, instead of storing in external database.
- **Deadline Reminders** - proactive DMs to task owners as deadlines approach, and escalation alerts to organizers when tasks are overdue.

---

## Table of Contents

1. [Product Walkthrough](#product-walkthrough)
2. [Responsible AI](#responsible-ai)
3. [Tech Stack Used](#tech-stack-used)
4. [Why These Technologies?](#why-these-technologies)
5. [System Architecture Diagram](#system-architecture-diagram)
6. [Evaluations](#evaluations)
7. [Challenges Faced](#challenges-faced)
8. [View PRD](#view-prd)

---

## Why These Technologies?

**Slack Bolt (Python)** - Delegate lives inside Slack, so building natively on Bolt gave us the full event handling, block kit, and OAuth surface without abstraction layers. Socket Mode allowed rapid local development without exposing a public endpoint during iteration.

**OpenAI GPT-4o-mini** - Task extraction, reply interpretation, and semantic search answers all require language understanding. GPT-4o-mini hits the right balance of capability and cost for high-frequency operations like per-transcript extraction and per-query answering.

**OpenAI text-embedding-3-small** - Fast, cheap, and accurate enough for semantic similarity over meeting transcript chunks. Used to embed both transcript chunks at upload time and user queries at search time.

**AWS DynamoDB** - Serverless, pay-per-request, and schema-flexible. Since each workspace has its own isolated data and load patterns vary significantly, DynamoDB's on-demand billing avoids over-provisioning. The multi-tenant model scoped entirely by `workspace_id` maps cleanly onto DynamoDB's partition key design.

**AWS KMS** - Bot tokens are sensitive credentials. KMS ensures they are never stored in plaintext, with encryption and decryption happening server-side without the key ever touching application memory.

**FastAPI** - Handles the OAuth install flow (the `/slack/install` and `/slack/oauth/callback` endpoints). Thin, fast, and easy to deploy alongside the Bolt app.

**Langfuse** - LLM observability. Every extraction, embedding, search, and reranking call is traced with token counts and latency, which feeds directly into the internal cost monitor.

---

## Product Walkthrough

### Task Delegation Flow

**1. Upload and Read Transcript**

The organizer uploads a meeting transcript (PDF or DOCX) directly into the Delegate bot DM. The bot reads the file and begins extracting action items.

![Upload and Read Transcript](gallery/upload_and_read_transcript.png)

**2. View Extracted Tasks**

The bot presents all extracted tasks in a review card before anything is sent. Each task shows the owner, description, and due date. If a name from the transcript could not be matched to a Slack user, an unmatched warning is shown and the organizer can manually assign someone from within the organisation. If a match is found, the Slack user is tagged automatically and no manual action is needed.

![View Extracted Tasks](gallery/view_extracted_tasks.png)

**3. Edit Task**

The organizer can edit any task before sending, including the description, owner, and due date, via a modal.

![Edit Task](gallery/edit_task.png)

**4. Delegate Tasks**

Once the organizer is satisfied, they confirm and the bot sends individualised task DMs to each owner.

![Delegate Tasks](gallery/delegate_tasks.png)

**5. Tasks Assigned to Oneself**

What a task DM looks like from the perspective of someone who has been assigned a task.

![Tasks Assigned to Oneself](gallery/tasks_assigned_to_oneself.png)

**6. Tasks Assigned to Another Person (POV)**

What the task DM looks like from the perspective of another assignee in the same delegation batch.

![Tasks Assigned to Another Person](gallery/tasks_assigned_to_another_personpov.png)

**7. Request for Extension**

A task owner can reply in-thread to request a deadline extension. The bot routes the request to the organizer for approval.

![Request for Extension](gallery/request_for_extension.png)

**8. Approve or Deny Request**

The organizer receives an approval card with the request details and can approve or deny with an optional reason.

![Approve or Deny Request](gallery/approve_or_deny_request.png)

**9. Get Updated on Request**

The task owner is notified in their original task thread once the organizer approves or denies the request.

![Get Updated on Request](gallery/get_updated_on_request.png)

**10. Mark Task as Done**

The task owner replies in-thread to mark their task as complete. The organizer is notified and the task status is updated.

![Mark Task as Done](gallery/mark_task_as_done.png)

---

### Delegate Commands

**Commands Overview**

A summary of all available slash commands.

![Delegate Commands](gallery/delegate%20commands.png)

**1. Delegate Status**

Shows the most recent delegation batch with the current status of each task.

![Delegate Status](gallery/delegate%20status.png)

**2. Delegate Digest**

Shows all past delegations grouped by meeting, with done and pending tasks.

![Delegate Digest](gallery/delegate%20digest.png)

**3. Delegate Digest (Overdue)**

The digest also surfaces overdue tasks so the organizer can follow up immediately.

![Delegate Digest Overdue](gallery/delegate%20digest%202.png)

**4. Delegate Cancel**

The organizer can cancel any active task. The task owner is notified in their task DM thread.

![Delegate Cancel](gallery/delegate%20cancel.png)

---

### Search Feature

**RAG Search with Transparency**

Organizers can ask the bot questions about past meetings in plain English. The bot retrieves the most relevant transcript chunks, passes them through an LLM reranker to filter noise, and synthesises a grounded answer. Sources are shown so the user knows exactly which transcript the answer came from.

![RAG Search with Transparency](gallery/rag_search_with_transparency.png)

**How this was built**

The query is embedded using the same embedding model used at upload time. The embedding is scored via cosine similarity against all stored transcript chunks and the top 10 chunks are retrieved. An LLM reranker then labels each chunk as relevant or not in a single call. Only the relevant chunks are passed to the answer LLM, which synthesises a response grounded strictly in that context.

---

## Responsible AI

When the search feature returns an answer, Delegate shows the user which transcript the answer was sourced from. This is an intentional design decision rooted in transparency and trust. AI-generated answers can be wrong, and users should always be able to verify the source themselves. By surfacing the originating transcript as a clickable link, we give users the means to check the answer against the actual meeting record rather than having to take it on faith.

![RAG Search with Transparency](gallery/rag_search_with_transparency.png)
