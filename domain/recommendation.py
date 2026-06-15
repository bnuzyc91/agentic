"""Required field evaluation and action recommendation."""

from __future__ import annotations

from ticket_triage.domain.duplicates import find_similar_tickets
from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.hierarchy.registry import get_rulebook, traverse
from ticket_triage.domain.parsing import coerce_ticket
from ticket_triage.schema import (
    ActionType,
    ApplicationIssueSubcategory,
    AuditEntry,
    DuplicateCandidate,
    ExtractedEntities,
    HierarchyClassification,
    MissingField,
    PrimaryCategory,
    RecommendedAction,
    RoutingTeam,
    Ticket,
    TriageEvent,
    TriageOutput,
    TriagePhase,
    TriageState,
)

# Maps hierarchy leaf → (PrimaryCategory, subcategory) for backward-compat TriageOutput fields.
_HIERARCHY_TO_PRIMARY: dict[
    tuple[str, str], tuple[PrimaryCategory, ApplicationIssueSubcategory | None]
] = {
    ("app_support", "access_request"): (PrimaryCategory.ACCESS_REQUEST, None),
    ("app_support", "integration_issue"): (
        PrimaryCategory.APPLICATION_ISSUE, ApplicationIssueSubcategory.INTEGRATION_ISSUE,
    ),
    ("app_support", "ui_workflow_issue"): (
        PrimaryCategory.APPLICATION_ISSUE, ApplicationIssueSubcategory.UI_WORKFLOW_ISSUE,
    ),
    ("finance_platform", "budget_variance_issue"): (
        PrimaryCategory.APPLICATION_ISSUE, ApplicationIssueSubcategory.BUDGET_VARIANCE_ISSUE,
    ),
    ("finance_platform", "report_performance_issue"): (
        PrimaryCategory.APPLICATION_ISSUE, ApplicationIssueSubcategory.REPORT_PERFORMANCE_ISSUE,
    ),
    ("finance_platform", "forecast_discrepancy"): (PrimaryCategory.APPLICATION_ISSUE, None),
    ("data_engineering", "data_quality_issue"): (
        PrimaryCategory.APPLICATION_ISSUE, ApplicationIssueSubcategory.DATA_QUALITY_ISSUE,
    ),
    ("data_engineering", "pipeline_failure"): (PrimaryCategory.APPLICATION_ISSUE, None),
    ("data_engineering", "schema_change"): (PrimaryCategory.APPLICATION_ISSUE, None),
}


def _to_primary(
    classification: HierarchyClassification,
) -> tuple[PrimaryCategory, ApplicationIssueSubcategory | None]:
    key = (classification.routing_team.value, classification.issue_type)
    return _HIERARCHY_TO_PRIMARY.get(key, (PrimaryCategory.OTHER_OR_UNKNOWN, None))


def _is_missing(entities: ExtractedEntities, field: str) -> bool:
    value = getattr(entities, field, None)
    if isinstance(value, bool):
        return not value
    if isinstance(value, list):
        return len(value) == 0
    return value is None or str(value).strip() == ""


def evaluate_required_fields(
    classification: HierarchyClassification,
    entities: ExtractedEntities | dict,
) -> list[MissingField]:
    """Return required fields missing for the matched hierarchy leaf."""
    parsed_entities = (
        ExtractedEntities.model_validate(entities) if isinstance(entities, dict) else entities
    )
    rulebook = get_rulebook(classification.routing_team, classification.issue_type)
    if rulebook is None:
        return []
    missing: list[MissingField] = []
    for rule in rulebook.required_fields:
        if _is_missing(parsed_entities, rule.field):
            missing.append(MissingField(field=rule.field, label=rule.label, prompt=rule.prompt))
    return missing


def _clarification_comment(missing_fields: list[MissingField]) -> str:
    requested = "\n".join(f"- {field.label}: {field.prompt}" for field in missing_fields)
    return (
        "Thanks for the ticket. To route this correctly, please provide the missing "
        f"information below:\n{requested}"
    )


def _allowed_next_events(state: TriageState) -> list[TriageEvent]:
    mapping: dict[TriageState, list[TriageEvent]] = {
        TriageState.NEW: [TriageEvent.CONTEXT_EXTRACTION_STARTED],
        TriageState.EXTRACTING_CONTEXT: [
            TriageEvent.ISSUE_SUMMARY_MISSING,
            TriageEvent.SOURCE_SYSTEM_MISSING,
            TriageEvent.DIAGNOSTIC_EVIDENCE_MISSING,
            TriageEvent.MINIMUM_CONTEXT_SATISFIED,
        ],
        TriageState.ROUTE_DECISION: [
            TriageEvent.ISSUE_SUMMARY_MISSING,
            TriageEvent.SOURCE_SYSTEM_MISSING,
            TriageEvent.DIAGNOSTIC_EVIDENCE_MISSING,
            TriageEvent.EXTERNAL_SYNC_LAG_DETECTED,
            TriageEvent.APP_VIEW_FILTER_MISMATCH_DETECTED,
            TriageEvent.HISTORICAL_DATA_LOGIC_DETECTED,
            TriageEvent.ROUTE_MATCHED,
            TriageEvent.ROUTING_UNCLEAR,
        ],
        TriageState.MISSING_INFO: [
            TriageEvent.REPORTER_PROVIDED_MISSING_INFO,
            TriageEvent.INACTIVITY_TIMEOUT_REACHED,
            TriageEvent.HUMAN_OVERRIDE,
        ],
        TriageState.CONTEXT_VALIDATED: [TriageEvent.KNOWN_BEHAVIOR_CHECK_STARTED],
        TriageState.CHECKING_KNOWN_BEHAVIOR: [
            TriageEvent.EXTERNAL_SYNC_LAG_DETECTED,
            TriageEvent.APP_VIEW_FILTER_MISMATCH_DETECTED,
            TriageEvent.HISTORICAL_DATA_LOGIC_DETECTED,
            TriageEvent.KNOWN_BEHAVIOR_NOT_MATCHED,
        ],
        TriageState.ROUTING_REVIEW: [
            TriageEvent.FINANCE_POLICY_ISSUE_DETECTED,
            TriageEvent.INTEGRATION_ISSUE_DETECTED,
            TriageEvent.DATA_STEWARDSHIP_ISSUE_DETECTED,
            TriageEvent.ROUTING_UNCLEAR,
        ],
        TriageState.ROUTED_TO_TEAM: [
            TriageEvent.FIX_APPLIED,
            TriageEvent.REPORTER_REPORTS_NOT_RESOLVED,
            TriageEvent.HUMAN_OVERRIDE,
        ],
        TriageState.WAITING_REPORTER_CONFIRMATION: [
            TriageEvent.REPORTER_CONFIRMED_RESOLVED,
            TriageEvent.REPORTER_REPORTS_NOT_RESOLVED,
            TriageEvent.INACTIVITY_TIMEOUT_REACHED,
        ],
    }
    return mapping.get(state, [TriageEvent.HUMAN_OVERRIDE])


def _audit(
    *,
    event: TriageEvent,
    from_state: TriageState,
    to_state: TriageState,
    action_type: ActionType,
    rule_id: str,
    reason: str,
) -> list[AuditEntry]:
    return [
        AuditEntry(
            event=event,
            from_state=from_state,
            to_state=to_state,
            action_type=action_type,
            rule_id=rule_id,
            reason=reason,
        )
    ]


def recommend_next_action(
    ticket: str | dict | Ticket,
    classification: HierarchyClassification,
    entities: ExtractedEntities | dict,
    missing_fields: list[MissingField] | list[dict],
    duplicates: list[DuplicateCandidate] | list[dict],
) -> RecommendedAction:
    """Recommend the next copilot action based on hierarchy classification."""
    parsed_missing = [MissingField.model_validate(item) for item in missing_fields]
    parsed_duplicates = [DuplicateCandidate.model_validate(item) for item in duplicates]

    strong_duplicate = (
        parsed_duplicates[0]
        if parsed_duplicates and parsed_duplicates[0].score >= 0.74
        else None
    )
    if strong_duplicate:
        return RecommendedAction(
            action_type=ActionType.SUGGEST_DUPLICATE_REVIEW,
            state=TriageState.DUPLICATE_REVIEW.value,
            team="app-support-triage",
            comment_template="suggest_duplicate_review",
            comment=(
                f"This ticket may duplicate {strong_duplicate.issue_id} "
                f"('{strong_duplicate.title}'). Please review the match before closing."
            ),
            confidence=strong_duplicate.score,
        )

    if parsed_missing:
        return RecommendedAction(
            action_type=ActionType.ASK_FOR_INFO,
            state=TriageState.MISSING_INFO.value,
            next_assignee="reporter",
            comment_template="ask_for_missing_info",
            comment=_clarification_comment(parsed_missing),
            confidence=0.88,
        )

    rulebook = get_rulebook(classification.routing_team, classification.issue_type)
    if rulebook is not None:
        hint = rulebook.routing_hint
        return RecommendedAction(
            action_type=ActionType.ROUTE_TO_TEAM,
            state=TriageState.ROUTED_TO_TEAM.value,
            team=hint.team,
            comment_template="route_to_team",
            comment=(
                f"Classified as {classification.routing_team.value}/{classification.issue_type}. "
                f"Route to {hint.team}: {hint.reason}"
            ),
            confidence=round(classification.confidence, 3),
        )

    return RecommendedAction(
        action_type=ActionType.HUMAN_REVIEW,
        state=TriageState.HUMAN_REVIEW.value,
        team="app-support-triage",
        comment_template="route_or_review",
        comment=(
            f"Classification unclear (team: {classification.routing_team.value}). "
            "Route to app-support-triage for human review."
        ),
        confidence=0.78,
    )


def triage_ticket(ticket: str | dict | Ticket) -> TriageOutput:
    """Run the deterministic triage pipeline for one ticket."""
    parsed_ticket = coerce_ticket(ticket)
    entities = extract_entities(parsed_ticket)
    classification, route_decision = traverse(parsed_ticket, entities)
    duplicates = find_similar_tickets(parsed_ticket)
    primary_category, subcategory = _to_primary(classification)

    # Leaves with internal state machines (e.g. DataQualityRouteModule) encode
    # MISSING_INFO and INTENDED_BEHAVIOR themselves — honour their decision directly.
    if route_decision is not None and route_decision.state in {
        TriageState.MISSING_INFO,
        TriageState.INTENDED_BEHAVIOR,
    }:
        evidence = list(classification.evidence) + list(route_decision.audit_evidence)
        if duplicates:
            evidence.append(
                f"Top duplicate candidate: {duplicates[0].issue_id} ({duplicates[0].score:.2f})."
            )
        return TriageOutput(
            issue_id=parsed_ticket.issue_id,
            phase=route_decision.phase,
            state=route_decision.state.value,
            last_event=route_decision.last_event,
            allowed_next_events=_allowed_next_events(route_decision.state),
            primary_category=primary_category,
            subcategory=subcategory,
            extracted_entities=entities,
            missing_fields=route_decision.missing_fields,
            duplicate_candidates=duplicates,
            recommended_action=route_decision.recommended_action,
            confidence=round((classification.confidence + route_decision.confidence) / 2, 3),
            audit_evidence=evidence,
            audit=route_decision.audit,
            module_path=route_decision.module_path,
            module_state=route_decision.module_state,
            route_target=route_decision.route_target,
            route_rule_id=route_decision.route_rule_id,
            deflection_rule_id=route_decision.deflection_rule_id,
        )

    # Standard path: duplicates > missing fields > leaf route > human review
    missing = evaluate_required_fields(classification, entities)
    action = recommend_next_action(parsed_ticket, classification, entities, missing, duplicates)

    evidence = list(classification.evidence)
    phase = TriagePhase.EXCEPTION
    state = TriageState.HUMAN_REVIEW
    event = TriageEvent.HUMAN_OVERRIDE
    from_state = TriageState.ROUTING_REVIEW

    if missing:
        phase = TriagePhase.CONTEXT_VALIDATION
        state = TriageState.MISSING_INFO
        event = TriageEvent.MISSING_REQUIRED_FIELDS_DETECTED
        from_state = TriageState.EXTRACTING_CONTEXT
    elif duplicates and duplicates[0].score >= 0.74:
        phase = TriagePhase.ROUTING
        state = TriageState.DUPLICATE_REVIEW
        event = TriageEvent.DUPLICATE_CANDIDATE_FOUND
    elif (
        classification.routing_team == RoutingTeam.APP_SUPPORT
        and classification.issue_type == "access_request"
    ):
        phase = TriagePhase.ROUTING
        state = TriageState.READY_FOR_ACCESS_REVIEW
        event = TriageEvent.REQUIRED_FIELDS_EXTRACTED
    elif route_decision is not None:
        phase = route_decision.phase
        state = route_decision.state
        event = route_decision.last_event or TriageEvent.ROUTE_MATCHED
        from_state = TriageState.ROUTE_DECISION

    if duplicates:
        evidence.append(
            f"Top duplicate candidate: {duplicates[0].issue_id} ({duplicates[0].score:.2f})."
        )
    if missing:
        evidence.append(f"Missing required fields: {', '.join(f.field for f in missing)}.")

    module_path = route_decision.module_path if route_decision else []
    module_state_val = route_decision.module_state if route_decision else None
    route_target = route_decision.route_target if route_decision else None
    route_rule_id = route_decision.route_rule_id if route_decision else None

    return TriageOutput(
        issue_id=parsed_ticket.issue_id,
        phase=phase,
        state=state.value,
        last_event=event,
        allowed_next_events=_allowed_next_events(state),
        primary_category=primary_category,
        subcategory=subcategory,
        extracted_entities=entities,
        missing_fields=missing,
        duplicate_candidates=duplicates,
        recommended_action=action,
        confidence=round((classification.confidence + action.confidence) / 2, 3),
        audit_evidence=evidence,
        audit=_audit(
            event=event,
            from_state=from_state,
            to_state=state,
            action_type=action.action_type,
            rule_id=f"{classification.routing_team.value}.{classification.issue_type}",
            reason="Selected next state and action from hierarchy rulebook.",
        ),
        module_path=module_path,
        module_state=module_state_val,
        route_target=route_target,
        route_rule_id=route_rule_id,
    )
