"""Ticket category and subcategory classification."""

from __future__ import annotations

from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.parsing import coerce_ticket, normalized_text
from ticket_triage.schema import (
    ApplicationIssueSubcategory,
    ClassificationResult,
    ExtractedEntities,
    PrimaryCategory,
    Ticket,
)


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _classify_application_subcategory(text: str) -> tuple[ApplicationIssueSubcategory | None, list[str]]:
    if _contains_any(text, ["variance", "forecast", "q1", "q2", "q3", "q4", "currency"]):
        return ApplicationIssueSubcategory.BUDGET_VARIANCE_ISSUE, ["Budget variance or forecast terms found."]
    if _contains_any(text, ["report", "download", "view", "timeout", "slow", "performance"]):
        return ApplicationIssueSubcategory.REPORT_PERFORMANCE_ISSUE, ["Report view/download/performance terms found."]
    if _contains_any(
        text,
        [
            "missing data",
            "missing record",
            "missing po",
            "stale",
            "inconsistent",
            "wrong data",
            "incorrect data",
            "data discrepancy",
            "quickbase",
            "cashflow",
            "sap",
            "buyinghub",
            "ebuilder",
            "e-builder",
        ],
    ):
        return ApplicationIssueSubcategory.DATA_QUALITY_ISSUE, ["Data quality terms found."]
    if _contains_any(text, ["button", "filter", "page", "screen", "workflow", "disabled"]):
        return ApplicationIssueSubcategory.UI_WORKFLOW_ISSUE, ["UI workflow terms found."]
    if _contains_any(text, ["sync", "import", "export", "api", "integration"]):
        return ApplicationIssueSubcategory.INTEGRATION_ISSUE, ["Integration terms found."]
    return None, []


def classify_ticket(
    ticket: str | dict | Ticket,
    entities: ExtractedEntities | dict | None = None,
) -> ClassificationResult:
    """Classify a ticket into primary category and optional application subcategory."""

    parsed_ticket = coerce_ticket(ticket)
    parsed_entities = (
        ExtractedEntities.model_validate(entities)
        if isinstance(entities, dict)
        else entities or extract_entities(parsed_ticket)
    )

    if parsed_ticket.known_primary_category:
        return ClassificationResult(
            primary_category=parsed_ticket.known_primary_category,
            subcategory=parsed_ticket.known_subcategory,
            confidence=0.98,
            evidence=["Known historical category supplied on ticket."],
        )

    text = normalized_text(parsed_ticket)
    evidence: list[str] = []

    if "duplicate" in parsed_ticket.labels or _contains_any(text, ["duplicate of", "same as ticket"]):
        return ClassificationResult(
            primary_category=PrimaryCategory.DUPLICATE,
            subcategory=parsed_ticket.known_subcategory,
            confidence=0.92,
            evidence=["Ticket text or labels explicitly mention duplicate."],
        )

    if _contains_any(text, ["working as designed", "as designed", "intended behavior", "expected behavior"]):
        return ClassificationResult(
            primary_category=PrimaryCategory.INTENDED_BEHAVIOR,
            confidence=0.9,
            evidence=["Ticket text indicates intended behavior."],
        )

    if _contains_any(text, ["new feature", "enhancement", "add ", "bulk upload", "functionality"]):
        return ClassificationResult(
            primary_category=PrimaryCategory.FEATURE_REQUEST,
            confidence=0.84,
            evidence=["Feature or enhancement request terms found."],
        )

    access_terms = ["access", "permission", "role", "viewer", "approver", "manager"]
    if parsed_entities.ldap or parsed_entities.user_role or _contains_any(text, access_terms):
        return ClassificationResult(
            primary_category=PrimaryCategory.ACCESS_REQUEST,
            confidence=0.86,
            evidence=["Access, permission, role, or LDAP indicators found."],
        )

    issue_terms = [
        "bug",
        "error",
        "unable",
        "cannot",
        "can't",
        "fail",
        "fails",
        "incorrect",
        "wrong",
        "slow",
        "missing",
        "mismatch",
        "discrepancy",
        "quickbase",
        "sap",
        "cashflow",
        "disabled",
        "variance",
        "report",
    ]
    if _contains_any(text, issue_terms):
        subcategory, subcategory_evidence = _classify_application_subcategory(text)
        evidence.extend(subcategory_evidence or ["Application issue terms found."])
        return ClassificationResult(
            primary_category=PrimaryCategory.APPLICATION_ISSUE,
            subcategory=subcategory,
            confidence=0.82 if subcategory else 0.74,
            evidence=evidence,
        )

    return ClassificationResult(
        primary_category=PrimaryCategory.OTHER_OR_UNKNOWN,
        confidence=0.45,
        evidence=["No strong category indicators found."],
    )
