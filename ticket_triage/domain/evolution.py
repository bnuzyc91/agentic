"""Template evolution proposal generation."""

from __future__ import annotations

from collections import Counter

from ticket_triage.domain.classification import classify_ticket
from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.loading import load_sample_tickets, load_state_machine
from ticket_triage.schema import (
    PrimaryCategory,
    TemplateEvolutionProposal,
    TemplateProposalType,
    Ticket,
)


def propose_template_evolution(
    history: list[Ticket] | None = None,
) -> list[TemplateEvolutionProposal]:
    """Generate human-reviewable template improvement proposals."""

    tickets = history or load_sample_tickets()
    template = load_state_machine()
    proposals: list[TemplateEvolutionProposal] = []

    unknown_tickets = [
        ticket
        for ticket in tickets
        if classify_ticket(ticket, extract_entities(ticket)).primary_category
        == PrimaryCategory.OTHER_OR_UNKNOWN
    ]
    if len(unknown_tickets) >= 2:
        proposals.append(
            TemplateEvolutionProposal(
                proposal_type=TemplateProposalType.ADD_PRIMARY_CATEGORY,
                title="Investigate recurring unknown ticket pattern",
                rationale="Multiple historical tickets do not fit the current primary taxonomy.",
                evidence_ticket_ids=[ticket.issue_id for ticket in unknown_tickets[:5]],
                proposed_change={"candidate_category": "needs_human_taxonomy_review"},
                confidence=0.62,
            )
        )

    subcategory_counter: Counter[str] = Counter()
    evidence: dict[str, list[str]] = {}
    for ticket in tickets:
        classification = classify_ticket(ticket, extract_entities(ticket))
        if classification.primary_category == PrimaryCategory.APPLICATION_ISSUE and classification.subcategory:
            key = classification.subcategory.value
            subcategory_counter[key] += 1
            evidence.setdefault(key, []).append(ticket.issue_id)

    for subcategory, count in subcategory_counter.items():
        if count >= 2 and subcategory in template.application_issue_subcategories:
            proposals.append(
                TemplateEvolutionProposal(
                    proposal_type=TemplateProposalType.IMPROVE_DUPLICATE_EVIDENCE,
                    title=f"Strengthen duplicate evidence for {subcategory}",
                    rationale=(
                        f"{count} historical tickets share this subcategory; review "
                        "whether duplicate keywords and entity comparisons should be expanded."
                    ),
                    evidence_ticket_ids=evidence[subcategory][:5],
                    proposed_change={"subcategory": subcategory},
                    confidence=0.7,
                )
            )

    return proposals
