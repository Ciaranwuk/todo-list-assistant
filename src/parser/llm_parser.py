from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import requests


@dataclass(frozen=True)
class LLMIntent:
    action: str
    content: str | None = None
    selector: str | None = None
    new_content: str | None = None
    due_string: str | None = None
    project_ref: str | None = None
    confidence: float = 0.0
    clarify_question: str | None = None


class LLMParserError(RuntimeError):
    pass


class OpenAILLMParser:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 20.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._url = "https://api.openai.com/v1/chat/completions"

    def parse(self, text: str, context: dict[str, Any] | None = None) -> LLMIntent:
        system_prompt = (
            "You map user text into Todoist assistant actions. "
            "Return JSON only. Allowed actions: create_task, edit_task, complete_task, reschedule_task, unknown. "
            "Use edit_task only when user wants to change an existing task. "
            "Use complete_task when user wants to mark a task done. "
            "Use reschedule_task when user wants to move a task due date. "
            "Use create_task for adding a new task. "
            "Do not invent fields. Keep confidence between 0 and 1. "
            "If context contains projects/sections/tasks, use those names for selector/project_ref choices."
        )
        context_json = json.dumps(context or {}, ensure_ascii=True)
        user_prompt = (
            "Extract command fields from this message:\n"
            f"{text}\n\n"
            "Available assistant context (projects/sections/tasks):\n"
            f"{context_json}\n\n"
            "Examples:\n"
            '- "mark the milk task done" -> {"action":"complete_task","selector":"Buy milk"}\n'
            '- "move report to friday" -> {"action":"reschedule_task","selector":"Submit report","due_string":"friday"}\n'
            '- "add reminder to call mum tomorrow in To-Do/Joint to-do" -> {"action":"create_task","content":"Call mum","due_string":"tomorrow","project_ref":"To-Do/Joint to-do"}\n\n'
            "JSON schema:\n"
            "{"
            '"action":"create_task|edit_task|complete_task|reschedule_task|unknown",'
            '"content":"string|null",'
            '"selector":"string|null",'
            '"new_content":"string|null",'
            '"due_string":"string|null",'
            '"project_ref":"string|null",'
            '"confidence":0.0,'
            '"clarify_question":"string|null"'
            "}"
        )

        payload = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        response = requests.post(
            self._url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout_seconds,
        )
        if response.status_code >= 400:
            raise LLMParserError(f"LLM parse request failed ({response.status_code}): {response.text.strip()}")

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except Exception as exc:
            raise LLMParserError("LLM parse response was not valid JSON content") from exc

        return LLMIntent(
            action=str(parsed.get("action", "unknown") or "unknown"),
            content=_as_optional_str(parsed.get("content")),
            selector=_as_optional_str(parsed.get("selector")),
            new_content=_as_optional_str(parsed.get("new_content")),
            due_string=_as_optional_str(parsed.get("due_string")),
            project_ref=_as_optional_str(parsed.get("project_ref")),
            confidence=_as_float(parsed.get("confidence"), default=0.0),
            clarify_question=_as_optional_str(parsed.get("clarify_question")),
        )


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _as_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    if parsed < 0:
        return 0.0
    if parsed > 1:
        return 1.0
    return parsed
