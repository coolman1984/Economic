# Roadmap

The project must grow in verified layers. Do not skip ahead because later features are visually attractive.

## Phase 0 — Repository Foundation

Goal: make the project understandable before coding.

Deliverables:

- planning documents;
- architecture boundaries;
- project map;
- data model;
- agent contracts;
- investment/risk rules;
- definition of done;
- initial issue/milestone plan.

Gate:

A new coding agent can explain the product, first milestone, core boundaries, and non-goals without guessing.

---

## Phase 1 — Absolute CLI Core

Goal: prove the complete investment-decision loop with the smallest working system.

Deliverables:

- Python CLI application;
- local SQLite database;
- account creation;
- deposit/withdrawal;
- BUY/SELL transaction ledger;
- manual price snapshots;
- deterministic positions, cash, cost, P&L, and equity;
- what-if BUY/SELL simulation;
- Codex CLI adapter;
- Claude Code CLI adapter;
- structured output validation;
- dual independent analysis;
- one mutual critique round;
- final chair synthesis;
- explicit human decision recording;
- persisted run artifacts;
- tests.

Gate:

The full loop works locally and repeated tests prove that simulations never mutate the ledger and AI failures cannot corrupt portfolio truth.

---

## Phase 2 — Reliable EGX Data Layer

**Scope agreed 2026-09-10: the market-truth layer only. No new intelligence.**

Goal: replace manual context with traceable market/company data. Phase 2 adds
*facts and their provenance*. It adds no new agent roles, no extra review
rounds, and no new reasoning — the committee keeps working exactly as it does
today, just on better-sourced data.

Deliverables:

- instrument master;
- market price provider adapter;
- official disclosure ingestion;
- financial statement ingestion or normalized import path;
- source provenance on every record;
- publication and retrieval timestamps;
- freshness rules and visible stale-data exposure;
- duplicate detection;
- cached local data.

Explicitly deferred out of Phase 2:

- news provider abstraction (opinion-tier data; it can wait for Phase 4);
- any new agent role, review round, or orchestration change;
- any change to the deterministic accounting core.

Why this shape: Phase 1 closed with the evidence gate refusing actionable
recommendations on unpriced or stale securities (ADR-020). That restriction is
correct, and Phase 2 is what dissolves it naturally — once prices arrive with a
source and a retrieval time, the gate opens on its own. Nothing about the gate
needs relaxing.

Gate:

For selected EGX companies, the system can show exactly where each important
fact came from and when it was updated.

---

## Phase 3 — Portfolio Construction and Risk

Goal: make recommendations portfolio-aware.

Deliverables:

- security weight limits;
- sector classifications;
- sector limits;
- minimum cash rule;
- target allocation ranges;
- exposure across multiple accounts;
- risk gate;
- new-cash-only rebalance;
- full rebalance proposal;
- richer deterministic what-if analysis.

Gate:

A recommendation that would breach configured portfolio rules is reliably flagged before human review.

---

## Phase 4 — Research Intelligence

Goal: evolve from two generic agents into a disciplined investment committee.

Deliverables:

- data verifier role;
- fundamental analyst role;
- valuation role;
- news/disclosure role;
- market/price role;
- sector/macro role;
- portfolio/risk role;
- devil's advocate role;
- chair role;
- task-depth routing;
- evidence-driven disagreement records;
- targeted follow-up research;
- stop conditions;
- cost/performance tracking.

Gate:

The system can show independent opinions, disagreements, resolution evidence, rejected ideas, and the final reason for ranking each action.

---

## Phase 5 — Simulation and Stress Testing

Goal: understand downside and portfolio behavior before action.

Deliverables:

- configurable market shock tests;
- sector shocks;
- largest-position shock;
- cash/liquidity stress;
- event scenarios;
- scenario snapshots;
- optional historical stress periods;
- Monte Carlo only if methodology/data quality justify it.

Gate:

Every high-materiality recommendation can be evaluated through deterministic stored scenarios before human approval.

---

## Phase 6 — Local Web Application

Goal: put a premium, simple interface over the proven core.

Deliverables:

- local API around application services;
- dashboard;
- accounts;
- portfolios;
- transactions;
- positions;
- company page;
- watchlist;
- news/disclosures;
- research center;
- risk/rebalancing;
- simulations;
- investment room;
- recommendations;
- decision history;
- settings;
- one-click Windows launcher.

Gate:

All web actions call the same tested core. No financial or agent logic is duplicated in the UI.

---

## Phase 7 — Decision Memory and Learning

Goal: make the system improve through its own historical record.

Deliverables:

- investment theses;
- thesis version history;
- outcome reviews at defined horizons;
- expected-versus-actual comparison;
- confidence calibration;
- agent/role quality metrics;
- recurring-error discovery;
- decision-quality reports.

Gate:

The system can answer why a past decision was made using the information available at that historical moment.

---

## Phase 8 — Automation and Alerts

Goal: reduce manual monitoring while keeping decision authority human.

Deliverables:

- scheduled data refresh;
- daily material-event scan;
- disclosure alerts;
- price/volume alerts;
- thesis-change alerts;
- portfolio-limit alerts;
- daily/weekly/monthly reports;
- background task logs and retries.

Gate:

Automated monitoring surfaces useful exceptions without flooding the user with noise or silently changing portfolio state.

---

## Phase 9 — Remote and Mobile Access

Goal: access the proven local investment office safely from other devices.

Possible deliverables:

- authenticated remote access;
- optional encrypted synchronization;
- responsive mobile web UI;
- push notifications;
- secure deployment option.

Gate:

Remote capability does not weaken local data integrity or human-control rules.

---

## Explicitly Deferred

Until the system is mature and separately evaluated:

- automatic broker order placement;
- public advisory service;
- multi-user commercial SaaS;
- autonomous capital allocation;
- unrestricted agent loops.
