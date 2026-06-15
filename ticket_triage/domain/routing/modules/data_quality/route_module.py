"""Top-level data-quality route module."""

from __future__ import annotations

from ticket_triage.domain.routing.gates import ContextGate, evaluate_deflection_rules, is_missing
from ticket_triage.domain.routing.models import RouteContext, RouteDecision, RouteOutcome
from ticket_triage.domain.routing.modules.data_quality.finance_policy import FinancePolicyModule
from ticket_triage.domain.routing.modules.data_quality.integration import IntegrationModule
from ticket_triage.domain.routing.modules.data_quality.stewardship import DataStewardshipModule
from ticket_triage.schema import (
    ActionType,
    AuditEntry,
    MissingField,
    RecommendedAction,
    TriageEvent,
    TriagePhase,
    TriageState,
)


class DataQualityRouteModule:
    module_id = "data_quality"

    def __init__(self) -> None:
        self.context_gate = ContextGate(self.module_id)
        self.child_modules = [
            FinancePolicyModule(),
            IntegrationModule(),
            DataStewardshipModule(),
        ]
        self.deflection_rules = [
            {
                "id": "external_sync_lag",
                "keywords": ["sync lag", "batch sync", "sync delay"],
                "event": TriageEvent.EXTERNAL_SYNC_LAG_DETECTED,
                "comment_template": "deflect_sync_lag",
                "reason": "The discrepancy appears consistent with documented external batch sync delay behavior.",
            },
            {
                "id": "view_filter_mismatch",
                "keywords": ["filter", "dashboard view", "view mismatch", "applied filters"],
                "event": TriageEvent.APP_VIEW_FILTER_MISMATCH_DETECTED,
                "comment_template": "deflect_view_filters",
                "reason": "The discrepancy appears consistent with dashboard or view filter differences.",
            },
            {
                "id": "historical_data_logic",
                "keywords": ["tly", "prior year", "historical", "archival"],
                "event": TriageEvent.HISTORICAL_DATA_LOGIC_DETECTED,
                "comment_template": "deflect_historical_data_logic",
                "reason": "The discrepancy appears consistent with documented historical data logic.",
            },
        ]

    def evaluate(self, context: RouteContext) -> RouteDecision:
        missing_context = self._missing_context(context)
        context_decision = self.context_gate.evaluate(context, missing_context)
        if context_decision:
            return context_decision

        deflection_decision = evaluate_deflection_rules(
            context=context,
            module_id=self.module_id,
            rules=self.deflection_rules,
        )
        if deflection_decision:
            return deflection_decision

        parent_path = [self.module_id]
        for child_module in self.child_modules:
            decision = child_module.evaluate(context, parent_path)
            if decision:
                return decision

        return self._fallback(context)

    def _missing_context(self, context: RouteContext) -> list[MissingField]:
        entities = context.entities
        missing: list[MissingField] = []
        if is_missing(entities.issue_description):
            missing.append(
                MissingField(
                    field="issue_summary",
                    label="Issue summary",
                    prompt="Please describe the data discrepancy or requested correction.",
                )
            )
        if is_missing(entities.source_system):
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

    def _fallback(self, context: RouteContext) -> RouteDecision:
        reason = "Context is valid, but the data-quality route module did not find a confident child route."
        action = RecommendedAction(
            action_type=ActionType.ESCALATE_HUMAN_REVIEW,
            state=TriageState.HUMAN_REVIEW.value,
            team="app-support-triage",
            comment_template="routing_unclear",
            comment=reason,
            confidence=0.64,
        )
        return RouteDecision(
            outcome=RouteOutcome.ESCALATE_HUMAN_REVIEW,
            phase=TriagePhase.EXCEPTION,
            state=TriageState.HUMAN_REVIEW,
            last_event=TriageEvent.ROUTING_UNCLEAR,
            action_type=ActionType.ESCALATE_HUMAN_REVIEW,
            module_path=[self.module_id],
            module_state="no_child_route_matched",
            recommended_action=action,
            route_target="app-support-triage",
            confidence=0.64,
            audit_evidence=[reason],
            audit=[
                AuditEntry(
                    event=TriageEvent.ROUTING_UNCLEAR,
                    from_state=TriageState.ROUTE_DECISION,
                    to_state=TriageState.HUMAN_REVIEW,
                    action_type=ActionType.ESCALATE_HUMAN_REVIEW,
                    rule_id="data_quality.fallback",
                    reason=reason,
                )
            ],
        )
