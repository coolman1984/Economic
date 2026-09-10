# Data Model

## 1. Goal

The database is the authoritative local memory of accounts, transactions, portfolio state inputs, research runs, decisions, and outcomes. AI-generated prose is never the authoritative source for balances or holdings.

Initial database: SQLite with versioned migrations.

## 2. Core Invariants

- Transactions are append-oriented and auditable.
- A SELL cannot exceed available quantity unless an explicit future short-selling feature is designed.
- Historical decisions are never silently overwritten.
- Recommendation, human decision, and actual execution are separate records.
- External data preserves provenance and timestamps.
- Derived portfolio values are reproducible from source transactions and price snapshots.
- Imported records require duplicate detection/idempotency.

## 3. Initial Tables

### accounts

```text
id
name
broker
currency
status
created_at
updated_at
```

### portfolios

```text
id
account_id
name
objective
risk_profile
target_rules_json
created_at
updated_at
```

A simple first version may treat one account as one portfolio, but schema/service design must not prevent later separation.

### instruments

```text
id
symbol
name
exchange
sector
industry
currency
trading_status
isin_optional
created_at
updated_at
```

### transactions

```text
id
account_id
portfolio_id_optional
transaction_type
instrument_id_optional
quantity
unit_price
cash_amount
commission
fees
transaction_date
external_reference_optional
source
note
created_at
supersedes_transaction_id_optional
```

Initial transaction types:

- BUY
- SELL
- DEPOSIT
- WITHDRAW

Later:

- DIVIDEND
- TAX
- BONUS_SHARES
- RIGHTS
- SPLIT
- REVERSE_SPLIT
- TRANSFER_IN
- TRANSFER_OUT
- CAPITAL_INCREASE
- CORPORATE_ACTION

### price_snapshots

Implemented in migration 001 (Phase 1); `source_tier` and `published_at` added
by migration 003 (Phase 2, ADR-023) with safe defaults so existing rows need
no backfill.

```text
id
instrument_id
price_date
close_price
open_optional
high_optional
low_optional
volume_optional
source
source_url_optional
retrieved_at
source_tier          -- Phase 2: OFFICIAL | PROVIDER | NEWS | COMMUNITY | IMPORT
published_at          -- Phase 2: defaults to price_date when not supplied
```

### external_documents

For disclosures, statements, and official documents. Implemented in migration
003 (Phase 2). `fingerprint` is `source_name|external_id` when an external_id
is supplied, else `content|<sha256>` — either way, re-importing the identical
or corrected document updates the row rather than duplicating it (ADR-024).

```text
id
instrument_id_optional
symbol_optional
document_type
title
published_at
source_name
source_tier
source_url
external_id_optional
content_hash                    -- sha256 of the actual file bytes, always present
local_path_optional
retrieved_at
fingerprint
```

### news_items

Not implemented. Deferred past Phase 2 by explicit scope decision — see
`ROADMAP.md` Phase 2 scope note: news is opinion-tier data and can wait for
Phase 4's research layer.

### financial_facts

Implemented in migration 003 (Phase 2). `fingerprint` is
`symbol|period_end|period_type|metric|source_name`, so the same statement
metric reported again by the same source updates rather than duplicates
(ADR-024). `source_document_id` links a fact to the `external_documents` row
it was reported in, resolved by `source_document_external_id` at import time —
the fact-to-document link the Phase 2 traceability gate depends on.

```text
id
instrument_id
symbol
period_start_optional
period_end
period_type
metric
value
currency
source_document_id_optional
source_name
source_tier
source_url_optional
published_at_optional
retrieved_at
fingerprint
created_at
```

### ingestion_runs

New in Phase 2. An audit trail of every import attempt, successful or failed —
never silent, mirroring the agent-adapter failure taxonomy in spirit
(`data_providers/base.py`'s `FAILURE_KINDS`).

```text
id
kind                  -- instruments | prices | disclosures | financial_facts
provider
source_optional
ok
failure_kind_optional
error_optional
read_count
inserted_count
updated_count
duplicate_count
rejected_count
rejected_json          -- per-row rejection reasons, never a silently dropped row
started_at
completed_at
```

## 4. Research and Decision Tables

### research_runs

```text
id
created_at
question
scope_type
scope_reference_optional
status
portfolio_snapshot_json
market_context_reference_optional
contract_version
completed_at_optional
error_optional
committee_mode                 -- FULL | DEGRADED | UNKNOWN (ADR-021)
committee_integrity_json
analyst_count
critique_count
data_quality_score             -- deterministic, never the chair's own number
agreement_score_optional       -- NULL when fewer than two analyses existed
evidence_gate_json             -- the gate the run's actions were judged against
```

`committee_mode` records whether the dual-agent design actually happened. It is
not a run *state* (those are in `status`); a run can be READY_FOR_HUMAN and
DEGRADED at the same time. `agreement_score` is NULL rather than zero when
agreement was not measurable, so "not measured" is distinguishable from
"measured as no agreement".

### agent_runs

```text
id
research_run_id
agent_provider
agent_role
stage
session_reference_optional
started_at
completed_at_optional
status
input_hash
raw_output_path_optional
parsed_output_json_optional
validation_errors_optional
cost_optional
token_usage_optional
```

### disagreements

```text
id
research_run_id
topic
codex_position
claude_position
materiality
resolution_status
resolution_summary_optional
evidence_json_optional
created_at
```

### simulations

```text
id
research_run_id_optional
simulation_type
input_json
output_json
engine_version
created_at
```

### recommendations

```text
id
research_run_id
rank
instrument_id_optional
action                         -- after the evidence gate (ADR-020)
confidence                     -- after the evidence gate's confidence cap
proposed_action                -- what the chair actually asked for
proposed_confidence
restricted                     -- 1 when the gate downgraded the action
restriction_reasons_json       -- the deterministic reasons it was downgraded
data_quality_score             -- deterministic, never the chair's own number
current_weight_optional
suggested_weight_optional
thesis_summary
counterargument
invalidators_json
risks_json
portfolio_effect_json
evidence_json
created_at
```

### human_decisions

```text
id
research_run_id
recommendation_id_optional
decision
modified_action_optional
note_optional
created_at
```

Allowed initial decisions:

- APPROVE
- REJECT
- HOLD
- MODIFY

### executions

Actual transactions the user reports after acting at the broker.

```text
id
human_decision_id_optional
transaction_id
recorded_at
```

This table or relationship keeps proposal, decision, and execution separate.

### outcome_reviews

```text
id
research_run_id
review_horizon
review_date
thesis_status
price_outcome_optional
risk_events_json
expected_vs_actual_json
lessons_json
created_at
```

## 4a. Deterministic Overrides

Two fields on a research run and two on every recommendation are decided by
software after the model has answered, and the model cannot influence them:

| Field | Decided by | Rule |
| --- | --- | --- |
| `research_runs.committee_mode` | orchestrator | FULL only when two analyses were cross-reviewed |
| `research_runs.agreement_score` | orchestrator | NULL when fewer than two analyses exist |
| `research_runs.data_quality_score` | portfolio snapshot | pricing completeness and freshness |
| `recommendations.action` / `confidence` | evidence gate | downgraded and capped when evidence is thin |

The model's own claims are never discarded: they stay verbatim in the run
artifacts under `data/runs/<run-id>/`, so the difference between what was
proposed and what the system recorded is always auditable.

## 5. Audit Log

### audit_log

```text
id
created_at
actor_type
actor_reference_optional
action
entity_type
entity_id_optional
before_json_optional
after_json_optional
reason_optional
```

Important financial-state edits must be traceable.

## 6. Transaction Editing Policy

Avoid destructive edits where practical.

Preferred model:

1. Original transaction remains stored.
2. Correcting record references the original using `supersedes_transaction_id` or an equivalent mechanism.
3. Portfolio engine uses the active/latest logical record.
4. Audit log records who/what changed it and why.

Implementation may start simpler, but must never silently destroy history.

## 7. Duplicate Import Protection

Imported transactions should derive a stable fingerprint from fields such as:

```text
source + account + external_reference
```

or, when no reference exists:

```text
account + date + type + symbol + quantity + price + amount + fee
```

Duplicate detection must be tested before automated broker-statement ingestion is considered safe.

## 8. Portfolio Snapshot

A research run receives an immutable snapshot containing at minimum:

```json
{
  "as_of": "timestamp",
  "accounts": [],
  "positions": [],
  "cash": 0,
  "total_equity": 0,
  "prices_as_of": {},
  "missing_prices": [],
  "risk_limits": {}
}
```

The snapshot must be persisted with the run so later analysis can reproduce the historical decision context.

## 9. Source Freshness

Every externally sourced record should support freshness decisions using:

- source publication date;
- retrieval time;
- provider identity;
- source URL where available.

Stale data must be visible to the research and risk layers.

**Implemented (Phase 2):** every `price_snapshots`, `external_documents`, and
`financial_facts` row carries `source_name`/`source_tier`/`source_url`/
`published_at`/`retrieved_at`. Prices still classify freshness through the
frozen `domain/portfolio.py` staleness check used for valuation (ADR-017).
Disclosures and financial facts classify freshness through the new, separate
`data_providers/freshness.py` (`FreshnessPolicy`, ADR-023) — the two are
deliberately independent so nothing in Phase 2 needed to touch frozen code.

`source_tier` is one of `OFFICIAL | PROVIDER | NEWS | COMMUNITY | IMPORT`
(`data_providers/base.py::SourceTier`), matching the priority order in
`INVESTMENT_RULES.md` §4. Phase 2's file-based providers tag every record
`IMPORT` — the tier the software actually verified — rather than assuming
`OFFICIAL` for content that merely originated from an official source but
whose channel (a human-placed file) the software cannot itself authenticate.
A future live adapter reading directly from a confirmed EGX/EGID endpoint
would be the first to legitimately claim `OFFICIAL`.

## 10. Migration Rule

Every schema change must:

1. have a migration;
2. preserve existing personal data;
3. be tested against a representative database;
4. document rollback/backup considerations;
5. update this file when the logical model changes.
