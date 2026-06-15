"""Generic route engine."""

from __future__ import annotations

from ticket_triage.domain.routing.models import RouteContext, RouteDecision
from ticket_triage.domain.routing.registry import get_route_module


def route_ticket(context: RouteContext) -> RouteDecision | None:
    """Run the registered route module for the ticket category."""

    route_module = get_route_module(context.primary_category, context.subcategory)
    if route_module is None:
        return None
    return route_module.evaluate(context)
