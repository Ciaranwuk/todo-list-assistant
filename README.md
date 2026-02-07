# Personal Assistant (Milestone 1-2)

Telegram polling service that creates Todoist tasks from text commands.

## Current Scope
- Telegram bot polling (`getUpdates`)
- User allowlist check
- Deterministic task creation command
- Todoist task creation + confirmation message

## Command Format
- `add <task content>`
- `add <task content> /due <todoist due string>`
- `add <task content> /project <project path>`
- `add <task content> #<project path>`
- Also accepts `create ...` and `todo ...` prefixes.

Examples:
- `add Buy groceries`
- `add Pay electricity bill /due tomorrow at 6pm`
- `add Check bills /project To-Do/Joint to-do`
- `add Book dentist #To-Do/Joint to-do`
- `add Plan holiday /project joint` (fuzzy match if unambiguous)
- `projects` (lists known project paths)
- `sections` (lists known section paths, e.g. `To-Do/Joint to-do`)

## Setup
1. Create a virtualenv and install dependencies:
   - `pip install -r requirements.txt`
2. Copy env template:
   - `cp .env.example .env`
3. Fill required `.env` values:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_ALLOWED_USER_IDS`
   - `TODOIST_API_TOKEN`

## Run
- `python src/app.py`

## Test
- `pytest -q src/tests`

## Notes
- This stage intentionally uses deterministic parsing for create-task only.
- LLM parsing and follow-up state machine are planned in Milestone 3-4.
