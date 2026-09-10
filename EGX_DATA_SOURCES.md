# EGX Data Sources — Research Findings (Phase 2)

## Purpose

Before writing any ingestion code, this document records what was actually
verified about Egyptian Exchange data sources, and — just as important — what
could **not** be verified and why. Phase 1's rule applies here too: never
present an unverified claim as a fact.

## Environment constraint (read this first)

This research was performed from a sandboxed development session whose
outbound network egress is blocked by policy for every external host except a
small allowlist (package registries, the Anthropic API). Direct HTTP probes to
`egx.com.eg`, `egxapi.com`, `mubasher.info`, `eodhd.com`, `twelvedata.com`,
`developer.ice.com`, and even `wikipedia.org` all returned `403` from the
egress proxy. The `WebFetch` tool is blocked identically. Only `WebSearch`
(which returns model-summarized snippets of search results, not raw pages)
was reachable.

**Consequence:** no live endpoint, HTML structure, response schema, rate
limit, or authentication requirement described below has been confirmed by an
actual request from this session. Everything below is sourced from search
snippets about these providers, not from inspecting their real output.

This is exactly the situation the task instructions anticipated: *"Do not
assume scraping or APIs are reliable until proven with small probes."* No
probe was possible, so Phase 2 does not ship a live adapter for anything on
this list. See ADR-022 for the resulting architecture decision.

## Findings

### Tier 1 — Official

**EGX (`egx.com.eg`)** is the Egyptian Exchange's own site. It publishes a
market-watch/prices page (`/en/prices.aspx`) and a disclosures/news section
(`/en/NewsList.aspx`, and a newer `beta.egx.com.eg`). These are web pages
meant for human reading, not a documented public API. No official free
machine-readable feed was found published by EGX itself.

**EGID (`egidegypt.com`)** is described in search results as *"a fully owned
subsidiary of the Egyptian Exchange... the sole authorized data provider for
EGX market data"* for the past 25+ years, disseminating real-time prices,
trades, announcements, and historical data *"directly or through licensed
vendors."* This is the genuine Tier-1 machine-readable channel — and it is a
licensed commercial data feed, not a free public API. Phase 2 cannot
integrate it without a subscription and credentials neither available nor
appropriate to fabricate.

**FRA (Financial Regulatory Authority)** is named as the other body EGX-listed
companies must disclose to, alongside EGX itself. Company disclosures
(board decisions, dividends, capital changes) are described as filed with
both.

### Tier 2 — Reputable market-data providers (third-party)

Several aggregators claim EGX coverage: **EGXAPI** (`egxapi.com`, described as
"free forever, no card, real-time and historical bars/quotes/order book"),
**EODHD**, **Twelve Data**, **ICE Data Services**. All are plausible future
Tier-2 sources per `INVESTMENT_RULES.md` §4, but none has been reached from
this session, so none of their claimed free/no-auth status, actual schema, or
uptime has been confirmed. Building against an unverified schema risks
exactly what `AGENTS.md` §3 forbids: silently wrong data presented as fact.

### Tier 3 — Reputable financial data/news sites

`stockanalysis.com`, `african-markets.com`, `mubasher.info`, `investing.com`,
`tradingview.com`, `marketscreener.com`, `bloomberg.com` all carry EGX-listed
company profiles and quotes. Useful for citation, not for an automated feed
(they're display pages, and scraping a display page not built for machine
consumption is fragile and frequently against terms of service).

### Verified facts about two real EGX companies

These specific facts *were* returned by `WebSearch` with citable source URLs,
and are used as the Phase 2 traceability fixture (proving a stored fact can be
traced back to a real, dated source) rather than invented test data:

| Symbol | Company | ISIN | Sector | Notes |
|---|---|---|---|---|
| COMI | Commercial International Bank (Egypt) S.A.E. | EGS60121C018 | Banks | Founded 1975; listed EGX |
| HRHO | EFG Holding S.A.E. (formerly EFG Hermes Holding) | EGS69101C011 | Diversified Financials | Founded 1984; listed EGX and LSE |

Sources (as returned by WebSearch, retrieved 2026-09-10):
- COMI: https://stockanalysis.com/quote/egx/COMI/ ,
  https://www.african-markets.com/en/stock-markets/egyptian-exchange/listed-companies/company?code=COMI
- HRHO: https://english.mubasher.info/markets/EGX/stocks/HRHO/profile ,
  https://stockanalysis.com/quote/egx/HRHO/market-cap/

## Decision

Phase 2 ships **local, provenance-carrying import** as the working, tested,
default ingestion path for prices, disclosures, and financial statements —
not a live scraper or an unverified API client. A stable provider *contract*
is built so a live adapter can be added later, the day its schema is actually
confirmed against a real response. See ADR-022.
