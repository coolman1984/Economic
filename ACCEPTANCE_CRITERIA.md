# Acceptance Criteria

## Purpose

This file defines the minimum evidence required before a phase is considered complete. Passing a demo manually is not enough.

# Phase 1 — Absolute CLI Core

**Status: PASSED, hardened** — verified on 2026-09-10 by the 165-test suite (`python -m pytest`), the documented CLI walkthrough, full and degraded mock committee runs, and live runs against the real Claude Code CLI. A hardening pass then closed four defects found by adversarial review; see `CHANGELOG.md` for findings and evidence.

## A. Repository and Structure

- [x] Source code follows the boundaries in `PROJECT_MAP.md`.
- [x] Runtime financial data is excluded from git.
- [x] No secrets are committed.
- [x] `README.md` contains setup and usage instructions.
- [x] `CHANGELOG.md` records the delivered milestone.

## B. Database

- [x] SQLite database can be initialized from an empty state.
- [x] Schema versioning/migration mechanism exists.
- [x] Accounts persist after restart.
- [x] Transactions persist after restart.
- [x] Research runs and human decisions persist after restart.
- [x] Important financial edits are auditable.

## C. Ledger Correctness

- [x] Deposit increases cash by the exact amount.
- [x] Withdrawal decreases cash by the exact amount.
- [x] BUY decreases cash by price × quantity + fees.
- [x] Multiple BUY operations calculate the defined average-cost method correctly.
- [x] SELL increases cash by proceeds minus fees.
- [x] Partial SELL calculates realized P&L correctly.
- [x] SELL above current quantity is rejected.
- [x] Closed positions result in zero remaining quantity.
- [x] Rebuilding from stored transactions reproduces the same holdings.

## D. Portfolio Valuation

- [x] Latest known price is used according to documented policy.
- [x] Market value is correct.
- [x] Unrealized P&L is correct.
- [x] Realized P&L is correct.
- [x] Total account equity is correct.
- [x] Multiple accounts remain separated.
- [x] Consolidated view equals the sum of included accounts.
- [x] Missing prices are visible, not silently guessed.

## E. Simulation

- [x] BUY simulation returns expected post-trade cash and quantity.
- [x] SELL simulation validates available quantity.
- [x] Simulation returns resulting position weight.
- [x] Simulation cannot mutate transactions, balances, or positions.
- [x] Same inputs produce the same deterministic result.

## F. Codex Adapter

- [x] `doctor` can detect whether Codex CLI is available.
- [x] Adapter supports non-interactive execution.
- [x] Timeout is enforced.
- [x] stdout/stderr and exit status are captured.
- [x] Structured output is normalized.
- [x] Malformed output is rejected.
- [x] Failure cannot modify portfolio state.

## G. Claude Adapter

- [x] `doctor` can detect whether Claude Code CLI is available.
- [x] Adapter supports non-interactive execution.
- [x] Timeout is enforced.
- [x] stdout/stderr and exit status are captured.
- [x] Structured output is normalized.
- [x] Malformed output is rejected.
- [x] Failure cannot modify portfolio state.

## H. Committee Workflow

- [x] A run with fewer than two cross-reviewed analyses is recorded as DEGRADED (ADR-021).
- [x] A degraded committee is labelled in the database, run view, history, and at decision time.
- [x] An agreement score is not recorded when fewer than two analyses exist.
- [x] Missing, stale, or unpriced data programmatically restricts actionable recommendations (ADR-020).
- [x] A restriction records the proposed action, the restricted action, and the reasons.
- [x] The deterministic data-quality score is stored, never the chair's own claim.
- [x] Every committee task receives a unique run ID.
- [x] Portfolio snapshot is saved before analysis.
- [x] Codex independent analysis is generated without Claude's conclusion.
- [x] Claude independent analysis is generated without Codex's conclusion.
- [x] Both independent outputs are persisted before cross-review.
- [x] Codex critique of Claude is persisted.
- [x] Claude critique of Codex is persisted.
- [x] Exactly one cross-review round is used in Phase 1.
- [x] Final synthesis is structured and validated.
- [x] Final synthesis exposes uncertainty and missing data.
- [x] Final output requires human decision.

## I. Human Gate

- [x] User can record APPROVE.
- [x] User can record REJECT.
- [x] User can record HOLD.
- [x] User can record MODIFY with a note/change.
- [x] An APPROVE action does not create a market transaction automatically.
- [x] Actual execution can be recorded separately.

## J. Audit and Reproducibility

- [x] A past run can be re-opened.
- [x] Past portfolio snapshot can be viewed.
- [x] Independent agent outputs can be viewed.
- [x] Critiques can be viewed.
- [x] Final synthesis can be viewed.
- [x] Human decision can be viewed.
- [x] Historical records do not silently change when current portfolio data changes.

## K. Test Evidence

- [x] Unit tests cover ledger arithmetic.
- [x] Unit tests cover oversell protection.
- [x] Unit tests cover simulation non-mutation.
- [x] Unit tests cover malformed AI output.
- [x] Unit tests cover agent timeout/failure handling.
- [x] Integration test covers full mock committee flow.
- [x] Integration test proves persistence/reload.
- [x] Test command is documented.
- [x] All required tests pass on the target development machine.

# Phase 2 — EGX Data Layer Gate

**Status: PASSED, with an honest scope boundary** — verified 2026-09-10. See
`CHANGELOG.md` for the full evidence and `EGX_DATA_SOURCES.md` for what was and
was not verifiable from this development session (its egress is blocked to
every external host, confirmed by direct probe). Phase 2 ships local,
provenance-carrying **import** as the working default (ADR-022); a live
HTTP/scraping adapter behind the same contract is explicit future work, not
claimed done here.

Do not call Phase 2 complete until:

- [x] each provider has a stable adapter — `InstrumentFileProvider`,
      `PriceFileProvider`, `DisclosureFileProvider`, `FinancialFactFileProvider`
      all implement the shared `Provider` contract in `data_providers/base.py`;
      22 unit tests cover their parsing, validation, and rejection behavior.
- [x] every normalized record has source/provenance — every `price_snapshots`,
      `external_documents`, and `financial_facts` row carries source_name,
      source_tier, source_url (where given), published_at, and retrieved_at;
      documents additionally carry a SHA-256 of their actual file bytes.
- [x] duplicate ingestion is idempotent — re-importing identical files
      leaves row counts unchanged (routes to update, not insert) for every
      one of the four kinds; a corrected document with the same external_id
      updates in place. Verified by dedicated regression tests.
- [x] freshness can be evaluated — `data_providers/freshness.py`
      (`FreshnessPolicy`) classifies disclosures/financial facts as
      FRESH/AGING/STALE/UNKNOWN; prices continue using the frozen Phase 1
      staleness check (ADR-017, ADR-023 — the two are deliberately separate).
- [x] source failures are explicit — a missing file, empty file, or changed
      schema raises a typed `ProviderError` with a normalized failure_kind and
      writes nothing; every ingestion attempt (success or failure) is recorded
      in `ingestion_runs`, never silently dropped.
- [x] official-source data is preferred when available — `latest_mark` orders
      candidates for the same date by source-tier authority before recency of
      insertion, so an OFFICIAL-tier price beats a COMMUNITY-tier price
      reported for the same day. (This was a real gap found and fixed during
      the phase; see ADR-024 note in `CHANGELOG.md`.)
- [x] selected real EGX companies can be traced from displayed fact back to
      source — two real, currently-listed EGX companies (COMI — Commercial
      International Bank Egypt, ISIN EGS60121C018; HRHO — EFG Holding S.A.E.,
      ISIN EGS69101C011), with real ISINs and citation URLs gathered via
      research, are used as the traceability fixture. `economic market trace
      --symbol COMI` and `--symbol HRHO` show every stored fact — instrument
      identity, price, disclosure, financial-statement line item — each with
      its real source name, URL, and date, including the fact -> document ->
      source chain for the financial fact.

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
