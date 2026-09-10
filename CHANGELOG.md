# Changelog

All meaningful project changes should be recorded here.

## 2026-09-10 — Phase 1 Closed

Phase 1 reviewed and accepted. The deterministic accounting core is now frozen:
`ledger.py`, `portfolio.py`, `simulation.py`, and `decisions.py` change only to
fix a demonstrated bug, never for a feature.

### Added

- Continuous integration (`.github/workflows/tests.yml`). The review noted that
  a test count in a commit message is local evidence, not independent
  verification. The suite now re-runs on a clean machine for every push and
  pull request, on Python 3.10 and 3.12, followed by a smoke test that
  initializes an empty database and drives a full offline committee run.
- `python -m economic` entry point, so scripted and CI use does not depend on
  the console script being on PATH.

### Agreed

- Phase 2 is the market-truth layer only: prices, disclosures, financial
  statements, source, retrieval time, and visible stale-data exposure. No new
  agent roles, review rounds, or reasoning. Recorded in `ROADMAP.md`.
- The evidence gate stays as built. Phase 2 dissolves its restrictions by
  supplying real sourced prices, not by relaxing the rule.

---

## 2026-09-10 — Phase 1 Hardening Pass

A strict review of the delivered Phase 1 against `ARCHITECTURE.md` and
`ACCEPTANCE_CRITERIA.md`, before any Phase 2 work. Four defects were found by
adversarial probing and fixed. No features were added, and the deterministic
accounting core (`ledger.py`, `portfolio.py`, `simulation.py`, `decisions.py`)
was not modified.

### Findings

**F1 (P0) — A single surviving agent looked like a full committee.**
With Codex unavailable, a run reached READY_FOR_HUMAN with no marker of any
kind, and the chair reported an agreement score of 63/100 computed against an
analyst that never spoke. The whole value of the design is the independent
cross-check; a run without one was inheriting its credibility.

**F2 (P0) — Missing and stale data were governed only by the prompt.**
A chair returning `BUY GHOST` at confidence 95 for a security with no price
snapshot at all had that stored verbatim as a fully actionable recommendation.
The prompt asked models not to do this; nothing stopped them.

**F3 (P1) — The chair could overwrite deterministic truth.**
The chair's self-reported `data_quality_score` (99) was persisted on the
recommendation rows in place of the deterministic score (35), directly against
ADR-002.

**F4 (P1) — Duplicate ranks crashed a completed run.**
Two ranked actions sharing `rank: 1` raised an uncaught
`sqlite3.IntegrityError` after all agent work was done, losing the run and
showing the user a traceback.

### Fixes

- **Committee integrity (ADR-021).** Every run is recorded as FULL or DEGRADED.
  FULL requires two valid independent analyses and a completed cross-review of
  both; a missing CLI, a failed provider, an incomplete review round, or a
  single enabled provider all produce DEGRADED with specific reasons. When
  fewer than two analyses exist, the agreement score is recorded as NULL rather
  than accepting a fabricated number. Degradation is surfaced in the run view,
  in `economic history`, in the run artifacts, and again when a decision is
  recorded.
- **Evidence gate (ADR-020).** A deterministic gate in `domain/risk.py` now
  re-decides every ranked action before it is stored. Actionable actions (BUY,
  ADD, REDUCE, SELL) are downgraded to WATCH when the security has no price
  snapshot, no price evidence, or a stale price; when the deterministic
  data-quality score is below a configurable floor (`min_data_quality_for_action`,
  default 50); or when the committee was degraded. Confidence is capped at the
  data-quality score on thin evidence, and separately at 50 for a degraded
  committee, because complete price data does not replace a missing reviewer.
- **Deterministic scores win.** The recommendation rows and the run row now
  store the software's data-quality score. The chair's own claims remain
  verbatim in the run artifacts, so the difference is auditable.
- **Ranks are normalized** to 1..n by the gate, ordered by the chair's stated
  rank then original position, so duplicate or missing ranks can no longer break
  persistence. The CLI also no longer surfaces a database error as a traceback.
- **`doctor` warns in advance** when only one provider is available, since every
  run will then be degraded.

### Preserved deliberately

- A degraded run still reaches the human — it is labelled, not suppressed.
- A restricted recommendation can still be approved. The gate limits what the
  *software* asserts, never the human's authority (ADR-008).
- APPROVE still creates no transaction and no broker order.
- Ledger, valuation, and simulation behaviour is byte-for-byte unchanged.

### Schema

Migration `002_committee_integrity_and_gate.sql`, additive only: committee mode,
integrity, analyst/critique counts, deterministic data-quality and agreement
scores, and the evidence gate on `research_runs`; proposed action, proposed
confidence, restricted flag, and restriction reasons on `recommendations`. Runs
recorded before this migration are labelled `UNKNOWN` rather than being
retroactively claimed as full committees. Verified by upgrading a populated v1
database with no data loss.

### Verified

- `python -m pytest` — **165 passed** (117 before, 48 added).
- New suites: `tests/unit/test_evidence_gate.py` (21),
  `tests/unit/test_committee_integrity.py` (10),
  `tests/integration/test_hardening.py` (14), plus CLI visibility and migration
  regressions.
- Every original test still passes unmodified: no behavioural regression.
- Re-ran the adversarial probes that found F1-F4; all four are now closed.
- Live run against the real Claude Code CLI with Codex absent: recorded
  DEGRADED, agreement reported as not measurable, the actionable proposal
  downgraded to WATCH, and the chair's own summary independently described the
  degradation.
- Accounting walkthrough re-verified: average cost 55.10, realized P&L 1,480,
  equity 103,470; simulation left the ledger identical; oversell rejected;
  APPROVE created no transaction.

### Decisions

- ADR-020 the evidence gate is code, not a prompt.
- ADR-021 a committee is FULL only if it actually happened.

### Phase 1 verdict

**Ready to merge.** Phase 2 (EGX data layer) may begin.

---

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
