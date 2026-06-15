"""Route module registry."""

from __future__ import annotations

from ticket_triage.domain.routing.modules.data_quality.route_module import DataQualityRouteModule
from ticket_triage.schema import ApplicationIssueSubcategory, PrimaryCategory


def get_route_module(
    primary_category: PrimaryCategory,
    subcategory: ApplicationIssueSubcategory | None,
) -> object | None:
    if (
        primary_category == PrimaryCategory.APPLICATION_ISSUE
        and subcategory == ApplicationIssueSubcategory.DATA_QUALITY_ISSUE
    ):
        return DataQualityRouteModule()
    return None
