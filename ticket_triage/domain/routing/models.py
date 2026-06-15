"""Shared models for recursive routing modules."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ticket_triage.schema import (
    ActionType,
    ApplicationIssueSubcategory,
    AuditEntry,
    ExtractedEntities,
    MissingField,
    PrimaryCategory,
    RecommendedAction,
    Ticket,
    TriageEvent,
    TriagePhase,
    TriageState,
)


class RouteOutcome(str, Enum):
    REQUEST_INFORMATION = "request_information"
    DEFLECT_INTENDED_BEHAVIOR = "deflect_intended_behavior"
    ROUTE_TO_TEAM = "route_to_team"
    ESCALATE_HUMAN_REVIEW = "escalate_human_review"


class RouteContext(BaseModel):
    ticket: Ticket
    primary_category: PrimaryCategory
    subcategory: ApplicationIssueSubcategory | None = None
    entities: ExtractedEntities
    classification_confidence: float = 0.75


class RouteDecision(BaseModel):
    outcome: RouteOutcome
    phase: TriagePhase
    state: TriageState
    last_event: TriageEvent
    action_type: ActionType
    module_path: list[str]
    module_state: str
    recommended_action: RecommendedAction
    missing_fields: list[MissingField] = Field(default_factory=list)
    route_target: str | None = None
    route_rule_id: str | None = None
    deflection_rule_id: str | None = None
    confidence: float = 0.75
    audit: list[AuditEntry] = Field(default_factory=list)
    audit_evidence: list[str] = Field(default_factory=list)
