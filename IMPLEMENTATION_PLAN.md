# Personal Assistant (Telegram + Todoist) Implementation Plan

## Context
- Goal: Build a text-first personal assistant that updates Todoist from phone messages.
- Chosen channel for v1: Telegram bot (because follow-up questions are native and UX is straightforward).
- Required capabilities: create, edit, complete, and reschedule tasks.
- Natural language: support only patterns Todoist already handles (e.g., `tomorrow`, `next Monday`, `at 5pm`).
- Clarification behavior: ask follow-up questions when intent/fields are ambiguous.
- Secrets: Todoist token can be stored on host; OpenAI API key should be used with cost controls.

## High-Level Architecture
1. Telegram user sends message to bot.
2. Inbound adapter receives message and normalizes it.
3. Intent parser (LLM) converts message into strict JSON command.
4. Guardrails validate command (action allowlist, required fields, confidence threshold).
5. If unclear, assistant sends follow-up question and records pending conversation state.
6. Action runner executes Todoist API operation.
7. Assistant replies with explicit confirmation of what changed.

## Why Telegram Polling First
- Polling avoids public webhook exposure in early dev.
- Simpler local run loop and easier debugging.
- Can migrate to Telegram webhooks later with no domain logic changes.

## Proposed Repository Layout
```
.
├── IMPLEMENTATION_PLAN.md
├── README.md
├── .env.example
├── requirements.txt
├── src/
│   ├── app.py                  # process entrypoint / polling loop
│   ├── config.py               # env parsing and validation
│   ├── logging_config.py
│   ├── telegram/
│   │   ├── client.py           # Telegram API wrapper (getUpdates/sendMessage)
│   │   └── models.py           # normalized inbound message objects
│   ├── parser/
│   │   ├── llm_parser.py       # OpenAI call + schema-constrained parse
│   │   ├── schema.py           # command schema definitions
│   │   └── prompts.py          # system/user prompts for parser
│   ├── todoist/
│   │   ├── client.py           # Todoist REST wrapper
│   │   └── mapper.py           # map commands -> Todoist API requests
│   ├── orchestration/
│   │   ├── handler.py          # main message handler flow
│   │   ├── validation.py       # command validation + guardrails
│   │   └── followup.py         # clarification state machine
│   ├── storage/
│   │   ├── sqlite.py           # lightweight persistence
│   │   └── models.py           # pending followups, dedupe records
│   └── tests/
│       ├── test_parser.py
│       ├── test_validation.py
│       ├── test_followup_flow.py
│       └── test_todoist_mapper.py
└── docs/
    ├── API_SCHEMA.md
    └── RUNBOOK.md
```

## Command Schema (LLM Output Contract)
Use strict JSON object with these top-level fields:

```json
{
  "action": "create_task | update_task | complete_task | reschedule_task | clarify",
  "confidence": 0.0,
  "reason": "short rationale",
  "task_selector": {
    "by": "id | exact_text | fuzzy_text | none",
    "value": "string"
  },
  "task_payload": {
    "content": "string or null",
    "description": "string or null",
    "due_string": "string or null",
    "priority": 1,
    "labels": ["string"]
  },
  "clarify": {
    "question": "string or null",
    "missing_fields": ["string"]
  }
}
```

Rules:
- `create_task` requires `task_payload.content`.
- `update_task` requires `task_selector` and at least one mutable field in `task_payload`.
- `complete_task` requires `task_selector`.
- `reschedule_task` requires `task_selector` and `task_payload.due_string`.
- `clarify` requires non-empty `clarify.question`.

## Conversation and Follow-Up State
Store minimal state in SQLite:
- `conversations` table: `chat_id`, `last_seen_update_id`, timestamps.
- `pending_clarifications` table:
  - `chat_id`
  - `original_user_text`
  - `draft_command_json`
  - `question`
  - `missing_fields`
  - `expires_at`
- `dedupe` table:
  - `source` (telegram)
  - `message_id`
  - `handled_at`

Flow:
1. If no pending clarification: parse new text normally.
2. If pending clarification exists: combine prior draft + user answer, re-parse as continuation.
3. If still ambiguous: ask one tighter question.
4. If resolved: execute, clear pending record, send confirmation.

## Guardrails and Safety
- Action allowlist: only the 5 actions in schema.
- Telegram user allowlist: process only configured user IDs.
- No shell execution from user text.
- Confidence gate:
  - `>= 0.75`: execute
  - `0.45 - 0.74`: ask confirm-style follow-up
  - `< 0.45`: ask clarifying question
- Validate schema before action runner.
- Log all command decisions with redacted sensitive fields.

## Task Selection Strategy (Edit/Complete/Reschedule)
Priority order:
1. If user provides explicit Todoist task ID, use it.
2. Else list candidate open tasks (bounded query, e.g., top 10 recent).
3. Exact text match first.
4. Fuzzy text fallback with threshold.
5. If multiple plausible matches, ask user disambiguation question.

## Todoist API Operations Mapping
- `create_task` -> `POST /tasks`
- `update_task` -> `POST /tasks/{id}`
- `complete_task` -> `POST /tasks/{id}/close`
- `reschedule_task` -> `POST /tasks/{id}` with `due_string`

Note: Keep due parsing delegated to Todoist (`due_string`) instead of implementing custom date parser in v1.

## Confirmation Message Templates
- Create: `Created task: "{content}" (due: {due_or_none}).`
- Update: `Updated task "{old_content}" -> "{new_content}".`
- Complete: `Completed task: "{content}".`
- Reschedule: `Rescheduled "{content}" to {due_string}.`
- Clarify: one concise question only.

## Cost Control Plan (OpenAI)
- Use low-cost model tier for intent extraction.
- Keep prompts short and schema-focused.
- Set conservative `max_tokens`.
- Log token usage per request.
- Set billing budget/alerts in OpenAI dashboard before production rollout.

## Environment Variables (.env)
Required:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS` (comma-separated)
- `TODOIST_API_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `APP_TIMEZONE` (e.g., `America/New_York`)

Optional:
- `LOG_LEVEL=INFO`
- `SQLITE_PATH=./assistant.db`
- `CONFIDENCE_EXECUTE_THRESHOLD=0.75`
- `CONFIDENCE_CLARIFY_THRESHOLD=0.45`

## Milestones

### Milestone 1: Skeleton + Telegram Polling
Deliverables:
- project structure, config loader, logging
- Telegram `getUpdates` polling loop
- allowlist check
- echo reply smoke test
Acceptance:
- authorized user can send message and receive response
- unauthorized user is ignored and logged

### Milestone 2: Todoist Client + Create Task
Deliverables:
- Todoist client wrapper
- create task action from deterministic command (no LLM yet)
Acceptance:
- manual command fixture creates task successfully
- confirmation message sent with task content and due value

### Milestone 3: LLM Parser + Schema Validation
Deliverables:
- parser prompt + strict schema validation
- action mapping for create/update/complete/reschedule/clarify
Acceptance:
- parser tests pass on representative prompts
- malformed output rejected safely

### Milestone 4: Clarification State Machine
Deliverables:
- SQLite persistence for pending clarifications and dedupe
- follow-up question loop with expiry
Acceptance:
- ambiguous input triggers question
- user reply resolves and executes action
- expired clarification starts new intent cleanly

### Milestone 5: Production Hardening
Deliverables:
- retries/timeouts around external APIs
- structured logs and runbook
- budget alert setup and token usage log
Acceptance:
- service handles transient failures without duplicate task creation
- restart-safe dedupe behavior works

## Testing Strategy
- Unit tests:
  - schema validation edge cases
  - task selection ambiguity behavior
  - follow-up flow transitions
- Integration tests (mock APIs):
  - telegram inbound -> parse -> todoist call -> telegram confirmation
- Manual E2E:
  - create, edit, complete, reschedule, ambiguous request, unauthorized user

## Handoff Checklist for Future Agent
1. Read this file first.
2. Confirm current milestone and open TODOs in `README.md`.
3. Verify `.env` values and secrets are present.
4. Run tests before and after edits.
5. Update this file and `docs/RUNBOOK.md` if behavior or thresholds change.

## Open Decisions (Need User Input)
- Preferred model name for parser (cost/performance tradeoff).
- Whether to support multi-step commands in one message in v1 (recommended: no).
- Whether to include project/section routing in v1 (recommended: defer to v2).

## Recommended Next Task
Implement Milestone 1 and Milestone 2 in one pass so there is a working message-to-Todoist baseline before introducing LLM parsing complexity.
