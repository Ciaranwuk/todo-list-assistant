from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InboundMessage:
    update_id: int
    message_id: int
    chat_id: int
    user_id: int
    text: str
