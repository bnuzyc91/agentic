"""Local duplicate detection over sample or historical tickets."""

from __future__ import annotations

from difflib import SequenceMatcher

from ticket_triage.domain.classification import classify_ticket
from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.loading import load_sample_tickets
from ticket_triage.domain.parsing import coerce_ticket, normalized_text, tokenize
from ticket_triage.schema import DuplicateCandidate, ExtractedEntities, Ticket


def _safe_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _entity_overlap(current: ExtractedEntities, candidate: ExtractedEntities) -> float:
    fields = [
        "portfolio",
        "region",
        "site",
        "project_code",
        "project_name",
        "project_currency",
        "affected_link",
    ]
    comparable = 0
    matches = 0
    for field in fields:
        current_value = getattr(current, field)
        candidate_value = getattr(candidate, field)
        if current_value and candidate_value:
            comparable += 1
            if str(current_value).lower() == str(candidate_value).lower():
                matches += 1
    if comparable == 0:
        return 0.0
    return matches / comparable


def score_duplicate(current: Ticket, candidate: Ticket) -> tuple[float, str]:
    """Score whether candidate is likely a duplicate of current."""

    current_entities = extract_entities(current)
    candidate_entities = extract_entities(candidate)
    current_class = classify_ticket(current, current_entities)
    candidate_class = classify_ticket(candidate, candidate_entities)

    title_score = _safe_ratio(current.title, candidate.title)
    text_score = _jaccard(tokenize(normalized_text(current)), tokenize(normalized_text(candidate)))
    entity_score = _entity_overlap(current_entities, candidate_entities)
    category_score = (
        1.0
        if current_class.primary_category == candidate_class.primary_category
        and current_class.subcategory == candidate_class.subcategory
        else 0.0
    )

    score = (
        title_score * 0.28
        + text_score * 0.27
        + entity_score * 0.3
        + category_score * 0.15
    )
    rationale = (
        f"title={title_score:.2f}, text={text_score:.2f}, "
        f"entities={entity_score:.2f}, category={category_score:.2f}"
    )
    return round(min(score, 1.0), 3), rationale


def find_similar_tickets(
    ticket: str | dict | Ticket,
    limit: int = 3,
    threshold: float = 0.45,
    history: list[Ticket] | None = None,
) -> list[DuplicateCandidate]:
    """Return likely duplicate candidates from local ticket history."""

    parsed_ticket = coerce_ticket(ticket)
    candidates: list[DuplicateCandidate] = []
    for historical_ticket in history or load_sample_tickets():
        if historical_ticket.issue_id == parsed_ticket.issue_id:
            continue
        score, rationale = score_duplicate(parsed_ticket, historical_ticket)
        if score >= threshold:
            candidates.append(
                DuplicateCandidate(
                    issue_id=historical_ticket.issue_id,
                    score=score,
                    title=historical_ticket.title,
                    rationale=rationale,
                )
            )
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[:limit]
