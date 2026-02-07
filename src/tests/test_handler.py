from orchestration.handler import (
    handle_text,
    parse_create_command,
    parse_edit_command,
    reset_runtime_state,
)


class FakeTodoistClient:
    def __init__(self) -> None:
        self.projects = {"to-do": {"id": 10, "path": "To-Do"}, "inbox": {"id": 1, "path": "Inbox"}}
        self.sections = {"to-do/joint to-do": {"id": 999, "project_id": 10, "path": "To-Do/Joint to-do"}}
        self.tasks = [
            {
                "id": 101,
                "content": "Buy milk",
                "due": {"string": "tomorrow"},
                "project_id": 1,
                "section_id": None,
            },
            {
                "id": 102,
                "content": "Buy oat milk",
                "due": None,
                "project_id": 1,
                "section_id": None,
            },
            {
                "id": 103,
                "content": "Submit report",
                "due": None,
                "project_id": 1,
                "section_id": None,
            },
            {
                "id": 104,
                "content": "Create personal assistant bot",
                "due": {"string": "today"},
                "project_id": 10,
                "section_id": 999,
            },
            {
                "id": 105,
                "content": "Create personal assistant bot",
                "due": {"string": "today"},
                "project_id": 1,
                "section_id": None,
            },
        ]

    def create_task(
        self,
        content: str,
        due_string: str | None = None,
        project_id: int | None = None,
        section_id: int | None = None,
    ):
        result = {"content": content}
        if due_string:
            result["due"] = {"string": due_string}
        if project_id is not None:
            result["project_id"] = project_id
        if section_id is not None:
            result["section_id"] = section_id
        return result

    def list_open_tasks(self, limit: int = 100):
        return self.tasks[:limit]

    def update_task(self, *, task_id: int, content: str | None = None, due_string: str | None = None):
        for task in self.tasks:
            if int(task["id"]) != int(task_id):
                continue
            if content is not None:
                task["content"] = content
            if due_string is not None:
                task["due"] = {"string": due_string}
            return {}
        raise ValueError("task not found")

    def resolve_project(self, project_ref: str):
        key = project_ref.strip().lstrip("#").lower()
        if key in self.projects:
            return self.projects[key]
        return None

    def resolve_section(self, section_ref: str):
        key = section_ref.strip().lstrip("#").lower()
        if key in self.sections:
            return self.sections[key]
        if key in {"joint", "joint to-do"}:
            return self.sections["to-do/joint to-do"]
        return None

    def suggest_projects(self, project_ref: str, limit: int = 3):
        return ["to-do", "inbox"][:limit]

    def suggest_sections(self, project_ref: str, limit: int = 3):
        return ["to-do/joint to-do"][:limit]

    def list_project_paths(self, limit: int = 50):
        return ["To-Do", "Inbox"][:limit]

    def list_section_paths(self, limit: int = 50):
        return ["To-Do/Joint to-do"][:limit]


def setup_function() -> None:
    reset_runtime_state()


def test_parse_create_command_without_due() -> None:
    command = parse_create_command("add Buy milk")
    assert command is not None
    assert command.content == "Buy milk"
    assert command.due_string is None
    assert command.project_ref is None


def test_parse_create_command_with_due() -> None:
    command = parse_create_command("add Buy milk /due tomorrow at 6pm")
    assert command is not None
    assert command.content == "Buy milk"
    assert command.due_string == "tomorrow at 6pm"
    assert command.project_ref is None


def test_parse_edit_command_with_set() -> None:
    command = parse_edit_command("edit Buy milk /set Buy almond milk")
    assert command is not None
    assert command.selector == "Buy milk"
    assert command.new_content == "Buy almond milk"
    assert command.due_string is None


def test_parse_edit_command_with_due_only() -> None:
    command = parse_edit_command("edit Submit report /due next monday")
    assert command is not None
    assert command.selector == "Submit report"
    assert command.new_content is None
    assert command.due_string == "next monday"
    assert command.project_ref is None


def test_parse_edit_command_with_due_and_project() -> None:
    command = parse_edit_command("edit Create personal assistant bot /due tomorrow /project to-do/joint to-do")
    assert command is not None
    assert command.selector == "Create personal assistant bot"
    assert command.due_string == "tomorrow"
    assert command.project_ref == "to-do/joint to-do"


def test_parse_create_command_with_project_marker() -> None:
    command = parse_create_command("add Buy milk /project To-Do/Joint to-do")
    assert command is not None
    assert command.content == "Buy milk"
    assert command.project_ref == "To-Do/Joint to-do"


def test_parse_create_command_with_hash_project() -> None:
    command = parse_create_command("add Buy milk #To-Do/Joint to-do")
    assert command is not None
    assert command.content == "Buy milk"
    assert command.project_ref == "To-Do/Joint to-do"


def test_parse_create_command_requires_prefix() -> None:
    assert parse_create_command("Buy milk") is None


def test_handle_text_help_when_unrecognized() -> None:
    reply = handle_text("what can you do", todoist_client=FakeTodoistClient())
    assert "I can create and edit Todoist tasks" in reply


def test_handle_text_create_confirmation() -> None:
    reply = handle_text("add submit report /due monday", todoist_client=FakeTodoistClient())
    assert reply == 'Created task: "submit report" (due: monday, project: Inbox/default).'


def test_handle_text_with_project() -> None:
    reply = handle_text("add submit report /project To-Do/Joint to-do", todoist_client=FakeTodoistClient())
    assert reply == 'Created task: "submit report" (due: none, project: To-Do/Joint to-do).'


def test_handle_text_with_lowercase_project() -> None:
    reply = handle_text("add submit report /project to-do/joint to-do", todoist_client=FakeTodoistClient())
    assert reply == 'Created task: "submit report" (due: none, project: To-Do/Joint to-do).'


def test_handle_text_with_fuzzy_project() -> None:
    reply = handle_text("add submit report /project joint", todoist_client=FakeTodoistClient())
    assert reply == 'Created task: "submit report" (due: none, project: To-Do/Joint to-do).'


def test_handle_text_unknown_project() -> None:
    reply = handle_text("add submit report /project does-not-exist", todoist_client=FakeTodoistClient())
    assert 'Could not find project/section "does-not-exist".' in reply
    assert "Closest matches:" in reply


def test_handle_text_list_projects() -> None:
    reply = handle_text("projects", todoist_client=FakeTodoistClient())
    assert "Projects:" in reply
    assert "- To-Do" in reply


def test_handle_text_list_sections() -> None:
    reply = handle_text("sections", todoist_client=FakeTodoistClient())
    assert "Sections:" in reply
    assert "- To-Do/Joint to-do" in reply


def test_handle_text_list_tasks() -> None:
    reply = handle_text("tasks", todoist_client=FakeTodoistClient())
    assert "Open tasks:" in reply
    assert "Buy milk" in reply


def test_handle_text_edit_exact_match() -> None:
    client = FakeTodoistClient()
    reply = handle_text("edit Submit report /set Submit annual report", todoist_client=client)
    assert 'Updated task [103]: "Submit report" -> "Submit annual report"' in reply


def test_handle_text_edit_ambiguous_then_select() -> None:
    client = FakeTodoistClient()
    first = handle_text("edit buy /set Buy almond milk", todoist_client=client, chat_id=777)
    assert "Reply with a number" in first
    assert "1." in first

    second = handle_text("2", todoist_client=client, chat_id=777)
    assert 'Updated task [102]: "Buy oat milk" -> "Buy almond milk"' in second


def test_handle_text_edit_pending_cancel() -> None:
    client = FakeTodoistClient()
    _ = handle_text("edit buy /set Buy soy milk", todoist_client=client, chat_id=999)
    reply = handle_text("cancel", todoist_client=client, chat_id=999)
    assert reply == "Okay, canceled that edit request."


def test_handle_text_edit_not_found() -> None:
    reply = handle_text("edit random task /set New title", todoist_client=FakeTodoistClient())
    assert "Could not find an open task" in reply


def test_handle_text_edit_with_project_filter() -> None:
    client = FakeTodoistClient()
    reply = handle_text(
        "edit create personal assistant bot /due tomorrow /project to-do/joint to-do",
        todoist_client=client,
    )
    assert 'Updated task [104]: "Create personal assistant bot" -> "Create personal assistant bot"' in reply
    assert "(due: today -> tomorrow)." in reply
