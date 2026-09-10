"""Official disclosure import: a manifest CSV plus the document files it names.

A "disclosure" here is any official document a user has already downloaded
(a board decision, a dividend announcement, a financial statement PDF) and
wants recorded with real provenance. The manifest carries the facts about the
document that only a human (or a Tier-1 source) can assert honestly: what it
is, when it was published, and where it came from. This module never invents
any of those fields — a manifest row missing a required one is rejected.

Required manifest columns: document_type, title, file. Optional: symbol,
published_at, source_name, source_url, external_id.

``file`` is a path relative to the manifest's own directory (or absolute).
Its SHA-256 becomes part of the provenance, so a document's integrity is
independently checkable later, and re-importing an identical file is a no-op
(ADR-016 duplicate protection, extended to documents).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..domain import ledger
from .base import NormalizedDocument, Provenance, RejectedRecord, SourceTier, utc_now
from .csv_utils import content_hash, file_hash, read_rows

REQUIRED_COLUMNS = ["document_type", "title", "file"]

VALID_DOCUMENT_TYPES = frozenset({
    "BOARD_DECISION", "DIVIDEND", "CAPITAL_CHANGE", "TRADING_HALT",
    "QUARTERLY_REPORT", "ANNUAL_REPORT", "FINANCIAL_STATEMENT", "PROSPECTUS",
    "MATERIAL_NEWS", "OTHER",
})


class DisclosureFileProvider:
    """Reads a manifest CSV of official documents into normalized records."""

    name = "disclosure_file"
    source_tier = SourceTier.IMPORT

    def __init__(self, default_source_name: str = "manual disclosure import"):
        self.default_source_name = default_source_name

    def doctor(self) -> dict:
        return {"provider": self.name, "kind": "disclosures", "available": True}

    def read(self, manifest_path: Path, docs_dir: Optional[Path] = None):
        manifest_path = Path(manifest_path)
        base_dir = Path(docs_dir) if docs_dir else manifest_path.parent
        rows = read_rows(manifest_path, REQUIRED_COLUMNS)
        retrieved_at = utc_now()
        normalized: List[NormalizedDocument] = []
        rejected: List[RejectedRecord] = []

        for index, row in enumerate(rows):
            try:
                document_type = (row["document_type"] or "").strip().upper()
                if document_type not in VALID_DOCUMENT_TYPES:
                    raise ValueError(
                        f"document_type {document_type!r} is not one of "
                        f"{', '.join(sorted(VALID_DOCUMENT_TYPES))}"
                    )
                title = row["title"].strip()
                if not title:
                    raise ValueError("title must not be empty")

                symbol = None
                if row.get("symbol"):
                    symbol = ledger.normalize_symbol(row["symbol"])

                file_field = row["file"].strip()
                if not file_field:
                    raise ValueError("file must not be empty")
                document_path = Path(file_field)
                if not document_path.is_absolute():
                    document_path = base_dir / document_path
                if not document_path.exists() or not document_path.is_file():
                    raise ValueError(f"document file not found: {document_path}")

                published_at = (
                    ledger.normalize_date(row["published_at"])
                    if row.get("published_at") else None
                )
            except (ledger.LedgerError, ValueError) as exc:
                rejected.append(RejectedRecord(index, str(exc), row))
                continue

            digest = file_hash(document_path)
            provenance = Provenance(
                source_name=row.get("source_name") or self.default_source_name,
                source_tier=self.source_tier,
                retrieved_at=retrieved_at,
                source_url=row.get("source_url") or None,
                published_at=published_at,
                external_id=row.get("external_id") or None,
                content_hash=digest,
            )
            normalized.append(NormalizedDocument(
                document_type=document_type, title=title, published_at=published_at,
                symbol=symbol, local_path=str(document_path), provenance=provenance,
            ))
        return normalized, rejected
