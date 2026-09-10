"""File-based data providers: parsing, validation, and normalization.

Each provider must reject a bad file outright (ProviderError) but tolerate a
bad individual row (RejectedRecord) without losing the good rows in the same
file — the same "never fabricate, never lose what's valid" discipline as the
agent adapters (BUILD_GUIDE, AGENTS.md §3).
"""

from decimal import Decimal

import pytest

from economic.data_providers.base import ProviderError, SourceTier
from economic.data_providers.csv_utils import content_hash, file_hash, read_rows
from economic.data_providers.disclosure_provider import DisclosureFileProvider
from economic.data_providers.financial_provider import FinancialFactFileProvider
from economic.data_providers.instrument_provider import InstrumentFileProvider
from economic.data_providers.price_provider import PriceFileProvider


# ---- csv_utils --------------------------------------------------------

def test_missing_file_raises_source_unavailable(tmp_path):
    with pytest.raises(ProviderError) as excinfo:
        read_rows(tmp_path / "nope.csv", ["symbol"])
    assert excinfo.value.failure_kind == "source_unavailable"


def test_empty_file_raises_empty_result(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(ProviderError) as excinfo:
        read_rows(path, ["symbol"])
    assert excinfo.value.failure_kind == "empty_result"


def test_header_only_file_raises_empty_result(tmp_path):
    path = tmp_path / "headeronly.csv"
    path.write_text("symbol,price\n")
    with pytest.raises(ProviderError) as excinfo:
        read_rows(path, ["symbol"])
    assert excinfo.value.failure_kind == "empty_result"


def test_missing_required_column_raises_malformed_schema(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("foo,bar\n1,2\n")
    with pytest.raises(ProviderError) as excinfo:
        read_rows(path, ["symbol"])
    assert excinfo.value.failure_kind == "malformed_schema"
    assert "symbol" in str(excinfo.value)


def test_column_matching_is_case_insensitive_and_trimmed(tmp_path):
    path = tmp_path / "ok.csv"
    path.write_text(" Symbol , Price \nCOMI,50\n")
    rows = read_rows(path, ["symbol"])
    assert rows == [{"symbol": "COMI", "price": "50"}]


def test_file_hash_is_stable_and_content_dependent(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("hello")
    b.write_text("hello")
    c = tmp_path / "c.txt"
    c.write_text("different")
    assert file_hash(a) == file_hash(b)
    assert file_hash(a) != file_hash(c)
    assert content_hash("hello") == file_hash(a)


# ---- instrument provider ----------------------------------------------

def test_instrument_provider_normalizes_a_valid_row(tmp_path):
    path = tmp_path / "i.csv"
    path.write_text(
        "symbol,name,sector,isin,source_name,source_url\n"
        "comi,Commercial International Bank,Banks,EGS60121C018,"
        "stockanalysis.com,https://stockanalysis.com/quote/egx/COMI/\n"
    )
    normalized, rejected = InstrumentFileProvider().read(path)
    assert not rejected
    item = normalized[0]
    assert item.symbol == "COMI"
    assert item.isin == "EGS60121C018"
    assert item.provenance.source_tier == SourceTier.IMPORT
    assert item.provenance.source_url.startswith("https://stockanalysis.com")


def test_instrument_provider_rejects_invalid_symbol_without_losing_good_rows(tmp_path):
    path = tmp_path / "i.csv"
    path.write_text("symbol\nCOMI\nbad symbol!\nHRHO\n")
    normalized, rejected = InstrumentFileProvider().read(path)
    assert [n.symbol for n in normalized] == ["COMI", "HRHO"]
    assert len(rejected) == 1
    assert rejected[0].index == 1


def test_instrument_provider_defaults_exchange_and_currency(tmp_path):
    path = tmp_path / "i.csv"
    path.write_text("symbol\nCOMI\n")
    normalized, _ = InstrumentFileProvider().read(path)
    assert normalized[0].exchange == "EGX"
    assert normalized[0].currency == "EGP"


# ---- price provider -----------------------------------------------------

def test_price_provider_parses_exact_decimals_never_floats(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("symbol,date,close\nCOMI,2026-09-08,74.25\n")
    normalized, rejected = PriceFileProvider().read(path)
    assert not rejected
    assert normalized[0].close_price == Decimal("74.25")
    assert isinstance(normalized[0].close_price, Decimal)


def test_price_provider_rejects_bad_date_and_bad_price(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text(
        "symbol,date,close\n"
        "COMI,not-a-date,74.25\n"
        "HRHO,2026-09-08,-5\n"
        "COMI,2026-09-09,0\n"
    )
    normalized, rejected = PriceFileProvider().read(path)
    assert normalized == []
    assert len(rejected) == 3


def test_price_provider_captures_optional_ohlcv(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("symbol,date,close,open,high,low,volume\nCOMI,2026-09-08,74.25,73,75,72,1000000\n")
    normalized, _ = PriceFileProvider().read(path)
    item = normalized[0]
    assert item.open_price == Decimal("73")
    assert item.high_price == Decimal("75")
    assert item.low_price == Decimal("72")
    assert item.volume == Decimal("1000000")


def test_price_provider_sets_published_at_to_the_price_date(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("symbol,date,close\nCOMI,2026-09-08,74.25\n")
    normalized, _ = PriceFileProvider().read(path)
    assert normalized[0].provenance.published_at == "2026-09-08"


# ---- disclosure provider -------------------------------------------------

def test_disclosure_provider_reads_a_valid_manifest(tmp_path):
    (tmp_path / "doc.txt").write_text("body text")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "document_type,title,file,symbol,published_at,source_name,source_url,external_id\n"
        "QUARTERLY_REPORT,COMI Q2,doc.txt,COMI,2026-08-15,EGX disclosures,"
        "https://www.egx.com.eg/en/NewsList.aspx,EGX-COMI-Q2\n"
    )
    normalized, rejected = DisclosureFileProvider().read(manifest)
    assert not rejected
    doc = normalized[0]
    assert doc.document_type == "QUARTERLY_REPORT"
    assert doc.symbol == "COMI"
    assert doc.provenance.content_hash == file_hash(tmp_path / "doc.txt")
    assert doc.provenance.external_id == "EGX-COMI-Q2"


def test_disclosure_provider_rejects_unknown_document_type(tmp_path):
    (tmp_path / "doc.txt").write_text("body")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("document_type,title,file\nNOT_A_TYPE,title,doc.txt\n")
    normalized, rejected = DisclosureFileProvider().read(manifest)
    assert not normalized
    assert "document_type" in rejected[0].reason


def test_disclosure_provider_rejects_a_missing_document_file(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("document_type,title,file\nBOARD_DECISION,title,missing.txt\n")
    normalized, rejected = DisclosureFileProvider().read(manifest)
    assert not normalized
    assert "not found" in rejected[0].reason


def test_disclosure_provider_resolves_relative_paths_against_manifest_dir(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "doc.txt").write_text("body")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("document_type,title,file\nBOARD_DECISION,title,docs/doc.txt\n")
    normalized, rejected = DisclosureFileProvider().read(manifest)
    assert not rejected
    assert normalized[0].local_path.endswith("docs/doc.txt")


def test_disclosure_provider_honors_explicit_docs_dir(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc.txt").write_text("body")
    manifest = manifest_dir / "manifest.csv"
    manifest.write_text("document_type,title,file\nBOARD_DECISION,title,doc.txt\n")
    normalized, rejected = DisclosureFileProvider().read(manifest, docs_dir=docs_dir)
    assert not rejected


# ---- financial fact provider ----------------------------------------------

def test_financial_provider_parses_a_valid_row(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text(
        "symbol,period_end,period_type,metric,value,currency\n"
        "COMI,2025-12-31,ANNUAL,revenue,128540000000,EGP\n"
    )
    normalized, rejected = FinancialFactFileProvider().read(path)
    assert not rejected
    fact = normalized[0]
    assert fact.value == Decimal("128540000000")
    assert fact.period_type == "ANNUAL"
    assert fact.currency == "EGP"


def test_financial_provider_rejects_unknown_period_type(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text("symbol,period_end,period_type,metric,value\nCOMI,2025-12-31,DECADE,revenue,1\n")
    normalized, rejected = FinancialFactFileProvider().read(path)
    assert not normalized
    assert "period_type" in rejected[0].reason


def test_financial_provider_rejects_non_numeric_value(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text("symbol,period_end,period_type,metric,value\nCOMI,2025-12-31,ANNUAL,revenue,not-a-number\n")
    normalized, rejected = FinancialFactFileProvider().read(path)
    assert not normalized
    assert rejected


def test_financial_provider_links_to_source_document_via_external_id(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text(
        "symbol,period_end,period_type,metric,value,source_document_external_id\n"
        "COMI,2025-12-31,ANNUAL,revenue,100,EGX-COMI-2026-Q2\n"
    )
    normalized, _ = FinancialFactFileProvider().read(path)
    assert normalized[0].source_document_external_id == "EGX-COMI-2026-Q2"
    assert normalized[0].provenance.external_id == "EGX-COMI-2026-Q2"
