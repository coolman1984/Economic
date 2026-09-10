"""Freshness classification for ingested facts (disclosures, financial facts).

This is deliberately separate from ``domain.portfolio``'s price-staleness
check, which is frozen Phase 1 core and already governs price marks used for
valuation (ADR-002, ADR-017). This module answers a different question — not
"is this price safe to value a position at," but "how old is this disclosure
or financial-statement fact, and should the data-quality layer flag it."

No accounting value depends on this module. It is purely descriptive.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

FRESH = "FRESH"
AGING = "AGING"
STALE = "STALE"
UNKNOWN = "UNKNOWN"    # no publication or retrieval date to judge by

FRESHNESS_LEVELS = (FRESH, AGING, STALE, UNKNOWN)

DEFAULT_AGING_AFTER_DAYS = 3
DEFAULT_STALE_AFTER_DAYS = 10


def _parse(value: Optional[str]):
    if not value:
        return None
    text = value.strip()
    try:
        if len(text) <= 10:
            return date.fromisoformat(text)
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


@dataclass(frozen=True)
class FreshnessPolicy:
    """Thresholds, in days since the fact's own date, for each freshness band."""

    aging_after_days: int = DEFAULT_AGING_AFTER_DAYS
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS

    def classify(self, published_at: Optional[str], retrieved_at: Optional[str],
                as_of: Optional[str] = None) -> str:
        """Classify freshness using the earliest available reference date.

        Prefers ``published_at`` (when the fact became true) over
        ``retrieved_at`` (when we happened to fetch it) — a fact published a
        year ago is stale even if retrieved five minutes ago.
        """
        reference = _parse(published_at) or _parse(retrieved_at)
        if reference is None:
            return UNKNOWN
        today = _parse(as_of) or date.today()
        age_days = (today - reference).days
        if age_days < 0:
            return FRESH
        if age_days > self.stale_after_days:
            return STALE
        if age_days > self.aging_after_days:
            return AGING
        return FRESH

    def age_days(self, published_at: Optional[str], retrieved_at: Optional[str],
                as_of: Optional[str] = None) -> Optional[int]:
        reference = _parse(published_at) or _parse(retrieved_at)
        if reference is None:
            return None
        today = _parse(as_of) or date.today()
        return (today - reference).days
