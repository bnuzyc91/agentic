"""Root node and traversal function for the classification hierarchy.

Usage:
    from ticket_triage.domain.hierarchy.registry import traverse

    classification, route_decision = traverse(ticket, entities)
    # classification.routing_team  → RoutingTeam.DATA_ENGINEERING
    # classification.path          → ['data_engineering', 'data_quality_issue']
    # route_decision               → RouteDecision | None (None if no leaf reached)
"""

from __future__ import annotations

from ticket_triage.domain.hierarchy.base import ClassificationNode, InternalNode, LeafNode
from ticket_triage.domain.hierarchy.nodes.app_support import AppSupportTeam
from ticket_triage.domain.hierarchy.nodes.data_engineering import DataEngineeringTeam
from ticket_triage.domain.hierarchy.nodes.finance_platform import FinancePlatformTeam
from ticket_triage.domain.routing.models import RouteDecision
from ticket_triage.schema import ExtractedEntities, HierarchyClassification, RoutingTeam, Ticket

_TEAM_MAP: dict[str, RoutingTeam] = {
    "data_engineering": RoutingTeam.DATA_ENGINEERING,
    "finance_platform": RoutingTeam.FINANCE_PLATFORM,
    "app_support": RoutingTeam.APP_SUPPORT,
}


class RootNode(InternalNode):
    """Entry point of the classification hierarchy — selects the responsible team."""

    @property
    def name(self) -> str:
        return "root"

    @property
    def description(self) -> str:
        return "Top-level routing node — selects the responsible team."

    @property
    def children(self) -> list[ClassificationNode]:
        return [DataEngineeringTeam(), FinancePlatformTeam(), AppSupportTeam()]

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        return 1.0


def traverse(
    ticket: Ticket,
    entities: ExtractedEntities,
) -> tuple[HierarchyClassification, RouteDecision | None]:
    """Walk the classification tree top-down until a leaf or dead-end is reached.

    Returns:
        classification: The path taken and routing team identified.
        route_decision: The RouteDecision from the leaf Rulebook, or None if no
                        leaf was reached (unclassified ticket — evolution agent fodder).
    """
    root = RootNode()
    path: list[str] = []
    evidence: list[str] = []
    current: ClassificationNode = root
    confidence = 1.0

    while isinstance(current, InternalNode):
        # Trace through it with one ticket mentally. That loop IS the classification algorithm.
        child = current.classify(ticket, entities)
        if child is None:
            evidence.append(
                f"No child of '{current.name}' reached the confidence floor — "
                "classification stops here."
            )
            break
        score = child.matches(ticket, entities)
        path.append(child.name)
        evidence.append(f"Selected '{child.name}' with score {score:.2f}.")
        confidence = min(confidence, score)
        current = child

    route_decision: RouteDecision | None = None
    if isinstance(current, LeafNode):
        route_decision = current.resolve(ticket, entities)

    routing_team = _TEAM_MAP.get(path[0], RoutingTeam.UNKNOWN) if path else RoutingTeam.UNKNOWN
    issue_type = path[-1] if len(path) > 1 else "unknown"

    return (
        HierarchyClassification(
            routing_team=routing_team,
            issue_type=issue_type,
            path=path,
            confidence=round(confidence, 3),
            evidence=evidence,
        ),
        route_decision,
    )
