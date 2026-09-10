"""Ledger domain: transaction semantics and accounting invariants.

This module owns *what a transaction means*. It does not know about SQLite,
the CLI, or AI agents. Every rule here is deterministic and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from .money import ZERO, money, quantity, to_decimal, to_text

DEPOSIT = "DEPOSIT"
WITHDRAW = "WITHDRAW"
BUY = "BUY"
SELL = "SELL"

TRANSACTION_TYPES = (DEPOSIT, WITHDRAW, BUY, SELL)
TRADE_TYPES = (BUY, SELL)
CASH_TYPES = (DEPOSIT, WITHDRAW)

SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,19}$")


class LedgerError(ValueError):
    """A transaction violates an accounting rule."""


def normalize_symbol(symbol: str) -> str:
    """Uppercase and validate an instrument symbol."""
    if not isinstance(symbol, str):
        raise LedgerError("symbol must be a string")
    cleaned = symbol.strip().upper()
    if not SYMBOL_RE.match(cleaned):
        raise LedgerError(f"invalid symbol: {symbol!r}")
    return cleaned


def normalize_date(value) -> str:
    """Normalize a transaction date to an ISO ``YYYY-MM-DD`` string."""
    if value is None:
        return date.today().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise LedgerError(f"invalid date: {value!r} (expected YYYY-MM-DD)") from exc


@dataclass(frozen=True)
class Transaction:
    """A validated, immutable ledger entry.

    ``cash_amount`` is the signed effect on the account's cash balance, always
    derived here rather than supplied by a caller or an AI agent.
    """

    transaction_type: str
    account_id: int
    transaction_date: str
    cash_amount: Decimal
    quantity: Decimal = ZERO
    unit_price: Decimal = ZERO
    commission: Decimal = ZERO
    fees: Decimal = ZERO
    symbol: Optional[str] = None
    instrument_id: Optional[int] = None
    portfolio_id: Optional[int] = None
    external_reference: Optional[str] = None
    source: str = "manual"
    note: Optional[str] = None
    id: Optional[int] = None
    sequence: Optional[int] = None
    supersedes_transaction_id: Optional[int] = None
    superseded_by_transaction_id: Optional[int] = None
    created_at: Optional[str] = None
    extra: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def is_trade(self) -> bool:
        return self.transaction_type in TRADE_TYPES

    @property
    def total_charges(self) -> Decimal:
        return self.commission + self.fees

    @property
    def gross_amount(self) -> Decimal:
        """Quantity x unit price, before commission and fees."""
        return self.quantity * self.unit_price

    def fingerprint(self) -> str:
        """Stable identity used for duplicate-import protection (DATA_MODEL §7)."""
        if self.external_reference:
            return "|".join([self.source, str(self.account_id), self.external_reference])
        return "|".join(
            [
                self.source,
                str(self.account_id),
                self.transaction_date,
                self.transaction_type,
                self.symbol or "",
                to_text(self.quantity),
                to_text(self.unit_price),
                to_text(self.cash_amount),
                to_text(self.total_charges),
            ]
        )


def _validate_charges(commission: Decimal, fees: Decimal) -> None:
    if commission < 0:
        raise LedgerError("commission must be >= 0")
    if fees < 0:
        raise LedgerError("fees must be >= 0")


def build_cash_transaction(
    transaction_type: str,
    account_id: int,
    amount,
    transaction_date=None,
    fees="0",
    note: Optional[str] = None,
    source: str = "manual",
    external_reference: Optional[str] = None,
    portfolio_id: Optional[int] = None,
) -> Transaction:
    """Build a validated DEPOSIT or WITHDRAW.

    A deposit credits ``amount`` and debits any fee; a withdrawal debits both.
    """
    if transaction_type not in CASH_TYPES:
        raise LedgerError(f"{transaction_type} is not a cash transaction type")
    value = money(amount, "amount")
    charge = money(fees, "fees")
    _validate_charges(ZERO, charge)
    if value <= 0:
        raise LedgerError("amount must be > 0")

    cash_amount = value - charge if transaction_type == DEPOSIT else -(value + charge)
    return Transaction(
        transaction_type=transaction_type,
        account_id=account_id,
        transaction_date=normalize_date(transaction_date),
        cash_amount=cash_amount,
        fees=charge,
        note=note,
        source=source,
        external_reference=external_reference,
        portfolio_id=portfolio_id,
    )


def build_trade_transaction(
    transaction_type: str,
    account_id: int,
    symbol: str,
    qty,
    price,
    transaction_date=None,
    commission="0",
    fees="0",
    note: Optional[str] = None,
    source: str = "manual",
    external_reference: Optional[str] = None,
    instrument_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> Transaction:
    """Build a validated BUY or SELL.

    BUY cash effect: -(quantity x price + commission + fees).
    SELL cash effect: +(quantity x price - commission - fees).
    Oversell protection is a portfolio-state rule and lives in ``portfolio.py``.
    """
    if transaction_type not in TRADE_TYPES:
        raise LedgerError(f"{transaction_type} is not a trade transaction type")
    units = quantity(qty, "quantity")
    unit_price = money(price, "price")
    commission_amount = money(commission, "commission")
    fee_amount = money(fees, "fees")
    _validate_charges(commission_amount, fee_amount)
    if units <= 0:
        raise LedgerError("quantity must be > 0")
    if unit_price <= 0:
        raise LedgerError("price must be > 0")

    gross = units * unit_price
    charges = commission_amount + fee_amount
    cash_amount = -(gross + charges) if transaction_type == BUY else gross - charges

    return Transaction(
        transaction_type=transaction_type,
        account_id=account_id,
        transaction_date=normalize_date(transaction_date),
        cash_amount=money(cash_amount, "cash_amount"),
        quantity=units,
        unit_price=unit_price,
        commission=commission_amount,
        fees=fee_amount,
        symbol=normalize_symbol(symbol),
        instrument_id=instrument_id,
        portfolio_id=portfolio_id,
        note=note,
        source=source,
        external_reference=external_reference,
    )


def sort_key(transaction: Transaction):
    """Deterministic replay order: date, then insertion sequence, then id."""
    return (
        transaction.transaction_date,
        transaction.sequence if transaction.sequence is not None else 0,
        transaction.id if transaction.id is not None else 0,
    )


def ordered(transactions) -> list:
    """Return transactions in deterministic replay order, ignoring superseded rows."""
    active = [t for t in transactions if t.superseded_by_transaction_id is None]
    return sorted(active, key=sort_key)
