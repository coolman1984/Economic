# Project Map

This file is the repository navigation source of truth. Keep it updated whenever module boundaries change.

## Planned Repository Structure

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
│
├── src/
│   └── economic/
│       ├── domain/
│       │   ├── ledger.py
│       │   ├── portfolio.py
│       │   ├── risk.py
│       │   ├── simulation.py
│       │   └── decisions.py
│       │
│       ├── application/
│       │   ├── portfolio_service.py
│       │   ├── research_service.py
│       │   ├── simulation_service.py
│       │   └── decision_service.py
│       │
│       ├── persistence/
│       │   ├── sqlite_db.py
│       │   ├── repositories.py
│       │   └── migrations/
│       │
│       ├── agents/
│       │   ├── contracts.py
│       │   ├── codex_adapter.py
│       │   ├── claude_adapter.py
│       │   ├── orchestrator.py
│       │   ├── prompts/
│       │   └── validators.py
│       │
│       ├── data_providers/
│       │   ├── base.py
│       │   ├── market_data.py
│       │   ├── disclosures.py
│       │   ├── financials.py
│       │   └── news.py
│       │
│       ├── cli/
│       │   └── main.py
│       │
│       └── api/
│           └── app.py              # later phase
│
├── web/                            # later phase
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── data/                           # runtime; not committed
├── logs/                           # runtime; not committed
├── backups/                        # runtime; not committed
└── config/
    └── example_config.json
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
Owns portfolio-rule and risk-limit evaluation.

### `domain/simulation.py`
Owns deterministic what-if calculations.

### `domain/decisions.py`
Owns decision status/state rules, not AI reasoning.

### `agents/orchestrator.py`
Owns multi-agent workflow and stopping conditions.

### `agents/codex_adapter.py`
Only place that knows Codex CLI command details.

### `agents/claude_adapter.py`
Only place that knows Claude Code CLI command details.

### `agents/contracts.py`
Versioned machine-readable request/response structures.

### `persistence/`
Owns database connection, migrations, and repositories.

### `data_providers/`
Owns normalization of external market/company/news information.

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
- simulation math.

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
