"""Market-truth ingestion workflows (Phase 2).

Coordinates a file-based data provider with the repositories, inside one
database transaction per ingestion run — including the audit row for that
run, so a failed run is recorded exactly as reliably as a successful one.
Never invents a fact, never silently drops a bad row, and never leaves a
partial write behind a raised exception: if the source file itself can't be
read, nothing is written except the failure record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..data_providers.base import IngestionReport, ProviderError, SourceTier, utc_now
from ..data_providers.disclosure_provider import DisclosureFileProvider
from ..data_providers.financial_provider import FinancialFactFileProvider
from ..data_providers.instrument_provider import InstrumentFileProvider
from ..data_providers.price_provider import PriceFileProvider
from ..domain import ledger
from ..domain.money import to_text
from ..persistence import sqlite_db
from ..persistence.repositories import NotFoundError
from .context import AppContext


class MarketDataService:
    def __init__(self, context: AppContext):
        self.context = context
        self.repos = context.repos

    # ---- instruments -------------------------------------------------

    def import_instruments(self, path,
                           provider: Optional[InstrumentFileProvider] = None) -> IngestionReport:
        provider = provider or InstrumentFileProvider()
        report = IngestionReport(provider=provider.name, kind="instruments", ok=False,
                                 source=str(path))
        try:
            normalized, rejected = provider.read(Path(path))
        except ProviderError as exc:
            return self._fail_and_record(report, exc)

        report.read = len(normalized) + len(rejected)
        report.rejected = rejected
        with sqlite_db.transaction(self.context.connection):
            for item in normalized:
                existing = self._instrument_exists(item.symbol)
                self.repos.instruments.upsert(
                    item.symbol, name=item.name, sector=item.sector,
                    industry=item.industry, exchange=item.exchange, currency=item.currency,
                )
                if item.isin:
                    self.repos.instruments.set_isin(item.symbol, item.isin)
                report.updated += 1 if existing else 0
                report.inserted += 0 if existing else 1
            report.ok = True
            self._finish(report)
            self.repos.ingestion_runs.record(report)
        return report

    def _instrument_exists(self, symbol: str) -> bool:
        try:
            self.repos.instruments.get_by_symbol(symbol)
            return True
        except NotFoundError:
            return False

    # ---- prices --------------------------------------------------------

    def import_prices(self, path, provider: Optional[PriceFileProvider] = None) -> IngestionReport:
        provider = provider or PriceFileProvider()
        report = IngestionReport(provider=provider.name, kind="prices", ok=False,
                                 source=str(path))
        try:
            normalized, rejected = provider.read(Path(path))
        except ProviderError as exc:
            return self._fail_and_record(report, exc)

        report.read = len(normalized) + len(rejected)
        report.rejected = rejected
        with sqlite_db.transaction(self.context.connection):
            for price in normalized:
                instrument = self.repos.instruments.upsert(price.symbol)
                previous = self.repos.prices.latest_mark(price.symbol, price.price_date)
                is_update = previous is not None and previous.price_date == price.price_date
                tier = price.provenance.source_tier
                self.repos.prices.set_price(
                    instrument.id, price.symbol, price.close_price, price.price_date,
                    source=price.provenance.source_name, source_url=price.provenance.source_url,
                    source_tier=tier.value if isinstance(tier, SourceTier) else tier,
                    published_at=price.provenance.published_at,
                )
                report.updated += 1 if is_update else 0
                report.inserted += 0 if is_update else 1
            report.ok = True
            self._finish(report)
            self.repos.ingestion_runs.record(report)
        return report

    # ---- disclosures -----------------------------------------------------

    def import_disclosures(self, manifest_path, docs_dir=None,
                           provider: Optional[DisclosureFileProvider] = None) -> IngestionReport:
        provider = provider or DisclosureFileProvider()
        report = IngestionReport(provider=provider.name, kind="disclosures", ok=False,
                                 source=str(manifest_path))
        try:
            normalized, rejected = provider.read(Path(manifest_path), docs_dir)
        except ProviderError as exc:
            return self._fail_and_record(report, exc)

        report.read = len(normalized) + len(rejected)
        report.rejected = rejected
        with sqlite_db.transaction(self.context.connection):
            for document in normalized:
                instrument_id = None
                if document.symbol:
                    instrument_id = self.repos.instruments.upsert(document.symbol).id
                tier = document.provenance.source_tier
                record = self.repos.documents.add(
                    document_type=document.document_type, title=document.title,
                    source_name=document.provenance.source_name,
                    content_hash=document.provenance.content_hash,
                    symbol=document.symbol, instrument_id=instrument_id,
                    published_at=document.published_at,
                    source_tier=tier.value if isinstance(tier, SourceTier) else tier,
                    source_url=document.provenance.source_url,
                    external_id=document.provenance.external_id,
                    local_path=document.local_path,
                    retrieved_at=document.provenance.retrieved_at,
                )
                report.inserted += 1 if record["_was_new"] else 0
                report.updated += 0 if record["_was_new"] else 1
            report.ok = True
            self._finish(report)
            self.repos.ingestion_runs.record(report)
        return report

    # ---- financial facts ---------------------------------------------------

    def import_financial_facts(self, path,
                               provider: Optional[FinancialFactFileProvider] = None) -> IngestionReport:
        provider = provider or FinancialFactFileProvider()
        report = IngestionReport(provider=provider.name, kind="financial_facts", ok=False,
                                 source=str(path))
        try:
            normalized, rejected = provider.read(Path(path))
        except ProviderError as exc:
            return self._fail_and_record(report, exc)

        report.read = len(normalized) + len(rejected)
        report.rejected = rejected
        with sqlite_db.transaction(self.context.connection):
            for fact in normalized:
                instrument = self.repos.instruments.upsert(fact.symbol)
                source_document_id = None
                if fact.source_document_external_id:
                    document = self.repos.documents.find_by_external_id(
                        fact.source_document_external_id,
                    )
                    if document:
                        source_document_id = document["id"]
                tier = fact.provenance.source_tier
                record = self.repos.financial_facts.add(
                    instrument_id=instrument.id, symbol=fact.symbol,
                    period_end=fact.period_end, period_type=fact.period_type,
                    metric=fact.metric, value=fact.value,
                    source_name=fact.provenance.source_name, currency=fact.currency,
                    period_start=fact.period_start, source_document_id=source_document_id,
                    source_tier=tier.value if isinstance(tier, SourceTier) else tier,
                    source_url=fact.provenance.source_url,
                    published_at=fact.provenance.published_at,
                    retrieved_at=fact.provenance.retrieved_at,
                )
                report.inserted += 1 if record["_was_new"] else 0
                report.updated += 0 if record["_was_new"] else 1
            report.ok = True
            self._finish(report)
            self.repos.ingestion_runs.record(report)
        return report

    # ---- traceability -------------------------------------------------

    def trace_symbol(self, symbol: str) -> dict:
        """Every stored fact for a symbol with its provenance — the Phase 2
        gate deliverable: a displayed fact traced back to its original source."""
        symbol = ledger.normalize_symbol(symbol)
        instrument = self.repos.instruments.get_by_symbol(symbol)
        price_history = self.repos.prices.history(symbol, limit=10)
        documents = self.repos.documents.list_for_symbol(symbol)
        facts = self.repos.financial_facts.list_for_symbol(symbol)
        return {
            "symbol": symbol,
            "instrument": vars(instrument),
            "prices": [
                {"price_date": p.price_date, "close": to_text(p.price), "source": p.source,
                 "retrieved_at": p.retrieved_at}
                for p in price_history
            ],
            "documents": documents,
            "financial_facts": facts,
        }

    # ---- ingestion history -----------------------------------------------

    def list_ingestion_runs(self, limit: int = 30, kind: Optional[str] = None):
        return self.repos.ingestion_runs.list(limit=limit, kind=kind)

    # ---- helpers -----------------------------------------------------

    def _fail_and_record(self, report: IngestionReport, exc: ProviderError) -> IngestionReport:
        report.ok = False
        report.failure_kind = exc.failure_kind
        report.error = str(exc)
        self._finish(report)
        with sqlite_db.transaction(self.context.connection):
            self.repos.ingestion_runs.record(report)
        return report

    @staticmethod
    def _finish(report: IngestionReport) -> None:
        report.completed_at = utc_now()
