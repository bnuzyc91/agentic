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
    DuplicateCandidate,
    ExtractedEntities,
    MissingField,
    PrimaryCategory,
    RecommendedAction,
    StateMachineTemplate,
    Ticket,
    TriageOutput,
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
            state=parsed_template.final_state,
            team="app-support-triage",
            comment=(
                f"This ticket may duplicate {strong_duplicate.issue_id} "
                f"('{strong_duplicate.title}'). Please review the match before closing."
            ),
            confidence=strong_duplicate.score,
        )

    if parsed_missing:
        return RecommendedAction(
            action_type=ActionType.ASK_FOR_INFO,
            state=parsed_template.final_state,
            comment=_clarification_comment(parsed_missing),
            confidence=0.88,
        )

    if parsed_category == PrimaryCategory.INTENDED_BEHAVIOR:
        return RecommendedAction(
            action_type=ActionType.EXPLAIN_INTENDED_BEHAVIOR,
            state=parsed_template.final_state,
            team="app-support-triage",
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
            state=parsed_template.final_state,
            team=hint.team if hint else "product-owner-review",
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
            state=parsed_template.final_state,
            team=hint.team if hint else "app-support-triage",
            comment=(
                f"This is an application issue classified as {parsed_subcategory.value}. "
                f"Route to {hint.team if hint else 'app-support-triage'} for investigation."
            ),
            confidence=0.83,
        )

    hint = parsed_template.primary_categories[parsed_category].routing_hint
    return RecommendedAction(
        action_type=ActionType.ROUTE_TO_TEAM if hint else ActionType.HUMAN_REVIEW,
        state=parsed_template.final_state,
        team=hint.team if hint else "app-support-triage",
        comment=(
            f"This ticket is classified as {parsed_category.value}. "
            f"Route to {hint.team if hint else 'app-support-triage'} for human review."
        ),
        confidence=0.78,
    )


def triage_ticket(ticket: str | dict | Ticket) -> TriageOutput:
    """Run the deterministic triage pipeline for one ticket."""

    parsed_ticket = coerce_ticket(ticket)
    template = load_state_machine()
    entities = extract_entities(parsed_ticket)
    classification = classify_ticket(parsed_ticket, entities)
    duplicates = find_similar_tickets(parsed_ticket)
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
    if duplicates:
        evidence.append(f"Top duplicate candidate: {duplicates[0].issue_id} ({duplicates[0].score:.2f}).")
    if missing:
        evidence.append(f"Missing required fields: {', '.join(field.field for field in missing)}.")

    return TriageOutput(
        issue_id=parsed_ticket.issue_id,
        state=template.final_state,
        primary_category=classification.primary_category,
        subcategory=classification.subcategory,
        extracted_entities=entities,
        missing_fields=missing,
        duplicate_candidates=duplicates,
        recommended_action=action,
        confidence=round((classification.confidence + action.confidence) / 2, 3),
        audit_evidence=evidence,
    )
