# Architecture

## 1. Architectural Goal

Build a local-first system with a stable financial core and replaceable outer layers. The future web UI, market-data providers, and AI providers must be adapters around the core, not dependencies embedded inside it.

## 2. Layered Architecture

```text
User
  |
  v
Web UI / CLI
  |
  v
Application Services
  |
  +--> Portfolio Service
  +--> Research Service
  +--> Simulation Service
  +--> Decision Service
  |
  v
Domain Core
  |
  +--> Ledger Engine
  +--> Portfolio Engine
  +--> Risk Rules
  +--> Simulation Rules
  +--> Decision State Machine
  |
  +-------------------------------+
  |                               |
  v                               v
Persistence Adapters        External Adapters
  |                               |
SQLite                         Market Data
Audit Store                    EGX/Filings
Run Artifacts                  News
                               Codex CLI
                               Claude Code CLI
```

## 3. Core Boundaries

### Domain Core

Must not know about:

- HTTP.
- HTML.
- browser state.
- Codex command syntax.
- Claude command syntax.
- specific market-data websites.

It receives validated data structures and returns deterministic results.

### Application Layer

Coordinates workflows such as:

- record transaction;
- rebuild portfolio;
- run simulation;
- launch research committee;
- save human decision;
- evaluate past decision.

### Adapter Layer

Owns external variation:

- shell invocation of Codex/Claude;
- parsing provider outputs;
- EGX/data-provider fetches;
- persistence implementation;
- future HTTP API.

## 4. Local Runtime

Initial target:

```text
Windows PC
  |
  +-- local database
  +-- local application process
  +-- Codex CLI
  +-- Claude Code CLI
  +-- installed browser
  |
  +-- local web UI later
```

The system should work for portfolio viewing/calculation when internet access is unavailable. External research and model calls may require internet.

## 5. Deterministic Truth Boundary

These values must be calculated by software, never trusted from LLM prose:

- cash balance;
- units held;
- average cost;
- realized P&L;
- unrealized P&L;
- market value;
- account equity;
- portfolio weights;
- risk-limit checks;
- simulation arithmetic.

AI may explain these values, but it cannot redefine them.

## 6. Orchestrator Boundary

All agent calls flow through one orchestration service.

Responsibilities:

- unique run ID;
- role assignment;
- prompt construction;
- input minimization;
- process launch;
- timeout and cancellation;
- structured-output validation;
- retries when justified;
- cross-review control;
- stopping conditions;
- persistence;
- final synthesis;
- human approval state.

No UI component should shell directly into Codex or Claude.

## 7. Agent Run State Machine

```text
CREATED
  -> COLLECTING_DATA
  -> DATA_VALIDATED
  -> INDEPENDENT_ANALYSIS
  -> CROSS_REVIEW
  -> DISAGREEMENT_CHECK
  -> SIMULATION
  -> RISK_REVIEW
  -> READY_FOR_SYNTHESIS
  -> READY_FOR_HUMAN
  -> HUMAN_APPROVED | HUMAN_REJECTED | HUMAN_HELD | HUMAN_MODIFIED
  -> OUTCOME_MONITORING
  -> CLOSED
```

Failure states must be explicit and resumable where safe.

## 8. Structured Contracts

Every AI role returns validated JSON, not an unstructured final decision.

Minimum common fields:

```json
{
  "status": "complete",
  "facts": [],
  "analysis": [],
  "risks": [],
  "missing_data": [],
  "sources": [],
  "confidence": 0
}
```

Final recommendation contract additionally includes ranked actions, counterarguments, invalidators, portfolio effect, and `human_decision_required: true`.

## 9. Persistence Strategy

Initial database: SQLite.

Keep two forms of history:

### Normalized Database

For querying accounts, transactions, holdings, runs, decisions, and outcomes.

### Immutable/Append-Oriented Run Artifacts

For reproducibility:

```text
data/runs/<run-id>/
  portfolio_snapshot.json
  market_context.json
  codex_independent.json
  claude_independent.json
  codex_critique.json
  claude_critique.json
  simulations.json
  risk_review.json
  final_recommendation.json
  human_decision.json
```

## 10. Web App Architecture Later

The future UI should call a local HTTP API around the application layer.

Recommended shape:

```text
Browser UI -> Local API -> Application Services -> Core/DB/Orchestrator
```

The UI must never become the source of financial state.

## 11. Data Ingestion Architecture Later

Use provider adapters behind stable interfaces:

```text
MarketDataProvider
DisclosureProvider
FinancialStatementProvider
NewsProvider
```

Each normalized record should preserve:

- provider/source;
- source URL where available;
- publication date;
- retrieval time;
- original identifier;
- freshness status.

## 12. Simulation Architecture

Separate deterministic simulation from AI narrative.

Initial:

- what-if buy/sell;
- cash effect;
- resulting security weight;
- resulting sector weight;
- limit violations.

Later:

- historical stress scenarios;
- factor shocks;
- Monte Carlo where methodologically appropriate;
- scenario distributions.

AI may propose scenario assumptions, but simulation math must be deterministic and stored.

## 13. Security

- Runtime financial data excluded from git.
- Secrets kept out of repository/config committed to git.
- External agents receive minimum necessary context.
- Investment-analysis agent runs should have read-only project access unless a development task explicitly requires writes.
- All destructive database migrations require backup/rollback strategy.

## 14. Scalability Principle

Do not design for millions of public users now. Design clean boundaries so SQLite and local adapters can later be replaced if required.

Local simplicity is a feature, not technical debt, as long as contracts are clean.
