"""State-machine-aware template evolution proposal generation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re
from typing import Iterable

from ticket_triage.domain.classification import classify_ticket
from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.loading import load_sample_tickets, load_state_machine
from ticket_triage.domain.recommendation import triage_ticket
from ticket_triage.schema import (
    ApplicationIssueSubcategory,
    PrimaryCategory,
    TemplateEvolutionProposal,
    TemplateProposalType,
    Ticket,
    TriageEvent,
    TriageState,
    TriageOutput,
)


@dataclass(frozen=True)
class EvolutionThresholds:
    """Conservative defaults for rulebook evolution suggestions."""

    observe_min_count: int = 3
    suggest_min_count: int = 5
    suggest_min_share: float = 0.10
    strong_min_count: int = 10
    strong_min_share: float = 0.20
    routing_min_same_team_share: float = 0.70
    required_field_min_missing_share: float = 0.15
    new_state_min_count: int = 10
    new_state_min_share: float = 0.20


DEFAULT_THRESHOLDS = EvolutionThresholds()
KEYWORD_RE = re.compile(r"[a-z][a-z0-9_-]{2,}")
STOP_WORDS = {
    "and",
    "are",
    "but",
    "can",
    "cannot",
    "for",
    "from",
    "has",
    "have",
    "issue",
    "please",
    "project",
    "request",
    "system",
    "that",
    "the",
    "this",
    "ticket",
    "with",
}


def _share(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _proposal_confidence(count: int, share: float, thresholds: EvolutionThresholds) -> float:
    if count >= thresholds.strong_min_count and share >= thresholds.strong_min_share:
        return 0.86
    if count >= thresholds.suggest_min_count and share >= thresholds.suggest_min_share:
        return 0.72
    return 0.55


def _is_suggestible(count: int, share: float, thresholds: EvolutionThresholds) -> bool:
    return count >= thresholds.suggest_min_count and share >= thresholds.suggest_min_share


def _ticket_words(ticket: Ticket) -> set[str]:
    text = " ".join(
        [
            ticket.title,
            ticket.description,
            " ".join(comment.body for comment in ticket.comments),
            ticket.known_resolution or "",
            " ".join(ticket.labels),
        ]
    ).lower()
    return {word for word in KEYWORD_RE.findall(text) if word not in STOP_WORDS}


def _common_keywords(tickets: Iterable[Ticket], limit: int = 8) -> list[str]:
    counts: Counter[str] = Counter()
    for ticket in tickets:
        counts.update(_ticket_words(ticket))
    return [word for word, _ in counts.most_common(limit)]


def _group_by_output(
    tickets: list[Ticket],
) -> list[tuple[Ticket, TriageOutput]]:
    return [(ticket, triage_ticket(ticket)) for ticket in tickets]


def _proposal_level(count: int, share: float, thresholds: EvolutionThresholds) -> str:
    if count >= thresholds.strong_min_count and share >= thresholds.strong_min_share:
        return "strongly_suggest"
    if count >= thresholds.suggest_min_count and share >= thresholds.suggest_min_share:
        return "suggest"
    return "observe"


def _primary_taxonomy_proposals(
    tickets: list[Ticket],
    thresholds: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    unknown_tickets = [
        ticket
        for ticket in tickets
        if classify_ticket(ticket, extract_entities(ticket)).primary_category
        == PrimaryCategory.OTHER_OR_UNKNOWN
    ]
    share = _share(len(unknown_tickets), len(tickets))
    if not _is_suggestible(len(unknown_tickets), share, thresholds):
        return []

    return [
        TemplateEvolutionProposal(
            proposal_type=TemplateProposalType.ADD_PRIMARY_CATEGORY,
            title="Investigate recurring unknown ticket pattern",
            rationale=(
                f"{len(unknown_tickets)} tickets ({share:.0%}) do not fit the current "
                "primary taxonomy."
            ),
            evidence_ticket_ids=[ticket.issue_id for ticket in unknown_tickets[:8]],
            proposed_change={
                "candidate_category": "needs_human_taxonomy_review",
                "proposal_level": _proposal_level(len(unknown_tickets), share, thresholds),
                "common_keywords": _common_keywords(unknown_tickets),
            },
            confidence=_proposal_confidence(len(unknown_tickets), share, thresholds),
        )
    ]


def _duplicate_keyword_proposals(
    tickets: list[Ticket],
    thresholds: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    template = load_state_machine()
    subcategory_counter: Counter[str] = Counter()
    evidence: dict[str, list[Ticket]] = defaultdict(list)
    for ticket in tickets:
        classification = classify_ticket(ticket, extract_entities(ticket))
        if classification.primary_category == PrimaryCategory.APPLICATION_ISSUE and classification.subcategory:
            key = classification.subcategory.value
            subcategory_counter[key] += 1
            evidence[key].append(ticket)

    proposals: list[TemplateEvolutionProposal] = []
    for subcategory, count in subcategory_counter.items():
        share = _share(count, len(tickets))
        if not _is_suggestible(count, share, thresholds):
            continue
        if subcategory not in template.application_issue_subcategories:
            continue
        proposals.append(
            TemplateEvolutionProposal(
                proposal_type=TemplateProposalType.IMPROVE_DUPLICATE_EVIDENCE,
                title=f"Strengthen duplicate evidence for {subcategory}",
                rationale=(
                    f"{count} historical tickets ({share:.0%}) share this subcategory; "
                    "review whether duplicate keywords and entity comparisons should be expanded."
                ),
                evidence_ticket_ids=[ticket.issue_id for ticket in evidence[subcategory][:8]],
                proposed_change={
                    "subcategory": subcategory,
                    "candidate_duplicate_keywords": _common_keywords(evidence[subcategory]),
                    "proposal_level": _proposal_level(count, share, thresholds),
                },
                confidence=_proposal_confidence(count, share, thresholds),
            )
        )
    return proposals


def _missing_context_proposals(
    outputs: list[tuple[Ticket, TriageOutput]],
    thresholds: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    missing_outputs = [
        (ticket, output)
        for ticket, output in outputs
        if output.state == TriageState.MISSING_INFO
    ]
    total_missing = len(missing_outputs)
    field_counter: Counter[str] = Counter()
    evidence: dict[str, list[Ticket]] = defaultdict(list)
    for ticket, output in missing_outputs:
        for field in output.missing_fields:
            field_counter[field.field] += 1
            evidence[field.field].append(ticket)

    proposals: list[TemplateEvolutionProposal] = []
    for field, count in field_counter.items():
        share = _share(count, total_missing)
        if count < thresholds.suggest_min_count or share < thresholds.required_field_min_missing_share:
            continue
        proposals.append(
            TemplateEvolutionProposal(
                proposal_type=TemplateProposalType.ADD_CLARIFICATION_TEXT,
                title=f"Improve missing-context handling for {field}",
                rationale=(
                    f"{count} tickets ({share:.0%} of missing-info tickets) were blocked "
                    f"on {field}. This usually means the prompt, extraction rule, or "
                    "required-field rule needs review."
                ),
                evidence_ticket_ids=[ticket.issue_id for ticket in evidence[field][:8]],
                proposed_change={
                    "field": field,
                    "state": TriageState.MISSING_INFO.value,
                    "event_when_missing": _event_for_missing_field(field),
                    "action_when_missing": _action_for_missing_field(field),
                    "proposal_level": _proposal_level(count, share, thresholds),
                    "candidate_prompt_keywords": _common_keywords(evidence[field]),
                },
                confidence=_proposal_confidence(count, share, thresholds),
            )
        )
    return proposals


def _event_for_missing_field(field: str) -> str:
    if field == "issue_summary":
        return TriageEvent.ISSUE_SUMMARY_MISSING.value
    if field == "source_system":
        return TriageEvent.SOURCE_SYSTEM_MISSING.value
    if field == "diagnostic_evidence":
        return TriageEvent.DIAGNOSTIC_EVIDENCE_MISSING.value
    return TriageEvent.MISSING_REQUIRED_FIELDS_DETECTED.value


def _action_for_missing_field(field: str) -> str:
    if field == "issue_summary":
        return "request_issue_summary"
    if field == "source_system":
        return "request_source_system"
    if field == "diagnostic_evidence":
        return "request_diagnostic_evidence"
    return "request_missing_context"


def _routing_gap_proposals(
    outputs: list[tuple[Ticket, TriageOutput]],
    thresholds: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    ambiguous = [
        (ticket, output)
        for ticket, output in outputs
        if output.state == TriageState.HUMAN_REVIEW
        or output.last_event == TriageEvent.ROUTING_UNCLEAR
    ]
    if len(ambiguous) < thresholds.suggest_min_count:
        return []

    assignee_counter: Counter[str] = Counter(
        ticket.known_assignee or "" for ticket, _ in ambiguous if ticket.known_assignee
    )
    if not assignee_counter:
        return []

    assignee, count = assignee_counter.most_common(1)[0]
    share = _share(count, len(ambiguous))
    if count < thresholds.suggest_min_count or share < thresholds.routing_min_same_team_share:
        return []

    evidence = [ticket for ticket, _ in ambiguous if ticket.known_assignee == assignee]
    return [
        TemplateEvolutionProposal(
            proposal_type=TemplateProposalType.CHANGE_ROUTING_HINT,
            title=f"Add routing rule for ambiguous tickets assigned to {assignee}",
            rationale=(
                f"{count} ambiguous tickets ({share:.0%}) were historically assigned to "
                f"{assignee}. The rulebook may need a transition out of human_review or "
                "routing_unclear for this pattern."
            ),
            evidence_ticket_ids=[ticket.issue_id for ticket in evidence[:8]],
            proposed_change={
                "from_state": TriageState.ROUTING_REVIEW.value,
                "current_event": TriageEvent.ROUTING_UNCLEAR.value,
                "suggested_team": assignee,
                "candidate_keywords": _common_keywords(evidence),
                "proposal_level": _proposal_level(count, share, thresholds),
            },
            confidence=_proposal_confidence(count, share, thresholds),
        )
    ]


def _deflection_proposals(
    outputs: list[tuple[Ticket, TriageOutput]],
    thresholds: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    intended_resolution = [
        ticket
        for ticket, output in outputs
        if output.state != TriageState.INTENDED_BEHAVIOR
        and ticket.known_resolution
        and any(
            term in ticket.known_resolution.lower()
            for term in ["intended behavior", "expected behavior", "working as designed"]
        )
    ]
    share = _share(len(intended_resolution), len(outputs))
    if not _is_suggestible(len(intended_resolution), share, thresholds):
        return []

    return [
        TemplateEvolutionProposal(
            proposal_type=TemplateProposalType.ADD_TRANSITION_RULE,
            title="Add or improve intended-behavior deflection rule",
            rationale=(
                f"{len(intended_resolution)} tickets ({share:.0%}) were historically "
                "resolved as intended behavior but were not deflected by the current state machine."
            ),
            evidence_ticket_ids=[ticket.issue_id for ticket in intended_resolution[:8]],
            proposed_change={
                "from_state": TriageState.CHECKING_KNOWN_BEHAVIOR.value,
                "to_state": TriageState.INTENDED_BEHAVIOR.value,
                "suggested_event": "new_deflection_event_to_review",
                "suggested_action_type": "new_deflection_action_to_review",
                "candidate_keywords": _common_keywords(intended_resolution),
                "proposal_level": _proposal_level(len(intended_resolution), share, thresholds),
            },
            confidence=_proposal_confidence(len(intended_resolution), share, thresholds),
        )
    ]


def _new_state_candidate_proposals(
    outputs: list[tuple[Ticket, TriageOutput]],
    thresholds: EvolutionThresholds,
) -> list[TemplateEvolutionProposal]:
    waiting_tickets = [
        ticket
        for ticket, output in outputs
        if output.state == TriageState.HUMAN_REVIEW
        and ticket.known_resolution
        and any(term in ticket.known_resolution.lower() for term in ["waiting", "blocked", "pending"])
    ]
    share = _share(len(waiting_tickets), len(outputs))
    if len(waiting_tickets) < thresholds.new_state_min_count or share < thresholds.new_state_min_share:
        return []

    return [
        TemplateEvolutionProposal(
            proposal_type=TemplateProposalType.ADD_STATE,
            title="Review possible waiting/blocked state",
            rationale=(
                f"{len(waiting_tickets)} tickets ({share:.0%}) appear to represent a "
                "distinct waiting or blocked workflow condition. This may justify a new state."
            ),
            evidence_ticket_ids=[ticket.issue_id for ticket in waiting_tickets[:8]],
            proposed_change={
                "candidate_state": "waiting_condition_to_review",
                "requires_distinct_waiting_condition": True,
                "candidate_keywords": _common_keywords(waiting_tickets),
                "proposal_level": _proposal_level(len(waiting_tickets), share, thresholds),
            },
            confidence=_proposal_confidence(len(waiting_tickets), share, thresholds),
        )
    ]


def propose_template_evolution(
    history: list[Ticket] | None = None,
    thresholds: EvolutionThresholds = DEFAULT_THRESHOLDS,
) -> list[TemplateEvolutionProposal]:
    """Generate human-reviewable state-machine rulebook improvement proposals.

    The evolution agent replays historical tickets through the current state machine
    and proposes changes only when repeated patterns cross conservative thresholds.
    It never mutates the template directly.
    """

    tickets = history or load_sample_tickets()
    if not tickets:
        return []

    outputs = _group_by_output(tickets)
    proposals: list[TemplateEvolutionProposal] = []
    proposals.extend(_primary_taxonomy_proposals(tickets, thresholds))
    proposals.extend(_duplicate_keyword_proposals(tickets, thresholds))
    proposals.extend(_missing_context_proposals(outputs, thresholds))
    proposals.extend(_routing_gap_proposals(outputs, thresholds))
    proposals.extend(_deflection_proposals(outputs, thresholds))
    proposals.extend(_new_state_candidate_proposals(outputs, thresholds))
    return proposals
