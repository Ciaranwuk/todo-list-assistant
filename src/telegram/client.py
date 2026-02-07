from __future__ import annotations

from typing import Any

import requests

from .models import InboundMessage


class TelegramClient:
    def __init__(self, bot_token: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._timeout_seconds = timeout_seconds

    def get_updates(self, offset: int | None = None, timeout: int = 20) -> list[InboundMessage]:
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset

        response = requests.get(
            f"{self._base_url}/getUpdates",
            params=payload,
            timeout=self._timeout_seconds + timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            return []

        parsed: list[InboundMessage] = []
        for item in data.get("result", []):
            message = item.get("message")
            if not message:
                continue
            text = message.get("text")
            from_user = message.get("from")
            chat = message.get("chat")
            if not text or not from_user or not chat:
                continue

            parsed.append(
                InboundMessage(
                    update_id=item["update_id"],
                    message_id=message["message_id"],
                    chat_id=chat["id"],
                    user_id=from_user["id"],
                    text=text.strip(),
                )
            )
        return parsed

    def send_message(self, chat_id: int, text: str) -> None:
        response = requests.post(
            f"{self._base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
