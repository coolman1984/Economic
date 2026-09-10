"""Portfolio domain: deterministic holdings, cost, P&L, and allocation.

Pricing policy (ARCHITECTURE §5, ACCEPTANCE_CRITERIA D):
    A position is marked at the latest price snapshot whose ``price_date`` is on
    or before the valuation date. If no such snapshot exists the position is
    reported as *unpriced* — never marked at cost and never guessed.

Cost policy (ADR-014):
    Weighted moving average cost. A BUY adds ``quantity x price + commission +
    fees`` to the cost basis. A SELL releases ``average_cost x quantity`` from
    the basis and realizes ``net_proceeds - released_cost``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from . import ledger
from .money import ZERO, money, pct, quantity, to_text

DEFAULT_STALE_AFTER_DAYS = 5


class PortfolioError(ValueError):
    """A transaction cannot be applied to the current portfolio state."""


@dataclass
class PriceMark:
    """A price snapshot used to mark a position."""

    symbol: str
    price: Decimal
    price_date: str
    source: str = "manual"
    retrieved_at: Optional[str] = None

    def age_days(self, as_of: str) -> int:
        return (date.fromisoformat(as_of) - date.fromisoformat(self.price_date)).days


@dataclass
class Position:
    """Deterministic state of one holding, rebuilt from transactions."""

    symbol: str
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    total_commission: Decimal = ZERO
    total_fees: Decimal = ZERO
    buy_count: int = 0
    sell_count: int = 0
    last_transaction_date: Optional[str] = None

    @property
    def average_cost(self) -> Optional[Decimal]:
        """Weighted average cost per unit, or None for a closed/empty position."""
        if self.quantity == 0:
            return None
        return self.cost_basis / self.quantity

    @property
    def is_open(self) -> bool:
        return self.quantity > 0


@dataclass
class ValuedPosition:
    """A position combined with a price mark (or the absence of one)."""

    position: Position
    mark: Optional[PriceMark] = None
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS
    as_of: str = ""

    @property
    def symbol(self) -> str:
        return self.position.symbol

    @property
    def is_priced(self) -> bool:
        return self.mark is not None

    @property
    def market_value(self) -> Optional[Decimal]:
        if self.mark is None:
            return None
        return money(self.position.quantity * self.mark.price, "market_value")

    @property
    def unrealized_pnl(self) -> Optional[Decimal]:
        value = self.market_value
        if value is None:
            return None
        return money(value - self.position.cost_basis, "unrealized_pnl")

    @property
    def price_age_days(self) -> Optional[int]:
        if self.mark is None or not self.as_of:
            return None
        return self.mark.age_days(self.as_of)

    @property
    def is_stale(self) -> bool:
        age = self.price_age_days
        return age is not None and age > self.stale_after_days


@dataclass
class PortfolioState:
    """Result of replaying a ledger: cash plus positions. No prices involved."""

    account_id: Optional[int]
    cash: Decimal = ZERO
    positions: Dict[str, Position] = field(default_factory=dict)
    transaction_count: int = 0
    last_transaction_date: Optional[str] = None

    @property
    def realized_pnl(self) -> Decimal:
        return sum((p.realized_pnl for p in self.positions.values()), ZERO)

    @property
    def total_cost_basis(self) -> Decimal:
        return sum((p.cost_basis for p in self.positions.values()), ZERO)

    def open_positions(self) -> List[Position]:
        return sorted(
            (p for p in self.positions.values() if p.is_open), key=lambda p: p.symbol
        )

    def quantity_of(self, symbol: str) -> Decimal:
        position = self.positions.get(ledger.normalize_symbol(symbol))
        return position.quantity if position else ZERO

    def copy(self) -> "PortfolioState":
        """Deep-enough copy so simulations can never touch live state."""
        clone = PortfolioState(
            account_id=self.account_id,
            cash=self.cash,
            transaction_count=self.transaction_count,
            last_transaction_date=self.last_transaction_date,
        )
        for symbol, position in self.positions.items():
            clone.positions[symbol] = Position(**vars(position))
        return clone


@dataclass
class Valuation:
    """Priced portfolio view: market value, equity, weights, data-quality flags."""

    account_id: Optional[int]
    as_of: str
    cash: Decimal
    positions: List[ValuedPosition]
    account_names: Dict[int, str] = field(default_factory=dict)

    @property
    def priced_positions(self) -> List[ValuedPosition]:
        return [p for p in self.positions if p.is_priced]

    @property
    def unpriced_positions(self) -> List[ValuedPosition]:
        return [p for p in self.positions if not p.is_priced]

    @property
    def stale_positions(self) -> List[ValuedPosition]:
        return [p for p in self.positions if p.is_stale]

    @property
    def market_value(self) -> Decimal:
        """Market value of priced positions only. Unpriced holdings are excluded
        and surfaced separately so equity is never silently understated."""
        return sum((p.market_value for p in self.priced_positions), ZERO)

    @property
    def total_equity(self) -> Decimal:
        return money(self.cash + self.market_value, "total_equity")

    @property
    def unrealized_pnl(self) -> Decimal:
        return sum((p.unrealized_pnl for p in self.priced_positions), ZERO)

    @property
    def realized_pnl(self) -> Decimal:
        return sum((p.position.realized_pnl for p in self.positions), ZERO)

    @property
    def is_complete(self) -> bool:
        """True when every open position has a price mark."""
        return not self.unpriced_positions

    def weight_of(self, symbol: str) -> Decimal:
        """Position weight as a percentage of total equity."""
        equity = self.total_equity
        for valued in self.priced_positions:
            if valued.symbol == symbol:
                return pct(valued.market_value, equity)
        return ZERO

    def data_quality(self) -> dict:
        return {
            "complete": self.is_complete,
            "missing_prices": [p.symbol for p in self.unpriced_positions],
            "stale_prices": [
                {"symbol": p.symbol, "age_days": p.price_age_days}
                for p in self.stale_positions
            ],
        }


def apply_transaction(state: PortfolioState, transaction: ledger.Transaction) -> PortfolioState:
    """Apply one validated transaction to ``state`` in place and return it.

    Raises ``PortfolioError`` when the transaction would break an invariant
    (overselling, or selling an instrument that is not held).
    """
    kind = transaction.transaction_type

    if kind in ledger.CASH_TYPES:
        state.cash = money(state.cash + transaction.cash_amount, "cash")
    elif kind == ledger.BUY:
        position = state.positions.setdefault(
            transaction.symbol, Position(symbol=transaction.symbol)
        )
        cost = transaction.gross_amount + transaction.total_charges
        position.quantity = quantity(position.quantity + transaction.quantity)
        position.cost_basis = money(position.cost_basis + cost, "cost_basis")
        position.total_commission += transaction.commission
        position.total_fees += transaction.fees
        position.buy_count += 1
        position.last_transaction_date = transaction.transaction_date
        state.cash = money(state.cash + transaction.cash_amount, "cash")
    elif kind == ledger.SELL:
        position = state.positions.get(transaction.symbol)
        if position is None or position.quantity <= 0:
            raise PortfolioError(
                f"cannot SELL {transaction.symbol}: no open position in account "
                f"{transaction.account_id}"
            )
        if transaction.quantity > position.quantity:
            raise PortfolioError(
                f"cannot SELL {to_text(transaction.quantity)} {transaction.symbol}: "
                f"only {to_text(position.quantity)} held"
            )
        average_cost = position.average_cost
        released_cost = money(average_cost * transaction.quantity, "released_cost")
        net_proceeds = transaction.cash_amount
        position.quantity = quantity(position.quantity - transaction.quantity)
        # Guard against residual dust on a full exit.
        position.cost_basis = (
            ZERO if position.quantity == 0 else money(position.cost_basis - released_cost)
        )
        position.realized_pnl = money(
            position.realized_pnl + (net_proceeds - released_cost), "realized_pnl"
        )
        position.total_commission += transaction.commission
        position.total_fees += transaction.fees
        position.sell_count += 1
        position.last_transaction_date = transaction.transaction_date
        state.cash = money(state.cash + transaction.cash_amount, "cash")
    else:
        raise PortfolioError(f"unsupported transaction type: {kind}")

    state.transaction_count += 1
    if (
        state.last_transaction_date is None
        or transaction.transaction_date > state.last_transaction_date
    ):
        state.last_transaction_date = transaction.transaction_date
    return state


def rebuild(transactions: Iterable[ledger.Transaction], account_id: Optional[int] = None) -> PortfolioState:
    """Replay a ledger deterministically into a portfolio state."""
    state = PortfolioState(account_id=account_id)
    for transaction in ledger.ordered(list(transactions)):
        apply_transaction(state, transaction)
    return state


def merge(states: Iterable[PortfolioState]) -> PortfolioState:
    """Consolidate several account states into one combined view."""
    combined = PortfolioState(account_id=None)
    for state in states:
        combined.cash = money(combined.cash + state.cash, "cash")
        combined.transaction_count += state.transaction_count
        if state.last_transaction_date and (
            combined.last_transaction_date is None
            or state.last_transaction_date > combined.last_transaction_date
        ):
            combined.last_transaction_date = state.last_transaction_date
        for symbol, position in state.positions.items():
            target = combined.positions.setdefault(symbol, Position(symbol=symbol))
            target.quantity = quantity(target.quantity + position.quantity)
            target.cost_basis = money(target.cost_basis + position.cost_basis)
            target.realized_pnl = money(target.realized_pnl + position.realized_pnl)
            target.total_commission += position.total_commission
            target.total_fees += position.total_fees
            target.buy_count += position.buy_count
            target.sell_count += position.sell_count
            if position.last_transaction_date and (
                target.last_transaction_date is None
                or position.last_transaction_date > target.last_transaction_date
            ):
                target.last_transaction_date = position.last_transaction_date
    return combined


def value(
    state: PortfolioState,
    marks: Dict[str, PriceMark],
    as_of: Optional[str] = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> Valuation:
    """Combine a portfolio state with price marks into a priced valuation."""
    as_of = as_of or date.today().isoformat()
    valued = [
        ValuedPosition(
            position=position,
            mark=marks.get(position.symbol),
            stale_after_days=stale_after_days,
            as_of=as_of,
        )
        for position in state.open_positions()
    ]
    return Valuation(
        account_id=state.account_id, as_of=as_of, cash=state.cash, positions=valued
    )


def snapshot(valuation: Valuation, state: PortfolioState) -> dict:
    """Immutable JSON snapshot handed to a research run (DATA_MODEL §8)."""
    return {
        "as_of": valuation.as_of,
        "account_id": valuation.account_id,
        "accounts": [
            {"id": account_id, "name": name}
            for account_id, name in sorted(valuation.account_names.items())
        ],
        "cash": to_text(valuation.cash),
        "market_value": to_text(valuation.market_value),
        "total_equity": to_text(valuation.total_equity),
        "realized_pnl": to_text(valuation.realized_pnl),
        "unrealized_pnl": to_text(valuation.unrealized_pnl),
        "transaction_count": state.transaction_count,
        "positions": [
            {
                "symbol": v.symbol,
                "quantity": to_text(v.position.quantity),
                "average_cost": to_text(v.position.average_cost),
                "cost_basis": to_text(v.position.cost_basis),
                "price": to_text(v.mark.price) if v.mark else None,
                "price_date": v.mark.price_date if v.mark else None,
                "price_source": v.mark.source if v.mark else None,
                "price_age_days": v.price_age_days,
                "stale": v.is_stale,
                "market_value": to_text(v.market_value) if v.is_priced else None,
                "unrealized_pnl": to_text(v.unrealized_pnl) if v.is_priced else None,
                "realized_pnl": to_text(v.position.realized_pnl),
                "weight_pct": to_text(valuation.weight_of(v.symbol)) if v.is_priced else None,
            }
            for v in valuation.positions
        ],
        "prices_as_of": {
            v.symbol: v.mark.price_date for v in valuation.positions if v.mark
        },
        "missing_prices": [v.symbol for v in valuation.unpriced_positions],
        "stale_prices": [v.symbol for v in valuation.stale_positions],
        "data_quality": valuation.data_quality(),
    }
