# Runbook

## Start Service
- Activate env and run `python src/app.py`.

## Verify Telegram Connectivity
1. Send any message to your bot.
2. If your user ID is not in `TELEGRAM_ALLOWED_USER_IDS`, no reply should be sent.
3. If authorized, bot should respond.

## Verify Todoist Create
1. Send: `add Test from bot /due tomorrow`.
2. Confirm bot reply includes task name and due string.
3. Confirm task appears in Todoist.

## Troubleshooting
- `Missing required environment variable`: check `.env` keys.
- Telegram 401: invalid `TELEGRAM_BOT_TOKEN`.
- Todoist 401: invalid `TODOIST_API_TOKEN`.
- No bot replies: check allowlist user IDs and logs.
