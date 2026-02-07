from __future__ import annotations

from dataclasses import dataclass
import re

from todoist.client import TodoistClient


@dataclass(frozen=True)
class CreateCommand:
    content: str
    due_string: str | None
    project_ref: str | None


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


def handle_text(text: str, todoist_client: TodoistClient) -> str:
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

    command = parse_create_command(text)
    if command is None:
        return (
            "I can create Todoist tasks. Use: 'add <task>', "
            "'add <task> /due <todoist due string>', or "
            "'add <task> /project <project-or-section path>'."
        )

    project_id: int | None = None
    section_id: int | None = None
    resolved_project_path: str | None = None
    if command.project_ref:
        resolved = todoist_client.resolve_project(command.project_ref)
        if resolved:
            project_id = int(resolved["id"])
            resolved_project_path = str(resolved["path"])
        else:
            resolved_section = todoist_client.resolve_section(command.project_ref)
            if resolved_section:
                project_id = int(resolved_section["project_id"])
                section_id = int(resolved_section["id"])
                resolved_project_path = str(resolved_section["path"])
            else:
                project_suggestions = todoist_client.suggest_projects(command.project_ref, limit=3)
                section_suggestions = todoist_client.suggest_sections(command.project_ref, limit=3)
                all_suggestions = list(dict.fromkeys(project_suggestions + section_suggestions))
                if all_suggestions:
                    suggestion_text = ", ".join(all_suggestions)
                    return (
                        f'Could not find project/section "{command.project_ref}". '
                        f"Closest matches: {suggestion_text}."
                    )
                return (
                    f'Could not find project/section "{command.project_ref}". '
                    "Use the exact Todoist project or section path."
                )

    task = todoist_client.create_task(
        content=command.content,
        due_string=command.due_string,
        project_id=project_id,
        section_id=section_id,
    )
    due_text = task.get("due", {}).get("string") if task.get("due") else None
    due_part = due_text if due_text else "none"
    project_part = resolved_project_path if resolved_project_path else "Inbox/default"
    return (
        f'Created task: "{task.get("content", command.content)}" '
        f"(due: {due_part}, project: {project_part})."
    )
