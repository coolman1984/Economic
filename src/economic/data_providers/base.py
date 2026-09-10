"""Provider contracts shared by every market-data source.

Mirrors the shape of ``agents/base_adapter.py`` deliberately: both are external
I/O behind a normalized, testable interface that never lets a source failure
corrupt stored state and never lets malformed input pass as a fact (ADR-022).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SourceTier(str, Enum):
    """Source-quality ranking (INVESTMENT_RULES.md §4). Lower is more authoritative."""

    OFFICIAL = "OFFICIAL"          # EGX, FRA, regulator, company filings
    PROVIDER = "PROVIDER"          # reputable market-data providers
    NEWS = "NEWS"                  # reputable financial news
    COMMUNITY = "COMMUNITY"        # opinion/community sources
    IMPORT = "IMPORT"              # user-supplied manual entry, tier unknown until tagged


# Normalized failure states, parallel to agents/base_adapter.py's FAILURE_KINDS.
SOURCE_UNAVAILABLE = "source_unavailable"      # file/endpoint missing or unreachable
EMPTY_RESULT = "empty_result"                  # source returned nothing
MALFORMED_SCHEMA = "malformed_schema"          # rows/fields don't match the expected shape
VALIDATION_FAILED = "validation_failed"        # individual record failed domain validation
TIMEOUT = "timeout"                            # a network provider timed out
INTEGRITY_MISMATCH = "integrity_mismatch"      # declared checksum didn't match content

FAILURE_KINDS = (
    SOURCE_UNAVAILABLE, EMPTY_RESULT, MALFORMED_SCHEMA, VALIDATION_FAILED,
    TIMEOUT, INTEGRITY_MISMATCH,
)


class ProviderError(ValueError):
    """A source could not be read at all (as opposed to one bad row in it)."""

    def __init__(self, failure_kind: str, message: str):
        if failure_kind not in FAILURE_KINDS:
            raise ValueError(f"unknown failure_kind: {failure_kind}")
        self.failure_kind = failure_kind
        super().__init__(message)


@dataclass(frozen=True)
class Provenance:
    """Source identity and timing for one ingested fact (DATA_MODEL.md §9).

    ``source_url`` is optional (a locally supplied file has no URL of its own,
    but should still carry one if the *content* cites where it came from).
    """

    source_name: str
    source_tier: SourceTier
    retrieved_at: str
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    external_id: Optional[str] = None
    content_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "source_tier": self.source_tier.value,
            "source_url": self.source_url,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "external_id": self.external_id,
            "content_hash": self.content_hash,
        }


@dataclass
class RejectedRecord:
    """One input row/item that could not be normalized, with why."""

    index: int
    reason: str
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"index": self.index, "reason": self.reason, "raw": self.raw}


@dataclass
class IngestionReport:
    """What an ingestion run actually did. Never silent, never partial-looking.

    ``ok`` is True only when the source was readable at all; individual rows
    can still be rejected into ``rejected`` without failing the whole run,
    exactly like the agent orchestrator continuing with partial committee
    results rather than fabricating what's missing.
    """

    provider: str
    kind: str                      # "instruments" | "prices" | "disclosures" | "financial_facts"
    ok: bool
    source: Optional[str] = None
    failure_kind: Optional[str] = None
    error: Optional[str] = None
    read: int = 0
    inserted: int = 0
    updated: int = 0
    duplicate: int = 0
    rejected: List[RejectedRecord] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now)
    completed_at: Optional[str] = None

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def has_rejections(self) -> bool:
        return bool(self.rejected)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "kind": self.kind,
            "ok": self.ok,
            "source": self.source,
            "failure_kind": self.failure_kind,
            "error": self.error,
            "read": self.read,
            "inserted": self.inserted,
            "updated": self.updated,
            "duplicate": self.duplicate,
            "rejected_count": self.rejected_count,
            "rejected": [r.to_dict() for r in self.rejected],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class Provider:
    """Base class every concrete provider extends.

    Subclasses implement one ``fetch_*`` method appropriate to their kind and
    return plain normalized dataclasses (below) plus a ``Provenance``. They
    never touch the database — that is the application layer's job, exactly
    as agent adapters never touch portfolio state.
    """

    name: str = "provider"
    source_tier: SourceTier = SourceTier.IMPORT

    def doctor(self) -> dict:
        """Health/availability report, parallel to an agent adapter's doctor()."""
        raise NotImplementedError


@dataclass(frozen=True)
class NormalizedInstrument:
    symbol: str
    name: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    exchange: str
    currency: str
    isin: Optional[str]
    provenance: Provenance


@dataclass(frozen=True)
class NormalizedPrice:
    symbol: str
    price_date: str
    close_price: Decimal
    open_price: Optional[Decimal]
    high_price: Optional[Decimal]
    low_price: Optional[Decimal]
    volume: Optional[Decimal]
    provenance: Provenance


@dataclass(frozen=True)
class NormalizedDocument:
    document_type: str
    title: str
    published_at: Optional[str]
    symbol: Optional[str]
    local_path: Optional[str]
    provenance: Provenance


@dataclass(frozen=True)
class NormalizedFinancialFact:
    symbol: str
    period_end: str
    period_type: str
    metric: str
    value: Decimal
    currency: str
    period_start: Optional[str]
    source_document_external_id: Optional[str]
    provenance: Provenance
