# Build Guide

## Purpose

This is the exact implementation guide for the first coding agent. Follow it in order. Do not start with the web UI.

# Milestone 1 — Absolute CLI Core

## Goal

Build the smallest reliable local system that proves the complete decision loop:

```text
portfolio truth
-> independent Codex analysis
-> independent Claude analysis
-> mutual critique
-> synthesis
-> human decision
-> permanent history
```

## Step 1 — Scaffold

Create a Python package under:

```text
src/economic/
```

Add:

```text
domain/
application/
persistence/
agents/
cli/
```

Add `tests/` and runtime folders excluded by `.gitignore`.

Keep dependencies minimal. Prefer Python standard library for the first milestone unless a dependency clearly reduces risk.

## Step 2 — SQLite Foundation

Implement:

- database initialization;
- schema version/migration mechanism;
- repositories for accounts, transactions, price snapshots, research runs, agent runs, recommendations, decisions, audit log.

Do not allow UI/CLI code to contain raw SQL.

## Step 3 — Ledger Domain

Implement transaction types:

- DEPOSIT
- WITHDRAW
- BUY
- SELL

Rules:

- quantity > 0 for trades;
- price > 0 for trades;
- fees >= 0;
- SELL cannot exceed available quantity;
- transaction ordering must be deterministic;
- historical corrections must remain auditable.

## Step 4 — Portfolio Engine

From transactions plus latest known price, calculate:

- cash;
- quantity per symbol;
- average cost;
- realized P&L;
- unrealized P&L;
- market value;
- total equity.

Missing/stale prices must be explicit. Do not silently invent marks.

## Step 5 — CLI Commands

Minimum commands:

```text
init
doctor
account add
cash deposit
cash withdraw
trade buy
trade sell
price set
portfolio show
simulate
committee
decide
history
run show
```

Exact syntax may differ, but command intent must remain simple and scriptable.

## Step 6 — What-If Simulation

Initial deterministic simulation:

- hypothetical BUY or SELL;
- resulting cash;
- resulting quantity;
- estimated market value;
- resulting security weight;
- warnings.

Critical invariant:

**Simulation must never mutate the live ledger.**

## Step 7 — Agent Contract Types

Implement typed/versioned contracts for:

- independent analysis;
- critique;
- final synthesis.

Validate every AI output before persistence as a usable result.

Malformed output must become an explicit failure, never partially trusted.

## Step 8 — Codex Adapter

Implement one adapter responsible for all Codex CLI interaction.

Requirements:

- discover executable;
- doctor/version check;
- non-interactive execution;
- stdin prompt input where practical;
- timeout;
- stdout/stderr capture;
- structured output parsing;
- normalized error states;
- no project writes during investment-analysis mode.

Do not spread Codex command flags across the project.

## Step 9 — Claude Adapter

Same boundary and requirements as Codex adapter.

Support structured/non-interactive output and tolerate provider output-shape variations defensively without accepting invalid JSON as valid analysis.

## Step 10 — Independent Committee Pass

For a committee task:

1. build immutable portfolio snapshot;
2. persist task/run ID;
3. call Codex without Claude's opinion;
4. call Claude without Codex's opinion;
5. validate and persist both outputs.

If one fails, store the failure. Do not fabricate a replacement.

## Step 11 — Cross-Review

Run exactly one review round in Milestone 1:

- Codex critiques Claude;
- Claude critiques Codex.

Ask reviewers to focus on:

- unsupported claims;
- missing evidence;
- stale data;
- portfolio-fit errors;
- overlooked risks;
- useful insights missed by the reviewer.

Do not implement an unlimited debate loop yet.

## Step 12 — Final Synthesis

Use a configurable chair provider.

The chair receives:

- portfolio snapshot;
- independent reports;
- critiques.

It returns ranked actions plus:

- data-quality score;
- agreement score;
- strongest reasons;
- strongest counterargument;
- invalidators;
- unresolved questions;
- human-decision-required flag.

## Step 13 — Human Decision

Allow only explicit human states:

- APPROVE
- REJECT
- HOLD
- MODIFY

Saving APPROVE must not create a transaction or broker order.

Actual execution is recorded separately as a real transaction after the user acts with the broker.

## Step 14 — Run Artifacts

Persist a run directory such as:

```text
data/runs/<run-id>/
```

Store at minimum:

- portfolio snapshot;
- independent outputs;
- critiques;
- final recommendation;
- human decision when recorded.

Database rows and run files should cross-reference the same run ID.

## Step 15 — Tests

Required unit tests:

- deposit/withdraw cash math;
- multiple BUY average cost;
- partial SELL realized P&L;
- cannot oversell;
- price marking;
- missing-price behavior;
- multi-account separation;
- simulation does not mutate ledger;
- malformed agent output rejected;
- agent timeout handled;
- failed agent persisted;
- human approval does not create transaction.

Required integration tests:

- full mock committee workflow;
- SQLite reopen/rebuild produces same portfolio result;
- complete decision run can be reloaded from history.

## Step 16 — Demo Data

Add fictional demo symbols and data only.

Demo must allow a user to test the complete software flow without risking confusion with a real recommendation.

## Step 17 — Documentation Update

When Milestone 1 works:

- update `PROJECT_MAP.md` with actual paths;
- update `CHANGELOG.md`;
- document commands in `README.md`;
- record any architecture changes in `DECISIONS.md`.

# Do Not Build Yet

During Milestone 1 do not add:

- web UI;
- automatic EGX scraping;
- news feeds;
- Monte Carlo;
- charts;
- mobile access;
- broker integration;
- autonomous scheduling;
- many subagent roles.

# Exit Gate

Milestone 1 is complete only when all acceptance criteria for the core pass and the entire loop can be demonstrated locally using mock agents, then with real Codex/Claude adapters when credentials/connectivity are available.

Reliability beats feature count.
