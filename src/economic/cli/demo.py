"""Fictional demo data.

Every symbol here is invented. Demo data lets a user exercise the full software
flow without any risk of mistaking it for a real EGX recommendation
(BUILD_GUIDE Step 16).
"""

from __future__ import annotations

from datetime import date, timedelta

from ..application.portfolio_service import PortfolioService

DEMO_ACCOUNT = "DEMO Account"

# Deliberately non-existent tickers, prefixed so they can never be confused
# with a real Egyptian Exchange listing.
DEMO_INSTRUMENTS = [
    ("ZZDEMO1", "Demo Delta Bank (fictional)", "Banks"),
    ("ZZDEMO2", "Demo Nile Cement (fictional)", "Construction Materials"),
    ("ZZDEMO3", "Demo Oasis Foods (fictional)", "Food & Beverage"),
]


def _days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def seed(context, account_name: str = DEMO_ACCOUNT) -> dict:
    """Create a demo account with a small, deterministic fictional history."""
    service = PortfolioService(context)

    try:
        account = service.resolve_account(account_name)
        created = False
    except Exception:
        account = service.add_account(account_name, broker="DEMO Broker (fictional)")
        created = True

    for symbol, name, sector in DEMO_INSTRUMENTS:
        service.add_instrument(symbol, name=name, sector=sector)

    transactions = 0
    prices = 0

    def record(callback) -> int:
        """Run a demo write, tolerating a re-seed of the same data."""
        try:
            callback()
            return 1
        except Exception:
            return 0

    transactions += record(lambda: service.record_cash(
        account.id, "DEPOSIT", "250000", transaction_date=_days_ago(60),
        note="demo opening cash (fictional)"))

    plan = [
        ("ZZDEMO1", "1000", "48.50", 55, "25"),
        ("ZZDEMO1", "500", "52.00", 40, "15"),
        ("ZZDEMO2", "2000", "12.75", 30, "10"),
        ("ZZDEMO3", "800", "31.20", 25, "12"),
    ]
    for symbol, qty, price, days, commission in plan:
        transactions += record(lambda s=symbol, q=qty, p=price, d=days, c=commission:
                               service.record_trade(
                                   account.id, "BUY", s, q, p, transaction_date=_days_ago(d),
                                   commission=c, note="demo purchase (fictional)"))

    transactions += record(lambda: service.record_trade(
        account.id, "SELL", "ZZDEMO1", "600", "58.00", transaction_date=_days_ago(10),
        commission="18", note="demo partial sale (fictional)"))

    # ZZDEMO3 is deliberately left unpriced so the missing-price path is visible.
    for symbol, price, days in (("ZZDEMO1", "56.40", 1), ("ZZDEMO2", "11.90", 1)):
        prices += record(lambda s=symbol, p=price, d=days: service.set_price(
            s, p, price_date=_days_ago(d), source="demo (fictional)"))

    return {
        "account": account.name,
        "account_id": account.id,
        "created": created,
        "transactions": transactions,
        "prices": prices,
        "unpriced_on_purpose": ["ZZDEMO3"],
        "next_steps": [
            f'economic portfolio show --account "{account.name}"',
            f'economic simulate --account "{account.name}" --action BUY --symbol ZZDEMO2 '
            f"--qty 1000 --price 11.90",
            'economic committee --question "Is this portfolio too concentrated?" '
            f'--account "{account.name}" --mock',
            "economic history",
        ],
    }
