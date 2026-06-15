"""Finance Platform team hierarchy node.

Primary category: finance_platform
Subcategories (leaves):
  - budget_variance_issue      → variance between budget and actuals
  - report_performance_issue   → slow/broken financial reports
  - forecast_discrepancy       → forecast vs. actuals mismatch
"""

from __future__ import annotations

from ticket_triage.domain.hierarchy.base import (
    ClassificationNode,
    InternalNode,
    LeafNode,
    Rulebook,
)
from ticket_triage.domain.routing.models import RouteDecision, RouteOutcome
from ticket_triage.schema import (
    ActionType,
    AuditEntry,
    ExtractedEntities,
    RecommendedAction,
    RequiredFieldRule,
    RoutingHint,
    Ticket,
    TriageEvent,
    TriagePhase,
    TriageState,
)

_FP_KEYWORDS = {
    # unambiguous finance signals
    "budget variance": 0.92,
    "budget vs actuals": 0.92,
    "over budget": 0.90,
    "under budget": 0.90,
    "forecast discrepancy": 0.92,
    "forecast mismatch": 0.92,
    "plan vs actual": 0.90,
    "reforecast": 0.90,
    "p&l": 0.90,
    "income statement": 0.88,
    "journal entry": 0.85,
    "cost center": 0.82,
    "fiscal period": 0.82,
    "financial report": 0.88,
    "budget report": 0.88,
    "report timeout": 0.84,
    "report not loading": 0.84,
    # moderate signals — present but not alone sufficient
    "forecast": 0.78,
    "variance": 0.72,
}


def _score(text: str, keywords: dict[str, float]) -> float:
    text_lower = text.lower()
    hits = [score for kw, score in keywords.items() if kw in text_lower]
    return max(hits, default=0.0)


def _ticket_text(ticket: Ticket) -> str:
    return " ".join([ticket.title, ticket.description, " ".join(c.body for c in ticket.comments)])


def _simple_route_decision(
    *,
    team: str,
    rule_id: str,
    comment: str,
    module_path: list[str],
    confidence: float = 0.82,
) -> RouteDecision:
    action = RecommendedAction(
        action_type=ActionType.ROUTE_TO_TEAM,
        state=TriageState.ROUTED_TO_TEAM.value,
        team=team,
        comment=comment,
        confidence=confidence,
    )
    return RouteDecision(
        outcome=RouteOutcome.ROUTE_TO_TEAM,
        phase=TriagePhase.ROUTING,
        state=TriageState.ROUTED_TO_TEAM,
        last_event=TriageEvent.ROUTE_MATCHED,
        action_type=ActionType.ROUTE_TO_TEAM,
        module_path=module_path,
        module_state=rule_id,
        recommended_action=action,
        route_target=team,
        route_rule_id=rule_id,
        confidence=confidence,
        audit_evidence=[comment],
        audit=[
            AuditEntry(
                event=TriageEvent.ROUTE_MATCHED,
                from_state=TriageState.ROUTE_DECISION,
                to_state=TriageState.ROUTED_TO_TEAM,
                action_type=ActionType.ROUTE_TO_TEAM,
                rule_id=rule_id,
                reason=comment,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Leaf: budget_variance_issue
# ---------------------------------------------------------------------------

class _BudgetVarianceRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="fiscal_period",
                label="Fiscal period",
                prompt="Which fiscal period or quarter is affected (e.g. Q2 FY2026)?",
            ),
            RequiredFieldRule(
                field="project_code",
                label="Project or cost-center code",
                prompt="Provide the project S-code or cost-center to investigate.",
            ),
            RequiredFieldRule(
                field="issue_description",
                label="Variance description",
                prompt="Describe the discrepancy: budget figure, actual figure, expected delta.",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(team="finance-platform-budget", reason="Budget variance investigation.")

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        return _simple_route_decision(
            team="finance-platform-budget",
            rule_id="fp.budget_variance",
            comment=(
                "Budget vs. actuals variance detected. Route to finance-platform-budget for "
                "period reconciliation and journal-entry review."
            ),
            module_path=["finance_platform", "budget_variance_issue"],
        )


class BudgetVarianceLeaf(LeafNode):
    @property
    def name(self) -> str:
        return "budget_variance_issue"

    @property
    def description(self) -> str:
        return "Discrepancy between budgeted and actual figures for a project or cost center."

    @property
    def rulebook(self) -> Rulebook:
        return _BudgetVarianceRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        keywords = {
            "budget variance": 0.95, "variance": 0.85, "actuals": 0.82,
            "budget vs": 0.90, "over budget": 0.88, "under budget": 0.88,
            "budget discrepancy": 0.92, "cost center": 0.78, "fiscal period": 0.80,
            "journal entry": 0.80, "reconciliation": 0.82,
        }
        return _score(_ticket_text(ticket), keywords)


# ---------------------------------------------------------------------------
# Leaf: report_performance_issue
# ---------------------------------------------------------------------------

class _ReportPerformanceRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="affected_link",
                label="Report URL or name",
                prompt="Provide the report name or URL that is slow or broken.",
            ),
            RequiredFieldRule(
                field="issue_description",
                label="Symptom",
                prompt="Describe the issue: timeout duration, error message, or blank screen.",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(
            team="finance-platform-reports", reason="Report performance or rendering issue."
        )

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        return _simple_route_decision(
            team="finance-platform-reports",
            rule_id="fp.report_performance",
            comment=(
                "Financial report performance issue detected. Route to finance-platform-reports "
                "for query optimization or infrastructure triage."
            ),
            module_path=["finance_platform", "report_performance_issue"],
            confidence=0.80,
        )


class ReportPerformanceLeaf(LeafNode):
    @property
    def name(self) -> str:
        return "report_performance_issue"

    @property
    def description(self) -> str:
        return "Financial report is slow, timing out, or failing to render."

    @property
    def rulebook(self) -> Rulebook:
        return _ReportPerformanceRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        keywords = {
            "report timeout": 0.92, "slow report": 0.90, "report loading": 0.88,
            "report download": 0.85, "report blank": 0.88, "report error": 0.85,
            "cannot load report": 0.90, "report performance": 0.92,
            "dashboard timeout": 0.85, "report not loading": 0.90,
        }
        return _score(_ticket_text(ticket), keywords)


# ---------------------------------------------------------------------------
# Leaf: forecast_discrepancy
# ---------------------------------------------------------------------------

class _ForecastDiscrepancyRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="fiscal_period",
                label="Forecast period",
                prompt="Which forecast period is affected?",
            ),
            RequiredFieldRule(
                field="issue_description",
                label="Discrepancy detail",
                prompt="Describe how the forecast differs from expected (system, amount, %).",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(
            team="finance-platform-forecasting",
            reason="Forecast vs. actuals discrepancy.",
        )

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        return _simple_route_decision(
            team="finance-platform-forecasting",
            rule_id="fp.forecast_discrepancy",
            comment=(
                "Forecast vs. actuals discrepancy detected. Route to finance-platform-forecasting "
                "for model and data validation."
            ),
            module_path=["finance_platform", "forecast_discrepancy"],
        )


class ForecastDiscrepancyLeaf(LeafNode):
    @property
    def name(self) -> str:
        return "forecast_discrepancy"

    @property
    def description(self) -> str:
        return "Forecast figures do not match actuals or expected projections."

    @property
    def rulebook(self) -> Rulebook:
        return _ForecastDiscrepancyRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        keywords = {
            "forecast": 0.88, "forecast discrepancy": 0.95, "forecast vs": 0.90,
            "projected": 0.78, "projection": 0.80, "forecast mismatch": 0.92,
            "forward-looking": 0.80, "reforecast": 0.88, "plan vs actual": 0.88,
        }
        return _score(_ticket_text(ticket), keywords)


# ---------------------------------------------------------------------------
# Team internal node
# ---------------------------------------------------------------------------

class FinancePlatformTeam(InternalNode):
    @property
    def name(self) -> str:
        return "finance_platform"

    @property
    def description(self) -> str:
        return "Budget variance, financial report performance, and forecast discrepancies."

    @property
    def children(self) -> list[ClassificationNode]:
        return [BudgetVarianceLeaf(), ReportPerformanceLeaf(), ForecastDiscrepancyLeaf()]

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        return _score(_ticket_text(ticket), _FP_KEYWORDS)
