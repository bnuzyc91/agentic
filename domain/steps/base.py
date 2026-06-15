"""Abstract base classes for each step in the triage pipeline.

The pipeline is a sequence of steps, each with a well-defined input/output
contract.  Concrete implementations are swappable: the default ones wrap the
existing domain functions; team-specific routing modules can supply their own.

Pipeline flow
─────────────
  Ticket
    │
    ▼
  EntityExtractor.extract()          → ExtractedEntities
    │
    ▼
  TicketClassifier.classify()        → (HierarchyClassification, RouteDecision | None)
    │
    ▼
  DuplicateFinder.find()             → list[DuplicateCandidate]
    │
    ▼
  FieldEvaluator.evaluate()          → list[MissingField]
    │
    ▼
  ActionRecommender.recommend()      → RecommendedAction
    │
    ▼
  (TriageOutput assembled by caller)

The TemplateEvolver runs offline over historical tickets and proposes new
hierarchy nodes when patterns exceed configured thresholds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ticket_triage.domain.routing.models import RouteDecision
from ticket_triage.schema import (
    DuplicateCandidate,
    ExtractedEntities,
    HierarchyClassification,
    MissingField,
    RecommendedAction,
    TemplateEvolutionProposal,
    Ticket,
)


class EntityExtractor(ABC):
    """Extract structured entities from a raw ticket."""

    @abstractmethod
    def extract(self, ticket: Ticket) -> ExtractedEntities:
        """Return canonical entities present in the ticket."""


class TicketClassifier(ABC):
    """Walk the classification hierarchy and identify the leaf node for a ticket.

    Returns both the HierarchyClassification (which team + issue type + path)
    and the RouteDecision from the leaf's Rulebook (or None if no leaf reached).
    """

    @abstractmethod
    def classify(
        self, ticket: Ticket, entities: ExtractedEntities
    ) -> tuple[HierarchyClassification, RouteDecision | None]:
        """Traverse the hierarchy and return (classification, route_decision)."""


class DuplicateFinder(ABC):
    """Find likely duplicate tickets from historical data."""

    @abstractmethod
    def find(self, ticket: Ticket) -> list[DuplicateCandidate]:
        """Return scored duplicate candidates, highest score first."""


class FieldEvaluator(ABC):
    """Evaluate which required fields are missing for a given classification.

    Required fields come from the Rulebook attached to the matched leaf node;
    this step checks whether the extracted entities satisfy them.
    """

    @abstractmethod
    def evaluate(
        self,
        classification: HierarchyClassification,
        entities: ExtractedEntities,
    ) -> list[MissingField]:
        """Return fields required by the leaf Rulebook that are absent."""


class ActionRecommender(ABC):
    """Produce a human-reviewable recommended action given the full triage context.

    The recommender combines the hierarchy classification, the route decision
    from the leaf rulebook (if reached), missing fields, and duplicate
    candidates into a single suggested next action.
    """

    @abstractmethod
    def recommend(
        self,
        ticket: Ticket,
        classification: HierarchyClassification,
        entities: ExtractedEntities,
        missing_fields: list[MissingField],
        duplicates: list[DuplicateCandidate],
        route_decision: RouteDecision | None,
    ) -> RecommendedAction:
        """Return the recommended next action. Always requires human review in V1."""


class TemplateEvolver(ABC):
    """Propose new hierarchy nodes when ticket patterns exceed thresholds.

    The evolver inspects historical tickets that failed to reach a leaf node
    (routing_team == UNKNOWN or issue_type == 'unknown') and clusters them by
    keyword pattern.  When a cluster exceeds the configured min_count and
    min_share thresholds it emits a TemplateEvolutionProposal for human review.

    Proposals are never applied automatically — a human must approve and add
    the new LeafNode + Rulebook to the hierarchy.
    """

    @abstractmethod
    def propose(self, history: list[Ticket]) -> list[TemplateEvolutionProposal]:
        """Analyse history and return human-reviewable evolution proposals."""
