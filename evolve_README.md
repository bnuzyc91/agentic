# Evolution Proposal Flow

## Step 0: `_classify_all()` (lines 125-152)

Before any proposals are generated, every ticket in the history gets run through
`traverse()`. The result is stored as a `_ClassifiedTicket` with four pieces of
information:

- `routing_team`: which team `traverse()` selected, or `UNKNOWN`
- `issue_type`: which leaf was reached, or `"unknown"`
- `confidence`: the lowest score along the path, using the minimum of the team
  score and leaf score
- `state`: the final triage state, such as `missing_info`, `human_review`, or
  `routed_to_team`

This is the only place `traverse()` is called. Every proposal function below
just reads the pre-computed `_ClassifiedTicket` list.

## Step 1: `_is_unresolved()` (line 155)

A ticket is considered unresolved if any of these are true:

| Condition | Meaning |
| --- | --- |
| `routing_team == UNKNOWN` | No team matched above the `0.40` confidence floor. |
| `confidence < 0.50` | A team and leaf matched, but very weakly. |
| `state == "human_review"` | The ticket fell through to the default fallback. |

These are the tickets the evolution agent cares about. Well-routed tickets
(confident team + leaf + no `MISSING_INFO`) are used only as background for
computing share percentages.

## Step 2: Clustering With `_cluster_by_keywords()` (lines 167-187)

All unresolved tickets are passed through a greedy keyword-overlap clusterer.

For each ticket, `_ticket_words()` strips its title, description, comments, and
resolution into a set of lowercase tokens. It removes stop words and short words
using this regex:

```text
[a-z][a-z0-9_-]{2,}
```

The clusterer then does a single forward pass:

```text
for each unassigned ticket i:
    start a new cluster with ticket i
    scan every later unassigned ticket j:
        if |words(i) intersect words(j)| >= keyword_cluster_overlap (default 2):
            add j to the cluster
```

This is `O(n^2)` but is intentionally simple. History sets are small: hundreds,
not millions. The result is a list of clusters where every ticket shares at
least two keywords with the cluster's seed ticket.

Why keyword overlap and not embeddings? The evolution agent has to produce
proposals that a human can read and act on. "These tickets all mention pipeline
and airflow" is immediately actionable. A cosine distance of `0.14` is not.

## Step 3: `_guess_team()` (lines 194-216)

For each cluster of unresolved tickets, `_guess_team()` checks whether there is
a team signal even if no leaf matched. It runs a lighter version of
`traverse()`: it scores only the team-level nodes (`DataEngineeringTeam`,
`FinancePlatformTeam`, and `AppSupportTeam`), not their leaves.

```text
for each ticket in the cluster:
    score all three team nodes via team_node.matches()
    if the best team score >= 0.40:
        cast a vote for that team
```

If at least half the tickets in the cluster vote for the same team, that team is
returned. Otherwise, `_guess_team()` returns `None`.

This separates two situations:

| Signal | Interpretation | Proposal |
| --- | --- | --- |
| Team keywords fire but no leaf keywords fire | The team is recognizable, but the issue type is new. | `ADD_LEAF_NODE` |
| Neither team nor leaf keywords fire | The tickets are entirely uncharted territory. | `ADD_TEAM_NODE` |

## Proposal 1: `ADD_LEAF_NODE` / `ADD_TEAM_NODE` (lines 223-287)

Both proposal types come from `_unresolved_pattern_proposals()`. Once a cluster
is large enough (`>= observe_min_count`, currently `3`), the agent chooses one
of two proposal shapes.

### `ADD_LEAF_NODE`

This is proposed when `_guess_team()` returns a known team.

The cluster looks like it belongs to a known team, such as `data_engineering`,
because keywords like `pipeline`, `airflow`, and `dag` fire at the team level.
However, none of the existing leaves (`data_quality_issue`, `pipeline_failure`,
or `schema_change`) matched strongly enough.

The proposal says to add a new `LeafNode` under `DataEngineeringTeam` with the
cluster's common keywords as candidate match words.

### `ADD_TEAM_NODE`

This is proposed when `_guess_team()` returns `None`.

No team reached even the `0.40` team-level confidence floor. The tickets look
completely foreign to the existing tree. The proposal suggests that a new
`InternalNode` routing team may be needed.

## Proposal 2: `ADD_RULEBOOK_RULE` (lines 290-330)

This proposal comes from `_weak_classification_proposals()`.

It handles a different scenario: the ticket did reach a known leaf, but the
confidence was too low (`< 0.50`). The leaf was the best match but scored
weakly, usually because only a single generic keyword matched. For example,
`mismatch` might score `0.75`, with nothing stronger available.

The fix is not a new leaf. It is stronger multi-word keywords in the existing
leaf's `matches()` method. The proposal surfaces the common words across all
weakly scored tickets for that leaf, which the reviewer can promote to
high-confidence phrases.

## Proposal 3: `ADD_CLARIFICATION_TEXT` (lines 333-383)

This proposal comes from `_missing_context_proposals()`. It looks only at
tickets whose final state is `MISSING_INFO`.

For each such ticket, it finds which field was missing:

- If the leaf had its own internal gating, such as `DataQualityRouteModule`, it
  reads `route_missing_fields`: the actual `MissingField` objects the
  `ContextGate` set on the `RouteDecision`.
- For simple leaves, it falls back to checking each `RequiredFieldRule` in
  `rulebook.required_fields` against the extracted entities.

It then counts how often each field is the blocker across all `MISSING_INFO`
tickets. If one field (`diagnostic_evidence`, `ldap`, `affected_link`, and so
on) blocks more than `required_field_min_missing_share`, currently `15%` of
`MISSING_INFO` tickets, the prompt for that field in the `Rulebook` is probably
not clear enough. Reporters are not including it because they do not understand
what is being asked.

## Proposal 4: `CHANGE_ROUTING_HINT` (lines 386-419)

This proposal comes from `_routing_gap_proposals()`. It looks only at tickets
that ended in `HUMAN_REVIEW` and have a `known_assignee` field set. This is
historical data where someone recorded who actually resolved the ticket.

It counts who the human reviewers sent these ambiguous tickets to. If one
assignee received at least `70%` of them (`routing_min_same_team_share`), there
is a revealed routing preference in the data that the hierarchy does not yet
encode.

The proposal surfaces that assignee and the common keywords so a reviewer can
decide whether to add a new leaf, strengthen an existing routing hint, or add a
keyword rule.

## Threshold Pyramid

All proposals share the same three-tier signal gate:

| Level | Count threshold | Share threshold | Proposal confidence |
| --- | ---: | ---: | ---: |
| `observe` | `3` | Any | `0.55` |
| `suggest` | `5` | `10%` of history | `0.72` |
| `strongly_suggest` | `10` | `20%` of history | `0.86` |

`observe` means "interesting data point, may be noise".
`strongly_suggest` means "this pattern is too large to ignore".

Nothing is applied automatically at any level. Every proposal is a
human-reviewable diff.
