# Modular Routing Architecture Plan

The ticket executor should use divide-and-conquer routing. The outer state machine stays small, while category-specific complexity moves into recursive route modules.

## Problem With The Previous Shape

The previous implementation put too much logic into one flow:

```text
triage_ticket()
  access rules
  data-quality context rules
  data-quality deflection rules
  data-quality finance route
  data-quality CRC/L3 route
  data-quality stewardship route
  generic fallback logic
```

That works for a prototype, but it does not scale. Each new bug type would add more global states, events, and branches.

## Target Shape

Use one generic route engine:

```text
ticket_executor_agent
  -> extract entities
  -> classify ticket
  -> route_engine.evaluate(context)
       -> selected route module
            -> context gate
            -> deflection gate
            -> child route modules
            -> fallback
```

Every route module returns one of four outcomes:

```text
request_information
deflect_intended_behavior
route_to_team
escalate_human_review
```

## Global State vs Module State

The global state should stay generic:

```text
new
extracting_context
route_decision
missing_info
intended_behavior
routed_to_team
waiting_reporter_confirmation
complete
closed
human_review
```

Module-specific detail should be metadata:

```json
{
  "state": "routed_to_team",
  "module_path": ["data_quality", "finance_policy"],
  "module_state": "route_matched",
  "route_target": "finance_queue",
  "route_rule_id": "finance_policy_route"
}
```

This prevents enum explosion.

## Code Organization

Current implementation should use:

```text
ticket_triage/domain/routing/
  models.py
  criteria.py
  gates.py
  engine.py
  registry.py
  modules/
    data_quality.py
    data_quality/
      finance_policy.py
      integration.py
      stewardship.py
```

Responsibilities:

```text
models.py          RouteContext, RouteDecision, RouteOutcome
criteria.py        reusable text/keyword criteria helpers
gates.py           reusable context and deflection gates
engine.py          selects and runs the proper route module
registry.py        maps category/subcategory to route module
modules/           category-specific and child routing modules
```

## Data Quality Module

`DataQualityRouteModule` owns the high-level sequence:

```text
1. ContextGate
2. DeflectionGate
3. FinancePolicyModule
4. IntegrationModule
5. DataStewardshipModule
6. HumanReview fallback
```

Child modules own their own criteria and route targets:

```text
FinancePolicyModule
  criteria: accrual, currency, FX rate, financial policy, SAP financial records
  route_target: finance_queue

IntegrationModule
  criteria: sync failure, pipeline, SAP-to-Quickbase integration, crash
  route_target: crc_l3_support

DataStewardshipModule
  criteria: data entry, merge, void, configuration, missing record
  route_target: data_quality_team
```

## Extension Pattern

To add a new bug type:

```text
1. Create a new route module.
2. Define context requirements.
3. Define optional deflection rules.
4. Define child route modules or route rules.
5. Register it in routing/registry.py.
```

Do not create a new giant transition map.

The reusable contract is:

```text
RouteContext in -> RouteDecision out
```
