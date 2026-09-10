# Project Master Plan

## 1. Product Vision

Economic is a personal investment operating system for the Egyptian Exchange. It should behave like a disciplined digital investment office rather than a simple portfolio tracker or trading bot.

The system combines deterministic portfolio accounting, current market/company information, risk rules, scenario analysis, and a multi-agent research committee built around Codex CLI and Claude Code CLI.

The user remains the final investment authority.

## 2. Core User Journey

1. User opens the local web app on the PC.
2. The system loads all accounts, positions, cash, prices, and open investment theses.
3. Market data, disclosures, financial statements, and news are refreshed when available.
4. User asks a question, or the system identifies something that deserves attention.
5. The orchestrator creates a research task.
6. Codex and Claude analyze independently.
7. Each may delegate narrowly scoped sub-tasks.
8. They critique each other's conclusions.
9. The orchestrator isolates material disagreements and requests targeted follow-up only where useful.
10. Deterministic risk and simulation engines test the candidate actions.
11. A chair synthesis ranks the alternatives.
12. User approves, rejects, modifies, or postpones.
13. If the user later executes a real broker transaction, the actual execution is recorded separately.
14. The entire evidence/decision snapshot is preserved.
15. Later, the system evaluates what happened versus what was expected.

## 3. Major Capabilities

### Portfolio Management

- Multiple brokerage accounts.
- Multiple portfolios/strategies.
- Cash balances.
- Buy/sell transactions.
- Fees and commissions.
- Deposits and withdrawals.
- Dividends.
- Corporate actions later: rights, bonus shares, splits, mergers, symbol changes, delistings.
- Consolidated exposure across accounts.

### Deterministic Finance Engine

- Quantity on hand.
- Average cost.
- Realized and unrealized P&L.
- Market value.
- Cash and total equity.
- Allocation by security and sector.
- Performance by period/account/portfolio/security.
- Benchmark comparison later.

### Market Intelligence

- EGX prices and volume.
- Company metadata.
- Official disclosures.
- Financial statements.
- Corporate events.
- Material news.
- Insider/major shareholder information when available from authoritative sources.

### Portfolio Construction

- Target sector weights.
- Maximum security weight.
- Maximum sector weight.
- Minimum cash.
- Number-of-holdings constraints.
- Restricted securities/sectors.
- Rebalancing using new cash only or full rebalance.

### Risk

- Concentration.
- Liquidity.
- Sector exposure.
- Drawdown.
- Volatility.
- Correlation later.
- Event risk.
- Scenario and stress testing.

### Research Committee

Specialist roles may include:

- Data verifier.
- Company/fundamental analyst.
- Valuation analyst.
- News/disclosure analyst.
- Market/price analyst.
- Sector/macro analyst.
- Portfolio/risk manager.
- Devil's advocate.
- Investment committee chair.

These are logical roles. They do not all need separate processes or expensive models for every task.

## 4. Recommendation Model

The system must never return only 'buy this stock'.

Every recommendation should contain:

- action: BUY / ADD / HOLD / WATCH / REDUCE / SELL / NO_ACTION;
- confidence;
- data-quality score;
- current portfolio weight;
- proposed weight when relevant;
- strongest supporting evidence;
- strongest counterargument;
- key risks;
- thesis invalidators;
- time horizon;
- expected portfolio effect;
- source links and dates;
- unresolved questions;
- explicit human approval requirement.

## 5. Forecasting Philosophy

Do not present one future price as truth.

Use scenarios:

- Bear case.
- Base case.
- Bull case.

Each scenario should have assumptions, catalysts, risks, probability/confidence where defensible, and invalidation conditions.

## 6. Decision Memory

For every committee run preserve:

- portfolio snapshot;
- market-data timestamp;
- relevant disclosures/news;
- independent agent outputs;
- critiques;
- disagreements;
- simulation inputs/results;
- risk checks;
- final ranked proposal;
- human decision;
- actual execution, if any;
- later outcome evaluations.

The system must be able to answer: 'Why did we make this decision at that time?' using the information available then, not today's rewritten history.

## 7. Agent Performance Memory

Over time score agents/roles by dimensions such as:

- factual accuracy;
- unsupported-claim rate;
- risk detection;
- useful dissent;
- thesis quality;
- event interpretation;
- contribution to decisions;
- calibration of confidence.

Never assume one provider is always better. Weighting should eventually depend on measured performance by task type.

## 8. Fast Operating Modes

- Emergency review: investigate a sharp move or material event.
- Opportunity scan: find portfolio-relevant candidates.
- Rebalance: optimize use of cash or reductions.
- Deep company review: company-focused research.
- Stress test: evaluate a shock scenario.
- Full investment committee: highest-depth decision process.

## 9. Local-First Product Shape

Initial deployment:

- Windows PC.
- Local application server.
- Browser-based UI.
- SQLite database.
- Codex CLI installed/authenticated locally.
- Claude Code CLI installed/authenticated locally.
- One-click launcher later.

Remote/mobile access is a later layer and must not require replacing the core.

## 10. External Data Principle

Data sources are ranked:

1. Official EGX, regulator, company filings/statements.
2. Reputable market-data providers.
3. Reputable financial news.
4. Community/opinion sources.

Lower-tier information may generate a research lead but must not silently become a verified fact.

Every externally derived fact should carry source identity and retrieval/publication time where practical.

## 11. Safety and Control

The first product is decision support only.

- No autonomous order placement.
- No broker credentials required.
- Human confirmation cannot be bypassed.
- AI cannot mutate accounting truth.
- AI cannot hide data-quality failures.
- Old recommendations remain historically preserved.

If the product is ever offered as an investment advisory service to other people, regulatory/legal requirements must be evaluated separately before launch.

## 12. Product Success

Success is not measured only by return.

Measure:

- ledger accuracy;
- decision traceability;
- risk-adjusted performance;
- drawdown;
- benchmark-relative performance;
- quality of thesis/invalidation discipline;
- useful alerts versus noise;
- agent factual accuracy;
- decision review quality;
- time saved in research;
- ability to reproduce historical decisions.

## 13. Long-Term Vision

The product eventually becomes a personal investment memory and operating system that understands portfolio rules, recurring mistakes, successful patterns, preferred risk, company histories, thesis changes, and the measured reliability of its own analytical tools.

The goal is not magical prediction. The goal is continuously better, more disciplined, evidence-backed investment decisions.
