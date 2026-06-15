"""Hierarchy-aware evolution proposal generation.

The evolution agent collects tickets that could NOT be confidently routed by the
current team → issue-type → rulebook hierarchy, clusters them by keyword pattern,
and proposes human-reviewable diffs:

  ADD_RULEBOOK_RULE  — new keyword for an existing leaf (confidence too low)
  ADD_LEAF_NODE      — new issue type under an existing team
  ADD_TEAM_NODE      — new routing team (when no team matches at all)

Nothing is applied automatically.  Every proposal requires a human reviewer to
turn it into a code change in domain/hierarchy/nodes/<team>.py.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.hierarchy.registry import RootNode, traverse
from ticket_triage.domain.loading import load_sample_tickets
from ticket_triage.domain.parsing import coerce_ticket
from ticket_triage.schema import (
    ExtractedEntities,
    MissingField,
    RoutingTeam,
    TemplateEvolutionProposal,
    TemplateProposalType,
    Ticket,
    TriageState,
)


@dataclass(frozen=True)
class EvolutionThresholds:
    """Conservative defaults for hierarchy evolution suggestions."""

    min_confidence_for_routing: float = 0.50
    observe_min_count: int = 3
    suggest_min_count: int = 5
    suggest_min_share: float = 0.10
    strong_min_count: int = 10
    strong_min_share: float = 0.20
    routing_min_same_team_share: float = 0.70
    required_field_min_missing_share: float = 0.15
    keyword_cluster_overlap: int = 2  # shared keywords to consider tickets related


DEFAULT_THRESHOLDS = EvolutionThresholds()

KEYWORD_RE = re.compile(r"[a-z][a-z0-9_-]{2,}")
STOP_WORDS = {
    "and", "are", "but", "can", "cannot", "for", "from", "has", "have",
    "issue", "please", "project", "request", "system", "that", "the",
    "this", "ticket", "with",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _share(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _proposal_confidence(count: int, share: float, t: EvolutionThresholds) -> float:
    if count >= t.strong_min_count and share >= t.strong_min_share:
        return 0.86
    if count >= t.suggest_min_count and share >= t.suggest_min_share:
        return 0.72
    return 0.55


def _proposal_level(count: int, share: float, t: EvolutionThresholds) -> str:
    if count >= t.strong_min_count and share >= t.strong_min_share:
        return "strongly_suggest"
    if count >= t.suggest_min_count and share >= t.suggest_min_share:
        return "suggest"
    return "observe"


def _is_suggestible(count: int, share: float, t: EvolutionThresholds) -> bool:
    return count >= t.suggest_min_count and share >= t.suggest_min_share


def _ticket_words(ticket: Ticket) -> set[str]:
    text = " ".join([
        ticket.title,
        ticket.description,
        " ".join(c.body for c in ticket.comments),
        ticket.known_resolution or "",
        " ".join(ticket.labels),
    ]).lower()
    return {w for w in KEYWORD_RE.findall(text) if w not in STOP_WORDS}


def _common_keywords(tickets: Iterable[Ticket], limit: int = 8) -> list[str]:
    counts: Counter[str] = Counter()
    for t in tickets:
        counts.update(_ticket_words(t))
    return [w for w, _ in counts.most_common(limit)]


# ---------------------------------------------------------------------------
# Classification with confidence metadata
# ---------------------------------------------------------------------------

@dataclass
class _ClassifiedTicket:
    ticket: Ticket
    entities: ExtractedEntities
    routing_team: RoutingTeam
    issue_type: str
    confidence: float
    state: str  # TriageState value
    # Missing fields set by the leaf's own evaluate() (e.g. DQ ContextGate).
    # Empty for simple leaves — the evolution code checks rulebook.required_fields instead.
    route_missing_fields: list[MissingField] = field(default_factory=list)


def _classify_all(tickets: list[Ticket]) -> list[_ClassifiedTicket]:
    results = []
    for ticket in tickets:
        parsed = coerce_ticket(ticket)
        entities = extract_entities(parsed)
        classification, route_decision = traverse(parsed, entities)

        if route_decision is not None and route_decision.state in {
            TriageState.MISSING_INFO, TriageState.INTENDED_BEHAVIOR
        }:
            state = route_decision.state.value
        elif classification.routing_team == RoutingTeam.UNKNOWN:
            state = TriageState.HUMAN_REVIEW.value
        else:
            state = route_decision.state.value if route_decision else TriageState.HUMAN_REVIEW.value

        route_missing = route_decision.missing_fields if route_decision else []

        results.append(_ClassifiedTicket(
            ticket=parsed,
            entities=entities,
            routing_team=classification.routing_team,
            issue_type=classification.issue_type,
            confidence=classification.confidence,
            state=state,
            route_missing_fields=list(route_missing),
        ))
    return results


def _is_unresolved(ct: _ClassifiedTicket, t: EvolutionThresholds) -> bool:
    return (
        ct.routing_team == RoutingTeam.UNKNOWN
        or ct.confidence < t.min_confidence_for_routing
        or ct.state == TriageState.HUMAN_REVIEW.value
    )


# ---------------------------------------------------------------------------
# Cluster unresolved tickets by keyword overlap
# ---------------------------------------------------------------------------

def _cluster_by_keywords(
    tickets: list[Ticket],
    overlap: int,
) -> list[list[Ticket]]:
    """Greedy keyword-overlap clustering — O(n²) but fine for small history sets."""
    word_sets = [_ticket_words(t) for t in tickets]
    assigned = [False] * len(tickets)
    clusters: list[list[Ticket]] = []

    for i in range(len(tickets)):
        if assigned[i]:
            continue
        cluster = [tickets[i]]
        assigned[i] = True
        for j in range(i + 1, len(tickets)):
            if not assigned[j] and len(word_sets[i] & word_sets[j]) >= overlap:
                cluster.append(tickets[j])
                assigned[j] = True
        clusters.append(cluster)

    return [c for c in clusters if len(c) >= 1]


# ---------------------------------------------------------------------------
# Guess which team a cluster might belong to (for ADD_LEAF_NODE proposals)
# ---------------------------------------------------------------------------

def _guess_team(tickets: list[Ticket]) -> RoutingTeam | None:
    """Run traverse on each cluster ticket and see if a team emerges by majority."""
    team_votes: Counter[RoutingTeam] = Counter()
    for t in tickets:
        parsed = coerce_ticket(t)
        entities = extract_entities(parsed)
        # Only look at the team-level score, not the leaf
        root = RootNode()
        scored = sorted(
            [(child, child.matches(parsed, entities)) for child in root.children],
            key=lambda x: x[1],
            reverse=True,
        )
        if scored and scored[0][1] >= 0.40:
            from ticket_triage.domain.hierarchy.registry import _TEAM_MAP
            team = _TEAM_MAP.get(scored[0][0].name)
            if team:
                team_votes[team] += 1

    if not team_votes:
        return None
    best_team, count = team_votes.most_common(1)[0]
    return best_team if count >= max(1, len(tickets) // 2) else None


# ---------------------------------------------------------------------------
# Proposal generators
# ---------------------------------------------------------------------------

def _unresolved_pattern_proposals(
    classified: list[_ClassifiedTicket],
    t: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    """Cluster unresolved tickets and propose new leaves or rulebook rules."""
    unresolved_cts = [ct for ct in classified if _is_unresolved(ct, t)]
    if len(unresolved_cts) < t.observe_min_count:
        return []

    total = len(classified)
    unresolved_tickets = [ct.ticket for ct in unresolved_cts]
    clusters = _cluster_by_keywords(unresolved_tickets, t.keyword_cluster_overlap)

    proposals: list[TemplateEvolutionProposal] = []
    for cluster in clusters:
        count = len(cluster)
        share = _share(count, total)
        if count < t.observe_min_count:
            continue

        keywords = _common_keywords(cluster)
        team = _guess_team(cluster)
        ticket_ids = [t_.issue_id for t_ in cluster[:8]]

        if team is not None:
            # Cluster maps to a known team — suggest a new leaf under that team
            proposals.append(TemplateEvolutionProposal(
                proposal_type=TemplateProposalType.ADD_LEAF_NODE,
                title=f"New issue type under {team.value} — {keywords[0] if keywords else 'unknown pattern'}",
                rationale=(
                    f"{count} ticket(s) ({share:.0%} of history) could not be confidently "
                    f"classified under {team.value} but share a common keyword pattern. "
                    "Consider adding a new LeafNode with a Rulebook for this pattern."
                ),
                evidence_ticket_ids=ticket_ids,
                proposed_change={
                    "team": team.value,
                    "proposed_issue_type": f"{keywords[0].replace(' ', '_')}_issue" if keywords else "review_needed",
                    "candidate_keywords": keywords,
                    "suggested_required_fields": ["issue_description", "source_system"],
                    "suggested_routing_hint": f"{team.value.replace('_', '-')}-new-queue",
                    "proposal_level": _proposal_level(count, share, t),
                },
                confidence=_proposal_confidence(count, share, t),
            ))
        else:
            # No team matches — suggest a new team/actor
            proposals.append(TemplateEvolutionProposal(
                proposal_type=TemplateProposalType.ADD_TEAM_NODE,
                title=f"Possible new routing team — {keywords[0] if keywords else 'unknown pattern'}",
                rationale=(
                    f"{count} ticket(s) ({share:.0%} of history) match no existing team "
                    "and share a distinct keyword pattern. Review whether a new InternalNode "
                    "(routing team) is needed."
                ),
                evidence_ticket_ids=ticket_ids,
                proposed_change={
                    "candidate_keywords": keywords,
                    "suggested_team_name": f"{keywords[0].replace(' ', '_')}_team" if keywords else "review_needed",
                    "proposal_level": _proposal_level(count, share, t),
                },
                confidence=_proposal_confidence(count, share, t),
            ))

    return proposals


def _weak_classification_proposals(
    classified: list[_ClassifiedTicket],
    t: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    """Propose ADD_RULEBOOK_RULE for tickets that reached a known leaf but with low confidence."""
    weak: dict[tuple[str, str], list[Ticket]] = defaultdict(list)
    for ct in classified:
        if (
            ct.routing_team != RoutingTeam.UNKNOWN
            and ct.issue_type != "unknown"
            and ct.confidence < t.min_confidence_for_routing
        ):
            weak[(ct.routing_team.value, ct.issue_type)].append(ct.ticket)

    total = len(classified)
    proposals: list[TemplateEvolutionProposal] = []
    for (team, issue_type), tickets in weak.items():
        count = len(tickets)
        share = _share(count, total)
        if not _is_suggestible(count, share, t):
            continue
        keywords = _common_keywords(tickets)
        proposals.append(TemplateEvolutionProposal(
            proposal_type=TemplateProposalType.ADD_RULEBOOK_RULE,
            title=f"Strengthen keyword rules for {team}/{issue_type}",
            rationale=(
                f"{count} ticket(s) ({share:.0%}) reached {team}/{issue_type} but with "
                f"confidence below {t.min_confidence_for_routing:.0%}. Adding stronger "
                "multi-word keywords to the leaf's matches() method may improve precision."
            ),
            evidence_ticket_ids=[t_.issue_id for t_ in tickets[:8]],
            proposed_change={
                "team": team,
                "issue_type": issue_type,
                "candidate_keyword_additions": keywords,
                "file": f"domain/hierarchy/nodes/{team}.py",
                "proposal_level": _proposal_level(count, share, t),
            },
            confidence=_proposal_confidence(count, share, t),
        ))
    return proposals


def _missing_context_proposals(
    classified: list[_ClassifiedTicket],
    t: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    """Propose clarification-prompt improvements for repeatedly-blocked fields."""
    missing_cts = [ct for ct in classified if ct.state == TriageState.MISSING_INFO.value]
    if not missing_cts:
        return []

    field_counter: Counter[str] = Counter()
    field_tickets: dict[str, list[Ticket]] = defaultdict(list)
    for ct in missing_cts:
        if ct.route_missing_fields:
            # Use the leaf's own evaluate() output (e.g. DQ ContextGate fields).
            for mf in ct.route_missing_fields:
                field_counter[mf.field] += 1
                field_tickets[mf.field].append(ct.ticket)
        else:
            # Fallback: check the rulebook's static required_fields list.
            from ticket_triage.domain.hierarchy.registry import get_rulebook
            from ticket_triage.domain.recommendation import _is_missing
            rulebook = get_rulebook(ct.routing_team, ct.issue_type)
            if rulebook:
                for rule in rulebook.required_fields:
                    if _is_missing(ct.entities, rule.field):
                        field_counter[rule.field] += 1
                        field_tickets[rule.field].append(ct.ticket)

    total_missing = len(missing_cts)
    proposals: list[TemplateEvolutionProposal] = []
    for field_name, count in field_counter.items():
        share = _share(count, total_missing)
        if count < t.suggest_min_count or share < t.required_field_min_missing_share:
            continue
        proposals.append(TemplateEvolutionProposal(
            proposal_type=TemplateProposalType.ADD_CLARIFICATION_TEXT,
            title=f"Improve clarification prompt for missing field: {field_name}",
            rationale=(
                f"{count} ticket(s) ({share:.0%} of MISSING_INFO tickets) were blocked "
                f"on '{field_name}'. Improving the prompt in the Rulebook.required_fields "
                "list may reduce repeated back-and-forth."
            ),
            evidence_ticket_ids=[t_.issue_id for t_ in field_tickets[field_name][:8]],
            proposed_change={
                "field": field_name,
                "candidate_prompt_keywords": _common_keywords(field_tickets[field_name]),
                "proposal_level": _proposal_level(count, share, t),
            },
            confidence=_proposal_confidence(count, share, t),
        ))
    return proposals


def _routing_gap_proposals(
    classified: list[_ClassifiedTicket],
    t: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    """Propose CHANGE_ROUTING_HINT when ambiguous tickets share a known-assignee pattern."""
    ambiguous = [
        ct for ct in classified
        if ct.state == TriageState.HUMAN_REVIEW.value and ct.ticket.known_assignee
    ]
    if len(ambiguous) < t.suggest_min_count:
        return []

    assignee_counter: Counter[str] = Counter(ct.ticket.known_assignee for ct in ambiguous)
    assignee, count = assignee_counter.most_common(1)[0]
    share = _share(count, len(ambiguous))
    if not _is_suggestible(count, share, t):
        return []

    evidence = [ct.ticket for ct in ambiguous if ct.ticket.known_assignee == assignee]
    return [TemplateEvolutionProposal(
        proposal_type=TemplateProposalType.CHANGE_ROUTING_HINT,
        title=f"Add routing rule for ambiguous tickets historically assigned to {assignee}",
        rationale=(
            f"{count} ambiguous ticket(s) ({share:.0%}) were historically assigned to "
            f"{assignee}. A new keyword rule or leaf node may cover this pattern."
        ),
        evidence_ticket_ids=[t_.issue_id for t_ in evidence[:8]],
        proposed_change={
            "suggested_team": assignee,
            "candidate_keywords": _common_keywords(evidence),
            "proposal_level": _proposal_level(count, share, t),
        },
        confidence=_proposal_confidence(count, share, t),
    )]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def propose_hierarchy_evolution(
    history: list[Ticket] | None = None,
    thresholds: EvolutionThresholds = DEFAULT_THRESHOLDS,
) -> list[TemplateEvolutionProposal]:
    """Generate human-reviewable hierarchy improvement proposals.

    Runs traverse() on every historical ticket, separates confidently-routed tickets
    from unresolved ones (UNKNOWN team / low confidence / HUMAN_REVIEW), clusters the
    unresolved set by keyword overlap, and proposes new leaf nodes, rulebook rules,
    or routing hints.

    Never mutates the hierarchy.  All proposals require a human reviewer to turn them
    into code changes in domain/hierarchy/nodes/<team>.py.
    """
    tickets = history or load_sample_tickets()
    if not tickets:
        return []

    classified = _classify_all(tickets)
    proposals: list[TemplateEvolutionProposal] = []
    proposals.extend(_unresolved_pattern_proposals(classified, thresholds))
    proposals.extend(_weak_classification_proposals(classified, thresholds))
    proposals.extend(_missing_context_proposals(classified, thresholds))
    proposals.extend(_routing_gap_proposals(classified, thresholds))
    return proposals


# Keep old name as an alias so the ADK agent tool wrapper still resolves.
propose_template_evolution = propose_hierarchy_evolution
