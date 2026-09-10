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

**Phase 2 — EGX Data Layer (market-truth only) is implemented.** Instruments,
prices, official disclosures, and financial statements can be imported with
full provenance, idempotent re-import, explicit source-failure reporting, and
a `market trace` command that shows any stored fact traced back to its real
source. See `EGX_DATA_SOURCES.md` for what this phase's research found and
could not verify, and why it ships as import rather than a live scraper.

Everything else is a layer on top of these. See `CHANGELOG.md` for what
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
| `economic market import-instruments` | Bulk-import an instrument master CSV |
| `economic market import-prices` | Bulk-import an EOD price CSV |
| `economic market import-disclosures` | Import official documents from a manifest CSV |
| `economic market import-financials` | Import normalized financial-statement facts |
| `economic market trace` | Show every stored fact for a symbol and its source |
| `economic market history` | List past ingestion runs, successful and failed |

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

These are enforced in code and covered by tests, not requested in prompts.

- Cash, quantities, average cost, P&L, weights, and simulations are calculated
  by deterministic code and are never taken from model prose.
- A SELL larger than the holding, or a withdrawal larger than the cash balance,
  is rejected before anything is written.
- A simulation cannot modify the ledger.
- Unpriced holdings are excluded from market value and shown explicitly rather
  than marked at a guessed price.
- Model output is rejected unless it validates against a versioned contract.
- A provider failure is recorded, never replaced with an invented result.
- **A run with fewer than two cross-reviewed analyses is recorded as a DEGRADED
  committee** and is never presented as a full dual-agent review.
- **An actionable recommendation cannot stand on missing, stale, or unpriced
  data** — the evidence gate downgrades it and says why.
- Recording APPROVE never creates a transaction or a broker order.
- Past runs keep the portfolio snapshot as it was at the time.

### Degraded committees

A committee is FULL only when both agents produced an independent analysis and
both were cross-reviewed. If a provider CLI is missing, fails, times out, or
returns invalid output, the run is marked DEGRADED — in the database, in the run
view, in `economic history`, and again when you record your decision.

A degraded run still reaches you. It simply never pretends a second agent
checked the work: its agreement score is recorded as *not measurable*, its
actionable proposals are downgraded to WATCH, and its confidence is capped.

### The evidence gate

Before a proposal is stored as a recommendation, the software re-decides it:

| Situation | Effect |
| --- | --- |
| The security has no price snapshot | BUY/ADD/REDUCE/SELL is downgraded to WATCH |
| The security is marked at a stale price | downgraded to WATCH |
| Portfolio data quality is below the floor (default 50/100) | every actionable action is downgraded |
| The committee was degraded | every actionable action is downgraded |
| Any of the above | confidence is capped at the data-quality score |

Nothing is hidden: the run shows what the chair proposed, what it was reduced
to, and the exact reason. You can still approve a restricted recommendation —
you remain the decision maker — but you will always be told what you are
approving. Set `min_data_quality_for_action` in your config to change the floor.

## Market data (Phase 2)

Instruments, prices, official disclosures, and financial-statement facts are
loaded by importing CSV/manifest files you provide — there is no automatic EGX
scraping. This is a deliberate choice, not a shortcut: see
`EGX_DATA_SOURCES.md` for the research behind it and ADR-022 in `DECISIONS.md`.
Every imported record carries real provenance (source name, URL, publication
date, retrieval time), and every import is safe to re-run — an identical file
updates rows in place rather than duplicating them.

```bash
economic market import-instruments --file instruments.csv
economic market import-prices --file prices.csv
economic market import-disclosures --manifest disclosures.csv
economic market import-financials --file financials.csv

economic market trace --symbol COMI       # every stored fact for COMI, with its source
economic market history                   # every import attempt, successful or failed
```

**Instrument master CSV** — required: `symbol`. Optional: `name`, `sector`,
`industry`, `exchange`, `currency`, `isin`, `source_name`, `source_url`.

**Price CSV** — required: `symbol`, `date`, `close`. Optional: `open`, `high`,
`low`, `volume`, `source_name`, `source_url`.

**Disclosure manifest CSV** — required: `document_type` (one of
`BOARD_DECISION`, `DIVIDEND`, `CAPITAL_CHANGE`, `TRADING_HALT`,
`QUARTERLY_REPORT`, `ANNUAL_REPORT`, `FINANCIAL_STATEMENT`, `PROSPECTUS`,
`MATERIAL_NEWS`, `OTHER`), `title`, `file` (a path to the document you already
downloaded, relative to the manifest by default). Optional: `symbol`,
`published_at`, `source_name`, `source_url`, `external_id`. The document's
SHA-256 is recorded automatically.

**Financial-facts CSV** — required: `symbol`, `period_end`, `period_type` (one
of `ANNUAL`, `QUARTERLY`, `SEMI_ANNUAL`, `TTM`), `metric`, `value`. Optional:
`period_start`, `currency`, `source_document_external_id` (links the fact to a
disclosure imported with the same `external_id`, completing the fact -> document
-> source chain), `source_name`, `source_url`.

Any row that fails validation is rejected individually with a stated reason —
the rest of the file still imports. A bad file (missing, empty, or the wrong
columns) fails the whole run explicitly rather than guessing; nothing is ever
written from a run that failed to read.

## Tests

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Project Layout

```text
src/economic/
  domain/          deterministic rules: ledger, portfolio, simulation, risk, decisions
  application/     workflows: portfolio, simulation, research, decision, market-data services
  persistence/     SQLite connection, migrations, repositories
  agents/          contracts, validators, Codex/Claude/mock adapters, orchestrator
  data_providers/  Phase 2 file-based import: instruments, prices, disclosures, financials
  cli/             command-line interface
tests/             unit and integration tests
data/              runtime database and run artifacts (never committed)
```
