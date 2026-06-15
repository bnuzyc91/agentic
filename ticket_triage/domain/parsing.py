"""Shared ticket parsing and text helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from ticket_triage.schema import Ticket


WORD_RE = re.compile(r"[a-z0-9]+")
URL_RE = re.compile(r"https?://[^\s)>\"]+", re.IGNORECASE)


def coerce_ticket(ticket: str | Mapping[str, Any] | Ticket) -> Ticket:
    """Accept JSON strings, dictionaries, or Ticket models."""

    if isinstance(ticket, Ticket):
        return ticket
    if isinstance(ticket, str):
        return Ticket.model_validate(json.loads(ticket))
    return Ticket.model_validate(dict(ticket))


def ticket_text(ticket: Ticket) -> str:
    comments = "\n".join(comment.body for comment in ticket.comments)
    return "\n".join([ticket.title, ticket.description, comments]).strip()


def tokenize(text: str) -> set[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "please",
        "app",
        "application",
        "ticket",
        "need",
        "issue",
    }
    return {word for word in WORD_RE.findall(text.lower()) if word not in stop_words}


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def normalized_text(ticket: Ticket) -> str:
    return ticket_text(ticket).lower()
