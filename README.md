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
# Run the hierarchy on one ticket
python3 ticket_triage/unit_test.py

# Run all 31 synthetic tickets end-to-end
python3 ticket_triage/synthetic_run.py

# Run the test suite
python3 -m pytest tests/ -q

# Start the ADK conversational agent
cd ticket_triage && adk run ticket_triage
```

---

## Project layout

```
ticket_triage/
  schema.py                          # all Pydantic contracts — read this first
  agent.py                           # ADK agent definitions and tool wrappers

  domain/
    hierarchy/                       # classification tree (primary path)
      base.py                        #   ClassificationNode, InternalNode, LeafNode, Rulebook ABCs
      registry.py                    #   RootNode + traverse() — the main entry point
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

    classification.py                # keyword → PrimaryCategory (used by duplicates + evolution)
    duplicates.py                    # near-duplicate scoring against historical tickets
    evolution.py                     # proposes new hierarchy nodes from unclassified ticket patterns
    extraction.py                    # entity extraction from ticket text
    loading.py                       # load StateMachineTemplate JSON + sample tickets
    parsing.py                       # coerce raw dict/str to Ticket
    recommendation.py                # evaluate_required_fields, recommend_next_action, triage_ticket

  data/
    sample_tickets.jsonl             # seeded historical tickets (used by duplicates + evolution)
    synthetic/
      generator.py                   # 31 labelled synthetic tickets for testing

  templates/
    state_machine.v1.json            # state/action rulebook (used by recommendation + evolution)

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
7. **`domain/recommendation.py::triage_ticket`** — the main pipeline; data-quality branch calls `traverse()` directly.

### Review checklist for a new leaf node

- [ ] `name` is a unique slug (used in `HierarchyClassification.path`)
- [ ] `matches()` keyword scores are **higher** than any sibling leaf for the target ticket type
- [ ] Team-level `matches()` scores are **higher** than sibling teams for the target tickets
- [ ] `Rulebook.required_fields` covers what `ContextGate` will block on
- [ ] A representative ticket in `data/synthetic/generator.py` routes correctly via `synthetic_run.py`

---

## Adding a new issue type

1. Add a `_XxxRulebook(Rulebook)` with `required_fields`, `routing_hint`, `evaluate()`.
2. Add a `XxxLeaf(LeafNode)` with `name`, `description`, `rulebook`, `matches()`.
3. Add the leaf to the parent team's `children` list.
4. Add labelled tickets to `data/synthetic/generator.py` and run `synthetic_run.py`.

## Adding a new routing team

1. Create `domain/hierarchy/nodes/new_team.py` following `data_engineering.py`.
2. Add `NEW_TEAM = "new_team"` to `RoutingTeam` in `schema.py`.
3. Add the team node to `RootNode.children` in `domain/hierarchy/registry.py`.
4. Add it to `_TEAM_MAP` in `registry.py`.

---

## Evolution agent

Runs offline over historical tickets (`data/sample_tickets.jsonl`) and proposes new hierarchy nodes:

- Tickets with `routing_team = UNKNOWN` are the primary signal — they don't fit any existing leaf.
- A `TemplateEvolutionProposal` is emitted when a keyword cluster crosses `suggest_min_count` (5 tickets) and `suggest_min_share` (10% of sample).
- Proposals are **never applied automatically** — a human approves and adds the new `LeafNode` + `Rulebook`.

---

## ADK agents

| Agent | Tools | Purpose |
|---|---|---|
| `ticket_executor_agent` | `extract_ticket_entities`, `classify_by_hierarchy`, `find_similar_tickets`, `evaluate_required_fields`, `recommend_next_action`, `triage_ticket` | Classify and recommend for one ticket |
| `template_evolution_agent` | `load_state_machine_template`, `propose_template_evolution` | Propose hierarchy improvements from ticket history |

`root_agent = ticket_executor_agent` — default when running `adk run ticket_triage`.
