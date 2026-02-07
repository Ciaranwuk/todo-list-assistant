from __future__ import annotations

from dataclasses import dataclass
import difflib
import logging
import re
from typing import Any, Protocol

from todoist.client import TodoistClient


class IntentParser(Protocol):
    def parse(self, text: str, context: dict[str, Any] | None = None) -> Any:
        ...


@dataclass(frozen=True)
class CreateCommand:
    content: str
    due_string: str | None
    project_ref: str | None


@dataclass(frozen=True)
class EditCommand:
    selector: str
    new_content: str | None
    due_string: str | None
    project_ref: str | None


@dataclass
class CompleteCommand:
    selector: str
    project_ref: str | None


@dataclass
class RescheduleCommand:
    selector: str
    due_string: str
    project_ref: str | None


@dataclass
class PendingSelection:
    action: str
    changes: dict[str, str]
    options: list[dict[str, Any]]


_PENDING_SELECTIONS: dict[int, PendingSelection] = {}
_LOGGER = logging.getLogger("assistant.handler")


def reset_runtime_state() -> None:
    _PENDING_SELECTIONS.clear()


def _extract_marked_fields(body: str) -> tuple[str, str | None, str | None]:
    pattern = re.compile(r"\s/(due|project)\s+", re.IGNORECASE)
    matches = list(pattern.finditer(body))
    if not matches:
        return body.strip(), None, None

    content = body[: matches[0].start()].strip()
    due_string: str | None = None
    project_ref: str | None = None

    for idx, match in enumerate(matches):
        key = match.group(1).lower()
        value_start = match.end()
        value_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        value = body[value_start:value_end].strip()
        if not value:
            continue
        if key == "due":
            due_string = value
        elif key == "project":
            project_ref = value

    return content, due_string, project_ref


def _extract_hash_project(content: str) -> tuple[str, str | None]:
    if not content:
        return content, None

    hash_start = content.rfind(" #")
    if hash_start >= 0:
        task_content = content[:hash_start].strip()
        project_ref = content[hash_start + 2 :].strip()
        if task_content and project_ref:
            return task_content, project_ref

    if content.startswith("#"):
        project_ref = content[1:].strip()
        if project_ref:
            return "", project_ref

    return content, None


def _extract_edit_fields(body: str) -> tuple[str, str | None, str | None, str | None]:
    pattern = re.compile(r"\s/(set|due|project)\s+", re.IGNORECASE)
    matches = list(pattern.finditer(body))
    if not matches:
        return body.strip(), None, None, None

    selector = body[: matches[0].start()].strip()
    new_content: str | None = None
    due_string: str | None = None
    project_ref: str | None = None

    for idx, match in enumerate(matches):
        key = match.group(1).lower()
        value_start = match.end()
        value_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        value = body[value_start:value_end].strip()
        if not value:
            continue
        if key == "set":
            new_content = value
        elif key == "due":
            due_string = value
        elif key == "project":
            project_ref = value

    return selector, new_content, due_string, project_ref


def _normalize_task_text(value: str) -> str:
    lowered = value.strip().lower()
    return re.sub(r"\s+", " ", lowered)


def _format_task_label(task: dict[str, Any]) -> str:
    due_text = task.get("due", {}).get("string") if task.get("due") else None
    due_part = due_text if due_text else "no due"
    return f'[{task.get("id")}] {task.get("content", "")} (due: {due_part})'


def _find_task_matches(tasks: list[dict[str, Any]], selector: str) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]]]:
    raw = selector.strip()
    if not raw:
        return "none", None, []

    if raw.isdigit():
        task_id = int(raw)
        id_matches = [t for t in tasks if int(t.get("id", -1)) == task_id]
        if len(id_matches) == 1:
            return "found", id_matches[0], []
        return "none", None, []

    normalized_selector = _normalize_task_text(raw)

    exact_matches = [t for t in tasks if _normalize_task_text(str(t.get("content", ""))) == normalized_selector]
    if len(exact_matches) == 1:
        return "found", exact_matches[0], []
    if len(exact_matches) > 1:
        return "ambiguous", None, exact_matches[:5]

    contains_matches = [
        t for t in tasks if normalized_selector in _normalize_task_text(str(t.get("content", "")))
    ]
    if len(contains_matches) == 1:
        return "found", contains_matches[0], []
    if len(contains_matches) > 1:
        return "ambiguous", None, contains_matches[:5]

    scored: list[tuple[float, dict[str, Any]]] = []
    for task in tasks:
        ratio = difflib.SequenceMatcher(
            None,
            normalized_selector,
            _normalize_task_text(str(task.get("content", ""))),
        ).ratio()
        if ratio >= 0.62:
            scored.append((ratio, task))

    if not scored:
        return "none", None, []

    scored.sort(key=lambda item: item[0], reverse=True)
    top_score, top_task = scored[0]
    if top_score < 0.72:
        return "none", None, []

    if len(scored) == 1 or top_score - scored[1][0] >= 0.08:
        return "found", top_task, []

    close = [task for score, task in scored if top_score - score <= 0.08]
    return "ambiguous", None, close[:5]


def parse_create_command(text: str) -> CreateCommand | None:
    normalized = text.strip()
    lowered = normalized.lower()

    prefixes = ("create ", "add ", "todo ")
    matched_prefix = next((p for p in prefixes if lowered.startswith(p)), None)
    if not matched_prefix:
        return None

    body = normalized[len(matched_prefix) :].strip()
    if not body:
        return None

    content, due_string, project_ref = _extract_marked_fields(body)
    content, hash_project = _extract_hash_project(content)
    if not project_ref and hash_project:
        project_ref = hash_project

    if not content:
        return None

    return CreateCommand(content=content, due_string=due_string, project_ref=project_ref)


def parse_edit_command(text: str) -> EditCommand | None:
    normalized = text.strip()
    lowered = normalized.lower()

    prefixes = ("edit ", "update ", "change ")
    matched_prefix = next((p for p in prefixes if lowered.startswith(p)), None)
    if not matched_prefix:
        return None

    body = normalized[len(matched_prefix) :].strip()
    if not body:
        return None

    selector, new_content, due_string, project_ref = _extract_edit_fields(body)
    if not selector:
        return None
    if new_content is None and due_string is None:
        return None

    return EditCommand(
        selector=selector,
        new_content=new_content,
        due_string=due_string,
        project_ref=project_ref,
    )


def parse_complete_command(text: str) -> CompleteCommand | None:
    normalized = text.strip()
    lowered = normalized.lower()

    prefixes = ("complete ", "done ", "finish ", "close ")
    matched_prefix = next((p for p in prefixes if lowered.startswith(p)), None)
    if not matched_prefix:
        return None

    body = normalized[len(matched_prefix) :].strip()
    if not body:
        return None

    selector, _, _, project_ref = _extract_edit_fields(body)
    if not selector:
        return None
    return CompleteCommand(selector=selector, project_ref=project_ref)


def parse_reschedule_command(text: str) -> RescheduleCommand | None:
    normalized = text.strip()
    lowered = normalized.lower()

    prefixes = ("reschedule ", "move ")
    matched_prefix = next((p for p in prefixes if lowered.startswith(p)), None)
    if not matched_prefix:
        return None

    body = normalized[len(matched_prefix) :].strip()
    if not body:
        return None

    selector, _, due_string, project_ref = _extract_edit_fields(body)
    if not selector or due_string is None:
        return None
    return RescheduleCommand(selector=selector, due_string=due_string, project_ref=project_ref)


def _resolve_project_or_section(
    todoist_client: TodoistClient,
    project_ref: str,
) -> tuple[int | None, int | None, str | None, str | None]:
    resolved = todoist_client.resolve_project(project_ref)
    if resolved:
        return int(resolved["id"]), None, str(resolved["path"]), None

    resolved_section = todoist_client.resolve_section(project_ref)
    if resolved_section:
        return (
            int(resolved_section["project_id"]),
            int(resolved_section["id"]),
            str(resolved_section["path"]),
            None,
        )

    project_suggestions = todoist_client.suggest_projects(project_ref, limit=3)
    section_suggestions = todoist_client.suggest_sections(project_ref, limit=3)
    all_suggestions = list(dict.fromkeys(project_suggestions + section_suggestions))
    if all_suggestions:
        suggestion_text = ", ".join(all_suggestions)
        return None, None, None, (
            f'Could not find project/section "{project_ref}". '
            f"Closest matches: {suggestion_text}."
        )
    return None, None, None, (
        f'Could not find project/section "{project_ref}". '
        "Use the exact Todoist project or section path."
    )


def _execute_edit(
    todoist_client: TodoistClient,
    task: dict[str, Any],
    *,
    new_content: str | None,
    due_string: str | None,
) -> str:
    old_content = str(task.get("content", ""))
    old_due = task.get("due", {}).get("string") if task.get("due") else "none"

    todoist_client.update_task(
        task_id=int(task["id"]),
        content=new_content,
        due_string=due_string,
    )

    final_content = new_content if new_content is not None else old_content
    final_due = due_string if due_string is not None else old_due
    return (
        f'Updated task [{task.get("id")}]: "{old_content}" -> "{final_content}" '
        f"(due: {old_due} -> {final_due})."
    )


def _execute_complete(todoist_client: TodoistClient, task: dict[str, Any]) -> str:
    task_id = int(task["id"])
    content = str(task.get("content", ""))
    todoist_client.close_task(task_id=task_id)
    return f'Completed task [{task_id}]: "{content}".'


def _execute_reschedule(
    todoist_client: TodoistClient,
    task: dict[str, Any],
    *,
    due_string: str,
) -> str:
    old_due = task.get("due", {}).get("string") if task.get("due") else "none"
    todoist_client.update_task(
        task_id=int(task["id"]),
        due_string=due_string,
    )
    return (
        f'Rescheduled task [{task.get("id")}]: "{task.get("content", "")}" '
        f"(due: {old_due} -> {due_string})."
    )


def _handle_pending_selection(
    *,
    chat_id: int,
    text: str,
    todoist_client: TodoistClient,
) -> str:
    pending = _PENDING_SELECTIONS.get(chat_id)
    if pending is None:
        return ""

    normalized = text.strip().lower()
    if normalized in {"cancel", "stop", "nevermind", "never mind"}:
        _PENDING_SELECTIONS.pop(chat_id, None)
        return "Okay, canceled that request."

    if not normalized.isdigit():
        return "Reply with the task number shown in the list, or type 'cancel'."

    choice = int(normalized)
    if choice < 1 or choice > len(pending.options):
        return "That number is out of range. Reply with a listed number, or 'cancel'."

    task = pending.options[choice - 1]
    _PENDING_SELECTIONS.pop(chat_id, None)
    if pending.action == "edit":
        return _execute_edit(
            todoist_client,
            task,
            new_content=pending.changes.get("content"),
            due_string=pending.changes.get("due_string"),
        )
    if pending.action == "complete":
        return _execute_complete(todoist_client, task)
    if pending.action == "reschedule":
        due_string = pending.changes.get("due_string")
        if not due_string:
            return "Missing due date for reschedule. Please try again."
        return _execute_reschedule(todoist_client, task, due_string=due_string)
    return "Unsupported pending action. Please try again."


def _run_selector_action(
    *,
    action_name: str,
    selector: str,
    project_ref: str | None,
    chat_id: int | None,
    todoist_client: TodoistClient,
    changes: dict[str, str] | None = None,
) -> str:
    open_tasks = todoist_client.list_open_tasks(limit=200)
    if project_ref:
        project_id, section_id, _, project_error = _resolve_project_or_section(todoist_client, project_ref)
        if project_error:
            return project_error
        open_tasks = [
            task
            for task in open_tasks
            if (project_id is None or int(task.get("project_id", -1)) == project_id)
            and (section_id is None or int(task.get("section_id", -1)) == section_id)
        ]

    status, matched_task, candidates = _find_task_matches(open_tasks, selector)
    if status == "none" or (matched_task is None and not candidates):
        return f'Could not find an open task matching "{selector}". Try `tasks` to view candidates.'

    if status == "ambiguous":
        lines = [f'I found multiple open tasks matching "{selector}". Reply with a number:']
        for idx, task in enumerate(candidates, start=1):
            lines.append(f"{idx}. {_format_task_label(task)}")
        lines.append("Type 'cancel' to stop.")
        if chat_id is not None:
            _PENDING_SELECTIONS[chat_id] = PendingSelection(
                action=action_name,
                changes=changes or {},
                options=candidates,
            )
        return "\n".join(lines)

    if action_name == "edit":
        return _execute_edit(
            todoist_client,
            matched_task,
            new_content=(changes or {}).get("content"),
            due_string=(changes or {}).get("due_string"),
        )
    if action_name == "complete":
        return _execute_complete(todoist_client, matched_task)
    if action_name == "reschedule":
        due_string = (changes or {}).get("due_string")
        if not due_string:
            return "Missing due date for reschedule."
        return _execute_reschedule(todoist_client, matched_task, due_string=due_string)
    return "Unsupported action."


def _build_llm_context(todoist_client: TodoistClient) -> dict[str, Any]:
    projects = todoist_client.list_project_paths(limit=20)
    sections = todoist_client.list_section_paths(limit=30)
    tasks = todoist_client.list_open_tasks(limit=25)
    task_summaries = []
    for task in tasks:
        task_summaries.append(
            {
                "id": task.get("id"),
                "content": task.get("content"),
                "project_id": task.get("project_id"),
                "section_id": task.get("section_id"),
                "due": (task.get("due") or {}).get("string"),
            }
        )
    return {
        "projects": projects,
        "sections": sections,
        "open_tasks": task_summaries,
    }


def handle_text(
    text: str,
    todoist_client: TodoistClient,
    chat_id: int | None = None,
    llm_parser: IntentParser | None = None,
) -> str:
    if chat_id is not None and chat_id in _PENDING_SELECTIONS:
        return _handle_pending_selection(chat_id=chat_id, text=text, todoist_client=todoist_client)

    normalized_text = text.strip().lower()
    if normalized_text in {"projects", "list projects"}:
        paths = todoist_client.list_project_paths(limit=30)
        if not paths:
            return "No projects found in Todoist."
        return "Projects:\n" + "\n".join(f"- {path}" for path in paths)
    if normalized_text in {"sections", "list sections"}:
        paths = todoist_client.list_section_paths(limit=50)
        if not paths:
            return "No sections found in Todoist."
        return "Sections:\n" + "\n".join(f"- {path}" for path in paths)
    if normalized_text in {"tasks", "list tasks"}:
        tasks = todoist_client.list_open_tasks(limit=15)
        if not tasks:
            return "No open tasks found."
        return "Open tasks:\n" + "\n".join(f"- {_format_task_label(task)}" for task in tasks)

    edit_command = parse_edit_command(text)
    create_command = parse_create_command(text)
    complete_command = parse_complete_command(text)
    reschedule_command = parse_reschedule_command(text)

    if (
        edit_command is None
        and create_command is None
        and complete_command is None
        and reschedule_command is None
        and llm_parser is not None
    ):
        try:
            intent = llm_parser.parse(text, context=_build_llm_context(todoist_client))
        except Exception:
            _LOGGER.exception("LLM parse failed")
            intent = None

        if intent is not None:
            action = str(getattr(intent, "action", "unknown") or "unknown").lower()
            confidence = float(getattr(intent, "confidence", 0.0) or 0.0)
            clarify_question = getattr(intent, "clarify_question", None)
            if confidence < 0.55:
                if clarify_question:
                    return str(clarify_question)
                return "Could you rephrase that with the task and change you want?"

            selector = getattr(intent, "selector", None)
            project_ref = getattr(intent, "project_ref", None)
            due_string = getattr(intent, "due_string", None)
            new_content = getattr(intent, "new_content", None)
            content = getattr(intent, "content", None)

            if action == "edit_task" and selector and (new_content is not None or due_string is not None):
                edit_command = EditCommand(
                    selector=str(selector),
                    new_content=str(new_content) if new_content is not None else None,
                    due_string=str(due_string) if due_string is not None else None,
                    project_ref=str(project_ref) if project_ref is not None else None,
                )
            elif action == "create_task" and content:
                create_command = CreateCommand(
                    content=str(content),
                    due_string=str(due_string) if due_string is not None else None,
                    project_ref=str(project_ref) if project_ref is not None else None,
                )
            elif action == "complete_task" and selector:
                complete_command = CompleteCommand(
                    selector=str(selector),
                    project_ref=str(project_ref) if project_ref is not None else None,
                )
            elif action == "reschedule_task" and selector and due_string is not None:
                reschedule_command = RescheduleCommand(
                    selector=str(selector),
                    due_string=str(due_string),
                    project_ref=str(project_ref) if project_ref is not None else None,
                )

    if edit_command is not None:
        changes: dict[str, str] = {}
        if edit_command.new_content is not None:
            changes["content"] = edit_command.new_content
        if edit_command.due_string is not None:
            changes["due_string"] = edit_command.due_string
        return _run_selector_action(
            action_name="edit",
            selector=edit_command.selector,
            project_ref=edit_command.project_ref,
            chat_id=chat_id,
            todoist_client=todoist_client,
            changes=changes,
        )

    if complete_command is not None:
        return _run_selector_action(
            action_name="complete",
            selector=complete_command.selector,
            project_ref=complete_command.project_ref,
            chat_id=chat_id,
            todoist_client=todoist_client,
        )

    if reschedule_command is not None:
        return _run_selector_action(
            action_name="reschedule",
            selector=reschedule_command.selector,
            project_ref=reschedule_command.project_ref,
            chat_id=chat_id,
            todoist_client=todoist_client,
            changes={"due_string": reschedule_command.due_string},
        )

    if create_command is None:
        return (
            "I can create, edit, complete, and reschedule Todoist tasks. "
            "Use: 'add <task>', 'edit <selector> /set <new content>', "
            "'complete <selector>', or 'reschedule <selector> /due <todoist due string>'."
        )

    project_id: int | None = None
    section_id: int | None = None
    resolved_project_path: str | None = None
    if create_command.project_ref:
        project_id, section_id, resolved_project_path, project_error = _resolve_project_or_section(
            todoist_client, create_command.project_ref
        )
        if project_error:
            return project_error

    task = todoist_client.create_task(
        content=create_command.content,
        due_string=create_command.due_string,
        project_id=project_id,
        section_id=section_id,
    )
    due_text = task.get("due", {}).get("string") if task.get("due") else None
    due_part = due_text if due_text else "none"
    project_part = resolved_project_path if resolved_project_path else "Inbox/default"
    return (
        f'Created task: "{task.get("content", create_command.content)}" '
        f"(due: {due_part}, project: {project_part})."
    )
