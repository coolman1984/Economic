# AGENTS.md — Mandatory Instructions for Coding Agents

This repository is a personal EGX investment decision-support system. Read this file and the linked planning documents before changing code.

## 1. Mission

Build a reliable local-first investment operating system where deterministic software owns financial truth, AI agents perform research and analysis, and the human user makes the final decision.

## 2. Mandatory Reading Order

Before coding, read:

1. `README.md`
2. `PROJECT_MASTER_PLAN.md`
3. `PROJECT_MAP.md`
4. `ARCHITECTURE.md`
5. `DATA_MODEL.md`
6. `AGENT_ORCHESTRATION.md`
7. `INVESTMENT_RULES.md`
8. `ROADMAP.md`
9. `BUILD_GUIDE.md`
10. `ACCEPTANCE_CRITERIA.md`
11. `DECISIONS.md`

If documents conflict, prefer the more specific document, then update `DECISIONS.md` and `CHANGELOG.md` when a deliberate design change is made.

## 3. Absolute Rules

- Never let AI calculate or overwrite accounting truth.
- Never auto-execute broker trades.
- Never silently invent market data, financial statements, prices, dates, or sources.
- Never treat forecasts as facts.
- Never hide material disagreement between agents.
- Never delete historical investment decisions; preserve auditability.
- Never add a large subsystem before the current phase is verified.
- Never couple the future web UI directly to Codex CLI or Claude Code CLI. All AI access goes through the local orchestration layer.
- Never couple accounting logic to presentation/UI logic.
- Never modify unrelated areas while implementing a scoped task.

## 4. Engineering Philosophy

Prefer:

- Small explicit modules.
- Deterministic calculations.
- Typed contracts.
- SQLite for the initial local database.
- Standard library where practical for the first core.
- Clear adapters around external services.
- Reproducible simulations.
- Idempotent imports.
- Audit logs.
- Versioned migrations.
- Tests before feature expansion.

Avoid:

- Hidden global state.
- Agent prompts embedded throughout UI code.
- Direct shell calls scattered across the codebase.
- Business logic inside route handlers.
- Silent fallback from verified data to guessed data.
- Unbounded agent-to-agent loops.

## 5. Work Pattern

For every meaningful change:

1. Inspect `PROJECT_MAP.md` and the current implementation.
2. State the affected modules and contracts.
3. Keep the change inside the smallest valid boundary.
4. Add or update tests.
5. Run the relevant tests.
6. Update documentation if behavior or architecture changed.
7. Update `CHANGELOG.md`.

## 6. First Milestone

Do not start with a web UI.

Implement the CLI core described in `BUILD_GUIDE.md` first. It must prove:

- account creation;
- cash entry;
- buy/sell ledger;
- deterministic holdings and P&L;
- manual price snapshots;
- what-if simulation;
- Codex bridge;
- Claude bridge;
- independent analyses;
- one mutual critique round;
- final synthesis;
- human decision recording;
- complete history and audit trail.

## 7. AI Agent Boundary

Codex and Claude are workers, not authorities.

The orchestrator owns:

- task identity;
- prompts/contracts;
- timeouts;
- run state;
- review rounds;
- stopping conditions;
- output validation;
- persistence;
- human approval gate.

Agent outputs must be structured and machine-validated.

## 8. Data Safety

Financial data is personal and local by default.

- Send only the minimum context required to an agent.
- Do not store secrets in source code.
- Keep local runtime data out of git.
- Make backups before destructive schema changes.
- Preserve original imported records and provenance when practical.

## 9. Testing Priority

The highest-risk tests are:

1. ledger correctness;
2. duplicate import protection;
3. sell quantity validation;
4. transaction edit/audit behavior;
5. portfolio valuation;
6. simulation not mutating state;
7. agent timeout/failure handling;
8. malformed AI output rejection;
9. human approval gate;
10. reproducibility of historical decision context.

## 10. Definition of Good Work

A feature is not complete because it looks impressive. It is complete when its inputs, outputs, failure modes, persistence, tests, and relationship to the rest of the project are clear.
