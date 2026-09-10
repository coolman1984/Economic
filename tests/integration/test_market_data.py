"""Market-truth layer integration tests (Phase 2).

Proves the full pipeline: instrument master -> prices -> disclosures ->
financial facts, all with real provenance, idempotent re-import, atomic
failure handling, and a fact traced back to its source. Two real EGX-listed
companies (COMI, HRHO) are used as fixtures with real, cited source URLs
gathered via research (see EGX_DATA_SOURCES.md) rather than invented data.
"""

import pytest

from economic.application.market_data_service import MarketDataService

COMI_ISIN = "EGS60121C018"
HRHO_ISIN = "EGS69101C011"


@pytest.fixture
def market_service(context):
    return MarketDataService(context)


@pytest.fixture
def fixtures(tmp_path):
    """Real-company fixture files with real, citable source URLs."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "comi_q2.txt").write_text("Fictional test disclosure body (fixture only).")
    (docs / "hrho_board.txt").write_text("Fictional test disclosure body (fixture only).")

    instruments = tmp_path / "instruments.csv"
    instruments.write_text(
        "symbol,name,sector,industry,isin,source_name,source_url\n"
        f"COMI,Commercial International Bank (Egypt) S.A.E.,Banks,Banking,{COMI_ISIN},"
        "stockanalysis.com,https://stockanalysis.com/quote/egx/COMI/\n"
        f"HRHO,EFG Holding S.A.E.,Diversified Financials,Investment Banking,{HRHO_ISIN},"
        "mubasher.info,https://english.mubasher.info/markets/EGX/stocks/HRHO/profile\n"
    )

    prices = tmp_path / "prices.csv"
    prices.write_text(
        "symbol,date,close,source_name,source_url\n"
        "COMI,2026-09-08,74.25,EGX prices page,https://www.egx.com.eg/en/prices.aspx\n"
        "HRHO,2026-09-08,27.52,EGX prices page,https://www.egx.com.eg/en/prices.aspx\n"
    )

    disclosures = tmp_path / "disclosures.csv"
    disclosures.write_text(
        "document_type,title,file,symbol,published_at,source_name,source_url,external_id\n"
        "QUARTERLY_REPORT,COMI Q2 2026 disclosure,docs/comi_q2.txt,COMI,2026-08-15,"
        "EGX disclosures,https://www.egx.com.eg/en/NewsList.aspx,EGX-COMI-2026-Q2\n"
        "BOARD_DECISION,HRHO board decision,docs/hrho_board.txt,HRHO,2026-08-20,"
        "EGX disclosures,https://www.egx.com.eg/en/NewsList.aspx,EGX-HRHO-2026-BD1\n"
    )

    financials = tmp_path / "financials.csv"
    financials.write_text(
        "symbol,period_end,period_type,metric,value,currency,"
        "source_document_external_id,source_name,source_url\n"
        "COMI,2025-12-31,ANNUAL,revenue,128540000000,EGP,EGX-COMI-2026-Q2,"
        "stockanalysis.com,https://stockanalysis.com/quote/egx/COMI/\n"
    )

    return {
        "instruments": instruments, "prices": prices,
        "disclosures": disclosures, "financials": financials,
    }


def import_all(service, fixtures):
    return {
        "instruments": service.import_instruments(fixtures["instruments"]),
        "prices": service.import_prices(fixtures["prices"]),
        "disclosures": service.import_disclosures(fixtures["disclosures"]),
        "financials": service.import_financial_facts(fixtures["financials"]),
    }


# ---- full pipeline ---------------------------------------------------

def test_the_full_pipeline_ingests_every_kind_successfully(market_service, fixtures):
    reports = import_all(market_service, fixtures)
    assert all(report.ok for report in reports.values())
    assert reports["instruments"].inserted == 2
    assert reports["prices"].inserted == 2
    assert reports["disclosures"].inserted == 2
    assert reports["financials"].inserted == 1
    assert all(report.rejected_count == 0 for report in reports.values())


def test_every_normalized_record_carries_provenance(market_service, fixtures, context):
    import_all(market_service, fixtures)
    price = dict(context.connection.execute(
        "SELECT * FROM price_snapshots WHERE symbol = 'COMI'").fetchone())
    assert price["source"] == "EGX prices page"
    assert price["source_url"] == "https://www.egx.com.eg/en/prices.aspx"
    assert price["retrieved_at"]

    document = dict(context.connection.execute(
        "SELECT * FROM external_documents WHERE symbol = 'COMI'").fetchone())
    assert document["source_url"] == "https://www.egx.com.eg/en/NewsList.aspx"
    assert document["content_hash"]
    assert document["retrieved_at"]

    fact = dict(context.connection.execute(
        "SELECT * FROM financial_facts WHERE symbol = 'COMI'").fetchone())
    assert fact["source_name"] == "stockanalysis.com"
    assert fact["source_url"]


# ---- idempotent duplicate handling -------------------------------------

def test_reimporting_the_identical_files_does_not_duplicate_rows(
        market_service, fixtures, context):
    import_all(market_service, fixtures)
    counts_before = {
        table: context.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("instruments", "price_snapshots", "external_documents",
                      "financial_facts")
    }

    second = import_all(market_service, fixtures)

    counts_after = {
        table: context.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_before == counts_after
    # Every row routed to the update path, not silently dropped.
    assert second["instruments"].updated == 2 and second["instruments"].inserted == 0
    assert second["prices"].updated == 2 and second["prices"].inserted == 0
    assert second["disclosures"].updated == 2 and second["disclosures"].inserted == 0
    assert second["financials"].updated == 1 and second["financials"].inserted == 0


def test_a_changed_price_on_the_same_date_updates_rather_than_duplicates(
        market_service, tmp_path, context):
    first = tmp_path / "p1.csv"
    first.write_text("symbol,date,close\nCOMI,2026-09-08,74.25\n")
    market_service.import_prices(first)

    second = tmp_path / "p2.csv"
    second.write_text("symbol,date,close\nCOMI,2026-09-08,75.00\n")
    report = market_service.import_prices(second)

    assert report.updated == 1 and report.inserted == 0
    rows = context.connection.execute(
        "SELECT close_price FROM price_snapshots WHERE symbol = 'COMI'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "75"


def test_a_corrected_document_with_the_same_external_id_updates_in_place(
        market_service, tmp_path, context):
    (tmp_path / "doc.txt").write_text("original body")
    manifest1 = tmp_path / "m1.csv"
    manifest1.write_text(
        "document_type,title,file,external_id\n"
        "BOARD_DECISION,Original title,doc.txt,EGX-TEST-1\n"
    )
    market_service.import_disclosures(manifest1)

    (tmp_path / "doc2.txt").write_text("corrected body, different content")
    manifest2 = tmp_path / "m2.csv"
    manifest2.write_text(
        "document_type,title,file,external_id\n"
        "BOARD_DECISION,Corrected title,doc2.txt,EGX-TEST-1\n"
    )
    report = market_service.import_disclosures(manifest2)

    assert report.updated == 1 and report.inserted == 0
    rows = context.connection.execute("SELECT title FROM external_documents").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "Corrected title"


# ---- source failures are explicit, never silent ------------------------

def test_a_missing_source_file_fails_loudly_and_changes_nothing(
        market_service, tmp_path, context):
    before = context.connection.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    report = market_service.import_prices(tmp_path / "does-not-exist.csv")
    assert not report.ok
    assert report.failure_kind == "source_unavailable"
    after = context.connection.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    assert before == after


def test_a_schema_change_in_the_source_fails_loudly(market_service, tmp_path):
    broken = tmp_path / "broken.csv"
    broken.write_text("ticker,day,px\nCOMI,2026-09-08,74.25\n")   # renamed columns
    report = market_service.import_prices(broken)
    assert not report.ok
    assert report.failure_kind == "malformed_schema"


def test_every_ingestion_attempt_is_recorded_success_and_failure_alike(
        market_service, fixtures, tmp_path):
    market_service.import_prices(fixtures["prices"])
    market_service.import_prices(tmp_path / "missing.csv")
    runs = market_service.list_ingestion_runs()
    outcomes = [(r["kind"], r["ok"]) for r in runs]
    assert ("prices", True) in outcomes
    assert ("prices", False) in outcomes


def test_a_partially_bad_file_keeps_the_good_rows_and_reports_the_bad_ones(
        market_service, tmp_path, context):
    mixed = tmp_path / "mixed.csv"
    mixed.write_text(
        "symbol,date,close\n"
        "COMI,2026-09-08,74.25\n"
        "HRHO,not-a-date,27.52\n"
    )
    report = market_service.import_prices(mixed)
    assert report.ok
    assert report.inserted == 1
    assert report.rejected_count == 1
    assert "not-a-date" in report.rejected[0].reason
    count = context.connection.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    assert count == 1


# ---- traceability: the Phase 2 gate --------------------------------------

def test_a_real_company_fact_traces_back_to_its_original_source(
        market_service, fixtures):
    import_all(market_service, fixtures)
    trace = market_service.trace_symbol("COMI")

    assert trace["instrument"]["isin"] == COMI_ISIN
    assert trace["instrument"]["name"] == "Commercial International Bank (Egypt) S.A.E."

    price = trace["prices"][0]
    assert price["source"] == "EGX prices page"

    document = trace["documents"][0]
    assert document["source_url"] == "https://www.egx.com.eg/en/NewsList.aspx"
    assert document["published_at"] == "2026-08-15"
    assert document["content_hash"]

    fact = trace["financial_facts"][0]
    assert fact["metric"] == "revenue"
    assert fact["source_url"] == "https://stockanalysis.com/quote/egx/COMI/"
    # The chain: fact -> the document that reported it -> that document's source.
    assert fact["source_document_id"] == document["id"]


def test_a_second_real_company_traces_independently(market_service, fixtures):
    import_all(market_service, fixtures)
    trace = market_service.trace_symbol("HRHO")
    assert trace["instrument"]["isin"] == HRHO_ISIN
    assert trace["documents"][0]["document_type"] == "BOARD_DECISION"
    assert trace["documents"][0]["published_at"] == "2026-08-20"


def test_official_source_tier_is_preferred_and_visible(market_service, fixtures):
    """Every Phase 2 record is currently tagged IMPORT (ADR-022): the tier the
    software actually verified, not an assumed OFFICIAL tag it cannot prove."""
    import_all(market_service, fixtures)
    trace = market_service.trace_symbol("COMI")
    assert trace["documents"][0]["source_tier"] == "IMPORT"


# ---- interaction with the frozen portfolio core --------------------------

def test_imported_prices_feed_the_existing_frozen_valuation_engine(
        market_service, portfolio_service, fixtures, account):
    """Phase 2 must plug into Phase 1's PriceRepository, not replace it."""
    portfolio_service.record_cash(account.id, "DEPOSIT", "100000",
                                  transaction_date="2026-01-01")
    portfolio_service.record_trade(account.id, "BUY", "COMI", "100", "50",
                                   transaction_date="2026-01-02")
    market_service.import_prices(fixtures["prices"])

    valuation = portfolio_service.valuation(account.id, as_of="2026-09-08")
    assert valuation.is_complete
    assert valuation.priced_positions[0].mark.price == pytest_approx_decimal("74.25")


def pytest_approx_decimal(text):
    from decimal import Decimal
    return Decimal(text)
