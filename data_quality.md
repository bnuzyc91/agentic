2. mandatory context state logic

For this data quality issue, the first gate is minimum viable context.

Required components:
{
  "issue_summary": "required",
  "source_system": "required",
  "diagnostic_evidence": "at_least_one"
}

Diagnostic evidence is satisfied if at least one exists:

[
  "po_number",
  "project_code_or_s_code",
  "document_link",
  "screenshot"
]

So the state transition is:

Current State	Event	Condition	Next State	Action
NEW	ticket_received	always	NEW	extract fields
NEW	source_system_missing	no source system found	MISSING_INFO	ask for source system
NEW	diagnostic_evidence_missing	no PO/project/link/screenshot	MISSING_INFO	ask for evidence
NEW	issue_summary_missing	no clear discrepancy/request	MISSING_INFO	ask for issue summary
MISSING_INFO	reporter_provided_missing_info	all required context now present	CONTEXT_VALIDATED	continue triage
NEW	minimum_context_satisfied	summary + source + evidence present	CONTEXT_VALIDATED	proceed to deflection/routing


3. Intended Behavior Deflection
Before routing to engineering, check known issues.

[
  "external_sync_lag",
  "app_view_filter_mismatch",
  "historical_data_logic"
]
Transitions:

Current State	Event	Condition	Next State	Action
CONTEXT_VALIDATED	known_sync_lag_detected	mismatch likely due to batch sync delay	INTENDED_BEHAVIOR	explain sync delay
CONTEXT_VALIDATED	view_filter_mismatch_detected	difference due to filters	INTENDED_BEHAVIOR	explain filter behavior
CONTEXT_VALIDATED	historical_logic_detected	TLY/prior year archival behavior	INTENDED_BEHAVIOR	explain historical data logic
INTENDED_BEHAVIOR	explanation_sent	response drafted/sent	COMPLETE or WAITING_REPORTER_CONFIRMATION	wait or close
4. Routing Logic After Validation
Once context is validated and not deflected, route based on issue type.

Routing paths:

{
  "finance": [
    "accruals",
    "currency codes",
    "FX rates",
    "financial policies",
    "SAP financial records"
  ],
  "crc_l3": [
    "sync failure",
    "pipeline error",
    "SAP-to-Quickbase integration drops",
    "software crash",
    "complex logic"
  ],
  "data_quality": [
    "data entry error",
    "merge project",
    "void project",
    "minor configuration adjustment"
  ]
}
Transitions:

Current State	Event	Condition	Next State	Action
CONTEXT_VALIDATED	finance_policy_issue_detected	accrual/currency/FX/SAP finance terms	ROUTED_FINANCE	route to finance queue
CONTEXT_VALIDATED	integration_issue_detected	sync/pipeline/complex integration terms	ROUTED_CRC_L3	route to CRC/L3
CONTEXT_VALIDATED	data_stewardship_issue_detected	data entry/merge/void/config issue	ROUTED_DATA_QUALITY	route to data quality team
CONTEXT_VALIDATED	routing_unclear	no confident route	MISSING_INFO or HUMAN_REVIEW	ask clarification or escalate
5. Recommended Actions
Actions should be predefined.

Recommended  action type enum:

[
  "EXTRACT_CONTEXT",
  "REQUEST_INFO",
  "DEFLECT_INTENDED_BEHAVIOR",
  "ROUTE_FINANCE",
  "ROUTE_CRC_L3",
  "ROUTE_DATA_QUALITY",
  "WAIT_CONFIRMATION",
  "CLOSE_TICKET",
  "ESCALATE_HUMAN_REVIEW"
]

{
  "type": "REQUEST_INFO",
  "comment_template": "ask_for_evidence",
  "next_assignee": "reporter",
  "message": "Please provide a PO number, project ID/S-code, linked report, or screenshot so the team can locate the discrepancy."
}