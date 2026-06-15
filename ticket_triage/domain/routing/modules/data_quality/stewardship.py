"""Data-stewardship route skill for data quality tickets."""

from __future__ import annotations

from ticket_triage.domain.routing.criteria import contains_any, ticket_text
from ticket_triage.domain.routing.models import RouteContext, RouteDecision, RouteOutcome
from ticket_triage.schema import (
    ActionType,
    AuditEntry,
    RecommendedAction,
    TriageEvent,
    TriagePhase,
    TriageState,
)


class DataStewardshipModule:
    module_id = "data_stewardship"
    route_rule_id = "data_quality_stewardship_route"
    route_target = "data_quality_team"
    keywords = ["data entry", "merge", "void", "configuration", "missing record", "missing po"]

    def evaluate(self, context: RouteContext, parent_path: list[str]) -> RouteDecision | None:
        if not contains_any(ticket_text(context.ticket), self.keywords):
            return None

        reason = "Validated data quality issue involves direct remediation or data stewardship."
        action = RecommendedAction(
            action_type=ActionType.ROUTE_TO_TEAM,
            state=TriageState.ROUTED_TO_TEAM.value,
            team=self.route_target,
            target=self.route_target,
            rule_id=self.route_rule_id,
            comment_template="route_data_quality",
            comment=reason,
            confidence=0.82,
        )
        return RouteDecision(
            outcome=RouteOutcome.ROUTE_TO_TEAM,
            phase=TriagePhase.ROUTING,
            state=TriageState.ROUTED_TO_TEAM,
            last_event=TriageEvent.ROUTE_MATCHED,
            action_type=ActionType.ROUTE_TO_TEAM,
            module_path=[*parent_path, self.module_id],
            module_state="route_matched",
            recommended_action=action,
            route_target=self.route_target,
            route_rule_id=self.route_rule_id,
            confidence=0.82,
            audit_evidence=[reason],
            audit=[
                AuditEntry(
                    event=TriageEvent.ROUTE_MATCHED,
                    from_state=TriageState.ROUTE_DECISION,
                    to_state=TriageState.ROUTED_TO_TEAM,
                    action_type=ActionType.ROUTE_TO_TEAM,
                    rule_id=self.route_rule_id,
                    reason=reason,
                )
            ],
        )
