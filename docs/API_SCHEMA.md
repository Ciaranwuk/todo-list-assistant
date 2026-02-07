# API Schema (Planned for Milestone 3)

Planned parser output contract:
- `action`: `create_task | update_task | complete_task | reschedule_task | clarify`
- `confidence`: float 0-1
- `task_selector`: task identification strategy
- `task_payload`: mutable task fields
- `clarify`: follow-up question payload

See `IMPLEMENTATION_PLAN.md` for full JSON schema.
