"""Required field evaluation and action recommendation."""

from __future__ import annotations

from ticket_triage.domain.classification import classify_ticket
from ticket_triage.domain.duplicates import find_similar_tickets
from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.loading import load_state_machine
from ticket_triage.domain.parsing import coerce_ticket
from ticket_triage.domain.routing import RouteContext, route_ticket
from ticket_triage.schema import (
    ActionType,
    ApplicationIssueSubcategory,
    AuditEntry,
    DuplicateCandidate,
    ExtractedEntities,
    MissingField,
    PrimaryCategory,
    RecommendedAction,
    StateMachineTemplate,
    Ticket,
    TriageEvent,
    TriageOutput,
    TriagePhase,
    TriageState,
)


def _is_missing(entities: ExtractedEntities, field: str) -> bool:
    value = getattr(entities, field, None)
    if isinstance(value, bool):
        return not value
    if isinstance(value, list):
        return len(value) == 0
    return value is None or str(value).strip() == ""


def evaluate_required_fields(
    primary_category: PrimaryCategory | str,
    subcategory: ApplicationIssueSubcategory | str | None,
    entities: ExtractedEntities | dict,
    template: StateMachineTemplate | None = None,
) -> list[MissingField]:
    """Evaluate required fields from primary and subcategory templates."""

    parsed_template = template or load_state_machine()
    parsed_entities = (
        ExtractedEntities.model_validate(entities) if isinstance(entities, dict) else entities
    )
    parsed_category = PrimaryCategory(primary_category)
    parsed_subcategory = ApplicationIssueSubcategory(subcategory) if subcategory else None

    rules = list(parsed_template.primary_categories[parsed_category].required_fields)
    if parsed_category == PrimaryCategory.APPLICATION_ISSUE and parsed_subcategory:
        rules.extend(
            parsed_template.application_issue_subcategories[parsed_subcategory].required_fields
        )

    missing: list[MissingField] = []
    for rule in rules:
        if _is_missing(parsed_entities, rule.field):
            missing.append(
                MissingField(field=rule.field, label=rule.label, prompt=rule.prompt)
            )
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
    primary_category: PrimaryCategory | str,
    subcategory: ApplicationIssueSubcategory | str | None,
    entities: ExtractedEntities | dict,
    missing_fields: list[MissingField] | list[dict],
    duplicates: list[DuplicateCandidate] | list[dict],
    template: StateMachineTemplate | None = None,
) -> RecommendedAction:
    """Recommend the next copilot action. V1 always requires human review."""

    parsed_template = template or load_state_machine()
    parsed_category = PrimaryCategory(primary_category)
    parsed_subcategory = ApplicationIssueSubcategory(subcategory) if subcategory else None
    parsed_missing = [MissingField.model_validate(item) for item in missing_fields]
    parsed_duplicates = [DuplicateCandidate.model_validate(item) for item in duplicates]

    strong_duplicate = parsed_duplicates[0] if parsed_duplicates and parsed_duplicates[0].score >= 0.74 else None
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

    if parsed_category == PrimaryCategory.INTENDED_BEHAVIOR:
        return RecommendedAction(
            action_type=ActionType.EXPLAIN_INTENDED_BEHAVIOR,
            state=TriageState.INTENDED_BEHAVIOR.value,
            team="app-support-triage",
            comment_template="explain_intended_behavior",
            comment=(
                "This appears to be expected application behavior. Draft a support "
                "reply explaining the intended behavior and offer to open a feature "
                "request if the workflow should change."
            ),
            confidence=0.84,
        )

    if parsed_category == PrimaryCategory.FEATURE_REQUEST:
        hint = parsed_template.primary_categories[parsed_category].routing_hint
        return RecommendedAction(
            action_type=ActionType.PRODUCT_REVIEW,
            state=TriageState.ROUTED_PRODUCT_REVIEW.value,
            team=hint.team if hint else "product-owner-review",
            comment_template="route_to_product_review",
            comment=(
                "This appears to be a feature request. Route to product owner review "
                "with the requested capability, business reason, and urgency."
            ),
            confidence=0.82,
        )

    if parsed_category == PrimaryCategory.APPLICATION_ISSUE and parsed_subcategory:
        hint = parsed_template.application_issue_subcategories[parsed_subcategory].routing_hint
        return RecommendedAction(
            action_type=ActionType.ROUTE_TO_TEAM,
            state=TriageState.ROUTED_APPLICATION_SUPPORT.value,
            team=hint.team if hint else "app-support-triage",
            comment_template="route_application_issue",
            comment=(
                f"This is an application issue classified as {parsed_subcategory.value}. "
                f"Route to {hint.team if hint else 'app-support-triage'} for investigation."
            ),
            confidence=0.83,
        )

    hint = parsed_template.primary_categories[parsed_category].routing_hint
    return RecommendedAction(
        action_type=ActionType.ROUTE_TO_TEAM if hint else ActionType.HUMAN_REVIEW,
        state=TriageState.HUMAN_REVIEW.value,
        team=hint.team if hint else "app-support-triage",
        comment_template="route_or_review",
        comment=(
            f"This ticket is classified as {parsed_category.value}. "
            f"Route to {hint.team if hint else 'app-support-triage'} for human review."
        ),
        confidence=0.78,
    )


def _triage_data_quality_ticket(
    ticket: Ticket,
    entities: ExtractedEntities,
    classification_confidence: float,
) -> TriageOutput:
    route_decision = route_ticket(
        RouteContext(
            ticket=ticket,
            primary_category=PrimaryCategory.APPLICATION_ISSUE,
            subcategory=ApplicationIssueSubcategory.DATA_QUALITY_ISSUE,
            entities=entities,
            classification_confidence=classification_confidence,
        )
    )
    if route_decision is None:
        raise RuntimeError("No route module registered for data_quality_issue.")

    return TriageOutput(
        issue_id=ticket.issue_id,
        phase=route_decision.phase,
        state=route_decision.state.value,
        last_event=route_decision.last_event,
        allowed_next_events=_allowed_next_events(route_decision.state),
        primary_category=PrimaryCategory.APPLICATION_ISSUE,
        subcategory=ApplicationIssueSubcategory.DATA_QUALITY_ISSUE,
        extracted_entities=entities,
        missing_fields=route_decision.missing_fields,
        duplicate_candidates=[],
        recommended_action=route_decision.recommended_action,
        confidence=round((classification_confidence + route_decision.confidence) / 2, 3),
        audit_evidence=route_decision.audit_evidence,
        audit=route_decision.audit,
        module_path=route_decision.module_path,
        module_state=route_decision.module_state,
        route_target=route_decision.route_target,
        route_rule_id=route_decision.route_rule_id,
        deflection_rule_id=route_decision.deflection_rule_id,
    )


def triage_ticket(ticket: str | dict | Ticket) -> TriageOutput:
    """Run the deterministic triage pipeline for one ticket."""

    parsed_ticket = coerce_ticket(ticket)
    template = load_state_machine()
    entities = extract_entities(parsed_ticket)
    classification = classify_ticket(parsed_ticket, entities)
    duplicates = find_similar_tickets(parsed_ticket)

    if (
        classification.primary_category == PrimaryCategory.APPLICATION_ISSUE
        and classification.subcategory == ApplicationIssueSubcategory.DATA_QUALITY_ISSUE
    ):
        return _triage_data_quality_ticket(
            parsed_ticket,
            entities,
            classification.confidence,
        )

    missing = evaluate_required_fields(
        classification.primary_category,
        classification.subcategory,
        entities,
        template,
    )
    action = recommend_next_action(
        parsed_ticket,
        classification.primary_category,
        classification.subcategory,
        entities,
        missing,
        duplicates,
        template,
    )
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
    elif classification.primary_category == PrimaryCategory.ACCESS_REQUEST:
        phase = TriagePhase.ROUTING
        state = TriageState.READY_FOR_ACCESS_REVIEW
        event = TriageEvent.REQUIRED_FIELDS_EXTRACTED
    elif classification.primary_category == PrimaryCategory.FEATURE_REQUEST:
        phase = TriagePhase.ROUTING
        state = TriageState.ROUTED_PRODUCT_REVIEW
        event = TriageEvent.ROUTING_UNCLEAR
    elif classification.primary_category == PrimaryCategory.INTENDED_BEHAVIOR:
        phase = TriagePhase.DEFLECTION
        state = TriageState.INTENDED_BEHAVIOR
        event = TriageEvent.KNOWN_BEHAVIOR_CHECK_STARTED
    elif classification.primary_category == PrimaryCategory.APPLICATION_ISSUE:
        phase = TriagePhase.ROUTING
        state = TriageState.ROUTED_APPLICATION_SUPPORT
        event = TriageEvent.KNOWN_BEHAVIOR_NOT_MATCHED

    if duplicates:
        evidence.append(f"Top duplicate candidate: {duplicates[0].issue_id} ({duplicates[0].score:.2f}).")
    if missing:
        evidence.append(f"Missing required fields: {', '.join(field.field for field in missing)}.")

    return TriageOutput(
        issue_id=parsed_ticket.issue_id,
        phase=phase,
        state=state.value,
        last_event=event,
        allowed_next_events=_allowed_next_events(state),
        primary_category=classification.primary_category,
        subcategory=classification.subcategory,
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
            rule_id=f"{classification.primary_category.value}.state_transition",
            reason="Selected next state and action from the category rulebook.",
        ),
    )
