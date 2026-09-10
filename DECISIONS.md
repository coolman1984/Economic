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
