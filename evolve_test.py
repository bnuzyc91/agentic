from ticket_triage.domain.evolution import propose_hierarchy_evolution, EvolutionThresholds
from ticket_triage.schema import Ticket

# Simulate 5 tickets about a pattern the hierarchy doesn't know yet
unknown_tickets = [
    Ticket(
        issue_id=f'UNK-{i}',
        title='User cannot export approved budget to Excel',
        description='The export to Excel button on the approved budget screen does nothing. No error shown.',
    )
    for i in range(5)
]

proposals = propose_hierarchy_evolution(
    history=unknown_tickets,
    thresholds=EvolutionThresholds(suggest_min_count=5, suggest_min_share=0.10),
)

for p in proposals:
    print(p.proposal_type, '|', p.title)
    print('  rationale:', p.rationale)
    print('  change:', p.proposed_change)
    print()