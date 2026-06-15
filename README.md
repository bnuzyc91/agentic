# Ticket Triage Copilot

Suggestion-only ADK agent that classifies, routes, and recommends actions for tickets
in an annual budget planning application. Every output is a human-reviewable draft —
V1 never mutates a real ticket.

---

## Setup

```bash
cd /Users/yichenzhou/Documents/GitHub/ticket_triage_l
python3 -m pip install -e ".[dev]"
```

Fill `GOOGLE_API_KEY` in `.env` before using ADK with Gemini.

---

## How to run

```bash
# Run the hierarchy on one ticket (edit the ticket inside the file)
python3 ticket_triage/unit_test.py

# Run all 31 synthetic tickets end-to-end
python3 ticket_triage/synthetic_run.py

# Run the test suite
python3 -m pytest tests/ -q

# Start the ADK conversational agent
cd ticket_triage && adk run ticket_triage
```

---

## How to test

**Automated tests (28 assertions, ~1 second):**
```bash
python3 -m pytest tests/ -v
```

**Just evolution proposals:**
```bash
python3 -m pytest tests/test_evolution.py -v
```

**Manual — evolution agent on unknown tickets:**
```python
from ticket_triage.domain.evolution import propose_hierarchy_evolution, EvolutionThresholds
from ticket_triage.schema import Ticket

unknown_tickets = [
    Ticket(
        issue_id=f"UNK-{i}",
        title="User cannot export approved budget to Excel",
        description="Export to Excel button does nothing. No error shown.",
    )
    for i in range(5)
]

proposals = propose_hierarchy_evolution(
    history=unknown_tickets,
    thresholds=EvolutionThresholds(suggest_min_count=5, suggest_min_share=0.10),
)
for p in proposals:
    print(p.proposal_type, "|", p.title)
    print("  change:", p.proposed_change)
```

Change the ticket text to probe different outcomes:
- `"pipeline"` / `"airflow"` keywords → `ADD_LEAF_NODE` under `data_engineering`
- No team signal at all → `ADD_TEAM_NODE`
- Known leaf but weak score → `ADD_RULEBOOK_RULE`

---

## Project layout

```
ticket_triage/
  schema.py                          # all Pydantic contracts — read this first
  agent.py                           # ADK agent definitions and tool wrappers
  RULEBOOK.md                        # human-readable rulebook for all 9 leaf nodes

  domain/
    hierarchy/                       # classification tree (primary path)
      base.py                        #   ClassificationNode, InternalNode, LeafNode, Rulebook ABCs
      registry.py                    #   RootNode, traverse(), get_rulebook()
      nodes/
        data_engineering.py          #   DataEngineeringTeam → DataQualityLeaf, PipelineFailureLeaf, SchemaChangeLeaf
        finance_platform.py          #   FinancePlatformTeam → BudgetVarianceLeaf, ReportPerformanceLeaf, ForecastDiscrepancyLeaf
        app_support.py               #   AppSupportTeam → AccessRequestLeaf, IntegrationIssueLeaf, UIWorkflowLeaf

    steps/
      base.py                        # pipeline step ABCs (EntityExtractor, TicketClassifier, …)

    routing/                         # shared models used by leaf Rulebooks
      models.py                      #   RouteContext, RouteDecision, RouteOutcome
      gates.py                       #   ContextGate (missing fields), evaluate_deflection_rules
      criteria.py                    #   keyword helpers
      modules/data_quality/          #   DataQualityRouteModule + sub-modules (finance_policy, integration, stewardship)

    classification.py                # keyword → PrimaryCategory (used by duplicate scoring)
    duplicates.py                    # near-duplicate scoring against historical tickets
    evolution.py                     # proposes new hierarchy nodes from unclassified ticket patterns
    extraction.py                    # entity extraction from ticket text
    loading.py                       # load sample tickets from data/sample_tickets.jsonl
    parsing.py                       # coerce raw dict/str to Ticket
    recommendation.py                # evaluate_required_fields, recommend_next_action, triage_ticket

  data/
    sample_tickets.jsonl             # seeded historical tickets (used by duplicates + evolution)
    synthetic/
      generator.py                   # 31 labelled synthetic tickets for testing

tests/
  test_classification.py
  test_duplicates_and_agent.py
  test_evolution.py
  test_required_fields_and_recommendations.py
  test_template_and_schema.py
```

---

## Architecture

### Classification hierarchy

The primary axis is **which team to route to**; the secondary axis is **what kind of issue within that team**. Classification walks top-down:

```
RootNode
├── DataEngineeringTeam      (data_engineering)
│   ├── DataQualityLeaf         data_quality_issue      → DataQualityRouteModule (deep sub-routing)
│   ├── PipelineFailureLeaf     pipeline_failure        → data-engineering-pipelines
│   └── SchemaChangeLeaf        schema_change           → data-engineering-schema
│
├── FinancePlatformTeam      (finance_platform)
│   ├── BudgetVarianceLeaf      budget_variance_issue   → finance-platform-budget
│   ├── ReportPerformanceLeaf   report_performance_issue→ finance-platform-reports
│   └── ForecastDiscrepancyLeaf forecast_discrepancy   → finance-platform-forecasting
│
└── AppSupportTeam           (app_support)
    ├── AccessRequestLeaf       access_request          → app-access-admins
    ├── IntegrationIssueLeaf    integration_issue       → app-support-integrations
    └── UIWorkflowLeaf          ui_workflow_issue       → app-support-ui
```

**How `traverse()` works** (`domain/hierarchy/registry.py`):

1. Score every team node — pick the highest above `min_confidence` (0.40).
2. Inside the winning team, score every leaf — pick the highest above the floor.
3. Call `LeafNode.resolve()` → `Rulebook.evaluate()` → `RouteDecision`.
4. If no node clears the floor, `routing_team = UNKNOWN` — the evolution agent's input.

### The four ABCs (`domain/hierarchy/base.py`)

| ABC | Responsibility | Concrete examples |
|---|---|---|
| `ClassificationNode` | `name`, `description`, `matches(ticket, entities) → float` | All nodes |
| `InternalNode` | `children`; default `classify()` picks highest-scoring child | `DataEngineeringTeam`, `FinancePlatformTeam`, `AppSupportTeam` |
| `Rulebook` | `required_fields`, `routing_hint`, `evaluate() → RouteDecision` | `_DataQualityRulebook`, `_BudgetVarianceRulebook`, etc. |
| `LeafNode` | `rulebook`; inherited `resolve()` delegates to it | `DataQualityLeaf`, `PipelineFailureLeaf`, etc. |

Adding a new issue type = subclass `LeafNode` + write a `Rulebook`. Python raises `TypeError` at import time if any abstract method is missing.

### Pipeline step ABCs (`domain/steps/base.py`)

```
Ticket
  │
  ▼ EntityExtractor.extract()           → ExtractedEntities
  │
  ▼ TicketClassifier.classify()         → (HierarchyClassification, RouteDecision | None)
  │
  ▼ DuplicateFinder.find()              → list[DuplicateCandidate]
  │
  ▼ FieldEvaluator.evaluate()           → list[MissingField]
  │
  ▼ ActionRecommender.recommend()       → RecommendedAction
```

`TemplateEvolver.propose()` runs offline over historical tickets, not on a single ticket.

### Dynamic state — how `TriageState` is set at runtime

There is no static state machine config file. Every ticket's state is computed at runtime
by `triage_ticket()` (`domain/recommendation.py`) from what the hierarchy returned.

**Two code paths, one state output:**

```
traverse(ticket, entities)
        │
        ├─ route_decision.state ∈ {MISSING_INFO, INTENDED_BEHAVIOR}?
        │       └─ YES → use route_decision directly (leaf's own gating ran)
        │                e.g. DataQualityRouteModule's ContextGate or DeflectionGate
        │
        └─ NO → standard priority chain:
                  1. evaluate_required_fields() → any missing?
                  │       └─ YES → state = MISSING_INFO
                  │                phase = CONTEXT_VALIDATION
                  │                event = MISSING_REQUIRED_FIELDS_DETECTED
                  │
                  2. find_similar_tickets() → strong duplicate (score ≥ 0.74)?
                  │       └─ YES → state = DUPLICATE_REVIEW
                  │                phase = ROUTING
                  │                event = DUPLICATE_CANDIDATE_FOUND
                  │
                  3. routing_team == app_support AND issue_type == access_request?
                  │       └─ YES → state = READY_FOR_ACCESS_REVIEW
                  │                phase = ROUTING
                  │                event = REQUIRED_FIELDS_EXTRACTED
                  │
                  4. route_decision is not None (simple leaf)?
                  │       └─ YES → state = route_decision.state  (e.g. ROUTED_TO_TEAM)
                  │                phase = route_decision.phase
                  │                event = route_decision.last_event
                  │
                  5. fallback
                          └─ state = HUMAN_REVIEW
                             phase = EXCEPTION
                             event = HUMAN_OVERRIDE
```

**`TriagePhase`** is the lifecycle stage — coarser than state:

| Phase | Meaning |
|---|---|
| `context_validation` | Waiting for more information from the reporter |
| `routing` | Ready to be sent to a team queue |
| `deflection` | Issue is expected behavior — no engineering action needed |
| `exception` | No confident route found — needs human review |

**`_allowed_next_events(state)`** is the transition function. It maps the current state to the set of valid next events so the caller (agent or human reviewer) knows what can legally happen next. Example:

```
MISSING_INFO → [REPORTER_PROVIDED_MISSING_INFO, INACTIVITY_TIMEOUT_REACHED, HUMAN_OVERRIDE]
ROUTED_TO_TEAM → [FIX_APPLIED, REPORTER_REPORTS_NOT_RESOLVED, HUMAN_OVERRIDE]
```

**`AuditEntry`** records every transition as it happens:

```python
AuditEntry(
    event      = DUPLICATE_CANDIDATE_FOUND,
    from_state = ROUTING_REVIEW,
    to_state   = DUPLICATE_REVIEW,
    action_type= SUGGEST_DUPLICATE_REVIEW,
    rule_id    = "finance_platform.forecast_discrepancy",
    reason     = "Selected next state and action from hierarchy rulebook.",
)
```

The `TriageOutput.audit` list is the full trail — every state transition recorded in order.

**Concrete example — a budget variance ticket with a duplicate:**

```
traverse()  → finance_platform / forecast_discrepancy  (confidence 0.78)
              route_decision.state = ROUTED_TO_TEAM
              → NOT in {MISSING_INFO, INTENDED_BEHAVIOR} → standard path

evaluate_required_fields() → [] (fiscal_period and issue_description both present)
find_similar_tickets()     → [ABP-1002 score=0.81]  ← strong duplicate

Priority chain hits step 2:
  state = DUPLICATE_REVIEW
  phase = ROUTING
  event = DUPLICATE_CANDIDATE_FOUND
  action = SUGGEST_DUPLICATE_REVIEW

TriageOutput:
  state              = "duplicate_review"
  phase              = "routing"
  last_event         = DUPLICATE_CANDIDATE_FOUND
  allowed_next_events= [REPORTER_PROVIDED_MISSING_INFO, INACTIVITY_TIMEOUT_REACHED, HUMAN_OVERRIDE]
  recommended_action = { action_type: SUGGEST_DUPLICATE_REVIEW, team: "app-support-triage" }
```

### Key types (`schema.py`)

| Type | What it is |
|---|---|
| `Ticket` | Raw input — issue_id, title, description, comments, labels |
| `ExtractedEntities` | Structured fields: ldap, source_system, po_numbers, fiscal_period, … |
| `RoutingTeam` | `data_engineering` / `finance_platform` / `app_support` / `product` / `unknown` |
| `HierarchyClassification` | `traverse()` output: routing_team + issue_type + path + confidence + evidence |
| `RouteDecision` | Rulebook output: outcome + state + recommended_action + audit |
| `TriageOutput` | Final pipeline output from `triage_ticket()` |
| `TemplateEvolutionProposal` | Human-reviewable proposal from the evolution agent |

---

## Reading order for code review

1. **`schema.py`** — understand the contracts before reading any logic.
2. **`domain/hierarchy/base.py`** — four ABCs; read the ASCII tree in the module docstring.
3. **`domain/hierarchy/registry.py`** — `traverse()` is ~35 lines; trace through it mentally with one ticket.
4. **`domain/hierarchy/nodes/data_engineering.py`** — one node file end-to-end shows the team → leaf → rulebook pattern.
5. **`domain/routing/gates.py`** — `ContextGate` (blocks on missing fields) and `evaluate_deflection_rules` return `RouteDecision | None`; `None` means "keep going deeper".
6. **`domain/steps/base.py`** — pipeline ABCs; focus on method signatures, not implementations.
7. **`domain/recommendation.py::triage_ticket`** — where dynamic state is assembled. Read the two-path structure: (a) leaves that encode their own state (DQ module) are honoured directly; (b) all other tickets go through the priority chain — missing fields → duplicate → routing team → leaf route → human review. `_allowed_next_events()` just below it is the transition function that produces `allowed_next_events` in every `TriageOutput`.

### Review checklist for a new leaf node

- [ ] `name` is a unique slug (used in `HierarchyClassification.path`)
- [ ] `matches()` keyword scores are **higher** than any sibling leaf for the target ticket type
- [ ] Team-level `matches()` scores are **higher** than sibling teams for the target tickets
- [ ] `Rulebook.required_fields` covers what reporters commonly omit
- [ ] A representative ticket in `data/synthetic/generator.py` routes correctly via `synthetic_run.py`

---

## Adding a new issue type

1. Add a `_XxxRulebook(Rulebook)` with `required_fields`, `routing_hint`, `evaluate()`.
2. Add a `XxxLeaf(LeafNode)` with `name`, `description`, `rulebook`, `matches()`.
3. Add the leaf to the parent team's `children` list.
4. Add labelled tickets to `data/synthetic/generator.py` and run `synthetic_run.py`.
5. Add an entry to `RULEBOOK.md`.

## Adding a new routing team

1. Create `domain/hierarchy/nodes/new_team.py` following `data_engineering.py`.
2. Add `NEW_TEAM = "new_team"` to `RoutingTeam` in `schema.py`.
3. Add the team node to `RootNode.children` in `domain/hierarchy/registry.py`.
4. Add it to `_TEAM_MAP` in `registry.py`.

---

## Evolution agent

Runs offline (periodically or on demand) over historical tickets and proposes human-reviewable
diffs to the hierarchy. It never mutates any code or data directly.

**Input:** all tickets in `data/sample_tickets.jsonl` (or a supplied list).

**How it works:**

1. Runs `traverse()` on every ticket to get `routing_team`, `issue_type`, and `confidence`.
2. Marks a ticket **unresolved** if: `routing_team == UNKNOWN`, `confidence < 0.50`, or `state == human_review`.
3. Clusters unresolved tickets by keyword overlap (≥ 2 shared words).
4. For each cluster above the count + share threshold, emits a proposal.

**Proposal types:**

| Type | When emitted | What to do with it |
|---|---|---|
| `ADD_LEAF_NODE` | Cluster maps to a known team but no leaf matched | Add a new `LeafNode` + `Rulebook` under that team |
| `ADD_TEAM_NODE` | No team reached confidence floor | Consider a new `InternalNode` (routing team) |
| `ADD_RULEBOOK_RULE` | Known leaf was reached but confidence < 0.50 | Add stronger multi-word keywords to `matches()` |
| `ADD_CLARIFICATION_TEXT` | Same field repeatedly blocks routing (MISSING_INFO) | Improve the `prompt` in `Rulebook.required_fields` |
| `CHANGE_ROUTING_HINT` | Ambiguous tickets were consistently assigned to one team by humans | Update `Rulebook.routing_hint` or add a leaf |

**Thresholds (conservative by default):**

| Level | Min tickets | Min share of history |
|---|---|---|
| `observe` | 3 | any |
| `suggest` | 5 | 10% |
| `strongly_suggest` | 10 | 20% |

---

## ADK agents

| Agent | Tools | Purpose |
|---|---|---|
| `ticket_executor_agent` | `extract_ticket_entities`, `classify_by_hierarchy`, `find_similar_tickets`, `evaluate_required_fields`, `recommend_next_action`, `triage_ticket` | Classify and recommend for one ticket |
| `template_evolution_agent` | `propose_template_evolution` | Propose hierarchy improvements from ticket history |

`root_agent = ticket_executor_agent` — default when running `adk run ticket_triage`.
