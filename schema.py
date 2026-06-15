"""Pydantic contracts for the ticket triage framework."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RoutingTeam(str, Enum):
    DATA_ENGINEERING = "data_engineering"
    FINANCE_PLATFORM = "finance_platform"
    APP_SUPPORT = "app_support"
    PRODUCT = "product"
    UNKNOWN = "unknown"


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


class TriagePhase(str, Enum):
    INTAKE = "intake"
    CONTEXT_VALIDATION = "context_validation"
    DEFLECTION = "deflection"
    ROUTING = "routing"
    RESOLUTION = "resolution"
    CLOSURE = "closure"
    EXCEPTION = "exception"


class TriageState(str, Enum):
    NEW = "new"
    EXTRACTING_CONTEXT = "extracting_context"
    ROUTE_DECISION = "route_decision"
    MISSING_INFO = "missing_info"
    CONTEXT_VALIDATED = "context_validated"
    CHECKING_KNOWN_BEHAVIOR = "checking_known_behavior"
    INTENDED_BEHAVIOR = "intended_behavior"
    ROUTING_REVIEW = "routing_review"
    DUPLICATE_REVIEW = "duplicate_review"
    READY_FOR_ACCESS_REVIEW = "ready_for_access_review"
    APPROVER_REVIEW = "approver_review"
    ACCESS_PROVISIONING = "access_provisioning"
    VERIFICATION = "verification"
    ROUTED_FINANCE = "routed_finance"
    ROUTED_CRC_L3 = "routed_crc_l3"
    ROUTED_DATA_QUALITY = "routed_data_quality"
    ROUTED_TO_TEAM = "routed_to_team"
    ROUTED_APPLICATION_SUPPORT = "routed_application_support"
    ROUTED_PRODUCT_REVIEW = "routed_product_review"
    WAITING_FIX = "waiting_fix"
    WAITING_REPORTER_CONFIRMATION = "waiting_reporter_confirmation"
    RESOLVED = "resolved"
    COMPLETE = "complete"
    CLOSED = "closed"
    DENIED = "denied"
    STALE_WAITING_FOR_USER = "stale_waiting_for_user"
    HUMAN_REVIEW = "human_review"


class TriageEvent(str, Enum):
    TICKET_CREATED = "ticket_created"
    CONTEXT_EXTRACTION_STARTED = "context_extraction_started"
    REQUIRED_FIELDS_EXTRACTED = "required_fields_extracted"
    MISSING_REQUIRED_FIELDS_DETECTED = "missing_required_fields_detected"
    REPORTER_PROVIDED_MISSING_INFO = "reporter_provided_missing_info"
    DUPLICATE_CANDIDATE_FOUND = "duplicate_candidate_found"
    DUPLICATE_CONFIRMED = "duplicate_confirmed"
    DUPLICATE_REJECTED = "duplicate_rejected"
    ISSUE_SUMMARY_MISSING = "issue_summary_missing"
    SOURCE_SYSTEM_MISSING = "source_system_missing"
    DIAGNOSTIC_EVIDENCE_MISSING = "diagnostic_evidence_missing"
    MINIMUM_CONTEXT_SATISFIED = "minimum_context_satisfied"
    KNOWN_BEHAVIOR_CHECK_STARTED = "known_behavior_check_started"
    EXTERNAL_SYNC_LAG_DETECTED = "external_sync_lag_detected"
    APP_VIEW_FILTER_MISMATCH_DETECTED = "app_view_filter_mismatch_detected"
    HISTORICAL_DATA_LOGIC_DETECTED = "historical_data_logic_detected"
    KNOWN_BEHAVIOR_NOT_MATCHED = "known_behavior_not_matched"
    ROUTE_MATCHED = "route_matched"
    FINANCE_POLICY_ISSUE_DETECTED = "finance_policy_issue_detected"
    INTEGRATION_ISSUE_DETECTED = "integration_issue_detected"
    DATA_STEWARDSHIP_ISSUE_DETECTED = "data_stewardship_issue_detected"
    ROUTING_UNCLEAR = "routing_unclear"
    APPROVER_IDENTIFIED = "approver_identified"
    APPROVER_MISSING = "approver_missing"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    ACCESS_PROVISIONED = "access_provisioned"
    ACCESS_FAILED = "access_failed"
    FIX_APPLIED = "fix_applied"
    EXPLANATION_SENT = "explanation_sent"
    REPORTER_CONFIRMED_RESOLVED = "reporter_confirmed_resolved"
    REPORTER_REPORTS_NOT_RESOLVED = "reporter_reports_not_resolved"
    INACTIVITY_TIMEOUT_REACHED = "inactivity_timeout_reached"
    TICKET_CLOSED = "ticket_closed"
    TICKET_REOPENED = "ticket_reopened"
    HUMAN_OVERRIDE = "human_override"


class ActionType(str, Enum):
    ASK_FOR_INFO = "ask_for_info"
    ROUTE_TO_TEAM = "route_to_team"
    SUGGEST_DUPLICATE_REVIEW = "suggest_duplicate_review"
    EXPLAIN_INTENDED_BEHAVIOR = "explain_intended_behavior"
    PRODUCT_REVIEW = "product_review"
    HUMAN_REVIEW = "human_review"
    EXTRACT_CONTEXT = "extract_context"
    REQUEST_ISSUE_SUMMARY = "request_issue_summary"
    REQUEST_SOURCE_SYSTEM = "request_source_system"
    REQUEST_DIAGNOSTIC_EVIDENCE = "request_diagnostic_evidence"
    REQUEST_MISSING_CONTEXT = "request_missing_context"
    REQUEST_INFORMATION = "request_information"
    DEFLECT_SYNC_LAG = "deflect_sync_lag"
    DEFLECT_VIEW_FILTERS = "deflect_view_filters"
    DEFLECT_HISTORICAL_DATA_LOGIC = "deflect_historical_data_logic"
    ROUTE_FINANCE = "route_finance"
    ROUTE_CRC_L3 = "route_crc_l3"
    ROUTE_DATA_QUALITY = "route_data_quality"
    DEFLECT_INTENDED_BEHAVIOR = "deflect_intended_behavior"
    ASK_ROUTING_CLARIFICATION = "ask_routing_clarification"
    WAIT_FOR_FIX = "wait_for_fix"
    ASK_REPORTER_TO_CONFIRM = "ask_reporter_to_confirm"
    CLOSE_AS_RESOLVED = "close_as_resolved"
    ESCALATE_HUMAN_REVIEW = "escalate_human_review"


class TemplateProposalType(str, Enum):
    ADD_PRIMARY_CATEGORY = "add_primary_category"
    ADD_APPLICATION_ISSUE_SUBCATEGORY = "add_application_issue_subcategory"
    ADD_STATE = "add_state"
    ADD_EVENT = "add_event"
    ADD_ACTION_TYPE = "add_action_type"
    ADD_TRANSITION_RULE = "add_transition_rule"
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
    source_system: str | None = None
    comparison_system: str | None = None
    po_numbers: list[str] = Field(default_factory=list)
    project_codes: list[str] = Field(default_factory=list)
    document_links: list[str] = Field(default_factory=list)


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


class HierarchyClassification(BaseModel):
    """Result of traversing the classification hierarchy to a leaf node."""

    routing_team: RoutingTeam
    issue_type: str
    path: list[str] = Field(default_factory=list)
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
    phase: TriagePhase | None = None
    actions: list[str] = Field(default_factory=list)
    next_states: list[str] = Field(default_factory=list)


class StateTransitionRule(BaseModel):
    from_state: TriageState
    event: TriageEvent
    to_state: TriageState
    action_type: ActionType
    rule_id: str
    description: str


class StateMachineTemplate(BaseModel):
    version: str
    name: str
    description: str
    states: dict[str, StateDefinition]
    phases: list[TriagePhase] = Field(default_factory=list)
    events: list[TriageEvent] = Field(default_factory=list)
    action_types: list[ActionType] = Field(default_factory=list)
    transitions: list[StateTransitionRule] = Field(default_factory=list)
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
    comment_template: str | None = None
    next_assignee: str | None = None
    target: str | None = None
    rule_id: str | None = None
    comment: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool = True


class AuditEntry(BaseModel):
    event: TriageEvent
    from_state: TriageState
    to_state: TriageState
    action_type: ActionType
    rule_id: str
    reason: str


class TriageOutput(BaseModel):
    issue_id: str
    state: str
    phase: TriagePhase = TriagePhase.EXCEPTION
    last_event: TriageEvent | None = None
    allowed_next_events: list[TriageEvent] = Field(default_factory=list)
    primary_category: PrimaryCategory
    subcategory: ApplicationIssueSubcategory | None = None
    extracted_entities: ExtractedEntities
    missing_fields: list[MissingField] = Field(default_factory=list)
    duplicate_candidates: list[DuplicateCandidate] = Field(default_factory=list)
    recommended_action: RecommendedAction
    confidence: float = Field(ge=0.0, le=1.0)
    audit_evidence: list[str] = Field(default_factory=list)
    audit: list[AuditEntry] = Field(default_factory=list)
    module_path: list[str] = Field(default_factory=list)
    module_state: str | None = None
    route_target: str | None = None
    route_rule_id: str | None = None
    deflection_rule_id: str | None = None


class TemplateEvolutionProposal(BaseModel):
    proposal_type: TemplateProposalType
    title: str
    rationale: str
    evidence_ticket_ids: list[str] = Field(default_factory=list)
    proposed_change: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_approval: Literal[True] = True
