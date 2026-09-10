# Investment and Risk Rules

## 1. Purpose

This file defines the behavioral rules the product must enforce around portfolio construction, research evidence, simulations, recommendations, and human approval.

These are product rules, not personalized investment advice.

## 2. Human Authority

- The user is the sole final decision maker.
- AI recommendations are proposals only.
- An approved recommendation is not an executed trade.
- Real execution must be recorded separately after the user acts with the broker.

## 3. Evidence Rules

A material external claim should have:

- source name;
- source URL where available;
- publication date or period;
- retrieval time;
- source quality tier;
- freshness status when relevant.

If a claim cannot be verified, mark it as unverified or missing. Do not silently convert it into fact.

## 4. Source Priority

1. EGX, regulator, company filings, official financial statements.
2. Reputable market-data providers.
3. Reputable financial news.
4. Community and opinion sources.

Tier 4 can generate questions but should not independently drive high-confidence decisions.

## 5. Recommendation Actions

Allowed standard actions:

- BUY
- ADD
- HOLD
- WATCH
- REDUCE
- SELL
- NO_ACTION

`NO_ACTION` is a first-class correct result when data quality, expected value, or portfolio fit is insufficient.

## 6. Mandatory Recommendation Fields

Every material recommendation must show:

- action;
- confidence;
- data-quality score;
- current position weight;
- proposed weight when relevant;
- 3-5 strongest reasons;
- strongest counterargument;
- major risks;
- thesis invalidators;
- time horizon;
- expected portfolio effect;
- sources;
- unresolved questions.

## 7. Portfolio Context Rule

Never ask only: 'Is this stock good?'

The system must also ask:

- Does it improve the current portfolio?
- Does it duplicate an existing risk?
- Does it violate concentration limits?
- Does it reduce cash below the minimum?
- Is its market liquidity adequate for the intended position size?

## 8. Configurable Portfolio Limits

Do not hard-code the user's strategy into source code.

Initial configuration should support:

- maximum security weight;
- maximum sector weight;
- minimum cash percentage;
- optional maximum number of holdings;
- restricted sectors;
- restricted securities;
- target sector ranges;
- portfolio objective;
- risk profile;
- investment horizon.

## 9. Risk Gate

A candidate action must be flagged or blocked from recommendation as appropriate when:

- resulting security weight breaches limit;
- resulting sector weight breaches limit;
- resulting cash falls below limit;
- current price data is missing/stale beyond configured tolerance;
- instrument is suspended or status is unknown;
- liquidity is inadequate where liquidity data is available;
- material corporate/event risk is unresolved;
- source conflict affects a critical assumption;
- the recommendation depends on missing critical data.

## 10. Forecasting Rule

Forecasts are scenarios, not facts.

Use:

- bear case;
- base case;
- bull case.

Each should contain assumptions, catalysts, risks, and invalidators. Probability estimates must be clearly labeled as estimates and should not imply false precision.

## 11. Simulation Rule

Simulation math is deterministic.

AI may suggest assumptions, but the simulation engine owns calculations and stores:

- input snapshot;
- assumptions;
- engine version;
- outputs;
- warnings/limit violations.

## 12. Rebalancing Rule

Support two distinct modes:

### New Cash Only

Improve allocation using incoming cash without selling existing holdings.

### Full Rebalance

May propose additions, reductions, or exits, subject to costs, limits, and user approval.

## 13. Data Quality Score

The scoring method can evolve, but must consider at least:

- freshness;
- completeness;
- source authority;
- cross-source agreement;
- availability of current price;
- availability of relevant financial period;
- unresolved critical facts.

Low data quality must cap recommendation confidence.

## 14. Dissent Rule

A final report must not suppress a material opposing argument simply because both primary agents agree overall.

The strongest plausible counterargument must be shown.

## 15. Thesis Rule

For a held security, maintain a thesis containing:

- why we own it;
- expected value drivers;
- key risks;
- invalidation conditions;
- review horizon;
- last thesis update.

A new material disclosure/news event should be evaluated against the thesis rather than analyzed in isolation.

## 16. Decision Review Rule

Later outcome reviews must ask more than whether the price rose.

Evaluate:

- did the thesis develop as expected?
- did identified risks occur?
- did the invalidation condition trigger?
- was sizing appropriate?
- was confidence calibrated?
- was the timing horizon respected?

## 17. No Hidden Automation

No component may silently:

- place an order;
- change a human decision;
- alter risk limits;
- rewrite old recommendations;
- delete decision history.

All such future capabilities, if ever added, require explicit separate design and approval.
