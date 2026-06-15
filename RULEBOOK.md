# Ticket Triage Rulebook

Each leaf node in the classification hierarchy has a **Rulebook** — the source of truth for:
- Which fields are required before the ticket can be routed
- Which team receives the routed ticket
- How the issue is resolved

The hierarchy is: **Routing Team (actor) → Issue Type (subcategory) → Rulebook (resolution logic)**

---

## Team: `data_engineering`

Data quality, pipeline failures, and schema/contract changes.

---

### `data_quality_issue`

**Team queue:** `data-engineering-dq`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `source_system` | Source system | Specify the source system: SAP, Quickbase, BuyingHub, or eBuilder. |
| `issue_description` | Issue summary | Describe the data discrepancy or incorrect value. |

#### Diagnostic gates (evaluated before routing)

| Gate | Condition | Outcome |
|---|---|---|
| Context gate | No PO number, project code, or document link | → `MISSING_INFO` — request diagnostic evidence |
| Sync-lag deflection | Ticket mentions batch sync delay | → `INTENDED_BEHAVIOR` — explain expected sync window |
| Finance policy | Source = SAP + financial record keyword | → `finance_queue` (finance policy route) |
| Default | All gates pass, no special condition | → `data-engineering-dq` |

#### Resolution path

1. Compare source and target row counts for the affected period.
2. If sync lag: explain the ETL batch window and close.
3. If data load failure: file a pipeline incident and link the ticket.
4. If schema change: escalate to `data-engineering-schema`.

---

### `pipeline_failure`

**Team queue:** `data-engineering-pipelines`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `issue_description` | Pipeline / DAG name | Provide the pipeline, DAG, or job name that failed. |

#### Resolution path

1. Identify the DAG, job name, and failure timestamp from the reporter.
2. Check the Airflow/dbt run logs for the root cause.
3. Determine if SLA is breached and escalate to on-call if so.
4. Replay the run after fixing the upstream issue.

---

### `schema_change`

**Team queue:** `data-engineering-schema`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `source_system` | Affected table or dataset | Which table, dataset, or API changed? |
| `issue_description` | Change description | Describe the schema change (column added/removed/renamed, type change, etc.). |

#### Resolution path

1. Confirm the schema diff (added/removed/renamed columns, type changes).
2. Identify all downstream consumers of the affected table.
3. Notify consumers and coordinate migration or data contract update.
4. Update the data contract version and close.

---

## Team: `finance_platform`

Budget variance, financial report performance, and forecast discrepancies.

---

### `budget_variance_issue`

**Team queue:** `finance-platform-budget`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `fiscal_period` | Fiscal period | Which fiscal period or quarter is affected (e.g. Q2 FY2026)? |
| `project_code` | Project or cost-center code | Provide the project S-code or cost-center to investigate. |
| `issue_description` | Variance description | Describe the discrepancy: budget figure, actual figure, expected delta. |

#### Resolution path

1. Pull the journal entries for the affected fiscal period and cost center.
2. Compare budgeted vs. actual figures and identify the delta source.
3. Determine if the variance is a data load issue (→ data_engineering) or a finance policy decision.
4. Apply correction or document the approved variance and close.

---

### `report_performance_issue`

**Team queue:** `finance-platform-reports`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `affected_link` | Report URL or name | Provide the report name or URL that is slow or broken. |
| `issue_description` | Symptom | Describe the issue: timeout duration, error message, or blank screen. |

#### Resolution path

1. Reproduce the timeout or rendering failure using the provided report URL.
2. Check query execution plan and data volume for the affected report.
3. Apply query optimisation, index update, or infrastructure scaling.
4. Confirm with reporter that the report loads within acceptable time.

---

### `forecast_discrepancy`

**Team queue:** `finance-platform-forecasting`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `fiscal_period` | Forecast period | Which forecast period is affected? |
| `issue_description` | Discrepancy detail | Describe how the forecast differs from expected (system, amount, %). |

#### Resolution path

1. Pull the forecast model inputs for the affected period.
2. Compare forecast vs. actuals line-by-line.
3. Identify if the gap is a model input error, a data feed issue, or a business assumption change.
4. Correct the model or escalate the assumption change for finance sign-off.

---

## Team: `app_support`

Access requests, integration failures, and UI/workflow defects.

---

### `access_request`

**Team queue:** `app-access-admins`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `ldap` | LDAP / username | Provide the LDAP ID or username that needs access. |
| `user_role` | Requested role | Which role is being requested? (Viewer, Approver, Manager) |

#### Resolution path

1. Verify the requester's approver is identified and has provisioning authority.
2. Validate the role scope against the project type (pre-planning, active, closed).
3. Provision in LDAP and sync to the application.
4. Notify the reporter and close.

---

### `integration_issue`

**Team queue:** `app-support-integrations`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `source_system` | Integration system | Which integration or API is failing (e.g. SAP sync, BuyingHub export)? |
| `issue_description` | Error description | Describe the error message or sync failure symptom. |

#### Resolution path

1. Identify the failing integration endpoint and last successful sync timestamp.
2. Check API error logs for the root cause (auth failure, schema mismatch, network).
3. Retry the sync or escalate to the integration vendor if needed.
4. Verify downstream data is consistent after the retry.

---

### `ui_workflow_issue`

**Team queue:** `app-support-ui`

#### Required fields

| Field | Label | Clarification prompt |
|---|---|---|
| `affected_link` | Page or screen URL | Provide the page URL or screen name where the issue occurs. |
| `issue_description` | Steps to reproduce | Describe the steps to reproduce: what you clicked, what happened, what you expected. |

#### Resolution path

1. Reproduce the defect using the provided URL and steps.
2. Determine if it is a browser-specific, permissions-related, or application bug.
3. Apply a hotfix or workaround and confirm with the reporter.
4. File a bug report with the engineering team if a code change is required.

---

## How to add a new leaf node

1. Create a `_XxxRulebook(Rulebook)` in the relevant `domain/hierarchy/nodes/<team>.py`:
   - Set `required_fields` — the minimum context needed to route.
   - Set `routing_hint` — the team queue name and a one-line reason.
   - Implement `evaluate()` — either call a route module or use `_simple_route_decision`.
2. Create `XxxLeaf(LeafNode)` that references the rulebook and implements `matches()`.
3. Add the leaf to the team's `children` list in the `InternalNode` subclass.
4. Update `domain/hierarchy/registry.py` `_TEAM_MAP` if needed.
5. Add a synthetic ticket in `data/synthetic/generator.py` for regression testing.
6. Add an entry to this file.

## How the evolution agent suggests new leaves

When > `suggest_min_count` (default: 5) unresolved tickets share a keyword cluster and
no existing leaf matches them with confidence ≥ 0.50, the evolution agent proposes:

- **`ADD_RULEBOOK_RULE`** — if the cluster belongs to an existing leaf but keywords are missing.
- **`ADD_LEAF_NODE`** — if the cluster is distinct and no leaf covers it, under the matched team.
- **`ADD_TEAM_NODE`** — if no team matches, suggesting a new routing actor.

All proposals are human-reviewable diffs. Nothing is applied automatically.
