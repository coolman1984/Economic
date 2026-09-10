"""Freshness classification for disclosures and financial facts (ADR-023).

Deliberately separate from the frozen portfolio price-staleness check.
"""

from economic.data_providers.freshness import FreshnessPolicy, FRESH, AGING, STALE, UNKNOWN


def test_a_fact_published_today_is_fresh():
    policy = FreshnessPolicy()
    assert policy.classify("2026-09-10", None, as_of="2026-09-10") == FRESH


def test_a_fact_published_within_the_aging_threshold_is_still_fresh():
    policy = FreshnessPolicy(aging_after_days=3, stale_after_days=10)
    assert policy.classify("2026-09-08", None, as_of="2026-09-10") == FRESH


def test_a_fact_past_the_aging_threshold_is_aging():
    policy = FreshnessPolicy(aging_after_days=3, stale_after_days=10)
    assert policy.classify("2026-09-01", None, as_of="2026-09-10") == AGING


def test_a_fact_past_the_stale_threshold_is_stale():
    policy = FreshnessPolicy(aging_after_days=3, stale_after_days=10)
    assert policy.classify("2026-08-01", None, as_of="2026-09-10") == STALE


def test_no_date_at_all_is_unknown_not_guessed_fresh():
    policy = FreshnessPolicy()
    assert policy.classify(None, None, as_of="2026-09-10") == UNKNOWN


def test_published_at_takes_priority_over_retrieved_at():
    """A fact about a year-old event is stale even if fetched five minutes ago."""
    policy = FreshnessPolicy(aging_after_days=3, stale_after_days=10)
    result = policy.classify(published_at="2025-01-01", retrieved_at="2026-09-10",
                             as_of="2026-09-10")
    assert result == STALE


def test_retrieved_at_is_used_when_published_at_is_missing():
    policy = FreshnessPolicy(aging_after_days=3, stale_after_days=10)
    assert policy.classify(None, "2026-09-10", as_of="2026-09-10") == FRESH
    assert policy.classify(None, "2026-08-01", as_of="2026-09-10") == STALE


def test_the_thresholds_are_configurable():
    strict = FreshnessPolicy(aging_after_days=0, stale_after_days=1)
    assert strict.classify("2026-09-09", None, as_of="2026-09-10") == AGING
    assert strict.classify("2026-09-05", None, as_of="2026-09-10") == STALE


def test_age_days_reports_the_raw_age():
    policy = FreshnessPolicy()
    assert policy.age_days("2026-09-01", None, as_of="2026-09-10") == 9
    assert policy.age_days(None, None, as_of="2026-09-10") is None


def test_a_future_dated_fact_is_treated_as_fresh_not_negative_age():
    policy = FreshnessPolicy()
    assert policy.classify("2026-09-15", None, as_of="2026-09-10") == FRESH


def test_malformed_date_strings_are_treated_as_unknown_not_crashed():
    policy = FreshnessPolicy()
    assert policy.classify("not-a-date", None, as_of="2026-09-10") == UNKNOWN
