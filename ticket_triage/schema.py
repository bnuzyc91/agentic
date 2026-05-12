"""Pydantic contracts for the ticket triage framework."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PrimaryCategory(str, Enum):
    ACCESS_REQUEST = "access_request"
    APPLICATION_ISSUE = "application_issue"
    FEATURE_REQUEST = "feature_request"
    INTENDED_BEHAVIOR = "intended_behavior"
    DUPLICATE = "duplicate"
    OTHER_OR_UNKNOWN = "other_or_unknown"


class ApplicationIssueSubcategory(str, Enum):
    REPORT_PERFORMANCE_ISSUE = "report_performance_issue"
    BUDGET_VARIANCE_ISSUE = "budget_variance_issue"
    DATA_QUALITY_ISSUE = "data_quality_issue"
    UI_WORKFLOW_ISSUE = "ui_workflow_issue"
    INTEGRATION_ISSUE = "integration_issue"


class ActionType(str, Enum):
    ASK_FOR_INFO = "ask_for_info"
    ROUTE_TO_TEAM = "route_to_team"
    SUGGEST_DUPLICATE_REVIEW = "suggest_duplicate_review"
    EXPLAIN_INTENDED_BEHAVIOR = "explain_intended_behavior"
    PRODUCT_REVIEW = "product_review"
    HUMAN_REVIEW = "human_review"


class TemplateProposalType(str, Enum):
    ADD_PRIMARY_CATEGORY = "add_primary_category"
    ADD_APPLICATION_ISSUE_SUBCATEGORY = "add_application_issue_subcategory"
    ADD_REQUIRED_ENTITY = "add_required_entity"
    CHANGE_ROUTING_HINT = "change_routing_hint"
    ADD_CLARIFICATION_TEXT = "add_clarification_text"
    IMPROVE_DUPLICATE_EVIDENCE = "improve_duplicate_evidence"


class Comment(BaseModel):
    author: str = ""
    body: str
    created_at: str | None = None


class Attachment(BaseModel):
    filename: str | None = None
    url: str | None = None
    kind: str | None = None
    description: str | None = None


class Ticket(BaseModel):
    issue_id: str
    reporter: str | None = None
    ccs: list[str] = Field(default_factory=list)
    title: str
    description: str
    comments: list[Comment] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    known_primary_category: PrimaryCategory | None = None
    known_subcategory: ApplicationIssueSubcategory | None = None
    known_resolution: str | None = None
    known_assignee: str | None = None
    labels: list[str] = Field(default_factory=list)


class ExtractedEntities(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    ldap: str | None = None
    portfolio: str | None = None
    region: str | None = None
    user_role: str | None = None
    project_type: str | None = None
    leads: list[str] = Field(default_factory=list)
    additional_context: str | None = None
    site: str | None = None
    project_code: str | None = None
    project_name: str | None = None
    project_currency: str | None = None
    affected_link: str | None = None
    issue_description: str | None = None
    requested_capability: str | None = None
    business_reason: str | None = None
    urgency: str | None = None
    fiscal_period: str | None = None
    screenshot_provided: bool = False


class DuplicateCandidate(BaseModel):
    issue_id: str
    score: float = Field(ge=0.0, le=1.0)
    title: str
    rationale: str


class ClassificationResult(BaseModel):
    primary_category: PrimaryCategory
    subcategory: ApplicationIssueSubcategory | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class RequiredFieldRule(BaseModel):
    field: str
    label: str
    prompt: str


class RoutingHint(BaseModel):
    team: str
    reason: str


class CategoryTemplate(BaseModel):
    description: str
    required_fields: list[RequiredFieldRule] = Field(default_factory=list)
    routing_hint: RoutingHint | None = None
    clarification_style: str | None = None


class SubcategoryTemplate(BaseModel):
    description: str
    required_fields: list[RequiredFieldRule] = Field(default_factory=list)
    routing_hint: RoutingHint | None = None
    duplicate_keywords: list[str] = Field(default_factory=list)


class StateDefinition(BaseModel):
    description: str
    actions: list[str] = Field(default_factory=list)
    next_states: list[str] = Field(default_factory=list)


class StateMachineTemplate(BaseModel):
    version: str
    name: str
    description: str
    states: dict[str, StateDefinition]
    primary_categories: dict[PrimaryCategory, CategoryTemplate]
    application_issue_subcategories: dict[
        ApplicationIssueSubcategory, SubcategoryTemplate
    ] = Field(default_factory=dict)
    final_state: str = "human_review"


class MissingField(BaseModel):
    field: str
    label: str
    prompt: str


class RecommendedAction(BaseModel):
    action_type: ActionType
    state: str
    team: str | None = None
    comment: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool = True


class TriageOutput(BaseModel):
    issue_id: str
    state: str
    primary_category: PrimaryCategory
    subcategory: ApplicationIssueSubcategory | None = None
    extracted_entities: ExtractedEntities
    missing_fields: list[MissingField] = Field(default_factory=list)
    duplicate_candidates: list[DuplicateCandidate] = Field(default_factory=list)
    recommended_action: RecommendedAction
    confidence: float = Field(ge=0.0, le=1.0)
    audit_evidence: list[str] = Field(default_factory=list)


class TemplateEvolutionProposal(BaseModel):
    proposal_type: TemplateProposalType
    title: str
    rationale: str
    evidence_ticket_ids: list[str] = Field(default_factory=list)
    proposed_change: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_approval: Literal[True] = True
