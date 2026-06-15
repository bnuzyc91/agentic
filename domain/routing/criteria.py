"""Reusable criteria helpers for route modules."""

from __future__ import annotations

from ticket_triage.schema import Ticket


def ticket_text(ticket: Ticket) -> str:
    comments = " ".join(comment.body for comment in ticket.comments)
    return f"{ticket.title} {ticket.description} {comments}".lower()


def contains_any(text: str, keywords: list[str]) -> bool:
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in keywords)
