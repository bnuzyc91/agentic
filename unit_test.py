from ticket_triage.schema import Ticket
from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.hierarchy.registry import traverse

ticket = Ticket(
    issue_id='TEST-001',
    title='SAP actuals missing from Quickbase for project S-7821',
    description='The actuals are showing in SAP but missing from the Quickbase dashboard. PO: PO-99321.'
)

entities = extract_entities(ticket)
classification, route = traverse(ticket, entities)

print('Team:       ', classification.routing_team.value)
print('Issue type: ', classification.issue_type)
print('Path:       ', classification.path)
print('Confidence: ', classification.confidence)
print('Evidence:   ', classification.evidence)
if route:
    print('Route to:   ', route.route_target)
    print('Action:     ', route.recommended_action.comment)