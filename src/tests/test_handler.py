from orchestration.handler import handle_text, parse_create_command


class FakeTodoistClient:
    def __init__(self) -> None:
        self.projects = {"to-do": {"id": 10, "path": "To-Do"}, "inbox": {"id": 1, "path": "Inbox"}}
        self.sections = {"to-do/joint to-do": {"id": 999, "project_id": 10, "path": "To-Do/Joint to-do"}}

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

    def resolve_project_id(self, project_ref: str) -> int | None:
        match = self.resolve_project(project_ref)
        if not match:
            return None
        return int(match["id"])

    def suggest_projects(self, project_ref: str, limit: int = 3):
        return ["to-do", "inbox"][:limit]

    def suggest_sections(self, project_ref: str, limit: int = 3):
        return ["to-do/joint to-do"][:limit]

    def list_project_paths(self, limit: int = 50):
        return ["To-Do", "Inbox"][:limit]

    def list_section_paths(self, limit: int = 50):
        return ["To-Do/Joint to-do"][:limit]


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
    assert "I can create Todoist tasks" in reply


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
