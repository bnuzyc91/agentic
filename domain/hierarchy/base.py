"""Abstract base classes for the classification hierarchy.

The hierarchy is a tree:

    RootNode (InternalNode)
    ├── DataEngineeringTeam (InternalNode)
    │   ├── DataQualityLeaf  (LeafNode → Rulebook)
    │   ├── PipelineFailureLeaf
    │   └── SchemaChangeLeaf
    ├── FinancePlatformTeam (InternalNode)
    │   ├── BudgetVarianceLeaf
    │   ├── ReportPerformanceLeaf
    │   └── ForecastDiscrepancyLeaf
    └── AppSupportTeam (InternalNode)
        ├── AccessRequestLeaf
        ├── IntegrationIssueLeaf
        └── UIWorkflowLeaf

Classification walks top-down: each InternalNode scores its children and
descends into the best match. When a LeafNode is reached its Rulebook is
applied to produce a RouteDecision.

The evolution agent watches tickets that never reach a leaf and proposes new
nodes when patterns cross a frequency threshold.
the chain:
ClassificationNode.matches()     → float (how confident is this node?)
InternalNode.classify()          → ClassificationNode | None (which child?)
LeafNode.resolve()               → RouteDecision (what do we do?)
Rulebook.evaluate()              → RouteDecision (concrete action)

"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ticket_triage.domain.routing.models import RouteDecision
from ticket_triage.schema import ExtractedEntities, RequiredFieldRule, RoutingHint, Ticket


class ClassificationNode(ABC):
    """Base node in the routing hierarchy tree."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique slug for this node (e.g. 'data_engineering', 'data_quality_issue')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this node covers."""

    @abstractmethod
    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        """Return confidence [0.0, 1.0] that this node applies to the ticket."""


class InternalNode(ClassificationNode, ABC):
    """A non-leaf node that classifies into a child node.

    Subclasses define ``children``; the default ``classify`` implementation
    scores every child and descends into the highest-scoring one above
    ``min_confidence``.  Override ``classify`` for custom selection logic.
    """

    @property
    @abstractmethod
    def children(self) -> list[ClassificationNode]:
        """Ordered list of child nodes to score against."""

    @property
    def min_confidence(self) -> float:
        """Minimum score a child must reach to be selected."""
        return 0.40

    def classify(
        self, ticket: Ticket, entities: ExtractedEntities
    ) -> ClassificationNode | None:
        """Return the highest-scoring child that meets the confidence floor."""
        scored = sorted(
            ((child, child.matches(ticket, entities)) for child in self.children),
            key=lambda x: x[1],
            reverse=True,
        )
        if scored and scored[0][1] >= self.min_confidence:
            return scored[0][0]
        return None


class Rulebook(ABC):
    """Concrete resolution logic attached to a leaf node.

    Each Rulebook knows:
    - which fields are required before it can act
    - which team/queue to route to
    - how to produce a RouteDecision given the full ticket context
    """

    @property
    @abstractmethod
    def required_fields(self) -> list[RequiredFieldRule]:
        """Fields that must be present before the rulebook can resolve the ticket."""

    @property
    @abstractmethod
    def routing_hint(self) -> RoutingHint:
        """Default team/queue when this rulebook fires."""
    # only declared not implemented, the detailed implemented are in each leaf node
    # e.g. def evaluate(self, ticket, entities) in nodes/data_engineering.py
    @abstractmethod
    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        """Apply the rulebook and return a concrete RouteDecision."""


class LeafNode(ClassificationNode, ABC):
    """A terminal node that carries a Rulebook to resolve the ticket.

    Leaf nodes do not have children; they are the end of classification.
    Adding a new issue type means subclassing LeafNode and writing a Rulebook.
    """

    @property
    @abstractmethod
    def rulebook(self) -> Rulebook:
        """The concrete resolution logic for this issue type."""

    def resolve(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        """Delegate to the rulebook."""
        return self.rulebook.evaluate(ticket, entities)
