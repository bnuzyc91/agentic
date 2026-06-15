"""App Support team hierarchy node.

Primary category: app_support
Subcategories (leaves):
  - access_request       → permission / role provisioning
  - integration_issue    → sync, import/export, API failures
  - ui_workflow_issue    → broken buttons, filters, workflow steps
"""

from __future__ import annotations

from ticket_triage.domain.hierarchy.base import (
    ClassificationNode,
    InternalNode,
    LeafNode,
    Rulebook,
)
from ticket_triage.domain.routing.models import RouteDecision, RouteOutcome
from ticket_triage.schema import (
    ActionType,
    AuditEntry,
    ExtractedEntities,
    RecommendedAction,
    RequiredFieldRule,
    RoutingHint,
    Ticket,
    TriageEvent,
    TriagePhase,
    TriageState,
)

_AS_KEYWORDS = {
    # access signals
    "access request": 0.95,
    "need access": 0.92,
    "grant access": 0.92,
    "request access": 0.92,
    "needs access": 0.92,
    "viewer access": 0.90,
    "viewer role": 0.90,
    "approver role": 0.90,
    "manager role": 0.90,
    "user role": 0.88,
    "permission": 0.85,
    "ldap": 0.88,
    "provision": 0.85,
    # integration / sync signals
    "sync failed": 0.92,
    "sync error": 0.92,
    "not syncing": 0.92,
    "import failed": 0.90,
    "export failed": 0.90,
    "api error": 0.90,
    "api failure": 0.90,
    "sap sync": 0.92,
    "integration": 0.82,
    # ui / workflow signals
    "button disabled": 0.92,
    "cannot click": 0.90,
    "filter broken": 0.90,
    "ui issue": 0.90,
    "screen blank": 0.88,
    "workflow step": 0.88,
}


def _score(text: str, keywords: dict[str, float]) -> float:
    text_lower = text.lower()
    hits = [score for kw, score in keywords.items() if kw in text_lower]
    return max(hits, default=0.0)


def _ticket_text(ticket: Ticket) -> str:
    return " ".join([ticket.title, ticket.description, " ".join(c.body for c in ticket.comments)])


def _simple_route_decision(
    *,
    team: str,
    rule_id: str,
    comment: str,
    module_path: list[str],
    confidence: float = 0.82,
) -> RouteDecision:
    action = RecommendedAction(
        action_type=ActionType.ROUTE_TO_TEAM,
        state=TriageState.ROUTED_TO_TEAM.value,
        team=team,
        comment=comment,
        confidence=confidence,
    )
    return RouteDecision(
        outcome=RouteOutcome.ROUTE_TO_TEAM,
        phase=TriagePhase.ROUTING,
        state=TriageState.ROUTED_TO_TEAM,
        last_event=TriageEvent.ROUTE_MATCHED,
        action_type=ActionType.ROUTE_TO_TEAM,
        module_path=module_path,
        module_state=rule_id,
        recommended_action=action,
        route_target=team,
        route_rule_id=rule_id,
        confidence=confidence,
        audit_evidence=[comment],
        audit=[
            AuditEntry(
                event=TriageEvent.ROUTE_MATCHED,
                from_state=TriageState.ROUTE_DECISION,
                to_state=TriageState.ROUTED_TO_TEAM,
                action_type=ActionType.ROUTE_TO_TEAM,
                rule_id=rule_id,
                reason=comment,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Leaf: access_request
# ---------------------------------------------------------------------------

class _AccessRequestRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="ldap",
                label="LDAP / username",
                prompt="Provide the LDAP ID or username that needs access.",
            ),
            RequiredFieldRule(
                field="user_role",
                label="Requested role",
                prompt="Which role or permission level is being requested (Viewer, Approver, Manager)?",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(team="app-access-admins", reason="Access provisioning request.")

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        return _simple_route_decision(
            team="app-access-admins",
            rule_id="as.access_request",
            comment=(
                "Access provisioning request. Route to app-access-admins to validate "
                "approver identity, role scope, and project assignment before provisioning."
            ),
            module_path=["app_support", "access_request"],
        )


class AccessRequestLeaf(LeafNode):
    @property
    def name(self) -> str:
        return "access_request"

    @property
    def description(self) -> str:
        return "User needs a new role, permission, or access level in the application."

    @property
    def rulebook(self) -> Rulebook:
        return _AccessRequestRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        if entities.ldap or entities.user_role:
            return 0.88
        keywords = {
            "access request": 0.95, "grant access": 0.92, "need access": 0.90,
            "request access": 0.90, "permission": 0.82, "role": 0.72,
            "viewer role": 0.88, "approver role": 0.88, "ldap": 0.85,
            "provision": 0.82, "user role": 0.85,
        }
        return _score(_ticket_text(ticket), keywords)


# ---------------------------------------------------------------------------
# Leaf: integration_issue
# ---------------------------------------------------------------------------

class _IntegrationIssueRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="source_system",
                label="Integration system",
                prompt="Which integration or API is failing (e.g. SAP sync, BuyingHub export)?",
            ),
            RequiredFieldRule(
                field="issue_description",
                label="Error description",
                prompt="Describe the error message or sync failure symptom.",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(team="app-support-integrations", reason="Integration / sync failure.")

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        return _simple_route_decision(
            team="app-support-integrations",
            rule_id="as.integration_issue",
            comment=(
                "Integration or sync failure detected. Route to app-support-integrations "
                "for API error diagnosis and retry coordination."
            ),
            module_path=["app_support", "integration_issue"],
        )


class IntegrationIssueLeaf(LeafNode):
    @property
    def name(self) -> str:
        return "integration_issue"

    @property
    def description(self) -> str:
        return "Sync, import/export, or API integration failure between systems."

    @property
    def rulebook(self) -> Rulebook:
        return _IntegrationIssueRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        keywords = {
            "integration": 0.88, "sync failed": 0.92, "sync error": 0.90,
            "import failed": 0.90, "export failed": 0.90, "api error": 0.88,
            "api failure": 0.90, "webhook": 0.85, "connection failed": 0.85,
            "not syncing": 0.88, "sync issue": 0.88,
        }
        return _score(_ticket_text(ticket), keywords)


# ---------------------------------------------------------------------------
# Leaf: ui_workflow_issue
# ---------------------------------------------------------------------------

class _UIWorkflowRulebook(Rulebook):
    @property
    def required_fields(self) -> list[RequiredFieldRule]:
        return [
            RequiredFieldRule(
                field="affected_link",
                label="Page or screen URL",
                prompt="Provide the page URL or screen name where the issue occurs.",
            ),
            RequiredFieldRule(
                field="issue_description",
                label="Steps to reproduce",
                prompt="Describe the steps to reproduce: what you clicked, what happened, what you expected.",
            ),
        ]

    @property
    def routing_hint(self) -> RoutingHint:
        return RoutingHint(team="app-support-ui", reason="UI or workflow defect.")

    def evaluate(self, ticket: Ticket, entities: ExtractedEntities) -> RouteDecision:
        return _simple_route_decision(
            team="app-support-ui",
            rule_id="as.ui_workflow_issue",
            comment=(
                "UI or application workflow issue detected. Route to app-support-ui for "
                "defect reproduction and front-end investigation."
            ),
            module_path=["app_support", "ui_workflow_issue"],
            confidence=0.78,
        )


class UIWorkflowLeaf(LeafNode):
    @property
    def name(self) -> str:
        return "ui_workflow_issue"

    @property
    def description(self) -> str:
        return "Broken button, filter, page element, or application workflow step."

    @property
    def rulebook(self) -> Rulebook:
        return _UIWorkflowRulebook()

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        keywords = {
            "button": 0.80, "button disabled": 0.88, "cannot click": 0.85,
            "filter": 0.72, "filter broken": 0.85, "page not loading": 0.82,
            "screen blank": 0.82, "workflow": 0.72, "step missing": 0.80,
            "ui issue": 0.88, "interface": 0.70, "dropdown": 0.78,
        }
        return _score(_ticket_text(ticket), keywords)


# ---------------------------------------------------------------------------
# Team internal node
# ---------------------------------------------------------------------------

class AppSupportTeam(InternalNode):
    @property
    def name(self) -> str:
        return "app_support"

    @property
    def description(self) -> str:
        return "Access requests, integration failures, and UI/workflow defects."

    @property
    def children(self) -> list[ClassificationNode]:
        return [AccessRequestLeaf(), IntegrationIssueLeaf(), UIWorkflowLeaf()]

    def matches(self, ticket: Ticket, entities: ExtractedEntities) -> float:
        if entities.ldap or entities.user_role:
            return 0.85
        return _score(_ticket_text(ticket), _AS_KEYWORDS)
