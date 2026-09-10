# Economic — Personal AI Investment Office for the Egyptian Exchange

Economic is a local-first personal investment operating system for the Egyptian Exchange (EGX).

Its purpose is not to auto-trade. Its purpose is to improve the quality, traceability, and discipline of human investment decisions.

## Core Principle

**Software calculates facts. AI researches, analyzes, challenges, and proposes. The human makes the final decision.**

## Target Experience

The user opens a local web app on a Windows PC while Codex CLI and Claude Code CLI are available on the same machine. A local orchestrator can ask both agents to work independently, delegate research, critique each other, resolve material disagreements, run deterministic portfolio simulations, and return ranked recommendations with evidence and uncertainty. The user approves, rejects, modifies, or postpones the decision. The system then records the complete decision context and later compares expectations with actual outcomes.

## Product Scope

The system will eventually provide:

- Multiple brokerage accounts and portfolios.
- Complete transaction ledger and cash tracking.
- Deterministic cost, P&L, exposure, and performance calculations.
- EGX prices, company information, disclosures, financial statements, and news.
- Portfolio allocation and rebalancing.
- Risk limits and stress tests.
- Company and sector research.
- Multi-agent investment committee using Codex CLI and Claude Code CLI.
- Independent analysis before cross-review.
- Evidence-based disagreement resolution.
- Scenario analysis rather than false certainty about future prices.
- Human approval gate before any decision is recorded as accepted.
- Permanent decision memory and agent-performance evaluation.
- Local web UI first, remote/mobile access later.

## Non-Goals for the First Versions

- No broker order execution.
- No autonomous trading.
- No public SaaS platform.
- No mobile app before the local core is stable.
- No AI-generated accounting truth.
- No recommendation without traceable evidence and data-quality status.

## Build Strategy

Do not build the entire product at once. Start with the absolute core:

1. Deterministic ledger and portfolio engine.
2. Local SQLite database.
3. Manual prices and transaction entry.
4. What-if simulation.
5. Codex CLI bridge.
6. Claude Code CLI bridge.
7. Independent dual-agent analysis.
8. One cross-review round.
9. Final synthesis.
10. Human decision recording.
11. Full audit trail.

Only after this core is reliable should we add market ingestion, risk, richer simulation, the web app, alerts, and automation.

## Repository Documents

Start with these files before writing code:

- `AGENTS.md` — mandatory operating instructions for coding agents.
- `PROJECT_MASTER_PLAN.md` — complete product vision and scope.
- `PROJECT_MAP.md` — source-of-truth map for repository structure and dependencies.
- `ARCHITECTURE.md` — technical architecture and boundaries.
- `DATA_MODEL.md` — database model and invariants.
- `AGENT_ORCHESTRATION.md` — Codex/Claude collaboration contract.
- `INVESTMENT_RULES.md` — portfolio, evidence, and risk rules.
- `ROADMAP.md` — staged implementation plan.
- `BUILD_GUIDE.md` — exact development sequence and gates.
- `ACCEPTANCE_CRITERIA.md` — definition of done.
- `DECISIONS.md` — architectural decisions and reasons.
- `CHANGELOG.md` — project history.

## Status

**Phase 1 — Absolute CLI Core is implemented.** The CLI proves the complete loop:

`portfolio facts -> independent research -> cross-review -> synthesis -> human decision -> permanent history`

Everything else is a layer on top of that core. See `CHANGELOG.md` for what
shipped and `ROADMAP.md` for what comes next.

## Setup

Requires Python 3.10+. No third-party runtime dependencies.

```bash
python -m pip install -e .          # add [dev] for the test tools
economic init
```

`economic init` creates `data/economic.db` and the runtime folders. Everything
stays on your machine; nothing is uploaded.

Optional configuration lives in `config/local_config.json` (git-ignored). Copy
`config/example_config.json` to start. Never put credentials there — Codex and
Claude authenticate through their own CLIs.

Check your environment at any time:

```bash
economic doctor
```

It reports the database schema version, integrity, and whether the Codex and
Claude Code CLIs were found on your PATH.

## Commands

| Command | What it does |
| --- | --- |
| `economic init` | Create the database and runtime folders |
| `economic doctor` | Check the database and the agent CLIs |
| `economic account add\|list` | Manage brokerage accounts |
| `economic instrument add\|list` | Manage instruments (symbol, name, sector) |
| `economic cash deposit\|withdraw` | Record cash movements |
| `economic trade buy\|sell` | Record purchases and sales |
| `economic price set\|show` | Record and review manual price snapshots |
| `economic portfolio show` | Holdings, cost, P&L, weights, equity, data quality |
| `economic portfolio ledger` | List the recorded transactions |
| `economic simulate` | What-if BUY/SELL that never touches the ledger |
| `economic committee` | Run the dual-agent investment committee |
| `economic decide` | Record APPROVE / REJECT / HOLD / MODIFY |
| `economic execution record` | Link a real broker trade to a decision |
| `economic history` | List past research runs |
| `economic run show` | Reload one complete run from history |
| `economic audit` | Show the audit log |
| `economic demo seed` | Load fictional demo data |

Add `--json` to any command for machine-readable output. `--home <dir>` selects
a different project directory.

## Walkthrough

```bash
economic init
economic account add --name "Main" --broker "EFG Hermes"

economic cash deposit  --account Main --amount 500000 --date 2026-07-01
economic trade buy     --account Main --symbol COMI --qty 1000 --price 50 --commission 100
economic trade buy     --account Main --symbol COMI --qty 1000 --price 60 --commission 120
economic trade sell    --account Main --symbol COMI --qty 500  --price 70 --commission 70
economic price set     --symbol COMI --price 74.25 --date 2026-09-09 --source "EGX close"

economic portfolio show --account Main
economic simulate --account Main --action BUY --symbol COMI --qty 1000 --price 74.25

economic committee --question "Am I too concentrated in COMI?" --account Main --mock
economic decide --run <run-id> --decision HOLD --note "Waiting for results."
economic run show <run-id>
```

Prefer to try it without typing your own data? `economic demo seed` creates a
fictional account using invented `ZZDEMO*` symbols.

### Mock mode

`--mock` runs the committee entirely offline with deterministic fictional
output, so you can exercise the full workflow without model calls. Every mock
result is labelled `MOCK` and must never be read as investment analysis. Use
`--live` to force the real provider CLIs.

## What the software guarantees

- Cash, quantities, average cost, P&L, weights, and simulations are calculated
  by deterministic code and are never taken from model prose.
- A SELL larger than the holding, or a withdrawal larger than the cash balance,
  is rejected before anything is written.
- A simulation cannot modify the ledger.
- Unpriced holdings are excluded from market value and shown explicitly rather
  than marked at a guessed price.
- Model output is rejected unless it validates against a versioned contract.
- A provider failure is recorded, never replaced with an invented result.
- Recording APPROVE never creates a transaction or a broker order.
- Past runs keep the portfolio snapshot as it was at the time.

## Tests

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Project Layout

```text
src/economic/
  domain/        deterministic rules: ledger, portfolio, simulation, risk, decisions
  application/   workflows: portfolio, simulation, research, decision services
  persistence/   SQLite connection, migrations, repositories
  agents/        contracts, validators, Codex/Claude/mock adapters, orchestrator
  cli/           command-line interface
tests/           unit and integration tests
data/            runtime database and run artifacts (never committed)
```
