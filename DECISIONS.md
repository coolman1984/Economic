# Architectural Decision Record

This file records important project decisions and why they exist. Add new entries when a meaningful architectural rule changes.

---

## ADR-001 — Local-First Before Cloud

**Decision:** Build the first usable system on the user's Windows PC with local persistence.

**Reason:** Personal financial data stays under user control, development is simpler, and the product can prove its core before adding hosting complexity.

**Consequence:** Remote/mobile access is deferred, but interfaces must remain clean enough to support it later.

---

## ADR-002 — Deterministic Finance Core

**Decision:** Portfolio accounting, P&L, weights, cash, and simulations are calculated by deterministic software, never accepted from LLM prose.

**Reason:** Financial truth must be reproducible and testable.

**Consequence:** AI can interpret numbers but cannot define them.

---

## ADR-003 — SQLite for Initial Persistence

**Decision:** Use SQLite for the initial local database.

**Reason:** Zero-server setup, reliable transactions, good local performance, easy backup, and sufficient scale for one personal investment office.

**Consequence:** Repository/data access must sit behind adapters so storage can change later if genuinely needed.

---

## ADR-004 — CLI Core Before Web UI

**Decision:** Build and verify the complete investment-decision loop as a CLI before building the web interface.

**Reason:** A beautiful UI can hide broken accounting or orchestration. The real product value is the core workflow.

**Consequence:** Phase 1 intentionally looks simple.

---

## ADR-005 — Codex and Claude Behind Adapters

**Decision:** All Codex CLI and Claude Code CLI interaction goes through provider-specific adapters controlled by one orchestrator.

**Reason:** CLI flags, output formats, and provider behavior can change. Business logic must not depend directly on them.

**Consequence:** No direct UI-to-agent shell calls.

---

## ADR-006 — Independent Analysis Before Cross-Review

**Decision:** Codex and Claude produce their first analyses without seeing each other's conclusions.

**Reason:** Reduce anchoring and artificial consensus.

**Consequence:** Independent outputs must be persisted before review begins.

---

## ADR-007 — Bounded Agent Debate

**Decision:** Phase 1 allows one cross-review round. Later rounds must be evidence-driven and bounded.

**Reason:** Unlimited agent conversation can increase cost and latency without improving decisions.

**Consequence:** The orchestrator owns stopping conditions.

---

## ADR-008 — Human Decision Gate

**Decision:** The system cannot convert a recommendation into a market transaction automatically.

**Reason:** The user is the final authority and the product initially provides decision support, not autonomous trading.

**Consequence:** Recommendation, human decision, and real execution are separate records.

---

## ADR-009 — Source Provenance Is First-Class Data

**Decision:** Important external facts must preserve source and timestamps.

**Reason:** Investment research must be auditable and stale/unverified information must be distinguishable from reliable facts.

**Consequence:** Data-provider schemas and agent contracts include provenance/freshness concepts.

---

## ADR-010 — Forecasts Are Scenarios

**Decision:** Future market outcomes are represented as scenarios and assumptions rather than certain point predictions.

**Reason:** Avoid false precision and force explicit reasoning about uncertainty.

**Consequence:** Bear/base/bull cases and invalidators are preferred to unsupported target-price certainty.

---

## ADR-011 — History Is Append-Oriented

**Decision:** Past decisions and important financial-state changes must remain auditable rather than being silently overwritten.

**Reason:** The system's long-term value depends on being able to reconstruct why a decision was made at a historical moment.

**Consequence:** Corrections require audit history/supersession semantics.

---

## ADR-012 — Use the Smallest Sufficient Agent Workflow

**Decision:** Not every task invokes a full committee.

**Reason:** Cost, latency, and complexity should match decision importance.

**Consequence:** Later orchestration supports task-depth levels from one analyst to full committee.

---

## ADR-013 — Web UI Reuses the Same Core

**Decision:** The future local web app will call application services/API built around the verified core.

**Reason:** Avoid duplicated business logic and inconsistent results between CLI and web.

**Consequence:** UI is a presentation layer, not a second implementation of investment logic.

---

## ADR-014 — Weighted Moving Average Cost

**Decision:** A position's cost basis uses weighted moving average cost. A BUY adds `quantity x price + commission + fees` to the basis. A SELL releases `average_cost x quantity` and realizes `net_proceeds - released_cost`.

**Reason:** It is the method a single private investor can verify by hand, it needs no lot-tracking, and it stays correct under partial sells. FIFO or specific-lot identification would require a lot ledger that Phase 1 does not need.

**Consequence:** Realized P&L is measured against the average, not against a chosen lot. If Egyptian tax treatment later requires lot identification, it becomes a schema migration plus a cost-policy setting, not a rewrite of the engine.

---

## ADR-015 — Exact Decimals, Never Floats

**Decision:** Every money and quantity value is a `Decimal` parsed from a string and stored in SQLite as TEXT. Passing a float into the ledger raises an error rather than being silently accepted.

**Reason:** Binary floating point cannot represent ordinary decimal amounts exactly. A rounding drift in a ledger is invisible until it is expensive.

**Consequence:** Callers must pass strings or Decimals. Values are stored as readable text, which also keeps the database inspectable.

---

## ADR-016 — Duplicate Protection by Fingerprint, Repeats by Explicit Consent

**Decision:** Every transaction carries a fingerprint (source + account + external reference, or source + account + date + type + symbol + quantity + price + amount + fees) under a unique index. A second identical transaction is rejected unless the caller explicitly asks to record a repeat, which is then stored with an occurrence suffix.

**Reason:** Idempotent import must be the default before broker-statement ingestion is ever considered safe. But a genuine identical repeat (two equal deposits on one day) is legitimate and must not be impossible.

**Consequence:** Imports are safe to re-run. Manual repeats need `--allow-duplicate`, which makes the intention explicit and auditable.

---

## ADR-017 — Unpriced Holdings Are Excluded and Shown, Not Marked at Cost

**Decision:** A position with no price snapshot on or before the valuation date is excluded from market value and total equity, and is reported explicitly as unpriced.

**Reason:** Marking at cost would silently present a stale purchase price as a current market value. Excluding it understates equity, but visibly and correctly.

**Consequence:** Equity is a lower bound whenever prices are missing. A data-quality score and an explicit missing-price list travel with every valuation, snapshot, and committee run.

---

## ADR-018 — Mock Adapter Runs the Real Pipeline

**Decision:** Mock mode is a provider adapter that produces fictional output and then passes it through exactly the same normalization and contract validation as a real provider CLI.

**Reason:** A mock that returns pre-validated Python objects would test nothing. Reusing the real path means the mock exercises extraction, validation, persistence, and artifacts.

**Consequence:** The whole workflow is testable offline and for free. Every mock output is labelled `MOCK` so it can never be mistaken for analysis.

---

## ADR-019 — Global CLI Options Accepted on Either Side of the Subcommand

**Decision:** `--home`, `--config`, and `--json` are accepted both before and after the subcommand.

**Reason:** `economic portfolio show --json` is what a user naturally types. Requiring `economic --json portfolio show` is a needless failure.

**Consequence:** The shared option parser uses suppressed defaults so the unused copy cannot overwrite the value the user gave on the other side.
