# Project Map

This file is the repository navigation source of truth. Keep it updated whenever module boundaries change.

## Repository Structure

Phase 1 is implemented. Paths below marked `later` do not exist yet.

```text
Economic/
│
├── README.md
├── AGENTS.md
├── PROJECT_MASTER_PLAN.md
├── PROJECT_MAP.md
├── ARCHITECTURE.md
├── DATA_MODEL.md
├── AGENT_ORCHESTRATION.md
├── INVESTMENT_RULES.md
├── ROADMAP.md
├── BUILD_GUIDE.md
├── ACCEPTANCE_CRITERIA.md
├── DECISIONS.md
├── CHANGELOG.md
├── pyproject.toml
│
├── src/
│   └── economic/
│       ├── __init__.py              # version and contract/engine version constants
│       ├── config.py                # configuration resolution and runtime paths
│       │
│       ├── domain/
│       │   ├── money.py             # exact decimal arithmetic
│       │   ├── ledger.py            # transaction semantics and validation
│       │   ├── portfolio.py         # holdings, cost, P&L, valuation, snapshot
│       │   ├── risk.py              # portfolio rules, data quality, evidence gate
│       │   ├── simulation.py        # deterministic what-if engine
│       │   └── decisions.py         # decision vocabulary and run state machine
│       │
│       ├── application/
│       │   ├── context.py           # config + database + repositories
│       │   ├── portfolio_service.py
│       │   ├── research_service.py
│       │   ├── simulation_service.py
│       │   └── decision_service.py
│       │
│       ├── persistence/
│       │   ├── sqlite_db.py         # connection, migration runner, backup
│       │   ├── repositories.py      # the only SQL in the project
│       │   └── migrations/
│       │       ├── 001_initial.sql
│       │       └── 002_committee_integrity_and_gate.sql
│       │
│       ├── agents/
│       │   ├── contracts.py         # versioned output contracts
│       │   ├── validators.py        # raw output -> validated payload
│       │   ├── base_adapter.py      # process execution and failure states
│       │   ├── codex_adapter.py     # Codex CLI details only
│       │   ├── claude_adapter.py    # Claude Code CLI details only
│       │   ├── mock_adapter.py      # offline deterministic adapter
│       │   ├── orchestrator.py      # workflow, stages, stopping conditions
│       │   ├── artifacts.py         # run directory on disk
│       │   └── prompts/
│       │       └── templates.py     # every prompt lives here
│       │
│       ├── cli/
│       │   ├── main.py              # argument parsing and command handlers
│       │   ├── formatting.py        # table rendering
│       │   └── demo.py              # fictional demo data
│       │
│       ├── data_providers/
│       │   ├── base.py              # provider contracts, SourceTier, ProviderError
│       │   ├── freshness.py         # FreshnessPolicy for disclosures/financial facts
│       │   ├── csv_utils.py         # shared eager CSV reading + hashing
│       │   ├── instrument_provider.py   # instrument-master CSV import
│       │   ├── price_provider.py        # EOD price CSV import
│       │   ├── disclosure_provider.py   # official-document manifest import
│       │   └── financial_provider.py    # financial-statement fact CSV import
│       └── api/                     # later phase (Phase 6)
│
├── web/                             # later phase (Phase 6)
├── EGX_DATA_SOURCES.md              # Phase 2 research findings and what could/could not be verified
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_ledger.py
│   │   ├── test_portfolio.py
│   │   ├── test_simulation.py
│   │   ├── test_agent_contracts.py
│   │   ├── test_adapters.py
│   │   ├── test_decisions.py
│   │   ├── test_evidence_gate.py
│   │   ├── test_committee_integrity.py
│   │   ├── test_freshness.py
│   │   ├── test_data_providers.py
│   │   └── test_persistence.py
│   ├── integration/
│   │   ├── test_committee_workflow.py
│   │   ├── test_persistence_reload.py
│   │   ├── test_human_gate.py
│   │   ├── test_hardening.py
│   │   ├── test_market_data.py
│   │   └── test_cli.py
│   └── fixtures/
│
├── data/                            # runtime; not committed
│   ├── economic.db
│   └── runs/<run-id>/
├── logs/                            # runtime; not committed
├── backups/                         # runtime; not committed
└── config/
    ├── example_config.json
    └── local_config.json            # optional, git-ignored
```

## Dependency Direction

Allowed direction:

```text
UI/CLI/API
   -> application
      -> domain

application
   -> persistence interfaces/adapters
   -> agent interfaces/adapters
   -> data-provider interfaces/adapters
```

Forbidden direction:

- `domain` importing UI/API code.
- `domain` importing Codex/Claude shell code.
- UI directly opening SQLite tables.
- UI directly spawning AI processes.
- agent adapters modifying ledger calculations.

## Ownership by Module

### `domain/ledger.py`
Owns transaction semantics and accounting invariants.

### `domain/portfolio.py`
Owns deterministic holdings, value, cost, P&L, and allocation calculations.

### `domain/risk.py`
Owns portfolio-rule and risk-limit evaluation, the deterministic data-quality
score, and the **evidence gate** (ADR-020) that decides whether a proposed action
may stand as actionable. The gate is deliberately in the domain layer: it is a
rule about evidence, not a prompt, and no adapter or model can reach it.

### `domain/simulation.py`
Owns deterministic what-if calculations.

### `domain/decisions.py`
Owns decision status/state rules, not AI reasoning.

### `agents/orchestrator.py`
Owns multi-agent workflow, stopping conditions, and **committee integrity**
(ADR-021) — whether a run was a full dual-agent committee or a degraded one.

### `agents/codex_adapter.py`
Only place that knows Codex CLI command details.

### `agents/claude_adapter.py`
Only place that knows Claude Code CLI command details.

### `agents/contracts.py`
Versioned machine-readable request/response structures.

### `persistence/`
Owns database connection, migrations, and repositories.

### `data_providers/`
Owns normalization of external market/company/news information into
provenance-carrying records (ADR-022). Implemented in Phase 2 as file-based
providers only — no live HTTP/scraping adapter ships yet; see
`EGX_DATA_SOURCES.md` and ADR-022 for why. Never touches SQL or the database
directly; `application/market_data_service.py` is the only caller.

### `application/market_data_service.py`
Owns Phase 2 ingestion workflows: reads a provider's normalized output,
upserts it through the repositories inside one atomic transaction (including
the ingestion-run audit row, success or failure), and answers
`trace_symbol()` — the fact-to-source lookup the Phase 2 gate requires.

### `domain/money.py`
Owns exact decimal parsing and formatting. Floats are rejected outright so
precision cannot be lost before a value reaches the ledger.

### `agents/validators.py`
Owns recovery of a JSON payload from raw provider output. It tolerates provider
output *shapes* (fenced blocks, envelopes, JSONL streams) but never relaxes a
contract.

### `agents/mock_adapter.py`
Owns offline deterministic output for testing. Every mock result is labelled
`MOCK` and flows through the same validation as a real provider.

### `agents/artifacts.py`
Owns the on-disk run directory. Database rows and run files share the run ID.

### `cli/formatting.py`
Presentation only. No calculation may live here.

## Critical Data Flow

```text
Transaction Input
 -> validation
 -> ledger persistence
 -> deterministic portfolio rebuild
 -> snapshot
 -> research task
 -> independent agents
 -> critiques
 -> disagreement handling
 -> deterministic simulation/risk
 -> synthesis
 -> human decision
 -> history
```

## Critical Files Agents Must Protect

Once implementation begins, changes to these areas require focused tests:

- ledger calculations;
- schema migrations;
- agent contracts;
- decision state machine;
- audit history;
- simulation math;
- the evidence gate in `domain/risk.py`;
- committee-integrity assessment in `agents/orchestrator.py`.

## Runtime Data

Never commit:

- personal portfolio database;
- broker statements;
- cached private research;
- model credentials;
- access tokens;
- raw personal financial exports.

## Update Rule

Whenever a new subsystem or cross-module dependency is added, update this map in the same change.
