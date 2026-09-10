# Acceptance Criteria

## Purpose

This file defines the minimum evidence required before a phase is considered complete. Passing a demo manually is not enough.

# Phase 1 — Absolute CLI Core

## A. Repository and Structure

- [ ] Source code follows the boundaries in `PROJECT_MAP.md`.
- [ ] Runtime financial data is excluded from git.
- [ ] No secrets are committed.
- [ ] `README.md` contains setup and usage instructions.
- [ ] `CHANGELOG.md` records the delivered milestone.

## B. Database

- [ ] SQLite database can be initialized from an empty state.
- [ ] Schema versioning/migration mechanism exists.
- [ ] Accounts persist after restart.
- [ ] Transactions persist after restart.
- [ ] Research runs and human decisions persist after restart.
- [ ] Important financial edits are auditable.

## C. Ledger Correctness

- [ ] Deposit increases cash by the exact amount.
- [ ] Withdrawal decreases cash by the exact amount.
- [ ] BUY decreases cash by price × quantity + fees.
- [ ] Multiple BUY operations calculate the defined average-cost method correctly.
- [ ] SELL increases cash by proceeds minus fees.
- [ ] Partial SELL calculates realized P&L correctly.
- [ ] SELL above current quantity is rejected.
- [ ] Closed positions result in zero remaining quantity.
- [ ] Rebuilding from stored transactions reproduces the same holdings.

## D. Portfolio Valuation

- [ ] Latest known price is used according to documented policy.
- [ ] Market value is correct.
- [ ] Unrealized P&L is correct.
- [ ] Realized P&L is correct.
- [ ] Total account equity is correct.
- [ ] Multiple accounts remain separated.
- [ ] Consolidated view equals the sum of included accounts.
- [ ] Missing prices are visible, not silently guessed.

## E. Simulation

- [ ] BUY simulation returns expected post-trade cash and quantity.
- [ ] SELL simulation validates available quantity.
- [ ] Simulation returns resulting position weight.
- [ ] Simulation cannot mutate transactions, balances, or positions.
- [ ] Same inputs produce the same deterministic result.

## F. Codex Adapter

- [ ] `doctor` can detect whether Codex CLI is available.
- [ ] Adapter supports non-interactive execution.
- [ ] Timeout is enforced.
- [ ] stdout/stderr and exit status are captured.
- [ ] Structured output is normalized.
- [ ] Malformed output is rejected.
- [ ] Failure cannot modify portfolio state.

## G. Claude Adapter

- [ ] `doctor` can detect whether Claude Code CLI is available.
- [ ] Adapter supports non-interactive execution.
- [ ] Timeout is enforced.
- [ ] stdout/stderr and exit status are captured.
- [ ] Structured output is normalized.
- [ ] Malformed output is rejected.
- [ ] Failure cannot modify portfolio state.

## H. Committee Workflow

- [ ] Every committee task receives a unique run ID.
- [ ] Portfolio snapshot is saved before analysis.
- [ ] Codex independent analysis is generated without Claude's conclusion.
- [ ] Claude independent analysis is generated without Codex's conclusion.
- [ ] Both independent outputs are persisted before cross-review.
- [ ] Codex critique of Claude is persisted.
- [ ] Claude critique of Codex is persisted.
- [ ] Exactly one cross-review round is used in Phase 1.
- [ ] Final synthesis is structured and validated.
- [ ] Final synthesis exposes uncertainty and missing data.
- [ ] Final output requires human decision.

## I. Human Gate

- [ ] User can record APPROVE.
- [ ] User can record REJECT.
- [ ] User can record HOLD.
- [ ] User can record MODIFY with a note/change.
- [ ] An APPROVE action does not create a market transaction automatically.
- [ ] Actual execution can be recorded separately.

## J. Audit and Reproducibility

- [ ] A past run can be re-opened.
- [ ] Past portfolio snapshot can be viewed.
- [ ] Independent agent outputs can be viewed.
- [ ] Critiques can be viewed.
- [ ] Final synthesis can be viewed.
- [ ] Human decision can be viewed.
- [ ] Historical records do not silently change when current portfolio data changes.

## K. Test Evidence

- [ ] Unit tests cover ledger arithmetic.
- [ ] Unit tests cover oversell protection.
- [ ] Unit tests cover simulation non-mutation.
- [ ] Unit tests cover malformed AI output.
- [ ] Unit tests cover agent timeout/failure handling.
- [ ] Integration test covers full mock committee flow.
- [ ] Integration test proves persistence/reload.
- [ ] Test command is documented.
- [ ] All required tests pass on the target development machine.

# Phase 2 — EGX Data Layer Gate

Do not call Phase 2 complete until:

- [ ] each provider has a stable adapter;
- [ ] every normalized record has source/provenance;
- [ ] duplicate ingestion is idempotent;
- [ ] freshness can be evaluated;
- [ ] source failures are explicit;
- [ ] official-source data is preferred when available;
- [ ] selected real EGX companies can be traced from displayed fact back to source.

# Phase 3 — Risk and Rebalancing Gate

- [ ] portfolio rules are configurable;
- [ ] resulting position weight is checked;
- [ ] sector weight is checked;
- [ ] minimum cash is checked;
- [ ] consolidated exposure across accounts is checked;
- [ ] a violating proposal is clearly flagged before human approval;
- [ ] new-cash-only rebalance works deterministically;
- [ ] full rebalance proposal never executes automatically.

# Phase 4 — Research Intelligence Gate

- [ ] role contracts are explicit;
- [ ] task depth is bounded;
- [ ] material disagreements are stored;
- [ ] targeted follow-up does not restart full analysis without reason;
- [ ] stopping conditions prevent loops;
- [ ] strongest counterargument is always visible;
- [ ] source quality and data quality affect confidence;
- [ ] cost/performance metadata is captured where available.

# Phase 6 — Web App Gate

- [ ] UI calls the tested application/core layer.
- [ ] no accounting calculations are duplicated in JavaScript/UI.
- [ ] no direct UI-to-Codex/Claude shell calls exist.
- [ ] all important actions have clear loading/error states.
- [ ] data timestamps are visible.
- [ ] investment room shows agent stages and disagreements clearly.
- [ ] human approval remains explicit.
- [ ] local launcher works on target Windows environment.

# Final Principle

A phase is complete only when the behavior is demonstrable, tested, persistent, and understandable by the next agent without reverse engineering.
