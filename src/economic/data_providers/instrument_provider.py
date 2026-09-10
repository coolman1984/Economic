"""Instrument-master import: bulk-load symbols, names, sectors from a CSV file.

Required columns: symbol. Optional: name, sector, industry, exchange, currency,
isin, source_name, source_url.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from ..domain import ledger
from .base import (
    NormalizedInstrument, Provenance, RejectedRecord, SourceTier, utc_now,
)
from .csv_utils import read_rows

REQUIRED_COLUMNS = ["symbol"]


class InstrumentFileProvider:
    """Reads an instrument-master CSV export into normalized records."""

    name = "instrument_file"
    source_tier = SourceTier.IMPORT

    def __init__(self, default_source_name: str = "manual instrument import"):
        self.default_source_name = default_source_name

    def doctor(self) -> dict:
        return {"provider": self.name, "kind": "instruments", "available": True}

    def read(self, path: Path):
        """Returns (normalized_instruments, rejected_records). Raises ProviderError
        only when the file itself is unreadable; bad individual rows are rejected,
        not fatal (BUILD_GUIDE-style: never let one bad row kill useful ones)."""
        rows = read_rows(Path(path), REQUIRED_COLUMNS)
        retrieved_at = utc_now()
        normalized: List[NormalizedInstrument] = []
        rejected: List[RejectedRecord] = []

        for index, row in enumerate(rows):
            try:
                symbol = ledger.normalize_symbol(row["symbol"])
            except ledger.LedgerError as exc:
                rejected.append(RejectedRecord(index, str(exc), row))
                continue

            provenance = Provenance(
                source_name=row.get("source_name") or self.default_source_name,
                source_tier=self.source_tier,
                retrieved_at=retrieved_at,
                source_url=row.get("source_url") or None,
            )
            normalized.append(NormalizedInstrument(
                symbol=symbol,
                name=row.get("name") or None,
                sector=row.get("sector") or None,
                industry=row.get("industry") or None,
                exchange=row.get("exchange") or "EGX",
                currency=row.get("currency") or "EGP",
                isin=row.get("isin") or None,
                provenance=provenance,
            ))
        return normalized, rejected
