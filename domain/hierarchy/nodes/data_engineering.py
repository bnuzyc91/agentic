"""Data Engineering team hierarchy node.

Primary category: data_engineering
Subcategories (leaves):
  - data_quality_issue   → wraps existing DataQualityRouteModule
  - pipeline_failure     → simple rulebook
  - schema_change        → simple rulebook
"""

from __future__ import annotations

from ticket_triage.domain.hierarchy.base import (
    ClassificationNode,
    InternalNode,
    LeafNode,
    Rulebook,
)
from ticket_triage.domain.routing.models import RouteContext, RouteDecision, RouteOutcome
from ticket_triage.domain.routing.modules.data_quality.route_module import DataQualityRouteModule
from ticket_triage.schema import (
    ActionType,
    ApplicationIssueSubcategory,
    AuditEntry,
    ExtractedEntities,
    MissingField,
    PrimaryCategory,
    RecommendedAction,
    RequiredFieldRule,
    RoutingHint,
    Ticket,
    TriageEvent,
    TriagePhase,
    TriageState,
)

_DE_KEYWORDS = {
    # pipeline / job signals — unambiguous DE
    "pipeline": 0.90,
    "pipeline failure": 0.95,
    "etl": 0.90,
    "dbt": 0.92,
    "airflow": 0.92,
    "dag": 0.92,
    "job failed": 0.90,
    "batch job": 0.88,
    "data load": 0.85,
    # schema signals
    "schema change": 0.92,
    "data contract": 0.90,
    "column added": 0.90,
    "column removed": 0.90,
    "breaking change": 0.88,
    # data-quality signals (multi-word — unambiguous when together)
    "data quality": 0.90,
    "data discrepancy": 0.90,
    "missing data": 0.88,
    "wrong data": 0.88,
    "stale data": 0.90,
    "missing record": 0.88,
    "data warehouse": 0.88,
    "inconsistent data": 0.88,
    # source systems — weaker signals, meaningful in data-quality context
    "quickbase": 0.78,
    "sap": 0.72,
    "ebuilder": 0.78,
    "buyinghub": 0.72,
    # single-word quality signals when nothing stronger matches
    "discrepancy": 0.75,
    "mismatch": 0.75,
}


def _score(text: str, keywords: dict[str, float]) -> float:
    # scores the team using _DE_KEYWORDS
    text_lower = text.lower()
    hits = [score for kw, score in keywords.items() if kw in text_lower]
    return max(hits, default=0.0)


def _ticket_text(ticket: Ticket) -> str:
    return " ".join([ticket.title, ticket.description, " ".join(c.body for c in ticket.comments)])


# ---------------------------------------------------------------------------
# Leaf: data_quality_issue
# ---------------------------------------------------------------------------

class _DataQualityRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="source_system",
                label="Source system",
                prompt="Specify the source system (SAP, Quickbase, BuyingHub, eBuilder).",
            ),
            RequiredFieldRule(
                field="issue_description",
                label="Issue summary",
                prompt="Describe the data discrepancy or incorrect value.",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(team="data-engineering-dq", reason="Data quality investigation.")

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        module = DataQualityRouteModule()
        return module.evaluate(
            RouteContext(
                ticket=ticket,
                primary_category=PrimaryCategory.APPLICATION_ISSUE,
                subcategory=ApplicationIssueSubcategory.DATA_QUALITY_ISSUE,
                entities=entities,
                classification_confidence=0.85,
            )
        )


class DataQualityLeaf(LeafNode):
    # Scores the specific issue type
    @property
    def name(self) -> str:
        return "data_quality_issue"

    @property
    def description(self) -> str:
        return "Missing, incorrect, or inconsistent data from a source system."

    @property
    def rulebook(self) -> Rulebook:
        return _DataQualityRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        dq_keywords = {
            "data quality": 0.92, "data discrepancy": 0.90, "missing data": 0.88,
            "wrong data": 0.88, "stale data": 0.85, "missing record": 0.85,
            "inconsistent": 0.80, "mismatch": 0.80, "incorrect data": 0.85,
            "quickbase": 0.78, "sap": 0.72, "buyinghub": 0.78, "cashflow": 0.75,
            "source system": 0.70,
        }
        return _score(_ticket_text(ticket), dq_keywords)


# ---------------------------------------------------------------------------
# Leaf: pipeline_failure
# ---------------------------------------------------------------------------

def _simple_route_decision(
    *,
    team: str,
    rule_id: str,
    comment: str,
    action_type: ActionType = ActionType.ROUTE_TO_TEAM,
    state: TriageState = TriageState.ROUTED_TO_TEAM,
    event: TriageEvent = TriageEvent.ROUTE_MATCHED,
    phase: TriagePhase = TriagePhase.ROUTING,
    missing_fields: list[MissingField] | None = None,
    confidence: float = 0.82,
) -> RouteDecision:
    action = RecommendedAction(
        action_type=action_type,
        state=state.value,
        team=team,
        comment=comment,
        confidence=confidence,
    )
    return RouteDecision(
        outcome=RouteOutcome.ROUTE_TO_TEAM,
        phase=phase,
        state=state,
        last_event=event,
        action_type=action_type,
        module_path=["data_engineering"],
        module_state=rule_id,
        recommended_action=action,
        missing_fields=missing_fields or [],
        route_target=team,
        route_rule_id=rule_id,
        confidence=confidence,
        audit_evidence=[comment],
        audit=[
            AuditEntry(
                event=event,
                from_state=TriageState.ROUTE_DECISION,
                to_state=state,
                action_type=action_type,
                rule_id=rule_id,
                reason=comment,
            )
        ],
    )


class _PipelineFailureRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="issue_description",
                label="Pipeline / DAG name",
                prompt="Provide the pipeline, DAG, or job name that failed.",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(team="data-engineering-pipelines", reason="Pipeline failure triage.")

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        return _simple_route_decision(
            team="data-engineering-pipelines",
            rule_id="de.pipeline_failure",
            comment=(
                "Pipeline failure detected. Route to data-engineering-pipelines for "
                "DAG/job investigation and on-call escalation if SLA-critical."
            ),
        )


class PipelineFailureLeaf(LeafNode):
    @property
    def name(self) -> str:
        return "pipeline_failure"

    @property
    def description(self) -> str:
        return "ETL/ELT pipeline, DAG, or batch job failure."

    @property
    def rulebook(self) -> Rulebook:
        return _PipelineFailureRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        keywords = {
            "pipeline": 0.92, "dag": 0.92, "airflow": 0.90, "etl": 0.90,
            "dbt": 0.88, "job failed": 0.90, "batch job": 0.88,
            "data load": 0.80, "ingestion": 0.82, "pipeline failure": 0.95,
        }
        return _score(_ticket_text(ticket), keywords)


# ---------------------------------------------------------------------------
# Leaf: schema_change
# ---------------------------------------------------------------------------

class _SchemaChangeRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="source_system",
                label="Affected table or dataset",
                prompt="Which table, dataset, or API changed?",
            ),
            RequiredFieldRule(
                field="issue_description",
                label="Change description",
                prompt="Describe the schema change (column added/removed/renamed, type change, etc.).",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(
            team="data-engineering-schema", reason="Schema / contract change review."
        )

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        return _simple_route_decision(
            team="data-engineering-schema",
            rule_id="de.schema_change",
            comment=(
                "Schema or data contract change detected. Route to data-engineering-schema "
                "for impact assessment and downstream consumer notification."
            ),
        )


class SchemaChangeLeaf(LeafNode):
    @property
    def name(self) -> str:
        return "schema_change"

    @property
    def description(self) -> str:
        return "Breaking or additive schema / data-contract change in a source or target."

    @property
    def rulebook(self) -> Rulebook:
        return _SchemaChangeRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        keywords = {
            "schema change": 0.95, "column added": 0.90, "column removed": 0.90,
            "column renamed": 0.90, "breaking change": 0.88, "data contract": 0.90,
            "schema migration": 0.88, "type change": 0.82, "field removed": 0.85,
            "api change": 0.78,
        }
        return _score(_ticket_text(ticket), keywords)


# ---------------------------------------------------------------------------
# Team internal node
# ---------------------------------------------------------------------------

class DataEngineeringTeam(InternalNode):
    @property
    def name(self) -> str:
        return "data_engineering"

    @property
    def description(self) -> str:
        return "Data quality, pipeline failures, and schema/contract changes."

    @property
    def children(self) -> list[ClassificationNode]:
        return [DataQualityLeaf(), PipelineFailureLeaf(), SchemaChangeLeaf()]

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        return _score(_ticket_text(ticket), _DE_KEYWORDS)
