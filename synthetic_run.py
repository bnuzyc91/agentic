from ticket_triage.schema import Ticket
from ticket_triage.domain.extraction import extract_entities
from ticket_triage.domain.hierarchy.registry import traverse
from ticket_triage.data.synthetic.generator import get_labelled_tickets

for raw in get_labelled_tickets():
    ticket = Ticket(**{k: v for k, v in raw.items() if not k.startswith('_')})
    entities = extract_entities(ticket)
    classification, route = traverse(ticket, entities)
    team = classification.routing_team.value
    issue = classification.issue_type
    action = route.recommended_action.action_type.value if route else 'no_leaf_reached'
    print(f'{ticket.issue_id:15} → {team}/{issue} | {action}')

