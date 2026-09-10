# Changelog

All meaningful project changes should be recorded here.

## 2026-09-10 — Phase 1 Delivered: Absolute CLI Core

### Added

- Python package `src/economic/` with strict layering: `cli -> application -> domain`,
  with persistence and agent adapters behind the application layer.
- Exact-decimal money module. Floats are rejected before they reach the ledger.
- Ledger domain covering DEPOSIT, WITHDRAW, BUY, and SELL with validation for
  quantity, price, fees, dates, symbols, and duplicate fingerprints.
- Deterministic portfolio engine: cash, quantity, weighted average cost,
  realized and unrealized P&L, market value, total equity, weights, and
  consolidated multi-account views.
- Documented pricing policy: the latest snapshot on or before the valuation
  date. Unpriced holdings are excluded from equity and reported explicitly.
- Portfolio rules and a deterministic data-quality score (minimum cash, maximum
  position weight, restricted symbols, missing and stale prices).
- SQLite persistence with a versioned migration runner, backup, integrity check,
  and repositories for every Phase 1 table. No SQL outside `persistence/`.
- Append-oriented audit log for account, transaction, price, run, decision, and
  execution changes.
- Deterministic what-if simulation that operates on a copy of portfolio state and
  cannot mutate the ledger.
- Versioned agent contracts for independent analysis, critique, and chair
  synthesis, with a validator that recovers a payload from fenced blocks,
  provider envelopes, and JSONL streams but never relaxes a contract.
- Codex and Claude Code CLI adapters with executable discovery, non-interactive
  execution, stdin prompts, timeouts, captured stdout/stderr/exit status, and
  normalized failure states.
- Offline mock adapter that produces clearly labelled fictional output through
  the same validation path as a real provider.
- Orchestrator running independent analysis, exactly one cross-review round, and
  a configurable chair synthesis, with explicit stopping conditions and recorded
  disagreements.
- Run artifacts under `data/runs/<run-id>/` cross-referenced with database rows.
- Human decision gate supporting APPROVE, REJECT, HOLD, and MODIFY, with actual
  broker executions recorded as separate linked records.
- CLI: `init`, `doctor`, `account`, `instrument`, `cash`, `trade`, `price`,
  `portfolio`, `simulate`, `committee`, `decide`, `execution`, `history`, `run`,
  `audit`, and `demo`, each with `--json` output.
- Fictional `ZZDEMO*` demo data, deliberately leaving one holding unpriced.
- 117 tests (unit and integration) covering ledger arithmetic, oversell
  protection, valuation, simulation non-mutation, malformed and timed-out agent
  output, the full mock committee flow, persistence reload, the human gate, and
  the CLI.

### Verified

- `python -m pytest` — 117 passed.
- CLI walkthrough: two buys and a partial sell produce average cost 55.10 and
  realized P&L 1,480 as calculated by hand.
- Oversell, overdraft, and unknown-account attempts are rejected with clear
  messages and a non-zero exit code.
- A simulation left the ledger byte-identical.
- A full mock committee run reached READY_FOR_HUMAN with both providers
  analyzing independently, one cross-review round, recorded disagreements, and a
  validated synthesis.
- A live run against the real Claude Code CLI produced valid contract output;
  with the Codex CLI absent, the failure was recorded as `executable_missing`,
  cross-review was skipped, and the run still reached the human gate without
  fabricating the missing analysis.
- A recorded APPROVE created no transaction; the portfolio snapshot was
  unchanged.
- A past run reloaded with its original snapshot after the live portfolio moved on.

### Decisions

- ADR-014 weighted moving average cost.
- ADR-015 exact decimals, never floats.
- ADR-016 duplicate protection by fingerprint, repeats by explicit consent.
- ADR-017 unpriced holdings excluded and shown, not marked at cost.
- ADR-018 mock adapter runs the real pipeline.
- ADR-019 global CLI options accepted on either side of the subcommand.

### Known Limitations

- No automated market data. Prices are manual snapshots only.
- No sector or liquidity limits yet; only minimum cash, maximum position weight,
  and restricted symbols are enforced.
- Corrections use supersession at the repository level; no `transaction edit`
  CLI command exists yet.
- Cost and token usage are not captured; provider CLIs do not report them on the
  path used here.
- Dividends and corporate actions are out of scope for Phase 1.

### Next Target

**Phase 2 — EGX Data Layer.** See `ROADMAP.md` and the Phase 2 gate in
`ACCEPTANCE_CRITERIA.md`.

---

## 2026-09-10 — Repository Foundation

### Added

- Project README and core product definition.
- Mandatory coding-agent instructions.
- Complete product master plan.
- Repository/project map and dependency boundaries.
- Layered technical architecture.
- Authoritative data model and invariants.
- Codex/Claude multi-agent orchestration contract.
- Investment, evidence, risk, simulation, and human-control rules.
- Staged development roadmap.
- Exact Phase 1 build guide.
- Acceptance criteria and quality gates.
- Architectural decision record.
- Direct implementation handoff for Opus 5 High.

### Target at the Time

**Phase 1 — Absolute CLI Core** (delivered; see the entry above).
