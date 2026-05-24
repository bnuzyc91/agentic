# Data Quality Ticket Triage — State Machine Design


---

## 1. Minimum Viable Context Gate

The first gate for any data quality issue is confirming minimum viable context.

### Required Components

| Field | Requirement |
|-------|-------------|
| `issue_summary` | Required |
| `source_system` | Required |
| `diagnostic_evidence` | At least one of the following |

**Diagnostic evidence** is satisfied if at least one of these is present:

- `po_number`
- `project_code_or_s_code`
- `document_link`
- `screenshot`

### State Transitions

| Current State | Event | Condition | Next State | Action |
|--------------|-------|-----------|------------|--------|
| `NEW` | `ticket_received` | always | `NEW` | Extract fields |
| `NEW` | `source_system_missing` | No source system found | `MISSING_INFO` | Ask for source system |
| `NEW` | `diagnostic_evidence_missing` | No PO / project / link / screenshot | `MISSING_INFO` | Ask for evidence |
| `NEW` | `issue_summary_missing` | No clear discrepancy or request | `MISSING_INFO` | Ask for issue summary |
| `MISSING_INFO` | `reporter_provided_missing_info` | All required context now present | `CONTEXT_VALIDATED` | Continue triage |
| `NEW` | `minimum_context_satisfied` | Summary + source + evidence present | `CONTEXT_VALIDATED` | Proceed to deflection / routing |

---

## 2. Intended Behavior Deflection

Before routing to engineering, check whether the reported issue matches a known, expected behavior pattern.

**Known deflection categories:**

- `external_sync_lag`
- `app_view_filter_mismatch`
- `historical_data_logic`

### State Transitions

| Current State | Event | Condition | Next State | Action |
|--------------|-------|-----------|------------|--------|
| `CONTEXT_VALIDATED` | `known_sync_lag_detected` | Mismatch likely due to batch sync delay | `INTENDED_BEHAVIOR` | Explain sync delay |
| `CONTEXT_VALIDATED` | `view_filter_mismatch_detected` | Difference due to active filters | `INTENDED_BEHAVIOR` | Explain filter behavior |
| `CONTEXT_VALIDATED` | `historical_logic_detected` | TLY / prior year archival behavior | `INTENDED_BEHAVIOR` | Explain historical data logic |
| `INTENDED_BEHAVIOR` | `explanation_sent` | Response drafted / sent | `COMPLETE` or `WAITING_REPORTER_CONFIRMATION` | Wait for confirmation or close |

---

## 3. Routing Logic After Validation

Once context is validated and the issue is not deflected, route based on issue type.

### Routing Paths

```json
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
```

### State Transitions

| Current State | Event | Condition | Next State | Action |
|--------------|-------|-----------|------------|--------|
| `CONTEXT_VALIDATED` | `finance_policy_issue_detected` | Accrual / currency / FX / SAP finance terms | `ROUTED_FINANCE` | Route to finance queue |
| `CONTEXT_VALIDATED` | `integration_issue_detected` | Sync / pipeline / complex integration terms | `ROUTED_CRC_L3` | Route to CRC / L3 |
| `CONTEXT_VALIDATED` | `data_stewardship_issue_detected` | Data entry / merge / void / config issue | `ROUTED_DATA_QUALITY` | Route to data quality team |
| `CONTEXT_VALIDATED` | `routing_unclear` | No confident route | `MISSING_INFO` or `HUMAN_REVIEW` | Ask for clarification or escalate |

---

## 4. Recommended Action Types

Actions must come from the predefined enum below — the agent cannot invent new action types.

```
EXTRACT_CONTEXT
REQUEST_INFO
DEFLECT_INTENDED_BEHAVIOR
ROUTE_FINANCE
ROUTE_CRC_L3
ROUTE_DATA_QUALITY
WAIT_CONFIRMATION
CLOSE_TICKET
ESCALATE_HUMAN_REVIEW
```

### Example Action Object

```json
{
  "type": "REQUEST_INFO",
  "comment_template": "ask_for_evidence",
  "next_assignee": "reporter",
  "message": "Please provide a PO number, project ID/S-code, linked report, or screenshot so the team can locate the discrepancy."
}
```
---

# Alternative Approach — One Unified Transition Map Across Phases

Rather than separate tables per phase, a single transition map covers the full workflow. Each row carries its phase as a column so the map remains one source of truth.

**Concept definitions:**

| Term | Meaning |
|------|---------|
| `phase` | Broad section of the workflow |
| `state` | Exact machine state (predefined enum) |
| `event` | What just happened / which rule fired |
| `recommended_action.type` | What the agent should suggest next |

---

## 1. State Map by Phase

| Phase | State | Meaning |
|-------|-------|---------|
| `INTAKE` | `NEW` | Ticket has arrived but has not been analyzed |
| `INTAKE` | `EXTRACTING_CONTEXT` | Agent extracts summary, systems, IDs, links, screenshot flags |
| `CONTEXT_VALIDATION` | `MISSING_INFO` | Minimum viable context is not satisfied |
| `CONTEXT_VALIDATION` | `CONTEXT_VALIDATED` | Required context is present |
| `DEFLECTION` | `CHECKING_KNOWN_BEHAVIOR` | Agent checks whether this is expected behavior |
| `DEFLECTION` | `INTENDED_BEHAVIOR` | Issue matches documented expected behavior |
| `ROUTING` | `ROUTING_REVIEW` | Context is valid and issue needs a team route |
| `ROUTING` | `ROUTED_FINANCE` | Routed to finance / policy team |
| `ROUTING` | `ROUTED_CRC_L3` | Routed to CRC / L3 engineering / support |
| `ROUTING` | `ROUTED_DATA_QUALITY` | Routed to data quality / stewardship team |
| `RESOLUTION` | `WAITING_FIX` | Ticket is assigned and waiting for fix / remediation |
| `RESOLUTION` | `WAITING_REPORTER_CONFIRMATION` | Fix / explanation sent; waiting for reporter confirmation |
| `CLOSURE` | `COMPLETE` | Work is functionally complete |
| `CLOSURE` | `CLOSED` | Ticket is formally closed |
| `EXCEPTION` | `HUMAN_REVIEW` | Rulebook cannot confidently decide |

---

## 2. Events by Group

**Intake / Context Events**
- `ticket_created`
- `context_extraction_started`
- `issue_summary_extracted`
- `source_system_extracted`
- `diagnostic_evidence_extracted`
- `minimum_context_satisfied`
- `issue_summary_missing`
- `source_system_missing`
- `diagnostic_evidence_missing`
- `reporter_provided_missing_info`
- `reporter_response_insufficient`
- `no_reporter_response`

**Diagnostic Evidence Events**
- `po_number_found`
- `project_code_found`
- `document_link_found`
- `screenshot_found`
- `diagnostic_evidence_satisfied`
- `diagnostic_evidence_not_found`

**Deflection Events**
- `known_behavior_check_started`
- `external_sync_lag_detected`
- `app_view_filter_mismatch_detected`
- `historical_data_logic_detected`
- `known_behavior_not_matched`
- `intended_behavior_explanation_sent`

**Routing Events**
- `routing_review_started`
- `finance_policy_issue_detected`
- `integration_issue_detected`
- `data_stewardship_issue_detected`
- `routing_unclear`
- `route_confirmed`

**Resolution / Closure Events**
- `fix_applied`
- `explanation_sent`
- `reporter_confirmed_resolved`
- `reporter_reports_not_resolved`
- `inactivity_timeout_reached`
- `ticket_closed`
- `ticket_reopened`
- `human_override`

---

## 3. Recommended Action Types

- `EXTRACT_CONTEXT`
- `REQUEST_ISSUE_SUMMARY`
- `REQUEST_SOURCE_SYSTEM`
- `REQUEST_DIAGNOSTIC_EVIDENCE`
- `REQUEST_MISSING_CONTEXT`
- `DEFLECT_SYNC_LAG`
- `DEFLECT_VIEW_FILTERS`
- `DEFLECT_HISTORICAL_DATA_LOGIC`
- `ROUTE_FINANCE`
- `ROUTE_CRC_L3`
- `ROUTE_DATA_QUALITY`
- `ASK_ROUTING_CLARIFICATION`
- `WAIT_FOR_FIX`
- `ASK_REPORTER_TO_CONFIRM`
- `CLOSE_AS_RESOLVED`
- `ESCALATE_HUMAN_REVIEW`

---

## 4. Full Transition Map

| Phase | From State | Event | Condition | To State | Recommended Action |
|-------|-----------|-------|-----------|----------|--------------------|
| INTAKE | `NEW` | `ticket_created` | always | `EXTRACTING_CONTEXT` | `EXTRACT_CONTEXT` |
| INTAKE | `EXTRACTING_CONTEXT` | `issue_summary_missing` | No clear discrepancy / request | `MISSING_INFO` | `REQUEST_ISSUE_SUMMARY` |
| INTAKE | `EXTRACTING_CONTEXT` | `source_system_missing` | No source / comparison system | `MISSING_INFO` | `REQUEST_SOURCE_SYSTEM` |
| INTAKE | `EXTRACTING_CONTEXT` | `diagnostic_evidence_missing` | No PO / project / link / screenshot | `MISSING_INFO` | `REQUEST_DIAGNOSTIC_EVIDENCE` |
| INTAKE | `EXTRACTING_CONTEXT` | `minimum_context_satisfied` | Summary + source + evidence present | `CONTEXT_VALIDATED` | `EXTRACT_CONTEXT` |
| CONTEXT_VALIDATION | `MISSING_INFO` | `reporter_provided_missing_info` | All required context now satisfied | `CONTEXT_VALIDATED` | `EXTRACT_CONTEXT` |
| CONTEXT_VALIDATION | `MISSING_INFO` | `reporter_response_insufficient` | Still missing required context | `MISSING_INFO` | `REQUEST_MISSING_CONTEXT` |
| CONTEXT_VALIDATION | `MISSING_INFO` | `no_reporter_response` | Timeout | `HUMAN_REVIEW` or `CLOSED` | `ESCALATE_HUMAN_REVIEW` |
| DEFLECTION | `CONTEXT_VALIDATED` | `known_behavior_check_started` | Always before routing | `CHECKING_KNOWN_BEHAVIOR` | `EXTRACT_CONTEXT` |
| DEFLECTION | `CHECKING_KNOWN_BEHAVIOR` | `external_sync_lag_detected` | Batch sync lag likely | `INTENDED_BEHAVIOR` | `DEFLECT_SYNC_LAG` |
| DEFLECTION | `CHECKING_KNOWN_BEHAVIOR` | `app_view_filter_mismatch_detected` | Dashboard / filter mismatch likely | `INTENDED_BEHAVIOR` | `DEFLECT_VIEW_FILTERS` |
| DEFLECTION | `CHECKING_KNOWN_BEHAVIOR` | `historical_data_logic_detected` | TLY / prior-year archival logic | `INTENDED_BEHAVIOR` | `DEFLECT_HISTORICAL_DATA_LOGIC` |
| DEFLECTION | `CHECKING_KNOWN_BEHAVIOR` | `known_behavior_not_matched` | Not deflectable | `ROUTING_REVIEW` | `EXTRACT_CONTEXT` |
| ROUTING | `ROUTING_REVIEW` | `finance_policy_issue_detected` | Accruals / currency / FX / SAP finance records | `ROUTED_FINANCE` | `ROUTE_FINANCE` |
| ROUTING | `ROUTING_REVIEW` | `integration_issue_detected` | Sync failure / pipeline / integration / crash | `ROUTED_CRC_L3` | `ROUTE_CRC_L3` |
| ROUTING | `ROUTING_REVIEW` | `data_stewardship_issue_detected` | Merge / void / data entry / config | `ROUTED_DATA_QUALITY` | `ROUTE_DATA_QUALITY` |
| ROUTING | `ROUTING_REVIEW` | `routing_unclear` | No confident route | `HUMAN_REVIEW` | `ESCALATE_HUMAN_REVIEW` |
| RESOLUTION | `ROUTED_*` | `fix_applied` | Fix / remediation completed | `WAITING_REPORTER_CONFIRMATION` | `ASK_REPORTER_TO_CONFIRM` |
| RESOLUTION | `INTENDED_BEHAVIOR` | `intended_behavior_explanation_sent` | Explanation sent | `WAITING_REPORTER_CONFIRMATION` | `ASK_REPORTER_TO_CONFIRM` |
| RESOLUTION | `WAITING_REPORTER_CONFIRMATION` | `reporter_confirmed_resolved` | Reporter confirms | `COMPLETE` | `CLOSE_AS_RESOLVED` |
| RESOLUTION | `WAITING_REPORTER_CONFIRMATION` | `reporter_reports_not_resolved` | Reporter still sees issue | `HUMAN_REVIEW` | `ESCALATE_HUMAN_REVIEW` |
| RESOLUTION | `WAITING_REPORTER_CONFIRMATION` | `inactivity_timeout_reached` | No response after policy window | `COMPLETE` | `CLOSE_AS_RESOLVED` |
| CLOSURE | `COMPLETE` | `ticket_closed` | Ticket formally closed | `CLOSED` | `CLOSE_AS_RESOLVED` |
| CLOSURE | `CLOSED` | `ticket_reopened` | Reporter reopens | `EXTRACTING_CONTEXT` | `EXTRACT_CONTEXT` |

---

## 5. Abstract State Object

```json
{
  "ticket_id": "BUG-123",
  "rulebook": "data_quality_v1",
  "category": "DATA_QUALITY",
  "phase": "CONTEXT_VALIDATION",
  "state": "MISSING_INFO",
  "last_event": "diagnostic_evidence_missing",

  "entities": {
    "issue_summary": "Quickbase cashflow is missing a PO record",
    "source_system": "SAP",
    "comparison_system": "Quickbase",
    "po_numbers": [],
    "project_codes": [],
    "document_links": [],
    "has_screenshot": false
  },

  "validation": {
    "minimum_context_satisfied": false,
    "missing_fields": ["diagnostic_evidence"],
    "diagnostic_evidence_satisfied": false
  },

  "known_behavior": {
    "matched": false,
    "type": null
  },

  "routing": {
    "route_target": null,
    "route_reason": null
  },

  "recommended_action": {
    "type": "REQUEST_DIAGNOSTIC_EVIDENCE",
    "comment_template": "ask_for_evidence",
    "next_assignee": "reporter",
    "message": "Please provide a PO number, project ID/S-code, linked report, or screenshot so the team can locate the discrepancy."
  },

  "audit": [
    {
      "from_state": "EXTRACTING_CONTEXT",
      "event": "diagnostic_evidence_missing",
      "to_state": "MISSING_INFO",
      "rule_id": "minimum_context.diagnostic_evidence",
      "reason": "No PO number, project code, document link, or screenshot was found."
    }
  ]
}
```