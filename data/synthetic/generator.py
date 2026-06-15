"""Synthetic ticket generator for the classification hierarchy.

Generates a labelled dataset of tickets covering:
  - data_engineering × {data_quality_issue, pipeline_failure, schema_change}
  - finance_platform  × {budget_variance_issue, report_performance_issue, forecast_discrepancy}
  - app_support       × {access_request, integration_issue, ui_workflow_issue}
  - edge cases: missing required fields, near-duplicate pairs, ambiguous/unknown

Run directly to write synthetic_tickets.jsonl next to this file:
    python -m ticket_triage.data.synthetic.generator
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Raw ticket definitions
# ---------------------------------------------------------------------------
# Each entry maps 1-to-1 onto the Ticket schema.  The `_expected_team` and
# `_expected_issue_type` keys are metadata for test assertions; they are
# stripped before writing the jsonl file.

_TICKETS: list[dict[str, Any]] = [
    # ── DATA ENGINEERING / data_quality_issue ──────────────────────────────
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "data_quality_issue",
        "issue_id": "SYN-DE-001",
        "reporter": "laura@example.com",
        "title": "SAP actuals missing from Quickbase for project S-7821",
        "description": (
            "The actuals for project S-7821 are showing in SAP but are completely "
            "missing from the Quickbase dashboard. The discrepancy started on 2026-06-01 "
            "after the monthly sync. PO: PO-99321."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["data_quality"],
    },
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "data_quality_issue",
        "issue_id": "SYN-DE-002",
        "reporter": "james@example.com",
        "title": "Wrong data in cashflow report — BuyingHub values differ from SAP",
        "description": (
            "The cashflow report shows different commitment values than what SAP has. "
            "Source system: BuyingHub. Project code: S-4421. The mismatch is ~$120K "
            "for Q2 FY2026. Screenshot attached."
        ),
        "comments": [{"author": "james@example.com", "body": "This is affecting month-end close."}],
        "attachments": [{"filename": "cashflow_diff.png", "kind": "screenshot"}],
        "links": [],
        "labels": ["data_quality", "urgent"],
    },
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "data_quality_issue",
        "issue_id": "SYN-DE-003",
        "reporter": "priya@example.com",
        "title": "Inconsistent project costs between eBuilder and reporting dashboard",
        "description": (
            "Project S-3310 shows $2.1M in eBuilder but $1.9M in our reporting dashboard. "
            "This is an inconsistent data issue. Source system: eBuilder. "
            "Document link: https://internal/ebuilder/s3310"
        ),
        "comments": [],
        "attachments": [],
        "links": ["https://internal/ebuilder/s3310"],
        "labels": [],
    },
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "data_quality_issue",
        "issue_id": "SYN-DE-004",
        "reporter": "ming@example.com",
        "title": "Missing PO record in data warehouse — PO-88123 not found",
        "description": (
            "PO-88123 was approved in SAP two days ago but is not appearing in the "
            "data warehouse or any downstream reports. Missing record from source system SAP."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["data_quality"],
    },
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "data_quality_issue",
        "issue_id": "SYN-DE-005",
        "reporter": "tatiana@example.com",
        "title": "Stale data in dashboard — Quickbase not refreshing",
        "description": (
            "The Quickbase data in our planning tool hasn't updated since last Thursday. "
            "The stale data is causing incorrect variance calculations. No POs to cite, "
            "but the project code is S-6612. Source system: Quickbase."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": [],
    },
    # ── DATA ENGINEERING / pipeline_failure ────────────────────────────────
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "pipeline_failure",
        "issue_id": "SYN-DE-006",
        "reporter": "devops@example.com",
        "title": "Airflow DAG sap_actuals_daily failed — no data loaded since midnight",
        "description": (
            "The pipeline sap_actuals_daily has not completed since the 00:00 run. "
            "DAG status shows 'failed' with a connection timeout to the SAP extractor. "
            "Downstream tables are stale."
        ),
        "comments": [{"author": "oncall@example.com", "body": "Investigating the Airflow job now."}],
        "attachments": [],
        "links": [],
        "labels": ["pipeline", "incident"],
    },
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "pipeline_failure",
        "issue_id": "SYN-DE-007",
        "reporter": "alex@example.com",
        "title": "ETL batch job failed — eBuilder data load did not complete",
        "description": (
            "The nightly ETL data load from eBuilder failed at step 3 (transformation). "
            "Error: NullPointerException in column mapping. Job failed at 02:15 UTC."
        ),
        "comments": [],
        "attachments": [{"filename": "etl_error.log", "kind": "log"}],
        "links": [],
        "labels": ["etl", "pipeline"],
    },
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "pipeline_failure",
        "issue_id": "SYN-DE-008",
        "reporter": "sonia@example.com",
        "title": "dbt model run failing — finance_actuals model errors on currency conversion",
        "description": (
            "The dbt pipeline for finance_actuals is failing during the currency conversion "
            "step. The job failed with: 'Division by zero in exchange_rate column'. "
            "This is blocking the weekly reporting pipeline."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["dbt", "pipeline"],
    },
    # ── DATA ENGINEERING / schema_change ───────────────────────────────────
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "schema_change",
        "issue_id": "SYN-DE-009",
        "reporter": "architect@example.com",
        "title": "Breaking schema change in SAP — column 'cost_center_code' removed",
        "description": (
            "SAP upstream team notified us that the column 'cost_center_code' has been "
            "removed from the extract. This is a breaking schema change that will break "
            "our mapping tables and downstream dbt models."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["schema_change", "breaking_change"],
    },
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "schema_change",
        "issue_id": "SYN-DE-010",
        "reporter": "data.contracts@example.com",
        "title": "Data contract update — new column added to BuyingHub PO export",
        "description": (
            "BuyingHub is adding the column 'vendor_country_code' to the PO export schema "
            "starting next Monday. Need to update the column added mapping and validate "
            "that the data contract is not broken for downstream consumers."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["schema_change"],
    },
    # ── FINANCE PLATFORM / budget_variance_issue ───────────────────────────
    {
        "_expected_team": "finance_platform",
        "_expected_issue_type": "budget_variance_issue",
        "issue_id": "SYN-FP-001",
        "reporter": "controller@example.com",
        "title": "Budget variance on project S-9910 — actuals $340K over budget",
        "description": (
            "Project S-9910 is showing a budget variance of $340K over the approved budget "
            "for Q2 FY2026. The actuals in the system do not reconcile with the approved "
            "cost center allocation. Please investigate."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["finance", "budget_variance"],
    },
    {
        "_expected_team": "finance_platform",
        "_expected_issue_type": "budget_variance_issue",
        "issue_id": "SYN-FP-002",
        "reporter": "pm@example.com",
        "title": "Q3 variance report shows wrong actuals for cost center CC-4412",
        "description": (
            "The Q3 budget variance report is showing actuals that differ from what our "
            "finance team has reconciled. Cost center CC-4412, fiscal period Q3 FY2026. "
            "Delta is approximately -$80K. We need a journal entry review."
        ),
        "comments": [{"author": "finance@example.com", "body": "Confirmed — the variance reconciliation is off."}],
        "attachments": [],
        "links": [],
        "labels": ["variance"],
    },
    {
        "_expected_team": "finance_platform",
        "_expected_issue_type": "budget_variance_issue",
        "issue_id": "SYN-FP-003",
        "reporter": "director@example.com",
        "title": "Over budget flag on project S-2201 — need reconciliation",
        "description": (
            "Project S-2201 is flagged as over budget in the planning tool but our "
            "budget vs actuals check shows we're within 2%. The system may have the wrong "
            "approved budget loaded. Fiscal period: Q2 FY2026."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": [],
    },
    # ── FINANCE PLATFORM / report_performance_issue ────────────────────────
    {
        "_expected_team": "finance_platform",
        "_expected_issue_type": "report_performance_issue",
        "issue_id": "SYN-FP-004",
        "reporter": "cfo.analyst@example.com",
        "title": "Monthly P&L report timing out — cannot download",
        "description": (
            "The monthly P&L report is timing out after 60 seconds when we try to download "
            "it. The report download was working fine last week. Report URL: "
            "https://app.internal/reports/pnl-monthly. Report performance has degraded."
        ),
        "comments": [],
        "attachments": [],
        "links": ["https://app.internal/reports/pnl-monthly"],
        "labels": ["report", "performance"],
    },
    {
        "_expected_team": "finance_platform",
        "_expected_issue_type": "report_performance_issue",
        "issue_id": "SYN-FP-005",
        "reporter": "analyst@example.com",
        "title": "Budget report not loading — blank screen after login",
        "description": (
            "After logging in and navigating to the budget report, the screen remains blank. "
            "The financial report is not loading and there is no error message. "
            "Tried Chrome and Edge. Report URL: https://app.internal/reports/budget-q2."
        ),
        "comments": [{"author": "analyst@example.com", "body": "Still broken as of this morning."}],
        "attachments": [],
        "links": [],
        "labels": ["report", "bug"],
    },
    # ── FINANCE PLATFORM / forecast_discrepancy ────────────────────────────
    {
        "_expected_team": "finance_platform",
        "_expected_issue_type": "forecast_discrepancy",
        "issue_id": "SYN-FP-006",
        "reporter": "fp.analyst@example.com",
        "title": "Forecast discrepancy — Q4 projection is $1.2M higher than model output",
        "description": (
            "The Q4 FY2026 forecast in the planning tool shows $8.4M but our financial "
            "model output is $7.2M. This forecast discrepancy needs to be reconciled before "
            "board presentation. Forecast period: Q4 FY2026."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["forecast"],
    },
    {
        "_expected_team": "finance_platform",
        "_expected_issue_type": "forecast_discrepancy",
        "issue_id": "SYN-FP-007",
        "reporter": "budget.owner@example.com",
        "title": "Reforecast figures not matching plan vs actual summary",
        "description": (
            "After the mid-year reforecast the plan vs actual summary is not reflecting "
            "the updated projection. The forecast mismatch is approximately 15% for the "
            "APAC region. Forecast period: H2 FY2026."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["forecast", "reforecast"],
    },
    # ── APP SUPPORT / access_request ──────────────────────────────────────
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "access_request",
        "issue_id": "SYN-AS-001",
        "reporter": "manager@example.com",
        "title": "Access request — need Site Approver role for jsmith",
        "description": (
            "Name: John Smith\nLDAP: jsmith\nPortfolio: Urban Infrastructure\n"
            "Region: NAM\nUser role: Site Approver\nProject type: active\n"
            "Leads: Rachel Kim\nAdditional context: John is covering approvals while "
            "the primary approver is on leave."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["access_request"],
    },
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "access_request",
        "issue_id": "SYN-AS-002",
        "reporter": "hr@example.com",
        "title": "New hire needs Viewer permission — ldap: tnguyen",
        "description": (
            "New hire Trang Nguyen (LDAP: tnguyen) needs Viewer access to the budget "
            "planning application. She joined the Finance team on 2026-06-01. "
            "Permission level: Viewer. No project-level restriction needed."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["access_request"],
    },
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "access_request",
        "issue_id": "SYN-AS-003",
        "reporter": "it.helpdesk@example.com",
        "title": "Request to grant Manager role for existing user kpatel",
        "description": (
            "User kpatel currently has Viewer access but needs to be promoted to Manager "
            "role to approve budget requests. Please grant the Manager permission as soon "
            "as possible — they have a pending approval due Friday."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": [],
    },
    # ── APP SUPPORT / integration_issue ───────────────────────────────────
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "integration_issue",
        "issue_id": "SYN-AS-004",
        "reporter": "ops@example.com",
        "title": "SAP sync failing — integration not syncing since last night",
        "description": (
            "The SAP integration sync has not completed since last night's scheduled run. "
            "Sync error: 'Connection refused on port 8443'. Data from SAP is not syncing "
            "to the application. This is blocking finance close."
        ),
        "comments": [{"author": "ops@example.com", "body": "Checked firewall — port looks open."}],
        "attachments": [],
        "links": [],
        "labels": ["integration", "incident"],
    },
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "integration_issue",
        "issue_id": "SYN-AS-005",
        "reporter": "systems@example.com",
        "title": "BuyingHub export API returning 503 — import failed",
        "description": (
            "The BuyingHub API is returning HTTP 503 errors on the nightly export. "
            "The import of PO data into our system has failed for two consecutive nights. "
            "API endpoint: /api/v2/po-export. Error code: 503 Service Unavailable."
        ),
        "comments": [],
        "attachments": [{"filename": "api_error.log", "kind": "log"}],
        "links": [],
        "labels": ["integration", "api_error"],
    },
    # ── APP SUPPORT / ui_workflow_issue ───────────────────────────────────
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "ui_workflow_issue",
        "issue_id": "SYN-AS-006",
        "reporter": "user1@example.com",
        "title": "Submit button disabled on budget approval screen",
        "description": (
            "The Submit button on the budget approval workflow screen is disabled and "
            "cannot click it. I have filled in all required fields. Page: "
            "https://app.internal/workflow/budget-approval. Browser: Chrome 125."
        ),
        "comments": [],
        "attachments": [],
        "links": ["https://app.internal/workflow/budget-approval"],
        "labels": ["ui", "bug"],
    },
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "ui_workflow_issue",
        "issue_id": "SYN-AS-007",
        "reporter": "user2@example.com",
        "title": "Portfolio filter broken — selecting APAC shows all regions",
        "description": (
            "The portfolio filter on the dashboard is not working correctly. When I select "
            "APAC from the filter dropdown it still shows data for all regions. "
            "The filter appears to have no effect. UI issue on the main dashboard."
        ),
        "comments": [{"author": "user2@example.com", "body": "Reproducible in both Chrome and Firefox."}],
        "attachments": [],
        "links": [],
        "labels": ["ui", "filter"],
    },
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "ui_workflow_issue",
        "issue_id": "SYN-AS-008",
        "reporter": "user3@example.com",
        "title": "Workflow step 'Request Review' missing from UI",
        "description": (
            "The 'Request Review' step in the budget approval workflow has disappeared "
            "from the interface. The workflow now jumps from 'Draft' directly to 'Submit'. "
            "This is blocking our review process. Screen: budget submission page."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["workflow", "ui"],
    },
    # ── EDGE CASES: missing required fields ────────────────────────────────
    {
        "_expected_team": "unknown",
        "_expected_issue_type": "unknown",
        "_note": "Intentionally vague — no system/PO/detail; should reach no leaf (evolution agent fodder)",
        "issue_id": "SYN-EDGE-001",
        "reporter": "incomplete@example.com",
        "title": "Data looks wrong in the dashboard",
        "description": (
            "Some of the data in our reporting dashboard looks incorrect. "
            "The numbers don't match what I expected from last week."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["data_quality"],
    },
    {
        "_expected_team": "app_support",
        "_expected_issue_type": "access_request",
        "_note": "Missing LDAP and role",
        "issue_id": "SYN-EDGE-002",
        "reporter": "vague@example.com",
        "title": "Need access to the system",
        "description": "Please give me access to the planning tool. I need to view some reports.",
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["access_request"],
    },
    # ── EDGE CASES: near-duplicate pair ────────────────────────────────────
    {
        "_expected_team": "data_engineering",
        "_expected_issue_type": "pipeline_failure",
        "_note": "Duplicate of SYN-DE-006",
        "issue_id": "SYN-DUP-001",
        "reporter": "another@example.com",
        "title": "Airflow DAG sap_actuals_daily is failing again — no data loaded",
        "description": (
            "Same issue as reported earlier — the pipeline sap_actuals_daily has failed "
            "again. The DAG shows 'failed' status and no data has been loaded to downstream tables."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": ["pipeline"],
    },
    # ── EDGE CASES: ambiguous / evolution fodder ───────────────────────────
    {
        "_expected_team": "unknown",
        "_expected_issue_type": "unknown",
        "_note": "Vendor onboarding — no current leaf matches; evolution agent should detect",
        "issue_id": "SYN-UNK-001",
        "reporter": "procurement@example.com",
        "title": "New vendor needs to be onboarded to the procurement system",
        "description": (
            "We have a new vendor (Apex Supplies Ltd) that needs to be onboarded to the "
            "procurement system before we can issue POs. The vendor setup process seems "
            "unclear and we don't know who to contact."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": [],
    },
    {
        "_expected_team": "unknown",
        "_expected_issue_type": "unknown",
        "_note": "Training request — no current leaf; future evolution candidate",
        "issue_id": "SYN-UNK-002",
        "reporter": "newjoin@example.com",
        "title": "Looking for training materials on the budget planning application",
        "description": (
            "I just joined the finance team and need to learn how to use the budget "
            "planning application. Are there any training materials, user guides, or "
            "onboarding sessions available?"
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": [],
    },
    {
        "_expected_team": "unknown",
        "_expected_issue_type": "unknown",
        "_note": "License / seat request — possible future leaf",
        "issue_id": "SYN-UNK-003",
        "reporter": "it.admin@example.com",
        "title": "Need additional user licenses for the planning tool",
        "description": (
            "Our team has grown and we need 5 additional user licenses for the budget "
            "planning application. Current license count is maxed out and new users cannot "
            "be added."
        ),
        "comments": [],
        "attachments": [],
        "links": [],
        "labels": [],
    },
]

# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

_METADATA_KEYS = {"_expected_team", "_expected_issue_type", "_note"}

OUTPUT_PATH = Path(__file__).parent / "synthetic_tickets.jsonl"
LABELLED_PATH = Path(__file__).parent / "synthetic_tickets_labelled.jsonl"


def get_tickets() -> list[dict[str, Any]]:
    """Return ticket dicts stripped of metadata keys (matches Ticket schema)."""
    return [{k: v for k, v in t.items() if k not in _METADATA_KEYS} for t in _TICKETS]


def get_labelled_tickets() -> list[dict[str, Any]]:
    """Return ticket dicts with metadata keys retained (for test assertions)."""
    return list(_TICKETS)


def write_jsonl(path: Path = OUTPUT_PATH) -> None:
    """Write clean tickets (no metadata keys) to a .jsonl file."""
    with path.open("w") as fh:
        for ticket in get_tickets():
            fh.write(json.dumps(ticket) + "\n")
    print(f"Wrote {len(_TICKETS)} tickets to {path}")


def write_labelled_jsonl(path: Path = LABELLED_PATH) -> None:
    """Write labelled tickets (with _expected_* keys) for test assertions."""
    with path.open("w") as fh:
        for ticket in get_labelled_tickets():
            fh.write(json.dumps(ticket) + "\n")
    print(f"Wrote {len(_TICKETS)} labelled tickets to {path}")


if __name__ == "__main__":
    write_jsonl()
    write_labelled_jsonl()
