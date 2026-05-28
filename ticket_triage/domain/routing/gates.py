"""Reusable gate helpers for route modules."""

from __future__ import annotations

from ticket_triage.domain.routing.criteria import contains_any, ticket_text
from ticket_triage.domain.routing.models import RouteContext, RouteDecision, RouteOutcome
from ticket_triage.schema import (
    ActionType,
    AuditEntry,
    MissingField,
    RecommendedAction,
    TriageEvent,
    TriagePhase,
    TriageState,
)


def is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, set, tuple)):
        return len(value) == 0
    if isinstance(value, bool):
        return not value
    return False


def clarification_comment(missing_fields: list[MissingField]) -> str:
    requested = "\n".join(f"- {field.label}: {field.prompt}" for field in missing_fields)
    return (
        "Thanks for the ticket. To route this correctly, please provide the missing "
        f"information below:\n{requested}"
    )


class ContextGate:
    """Checks required fields and returns a request-information decision if blocked."""

    def __init__(self, module_id: str) -> None:
        self.module_id = module_id

    def evaluate(self, context: RouteContext, missing_fields: list[MissingField]) -> RouteDecision | None:
        if not missing_fields:
            return None

        event = event_for_missing_field(missing_fields[0].field)
        action = RecommendedAction(
            action_type=ActionType.REQUEST_INFORMATION,
            state=TriageState.MISSING_INFO.value,
            next_assignee="reporter",
            comment_template=template_for_missing_field(missing_fields[0].field),
            comment=clarification_comment(missing_fields),
            confidence=0.9,
        )
        reason = "Required route-module context is missing."
        return RouteDecision(
            outcome=RouteOutcome.REQUEST_INFORMATION,
            phase=TriagePhase.CONTEXT_VALIDATION,
            state=TriageState.MISSING_INFO,
            last_event=event,
            action_type=ActionType.REQUEST_INFORMATION,
            module_path=[self.module_id, "context_gate"],
            module_state=f"missing_{missing_fields[0].field}",
            recommended_action=action,
            missing_fields=missing_fields,
            confidence=0.9,
            audit_evidence=[reason],
            audit=[
                AuditEntry(
                    event=event,
                    from_state=TriageState.ROUTE_DECISION,
                    to_state=TriageState.MISSING_INFO,
                    action_type=ActionType.REQUEST_INFORMATION,
                    rule_id=f"{self.module_id}.context_gate",
                    reason=reason,
                )
            ],
        )


def event_for_missing_field(field: str) -> TriageEvent:
    if field == "issue_summary":
        return TriageEvent.ISSUE_SUMMARY_MISSING
    if field == "source_system":
        return TriageEvent.SOURCE_SYSTEM_MISSING
    if field == "diagnostic_evidence":
        return TriageEvent.DIAGNOSTIC_EVIDENCE_MISSING
    return TriageEvent.MISSING_REQUIRED_FIELDS_DETECTED


def template_for_missing_field(field: str) -> str:
    if field == "issue_summary":
        return "ask_for_issue_summary"
    if field == "source_system":
        return "ask_for_source_system"
    if field == "diagnostic_evidence":
        return "ask_for_evidence"
    return "ask_for_missing_context"


def evaluate_deflection_rules(
    *,
    context: RouteContext,
    module_id: str,
    rules: list[dict[str, object]],
) -> RouteDecision | None:
    text = ticket_text(context.ticket)
    for rule in rules:
        keywords = list(rule.get("keywords", []))
        if not contains_any(text, keywords):
            continue

        rule_id = str(rule["id"])
        comment_template = str(rule["comment_template"])
        reason = str(rule["reason"])
        action = RecommendedAction(
            action_type=ActionType.DEFLECT_INTENDED_BEHAVIOR,
            state=TriageState.INTENDED_BEHAVIOR.value,
            team="app-support-triage",
            comment_template=comment_template,
            rule_id=rule_id,
            comment=(
                f"{reason} Draft a response explaining the expected behavior and "
                "ask the reporter to confirm whether this resolves the ticket."
            ),
            confidence=0.84,
        )
        return RouteDecision(
            outcome=RouteOutcome.DEFLECT_INTENDED_BEHAVIOR,
            phase=TriagePhase.DEFLECTION,
            state=TriageState.INTENDED_BEHAVIOR,
            last_event=rule["event"],
            action_type=ActionType.DEFLECT_INTENDED_BEHAVIOR,
            module_path=[module_id, "deflection_gate"],
            module_state="deflection_matched",
            recommended_action=action,
            deflection_rule_id=rule_id,
            confidence=0.84,
            audit_evidence=[reason],
            audit=[
                AuditEntry(
                    event=rule["event"],
                    from_state=TriageState.ROUTE_DECISION,
                    to_state=TriageState.INTENDED_BEHAVIOR,
                    action_type=ActionType.DEFLECT_INTENDED_BEHAVIOR,
                    rule_id=rule_id,
                    reason=reason,
                )
            ],
        )
    return None
