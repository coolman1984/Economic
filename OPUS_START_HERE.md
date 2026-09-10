# Opus 5 High — Start Here

You are the first implementation agent for the Economic repository.

Your job is **not** to build the full product. Your job is to implement and verify Phase 1: the Absolute CLI Core.

## Read First

Read these files in order before editing anything:

1. `AGENTS.md`
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

Then inspect the repository and confirm that Phase 1 is still the current implementation target.

# Mission

Deliver a small, reliable CLI application that proves this full loop:

```text
portfolio truth
-> Codex independent analysis
-> Claude independent analysis
-> mutual critique
-> final synthesis
-> human decision
-> permanent history
```

Do not start the web app yet.

# Required Phase 1 Capabilities

Implement:

- local SQLite persistence;
- multiple accounts;
- deposits and withdrawals;
- BUY and SELL ledger;
- manual price snapshots;
- deterministic quantity, average cost, realized P&L, unrealized P&L, cash, market value, and total equity;
- what-if BUY/SELL simulation without mutation;
- Codex CLI adapter;
- Claude Code CLI adapter;
- structured output contracts and validation;
- independent analysis from both providers;
- exactly one cross-review round;
- configurable final chair synthesis;
- human APPROVE / REJECT / HOLD / MODIFY states;
- run artifacts and audit/history;
- mock mode for end-to-end testing without live model calls;
- automated tests.

# Important Constraints

- No autonomous broker execution.
- No web UI in Phase 1.
- No automatic EGX scraping in Phase 1.
- No invented market data.
- No AI-calculated accounting truth.
- No unbounded agent loops.
- No hidden destructive edits.
- No secrets committed.

# Recommended Implementation Order

1. Scaffold package and tests.
2. Database initialization/migrations.
3. Ledger rules.
4. Portfolio calculation engine.
5. CLI commands.
6. Simulation engine.
7. Agent response schemas/validators.
8. Codex adapter.
9. Claude adapter.
10. Orchestrator independent pass.
11. Cross-review.
12. Chair synthesis.
13. Human decision persistence.
14. History/run inspection.
15. Mock end-to-end workflow.
16. Real adapter smoke tests if environment permits.
17. Documentation update.

# Engineering Expectations

Before changing architecture:

- explain why the existing plan cannot satisfy the requirement;
- prefer a smaller fix over a rewrite;
- update `DECISIONS.md` if a major decision changes;
- update `PROJECT_MAP.md` when actual paths differ from the planned map;
- update `CHANGELOG.md` when the milestone is delivered.

# Verification

Do not claim completion until the relevant checklist in `ACCEPTANCE_CRITERIA.md` passes.

At minimum demonstrate:

1. create account;
2. deposit cash;
3. record multiple buys;
4. verify average cost;
5. record a partial sell;
6. verify realized/unrealized P&L;
7. set price;
8. view portfolio;
9. run a simulation and prove database state did not change;
10. run a full committee in mock mode;
11. record a human decision;
12. reload the complete run from history;
13. run all tests successfully.

# Deliverable Report

When finished, report:

- implemented modules;
- commands available;
- tests and exact results;
- unresolved limitations;
- any deviations from the plan and why;
- exact next recommended phase.

The correct outcome of this task is a **small trusted core**, not a feature-rich prototype.
