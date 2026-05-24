"""Required field evaluation and action recommendation."""

from __future__ import annotations

from ticket_triage.domain.classification import classify_ticket
from ticket_triage.domain.duplicates import find_similar_tickets
from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.loading import load_state_machine
from ticket_triage.domain.parsing import coerce_ticket
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


def _text(ticket: Ticket) -> str:
    comments = " ".join(comment.body for comment in ticket.comments)
    return f"{ticket.title} {ticket.description} {comments}".lower()


def _missing_data_quality_context(entities: ExtractedEntities) -> list[MissingField]:
    missing: list[MissingField] = []
    if _is_missing(entities, "issue_description"):
        missing.append(
            MissingField(
                field="issue_summary",
                label="Issue summary",
                prompt="Please describe the data discrepancy or requested correction.",
            )
        )
    if _is_missing(entities, "source_system"):
        missing.append(
            MissingField(
                field="source_system",
                label="Source system",
                prompt="Please provide the source system, such as SAP, Quickbase, BuyingHub, or eBuilder.",
            )
        )
    evidence_satisfied = bool(
        entities.po_numbers
        or entities.project_codes
        or entities.document_links
        or entities.affected_link
        or entities.screenshot_provided
    )
    if not evidence_satisfied:
        missing.append(
            MissingField(
                field="diagnostic_evidence",
                label="Diagnostic evidence",
                prompt=(
                    "Please provide at least one PO number, project ID/S-code, "
                    "linked report, or screenshot."
                ),
            )
        )
    return missing


def _first_missing_context_event(missing_fields: list[MissingField]) -> TriageEvent:
    fields = [field.field for field in missing_fields]
    if "issue_summary" in fields:
        return TriageEvent.ISSUE_SUMMARY_MISSING
    if "source_system" in fields:
        return TriageEvent.SOURCE_SYSTEM_MISSING
    return TriageEvent.DIAGNOSTIC_EVIDENCE_MISSING


def _request_context_action_type(event: TriageEvent) -> ActionType:
    if event == TriageEvent.ISSUE_SUMMARY_MISSING:
        return ActionType.REQUEST_ISSUE_SUMMARY
    if event == TriageEvent.SOURCE_SYSTEM_MISSING:
        return ActionType.REQUEST_SOURCE_SYSTEM
    if event == TriageEvent.DIAGNOSTIC_EVIDENCE_MISSING:
        return ActionType.REQUEST_DIAGNOSTIC_EVIDENCE
    return ActionType.REQUEST_MISSING_CONTEXT


def _data_quality_deflection(text: str) -> tuple[TriageEvent, ActionType, str] | None:
    if any(term in text for term in ["sync lag", "batch sync", "sync delay"]):
        return (
            TriageEvent.EXTERNAL_SYNC_LAG_DETECTED,
            ActionType.DEFLECT_SYNC_LAG,
            "The discrepancy appears consistent with documented external batch sync delay behavior.",
        )
    if any(term in text for term in ["filter", "dashboard view", "view mismatch", "applied filters"]):
        return (
            TriageEvent.APP_VIEW_FILTER_MISMATCH_DETECTED,
            ActionType.DEFLECT_VIEW_FILTERS,
            "The discrepancy appears consistent with dashboard or view filter differences.",
        )
    if any(term in text for term in ["tly", "prior year", "historical", "archival"]):
        return (
            TriageEvent.HISTORICAL_DATA_LOGIC_DETECTED,
            ActionType.DEFLECT_HISTORICAL_DATA_LOGIC,
            "The discrepancy appears consistent with documented historical data logic.",
        )
    return None


def _data_quality_route(text: str) -> tuple[TriageState, TriageEvent, ActionType, str, str]:
    if any(term in text for term in ["accrual", "currency", "fx rate", "financial policy", "sap financial"]):
        return (
            TriageState.ROUTED_FINANCE,
            TriageEvent.FINANCE_POLICY_ISSUE_DETECTED,
            ActionType.ROUTE_FINANCE,
            "finance_queue",
            "Validated data quality issue involves finance policy, currency, FX, accrual, or SAP financial record alignment.",
        )
    if any(term in text for term in ["sync failure", "pipeline", "integration", "sap-to-quickbase", "crash"]):
        return (
            TriageState.ROUTED_CRC_L3,
            TriageEvent.INTEGRATION_ISSUE_DETECTED,
            ActionType.ROUTE_CRC_L3,
            "crc_l3_support",
            "Validated data quality issue involves sync, pipeline, integration, or complex application logic.",
        )
    if any(term in text for term in ["data entry", "merge", "void", "configuration", "missing record", "missing po"]):
        return (
            TriageState.ROUTED_DATA_QUALITY,
            TriageEvent.DATA_STEWARDSHIP_ISSUE_DETECTED,
            ActionType.ROUTE_DATA_QUALITY,
            "data_quality_team",
            "Validated data quality issue involves direct remediation or data stewardship.",
        )
    return (
        TriageState.HUMAN_REVIEW,
        TriageEvent.ROUTING_UNCLEAR,
        ActionType.ESCALATE_HUMAN_REVIEW,
        "app-support-triage",
        "Context is valid, but the rulebook does not identify a confident route.",
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
    text = _text(ticket)
    context_missing = _missing_data_quality_context(entities)

    if context_missing:
        event = _first_missing_context_event(context_missing)
        action_type = _request_context_action_type(event)
        action = RecommendedAction(
            action_type=action_type,
            state=TriageState.MISSING_INFO.value,
            next_assignee="reporter",
            comment_template={
                TriageEvent.ISSUE_SUMMARY_MISSING: "ask_for_issue_summary",
                TriageEvent.SOURCE_SYSTEM_MISSING: "ask_for_source_system",
                TriageEvent.DIAGNOSTIC_EVIDENCE_MISSING: "ask_for_evidence",
            }.get(event, "ask_for_missing_context"),
            comment=_clarification_comment(context_missing),
            confidence=0.9,
        )
        reason = "Minimum viable context is not satisfied."
        return TriageOutput(
            issue_id=ticket.issue_id,
            phase=TriagePhase.CONTEXT_VALIDATION,
            state=TriageState.MISSING_INFO.value,
            last_event=event,
            allowed_next_events=_allowed_next_events(TriageState.MISSING_INFO),
            primary_category=PrimaryCategory.APPLICATION_ISSUE,
            subcategory=ApplicationIssueSubcategory.DATA_QUALITY_ISSUE,
            extracted_entities=entities,
            missing_fields=context_missing,
            duplicate_candidates=[],
            recommended_action=action,
            confidence=round((classification_confidence + action.confidence) / 2, 3),
            audit_evidence=[reason],
            audit=_audit(
                event=event,
                from_state=TriageState.EXTRACTING_CONTEXT,
                to_state=TriageState.MISSING_INFO,
                action_type=action_type,
                rule_id="data_quality.minimum_viable_context",
                reason=reason,
            ),
        )

    deflection = _data_quality_deflection(text)
    if deflection:
        event, action_type, reason = deflection
        action = RecommendedAction(
            action_type=action_type,
            state=TriageState.INTENDED_BEHAVIOR.value,
            team="app-support-triage",
            comment_template=action_type.value,
            comment=(
                f"{reason} Draft a response explaining the expected behavior and "
                "ask the reporter to confirm whether this resolves the ticket."
            ),
            confidence=0.84,
        )
        return TriageOutput(
            issue_id=ticket.issue_id,
            phase=TriagePhase.DEFLECTION,
            state=TriageState.INTENDED_BEHAVIOR.value,
            last_event=event,
            allowed_next_events=[TriageEvent.EXPLANATION_SENT, TriageEvent.HUMAN_OVERRIDE],
            primary_category=PrimaryCategory.APPLICATION_ISSUE,
            subcategory=ApplicationIssueSubcategory.DATA_QUALITY_ISSUE,
            extracted_entities=entities,
            missing_fields=[],
            duplicate_candidates=[],
            recommended_action=action,
            confidence=round((classification_confidence + action.confidence) / 2, 3),
            audit_evidence=[reason],
            audit=_audit(
                event=event,
                from_state=TriageState.CHECKING_KNOWN_BEHAVIOR,
                to_state=TriageState.INTENDED_BEHAVIOR,
                action_type=action_type,
                rule_id="data_quality.known_behavior_deflection",
                reason=reason,
            ),
        )

    state, event, action_type, team, reason = _data_quality_route(text)
    action = RecommendedAction(
        action_type=action_type,
        state=state.value,
        team=team,
        comment_template=action_type.value,
        comment=reason,
        confidence=0.82 if state != TriageState.HUMAN_REVIEW else 0.64,
    )
    return TriageOutput(
        issue_id=ticket.issue_id,
        phase=TriagePhase.ROUTING if state != TriageState.HUMAN_REVIEW else TriagePhase.EXCEPTION,
        state=state.value,
        last_event=event,
        allowed_next_events=_allowed_next_events(state),
        primary_category=PrimaryCategory.APPLICATION_ISSUE,
        subcategory=ApplicationIssueSubcategory.DATA_QUALITY_ISSUE,
        extracted_entities=entities,
        missing_fields=[],
        duplicate_candidates=[],
        recommended_action=action,
        confidence=round((classification_confidence + action.confidence) / 2, 3),
        audit_evidence=["Minimum viable context is satisfied.", reason],
        audit=_audit(
            event=event,
            from_state=TriageState.ROUTING_REVIEW,
            to_state=state,
            action_type=action_type,
            rule_id="data_quality.routing",
            reason=reason,
        ),
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
