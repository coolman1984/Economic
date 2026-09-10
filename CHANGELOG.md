# Changelog

All meaningful project changes should be recorded here.

## 2026-09-10 — Phase 2 Delivered: Reliable EGX Data Layer (Market-Truth Only)

Built exactly to the scope locked in `ROADMAP.md` on 2026-09-10: instrument
master, price ingestion, official disclosure ingestion, financial-statement
ingestion/import, provenance, freshness, idempotent duplicate handling, and
local caching. No news feed, no new agent role, no orchestration change, and
no change to the frozen accounting core (`domain/ledger.py`,
`domain/portfolio.py`, `domain/simulation.py`, `domain/decisions.py`), agent
orchestration (`agents/orchestrator.py`, `agents/base_adapter.py`,
`agents/contracts.py`), or recommendation logic (`domain/risk.py`'s evidence
gate) — confirmed by `git status` against every file in that list before
closing the phase.

### Research first

Before writing ingestion code, this session probed candidate EGX data sources
directly. Every outbound request to an external host — `egx.com.eg`,
`egxapi.com`, `mubasher.info`, `eodhd.com`, `twelvedata.com`, even
`wikipedia.org` — returned `403` from this session's own egress policy, and
the `WebFetch` tool was blocked identically; only `WebSearch` (summarized
snippets, not raw pages) was reachable. Findings, and what could and could not
be verified, are recorded in `EGX_DATA_SOURCES.md`. Two things followed
directly from that research:

- EGX's real machine-readable feed is licensed through **EGID**, described in
  search results as *"the sole authorized data provider"* for EGX market data
  for 25+ years — not a free public API. No credential-free official feed
  exists to build against.
- The task's own instruction — *"do not assume scraping or APIs are reliable
  until proven with small probes"* — could not be satisfied for any live
  source from this session, so no live adapter for any source is shipped or
  claimed reliable (ADR-022).

### Added

- **`data_providers/` package** — provider contracts (`base.py`: `Provider`,
  `Provenance`, `SourceTier`, `IngestionReport`, `ProviderError` with a
  normalized failure taxonomy paralleling `agents/base_adapter.py`), a
  freshness classifier for disclosures/financial facts (`freshness.py`,
  ADR-023, deliberately independent of the frozen price-staleness check), and
  four file-based providers: `InstrumentFileProvider`, `PriceFileProvider`,
  `DisclosureFileProvider`, `FinancialFactFileProvider`. Each validates
  eagerly, parses money/quantity as exact `Decimal` (never float, per
  ADR-015), and rejects a bad individual row without losing the good ones in
  the same file.
- **`application/market_data_service.py`** — one atomic transaction per
  ingestion run (including the audit row, success or failure), plus
  `trace_symbol()`: every stored fact for a symbol with its source, satisfying
  the Phase 2 traceability gate.
- **Schema migration 003** — creates `external_documents` and
  `financial_facts` (documented in `DATA_MODEL.md` since Phase 1 planning but
  never built until now), a new `ingestion_runs` audit table, and adds
  `source_tier`/`published_at` to `price_snapshots` with safe defaults.
  Verified to upgrade a populated v2 database with zero data loss.
- **CLI**: `economic market import-instruments|import-prices|
  import-disclosures|import-financials|trace|history`, all with `--json`.
- **CI**: the GitHub Actions suite now also runs the market-data
  import-then-trace-then-reimport loop on every push, proving idempotency and
  traceability on a clean runner, not just locally.
- **Real-company traceability fixture**: two currently-listed EGX companies
  (COMI — Commercial International Bank Egypt, ISIN EGS60121C018; HRHO — EFG
  Holding S.A.E., ISIN EGS69101C011), with real ISINs and citation URLs
  gathered via research rather than invented, used throughout the test suite
  and the CI smoke test.
- 59 new tests (11 freshness, 22 provider parsing/validation, 13 full-pipeline
  integration, 3 tier-preference regression, repository-level upsert/dedup
  tests, 2 CLI round-trip tests, 1 migration-upgrade regression).

### Fixed during the phase (found by the phase's own tests, not shipped broken)

- **Document-to-fact linking ignored source-name mismatches incorrectly.** A
  financial fact and the document it cites are routinely attributed to
  different named sources (a data aggregator's number, the exchange's filing)
  even when a human links them with the same external reference. The initial
  lookup required both source names to match, which silently failed to link
  in exactly the ordinary case the feature exists for. Fixed by keying the
  lookup on the external_id alone (ADR-024).
- **A CSV-reading generator validated lazily.** `read_rows` originally used
  `yield`, so its file-not-found/empty/bad-schema checks only ran on first
  iteration — a caller that didn't immediately loop would silently get no
  error at all. Rewritten to validate eagerly and return a list; caught by a
  smoke test before it shipped.
- **`InstrumentRepository` stored `isin` but never selected it back out** —
  a pre-existing Phase 1 gap this phase's work exposed. `Instrument` and the
  repository's queries now carry it.
- **`official-source data is preferred when available` was not actually
  implemented.** When two sources reported a price for the same instrument on
  the same date, `latest_mark` picked whichever was inserted last, not the
  more authoritative one. Fixed: candidates now rank by source-tier authority
  first, insertion recency only as a same-tier tiebreak — which also
  reproduces exact Phase 1 behavior for every pre-Phase-2 row, since they all
  share the IMPORT default tier.

### Verified

- `python -m pytest` — **224 passed** (165 Phase 1 + 59 Phase 2), zero Phase 1
  tests modified.
- Full pipeline exercised end to end: instrument master -> prices ->
  disclosures -> financial facts, for two real EGX companies, with real
  provenance on every row.
- Idempotency: re-importing identical files after the first run left every
  row count unchanged; every row routed to the update path.
- Source failures: a missing file, an empty file, and a renamed-column
  ("schema changed") file each raised a typed, normalized failure and wrote
  nothing; every attempt — success and failure — appears in `market history`.
- Traceability: `economic market trace --symbol COMI` and `--symbol HRHO` each
  show instrument identity (including a real ISIN), a priced snapshot, a
  disclosure, and — for COMI — a financial fact whose `source_document_id`
  resolves to the actual disclosure row, completing fact -> document -> source.
- Tier preference: an OFFICIAL-tier price beats a COMMUNITY-tier price
  reported for the same date; a more recent date still always wins over an
  older OFFICIAL one (freshness first, tier only breaks a same-date tie).
- Architecture: `data_providers/` contains no SQL and no reference to
  `agents/`/`cli/`; no SQL exists outside `persistence/`; no `subprocess` call
  exists outside `agents/` — checked by grep, not assumed.
- CI: the exact sequence the GitHub Actions workflow runs (init, import
  instruments, import prices, trace, re-import, history) was run locally
  first and produced identical output before being pushed.

### Decisions

- ADR-022 local provenance-carrying import is the Phase 2 default, not a live
  scraper.
- ADR-023 freshness is judged separately for ingested facts and for portfolio
  pricing.
- ADR-024 documents and financial facts are deduplicated by fingerprint,
  linked by external ID.

### Known limitations (explicit, not silent)

- No live HTTP/scraping adapter for EGX or any third-party aggregator. Every
  fact enters through a file a human placed there. This is a deliberate
  boundary (ADR-022), not an oversight — see `EGX_DATA_SOURCES.md`.
- Every Phase 2 record is tagged `source_tier = IMPORT`: the tier the software
  actually verified, not an assumed `OFFICIAL` for content that merely
  originated from an official channel the software cannot itself authenticate.
- News ingestion is out of scope for Phase 2 by the locked scope decision
  (opinion-tier data, deferred to Phase 4).
- `financial_facts` normalization is a flat metric/value/period model; no
  statement-template or XBRL-style structure. Sufficient for the traceability
  gate; a richer model is future work if a real statement feed is added.

### Next Target

**Phase 3 — Portfolio Construction and Risk**, per `ROADMAP.md`.

---

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
