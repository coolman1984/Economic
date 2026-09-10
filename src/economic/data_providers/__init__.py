"""Market-truth data providers (Phase 2).

Owns normalization of external market/company/news information into
provenance-carrying records. See ARCHITECTURE.md §11 and ADR-022.

Nothing in this package touches accounting truth: it produces normalized,
sourced facts (prices, disclosures, financial-statement line items) that the
application layer then hands to repositories. The domain and agents packages
never import from here, and this package never imports them except for the
`domain.money` decimal helpers and `domain.ledger` symbol/date normalizers,
which are pure and side-effect free.
"""
