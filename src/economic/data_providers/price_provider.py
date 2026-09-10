"""EOD price import: bulk-load price snapshots from a CSV file.

Required columns: symbol, date, close. Optional: open, high, low, volume,
source_name, source_url. Every row is priced in the account currency (EGP by
default) and parsed as an exact Decimal — never a float (ADR-015).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..domain import ledger
from ..domain.money import AmountError, money, to_decimal
from .base import NormalizedPrice, Provenance, RejectedRecord, SourceTier, utc_now
from .csv_utils import read_rows

REQUIRED_COLUMNS = ["symbol", "date", "close"]


def _optional_money(row: dict, key: str) -> Optional:
    value = row.get(key)
    if not value:
        return None
    return money(value, key)


class PriceFileProvider:
    """Reads an EOD price CSV export into normalized price records."""

    name = "price_file"
    source_tier = SourceTier.IMPORT

    def __init__(self, default_source_name: str = "manual price export"):
        self.default_source_name = default_source_name

    def doctor(self) -> dict:
        return {"provider": self.name, "kind": "prices", "available": True}

    def read(self, path: Path):
        rows = read_rows(Path(path), REQUIRED_COLUMNS)
        retrieved_at = utc_now()
        normalized: List[NormalizedPrice] = []
        rejected: List[RejectedRecord] = []

        for index, row in enumerate(rows):
            try:
                symbol = ledger.normalize_symbol(row["symbol"])
                price_date = ledger.normalize_date(row["date"])
                close = money(row["close"], "close")
                if close <= 0:
                    raise AmountError("close must be > 0")
                open_price = _optional_money(row, "open")
                high_price = _optional_money(row, "high")
                low_price = _optional_money(row, "low")
                volume = to_decimal(row["volume"], "volume") if row.get("volume") else None
            except (ledger.LedgerError, AmountError) as exc:
                rejected.append(RejectedRecord(index, str(exc), row))
                continue

            provenance = Provenance(
                source_name=row.get("source_name") or self.default_source_name,
                source_tier=self.source_tier,
                retrieved_at=retrieved_at,
                source_url=row.get("source_url") or None,
                published_at=price_date,
            )
            normalized.append(NormalizedPrice(
                symbol=symbol, price_date=price_date, close_price=close,
                open_price=open_price, high_price=high_price, low_price=low_price,
                volume=volume, provenance=provenance,
            ))
        return normalized, rejected
