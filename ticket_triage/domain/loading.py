"""Load and validate local state machine and ticket history files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ticket_triage.schema import StateMachineTemplate, Ticket


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_PATH = PACKAGE_ROOT / "templates" / "state_machine.v1.json"
DEFAULT_TICKETS_PATH = PACKAGE_ROOT / "data" / "sample_tickets.jsonl"


def load_state_machine(path: Path | None = None) -> StateMachineTemplate:
    """Load the versioned state/action template."""

    template_path = path or DEFAULT_TEMPLATE_PATH
    with template_path.open("r", encoding="utf-8") as template_file:
        payload: dict[str, Any] = json.load(template_file)
    return StateMachineTemplate.model_validate(payload)


def load_sample_tickets(path: Path | None = None) -> list[Ticket]:
    """Load JSONL sample or historical tickets."""

    tickets_path = path or DEFAULT_TICKETS_PATH
    tickets: list[Ticket] = []
    with tickets_path.open("r", encoding="utf-8") as tickets_file:
        for line in tickets_file:
            if not line.strip():
                continue
            tickets.append(Ticket.model_validate_json(line))
    return tickets


def dump_model(model: Any) -> dict[str, Any]:
    """Return a JSON-ready dictionary for ADK tool responses."""

    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model
