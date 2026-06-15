"""Heuristic entity extraction for annual budget planning tickets."""

from __future__ import annotations

import re

from ticket_triage.domain.parsing import coerce_ticket, extract_urls, ticket_text
from ticket_triage.schema import ExtractedEntities, Ticket


FIELD_ALIASES = {
    "name": "name",
    "ldap": "ldap",
    "portfolio": "portfolio",
    "porfolio": "portfolio",
    "region": "region",
    "user role": "user_role",
    "role": "user_role",
    "project type": "project_type",
    "leads": "leads",
    "lead": "leads",
    "additional context": "additional_context",
    "site": "site",
    "project code": "project_code",
    "project name": "project_name",
    "project currency": "project_currency",
    "currency": "project_currency",
    "affected link": "affected_link",
    "link": "affected_link",
    "source system": "source_system",
    "comparison system": "comparison_system",
    "compared system": "comparison_system",
    "business reason": "business_reason",
    "urgency": "urgency",
    "requested capability": "requested_capability",
}


FIELD_RE = re.compile(
    r"(?im)^\s*(name|ldap|portfolio|porfolio|region|user role|role|project type|"
    r"leads?|additional context|site|project code|project name|project currency|"
    r"currency|affected link|link|source system|comparison system|compared system|"
    r"business reason|urgency|requested capability)"
    r"\s*[:=-]\s*(.+?)\s*$"
)

PO_RE = re.compile(r"\b(?:po|purchase order)\s*#?\s*[:=-]?\s*([a-z0-9-]{4,})\b", re.IGNORECASE)
PROJECT_CODE_RE = re.compile(
    r"\b(?:project\s*(?:id|code)|s-code|scode)\s*[:#=-]?\s*([a-z0-9-]{3,})\b",
    re.IGNORECASE,
)


def _apply_field(entities: ExtractedEntities, field: str, value: str) -> None:
    normalized_value = value.strip().strip(".")
    if not normalized_value:
        return
    if field == "leads":
        entities.leads = [
            item.strip() for item in re.split(r",|;|\band\b", normalized_value) if item.strip()
        ]
        return
    setattr(entities, field, normalized_value)


def _attachment_suggests_screenshot(ticket: Ticket) -> bool:
    screenshot_terms = ("screenshot", "screen shot", ".png", ".jpg", ".jpeg", ".gif")
    for attachment in ticket.attachments:
        haystack = " ".join(
            part or ""
            for part in [
                attachment.filename,
                attachment.kind,
                attachment.description,
                attachment.url,
            ]
        ).lower()
        if any(term in haystack for term in screenshot_terms):
            return True
    return False


def extract_entities(ticket: str | dict | Ticket) -> ExtractedEntities:
    """Extract common entities from a ticket using transparent deterministic rules."""

    parsed_ticket = coerce_ticket(ticket)
    text = ticket_text(parsed_ticket)
    lower_text = text.lower()
    entities = ExtractedEntities()

    for match in FIELD_RE.finditer(text):
        raw_field, value = match.groups()
        _apply_field(entities, FIELD_ALIASES[raw_field.lower()], value)

    urls = list(parsed_ticket.links) + extract_urls(text)
    if urls and not entities.affected_link:
        entities.affected_link = urls[0]
    entities.document_links = sorted(set(urls))

    entities.screenshot_provided = _attachment_suggests_screenshot(parsed_ticket) or (
        "screenshot attached" in lower_text or "screen shot attached" in lower_text
    )

    fiscal_match = re.search(r"\b(20\d{2}|fy\s*\d{2,4}|q[1-4])\b", lower_text)
    if fiscal_match:
        entities.fiscal_period = fiscal_match.group(0).upper().replace(" ", "")

    if not entities.requested_capability and any(
        term in lower_text for term in ["new feature", "add ", "enhancement", "bulk upload"]
    ):
        entities.requested_capability = parsed_ticket.title

    if not entities.issue_description:
        body = parsed_ticket.description.strip()
        if body:
            entities.issue_description = body

    entities.po_numbers = sorted(set(match.group(1) for match in PO_RE.finditer(text)))
    entities.project_codes = sorted(set(match.group(1) for match in PROJECT_CODE_RE.finditer(text)))
    if entities.project_code and entities.project_code not in entities.project_codes:
        entities.project_codes.append(entities.project_code)

    systems = ["sap", "quickbase", "ebuilder", "e-builder", "buyinghub", "cashflow"]
    detected_systems = [system for system in systems if system in lower_text]
    if not entities.source_system and detected_systems:
        entities.source_system = detected_systems[0]
    if not entities.comparison_system and len(detected_systems) > 1:
        entities.comparison_system = detected_systems[1]

    if not entities.additional_context and "additional context" not in lower_text:
        if any(term in lower_text for term in ["access", "role", "permission"]):
            entities.additional_context = parsed_ticket.description.strip() or None

    return entities
