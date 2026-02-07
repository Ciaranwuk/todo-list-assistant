from __future__ import annotations

import logging
import time

from config import load_settings
from logging_config import configure_logging
from orchestration.handler import handle_text
from parser.llm_parser import OpenAILLMParser
from telegram.client import TelegramClient
from todoist.client import TodoistAPIError, TodoistClient


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    logger = logging.getLogger("assistant")
    telegram = TelegramClient(settings.telegram_bot_token)
    todoist = TodoistClient(settings.todoist_api_token)
    llm_parser = None
    if settings.openai_api_key and settings.openai_model:
        llm_parser = OpenAILLMParser(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
        logger.info("LLM parser enabled")
    else:
        logger.info("LLM parser disabled (missing OPENAI_API_KEY or OPENAI_MODEL)")

    offset: int | None = None
    logger.info("Assistant started with Telegram polling")

    while True:
        try:
            updates = telegram.get_updates(offset=offset)
            for message in updates:
                offset = message.update_id + 1

                if message.user_id not in settings.telegram_allowed_user_ids:
                    logger.warning(
                        "Ignoring unauthorized user", extra={"user_id": message.user_id, "chat_id": message.chat_id}
                    )
                    continue

                try:
                    reply = handle_text(
                        message.text,
                        todoist,
                        chat_id=message.chat_id,
                        llm_parser=llm_parser,
                    )
                except TodoistAPIError as exc:
                    logger.exception("Todoist request failed")
                    reply = (
                        "Todoist rejected that request. "
                        f"Details: {exc.message}"
                    )
                except Exception:
                    logger.exception("Message handling failed")
                    reply = "Something went wrong while handling that message. Please try again."
                telegram.send_message(chat_id=message.chat_id, text=reply)

        except Exception:
            logger.exception("Polling loop error")
            time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
