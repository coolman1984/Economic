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

## First Coding Goal

The first coding milestone is described in `BUILD_GUIDE.md` and `ROADMAP.md`.

The first usable system must be a small CLI core that proves the complete loop:

`portfolio facts -> independent research -> cross-review -> synthesis -> human decision -> permanent history`

Everything else is a layer on top of that core.
