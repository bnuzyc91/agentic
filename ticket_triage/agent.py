"""Google ADK agents for the ticket triage framework."""

from __future__ import annotations

import os
from typing import Any

from ticket_triage.domain.classification import classify_ticket as _classify_ticket
from ticket_triage.domain.duplicates import find_similar_tickets as _find_similar_tickets
from ticket_triage.domain.evolution import propose_template_evolution as _propose_template_evolution
from ticket_triage.domain.extraction import extract_entities as _extract_entities
from ticket_triage.domain.loading import dump_model, load_state_machine
from ticket_triage.domain.recommendation import (
    evaluate_required_fields as _evaluate_required_fields,
    recommend_next_action as _recommend_next_action,
    triage_ticket as _triage_ticket,
)

try:
    from google.adk.agents import Agent
except ImportError:  # pragma: no cover - exercised only when ADK is not installed.
    Agent = None  # type: ignore[assignment]


def load_state_machine_template() -> dict[str, Any]:
    """Load the versioned JSON state/action template validated by schema.py."""

    return dump_model(load_state_machine())


def extract_ticket_entities(ticket: dict[str, Any]) -> dict[str, Any]:
    """Extract canonical entities from a ticket dictionary."""

    return dump_model(_extract_entities(ticket))


def classify_ticket(ticket: dict[str, Any], entities: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify a ticket into primary category and optional application issue subcategory."""

    return dump_model(_classify_ticket(ticket, entities))


def find_similar_tickets(ticket: dict[str, Any]) -> list[dict[str, Any]]:
    """Find likely duplicate candidates from local sample or historical tickets."""

    return [dump_model(candidate) for candidate in _find_similar_tickets(ticket)]


def evaluate_required_fields(
    primary_category: str,
    subcategory: str | None,
    entities: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return required fields missing for the selected category/subcategory."""

    return [
        dump_model(field)
        for field in _evaluate_required_fields(primary_category, subcategory, entities)
    ]


def recommend_next_action(
    ticket: dict[str, Any],
    primary_category: str,
    subcategory: str | None,
    entities: dict[str, Any],
    missing_fields: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recommend a next action as a copilot suggestion, not a live ticket mutation."""

    return dump_model(
        _recommend_next_action(
            ticket,
            primary_category,
            subcategory,
            entities,
            missing_fields,
            duplicates,
        )
    )


def propose_template_evolution() -> list[dict[str, Any]]:
    """Inspect local history and propose human-reviewable template improvements."""

    return [dump_model(proposal) for proposal in _propose_template_evolution()]


def triage_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Run the full deterministic triage pipeline for one ticket."""

    return dump_model(_triage_ticket(ticket))


TICKET_EXECUTOR_TOOLS = [
    load_state_machine_template,
    extract_ticket_entities,
    classify_ticket,
    find_similar_tickets,
    evaluate_required_fields,
    recommend_next_action,
    triage_ticket,
]

TEMPLATE_EVOLUTION_TOOLS = [
    load_state_machine_template,
    propose_template_evolution,
]


TICKET_EXECUTOR_INSTRUCTION = """
You are the ticket executor agent for an annual budget planning application.

Use the provided tools to analyze tickets. Prefer the full triage_ticket tool when the
user provides one ticket and wants a recommendation. Use the lower-level tools when
the user asks to inspect classification, extracted entities, duplicate candidates,
missing required fields, or the state/action template.

Explain recommendations in state-machine terms: phase, state, last_event,
recommended_action.type, missing_fields, allowed_next_events, and audit rationale.

V1 is suggestion-only. Do not claim that you assigned, closed, CC'd, approved, or
mutated a real ticket. Always present recommendations as human-reviewable drafts.
Explain the evidence briefly and include missing fields when the ticket cannot be
routed confidently.
"""


TEMPLATE_EVOLUTION_INSTRUCTION = """
You are the template evolution agent for an annual budget planning application.

Your job is to inspect historical tickets and propose improvements to the general
fallback state/action template. Use propose_template_evolution to generate structured
human-reviewable proposals. Do not apply changes to the JSON template, do not mutate
ticket history, and do not process live tickets as the executor. Future versions may
use feedback from newly resolved tickets; for now, work from local historical samples.

Focus on repeated state-machine gaps: tickets stuck in missing_info, human_review,
routing_unclear, or repeatedly resolved by humans in ways the current rulebook did
not predict. Be conservative with new states and action types; prefer routing-rule,
clarification-template, required-field, deflection, or duplicate-evidence proposals
first.
"""


class _LocalAgent:
    """Import-time fallback for environments that have not installed google-adk yet."""

    def __init__(
        self,
        name: str,
        model: str,
        description: str,
        instruction: str,
        tools: list[Any],
    ) -> None:
        self.name = name
        self.model = model
        self.description = description
        self.instruction = instruction
        self.tools = tools


def _build_agent(
    *,
    name: str,
    description: str,
    instruction: str,
    tools: list[Any],
) -> Any:
    model = os.getenv("TICKET_TRIAGE_MODEL", "gemini-2.5-flash")
    agent_cls = Agent or _LocalAgent
    return agent_cls(
        name=name,
        model=model,
        description=description,
        instruction=instruction,
        tools=tools,
    )


ticket_executor_agent = _build_agent(
    name="ticket_executor_agent",
    description=(
        "Suggestion-only agent for classifying, checking duplicates, finding missing "
        "fields, and recommending the next action for one ticket."
    ),
    instruction=TICKET_EXECUTOR_INSTRUCTION,
    tools=TICKET_EXECUTOR_TOOLS,
)

template_evolution_agent = _build_agent(
    name="template_evolution_agent",
    description=(
        "Proposal-only agent for evolving the fallback state/action template from "
        "historical tickets."
    ),
    instruction=TEMPLATE_EVOLUTION_INSTRUCTION,
    tools=TEMPLATE_EVOLUTION_TOOLS,
)

# ADK expects a module-level root_agent. Until a coordinator exists, normal
# `adk run ticket_triage` starts the executor agent.
root_agent = ticket_executor_agent
