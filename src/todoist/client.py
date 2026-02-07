from __future__ import annotations

import difflib
from functools import lru_cache
import re
from typing import Any

import requests


def _normalize_project_ref(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.replace("\\", "/")
    lowered = re.sub(r"\s*/\s*", "/", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _squash_project_ref(value: str) -> str:
    normalized = _normalize_project_ref(value)
    return re.sub(r"[^a-z0-9]", "", normalized)


class TodoistClient:
    def __init__(self, api_token: str, timeout_seconds: float = 15.0) -> None:
        self._base_url = "https://api.todoist.com/rest/v2"
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self._timeout_seconds = timeout_seconds

    def create_task(
        self,
        content: str,
        due_string: str | None = None,
        project_id: int | None = None,
        section_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": content}
        if due_string:
            payload["due_string"] = due_string
        if project_id is not None:
            payload["project_id"] = project_id
        if section_id is not None:
            payload["section_id"] = section_id

        response = requests.post(
            f"{self._base_url}/tasks",
            headers=self._headers,
            json=payload,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def list_projects(self) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self._base_url}/projects",
            headers=self._headers,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def list_sections(self) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self._base_url}/sections",
            headers=self._headers,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    @lru_cache(maxsize=1)
    def _project_records(self) -> list[dict[str, Any]]:
        projects = self.list_projects()
        by_id = {int(p["id"]): p for p in projects}
        records: list[dict[str, Any]] = []

        def build_path(project_id: int) -> str:
            project = by_id[project_id]
            name = str(project["name"]).strip()
            parent_id = project.get("parent_id")
            if parent_id:
                parent_path = build_path(int(parent_id))
                return f"{parent_path}/{name}"
            return name

        for pid in by_id:
            full_path = build_path(pid)
            records.append(
                {
                    "id": pid,
                    "name": str(by_id[pid]["name"]).strip(),
                    "path": full_path,
                    "path_norm": _normalize_project_ref(full_path),
                    "path_squash": _squash_project_ref(full_path),
                    "name_norm": _normalize_project_ref(str(by_id[pid]["name"]).strip()),
                    "name_squash": _squash_project_ref(str(by_id[pid]["name"]).strip()),
                }
            )

        return records

    @lru_cache(maxsize=1)
    def _section_records(self) -> list[dict[str, Any]]:
        project_by_id = {int(r["id"]): r for r in self._project_records()}
        sections = self.list_sections()
        records: list[dict[str, Any]] = []

        for section in sections:
            section_id = int(section["id"])
            section_name = str(section["name"]).strip()
            project_id = int(section["project_id"])
            project_path = str(project_by_id.get(project_id, {}).get("path", "")).strip()
            full_path = f"{project_path}/{section_name}" if project_path else section_name
            records.append(
                {
                    "id": section_id,
                    "name": section_name,
                    "project_id": project_id,
                    "path": full_path,
                    "path_norm": _normalize_project_ref(full_path),
                    "path_squash": _squash_project_ref(full_path),
                    "name_norm": _normalize_project_ref(section_name),
                    "name_squash": _squash_project_ref(section_name),
                }
            )

        return records

    def resolve_project(self, project_ref: str) -> dict[str, Any] | None:
        normalized = _normalize_project_ref(project_ref.strip().lstrip("#"))
        squashed = _squash_project_ref(project_ref.strip().lstrip("#"))
        if not normalized:
            return None

        records = self._project_records()

        exact_path = [r for r in records if r["path_norm"] == normalized]
        if len(exact_path) == 1:
            return exact_path[0]

        exact_name = [r for r in records if r["name_norm"] == normalized]
        if len(exact_name) == 1:
            return exact_name[0]

        squash_matches = [r for r in records if r["path_squash"] == squashed or r["name_squash"] == squashed]
        if len(squash_matches) == 1:
            return squash_matches[0]

        contains_matches = [
            r
            for r in records
            if squashed and (squashed in r["path_squash"] or r["name_squash"].startswith(squashed))
        ]
        if len(contains_matches) == 1:
            return contains_matches[0]

        choices = [r["path_norm"] for r in records]
        close = difflib.get_close_matches(normalized, choices, n=3, cutoff=0.72)
        if len(close) == 1:
            target = close[0]
            return next((r for r in records if r["path_norm"] == target), None)

        return None

    def resolve_project_id(self, project_ref: str) -> int | None:
        match = self.resolve_project(project_ref)
        if not match:
            return None
        return int(match["id"])

    def suggest_projects(self, project_ref: str, limit: int = 3) -> list[str]:
        normalized = _normalize_project_ref(project_ref.strip().lstrip("#"))
        if not normalized:
            return []
        choices = [r["path_norm"] for r in self._project_records()]
        close = difflib.get_close_matches(normalized, choices, n=limit, cutoff=0.45)
        return close

    def resolve_section(self, section_ref: str) -> dict[str, Any] | None:
        normalized = _normalize_project_ref(section_ref.strip().lstrip("#"))
        squashed = _squash_project_ref(section_ref.strip().lstrip("#"))
        if not normalized:
            return None

        records = self._section_records()

        exact_path = [r for r in records if r["path_norm"] == normalized]
        if len(exact_path) == 1:
            return exact_path[0]

        exact_name = [r for r in records if r["name_norm"] == normalized]
        if len(exact_name) == 1:
            return exact_name[0]

        squash_matches = [r for r in records if r["path_squash"] == squashed or r["name_squash"] == squashed]
        if len(squash_matches) == 1:
            return squash_matches[0]

        choices = [r["path_norm"] for r in records]
        close = difflib.get_close_matches(normalized, choices, n=3, cutoff=0.72)
        if len(close) == 1:
            target = close[0]
            return next((r for r in records if r["path_norm"] == target), None)

        return None

    def suggest_sections(self, section_ref: str, limit: int = 3) -> list[str]:
        normalized = _normalize_project_ref(section_ref.strip().lstrip("#"))
        if not normalized:
            return []
        choices = [r["path_norm"] for r in self._section_records()]
        close = difflib.get_close_matches(normalized, choices, n=limit, cutoff=0.45)
        return close

    def list_project_paths(self, limit: int = 50) -> list[str]:
        records = self._project_records()
        paths = sorted({str(r["path"]) for r in records}, key=lambda p: p.lower())
        return paths[:limit]

    def list_section_paths(self, limit: int = 50) -> list[str]:
        records = self._section_records()
        paths = sorted({str(r["path"]) for r in records}, key=lambda p: p.lower())
        return paths[:limit]
