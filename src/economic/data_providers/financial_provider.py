"""Financial-statement fact import: normalized line items from a CSV file.

Required columns: symbol, period_end, period_type, metric, value. Optional:
period_start, currency, source_document_external_id, source_name, source_url,
published_at. ``source_document_external_id`` links a fact back to the
disclosure/document it came from when one was imported via
``DisclosureFileProvider`` — that is the traceability chain the Phase 2 gate
asks for: fact -> statement document -> original source.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from ..domain import ledger
from ..domain.money import AmountError, to_decimal
from .base import (
    NormalizedFinancialFact, Provenance, RejectedRecord, SourceTier, utc_now,
)
from .csv_utils import read_rows

REQUIRED_COLUMNS = ["symbol", "period_end", "period_type", "metric", "value"]

VALID_PERIOD_TYPES = frozenset({"ANNUAL", "QUARTERLY", "SEMI_ANNUAL", "TTM"})


class FinancialFactFileProvider:
    """Reads a normalized financial-facts CSV export into normalized records."""

    name = "financial_fact_file"
    source_tier = SourceTier.IMPORT

    def __init__(self, default_source_name: str = "manual financial-statement import"):
        self.default_source_name = default_source_name

    def doctor(self) -> dict:
        return {"provider": self.name, "kind": "financial_facts", "available": True}

    def read(self, path: Path):
        rows = read_rows(Path(path), REQUIRED_COLUMNS)
        retrieved_at = utc_now()
        normalized: List[NormalizedFinancialFact] = []
        rejected: List[RejectedRecord] = []

        for index, row in enumerate(rows):
            try:
                symbol = ledger.normalize_symbol(row["symbol"])
                period_end = ledger.normalize_date(row["period_end"])
                period_start = (
                    ledger.normalize_date(row["period_start"])
                    if row.get("period_start") else None
                )
                period_type = (row["period_type"] or "").strip().upper()
                if period_type not in VALID_PERIOD_TYPES:
                    raise ValueError(
                        f"period_type {period_type!r} is not one of "
                        f"{', '.join(sorted(VALID_PERIOD_TYPES))}"
                    )
                metric = (row["metric"] or "").strip()
                if not metric:
                    raise ValueError("metric must not be empty")
                value = to_decimal(row["value"], "value")
                published_at = (
                    ledger.normalize_date(row["published_at"])
                    if row.get("published_at") else period_end
                )
            except (ledger.LedgerError, AmountError, ValueError) as exc:
                rejected.append(RejectedRecord(index, str(exc), row))
                continue

            provenance = Provenance(
                source_name=row.get("source_name") or self.default_source_name,
                source_tier=self.source_tier,
                retrieved_at=retrieved_at,
                source_url=row.get("source_url") or None,
                published_at=published_at,
                external_id=row.get("source_document_external_id") or None,
            )
            normalized.append(NormalizedFinancialFact(
                symbol=symbol, period_end=period_end, period_type=period_type,
                metric=metric, value=value, currency=row.get("currency") or "EGP",
                period_start=period_start,
                source_document_external_id=row.get("source_document_external_id") or None,
                provenance=provenance,
            ))
        return normalized, rejected
