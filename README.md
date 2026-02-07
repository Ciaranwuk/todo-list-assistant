# Personal Assistant (Milestone 1-2)

Telegram polling service that creates Todoist tasks from text commands.

## Current Scope
- Telegram bot polling (`getUpdates`)
- User allowlist check
- Deterministic task creation command
- Deterministic task edit command (open tasks only)
- Deterministic task complete command (open tasks only)
- Deterministic task reschedule command (open tasks only)
- Optional LLM translation fallback for natural-language create/edit/complete/reschedule requests
- Todoist task creation + confirmation message

## Command Format
- `add <task content>`
- `add <task content> /due <todoist due string>`
- `add <task content> /project <project path>`
- `add <task content> #<project path>`
- `edit <task selector> /set <new task content>`
- `edit <task selector> /due <todoist due string>`
- `edit <task selector> /due <todoist due string> /project <project-or-section path>`
- `complete <task selector> [/project <project-or-section path>]`
- `reschedule <task selector> /due <todoist due string> [/project <project-or-section path>]`
- Also accepts `create ...` and `todo ...` prefixes.

Examples:
- `add Buy groceries`
- `add Pay electricity bill /due tomorrow at 6pm`
- `add Check bills /project To-Do/Joint to-do`
- `add Book dentist #To-Do/Joint to-do`
- `add Plan holiday /project joint` (fuzzy match if unambiguous)
- `edit submit report /set submit annual report`
- `edit submit report /due next monday`
- `edit create personal assistant bot /due tomorrow /project to-do/joint to-do`
- `complete create personal assistant bot /project to-do/joint to-do`
- `reschedule create personal assistant bot /due friday /project to-do/joint to-do`
- `projects` (lists known project paths)
- `sections` (lists known section paths, e.g. `To-Do/Joint to-do`)
- `tasks` (lists open tasks for easy selector discovery)

## Setup
1. Create a virtualenv and install dependencies:
   - `pip install -r requirements.txt`
2. Copy env template:
   - `cp .env.example .env`
3. Fill required `.env` values:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_ALLOWED_USER_IDS`
   - `TODOIST_API_TOKEN`
4. Optional for natural-language LLM parsing:
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL` (low-cost model recommended)

## Run
- `python src/app.py`

## Test
- `pytest -q src/tests`

## Notes
- This stage intentionally uses deterministic parsing for create/edit flows.
- If `OPENAI_API_KEY` and `OPENAI_MODEL` are set, the bot attempts LLM parsing only when deterministic parsing does not match.
- LLM fallback currently supports create/edit/complete/reschedule intent extraction.
- LLM fallback is now grounded with current project/section paths and a small open-task snapshot to improve natural-language mapping.
- LLM parsing and follow-up state machine are planned in Milestone 3-4.
