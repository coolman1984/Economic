"""Portfolio workflows: accounts, cash, trades, prices, and valuation.

The service coordinates domain rules and persistence. Every ledger write is
validated by the domain first, checked against current holdings, then persisted
inside one transaction together with its audit entry.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from ..domain import ledger, portfolio, risk
from ..domain.money import to_text
from ..domain.portfolio import PriceMark
from ..persistence import sqlite_db
from ..persistence.repositories import Account, DuplicateTransactionError, NotFoundError
from .context import AppContext


class PortfolioService:
    def __init__(self, context: AppContext):
        self.context = context
        self.repos = context.repos
        self.config = context.config

    # ---- accounts and instruments ---------------------------------------

    def add_account(self, name: str, broker: Optional[str] = None,
                    currency: Optional[str] = None) -> Account:
        with sqlite_db.transaction(self.context.connection):
            account = self.repos.accounts.add(
                name, broker, currency or self.config.values.get("currency", "EGP")
            )
            self.repos.audit.record(
                action="ACCOUNT_CREATED", entity_type="account", entity_id=account.id,
                after={"name": account.name, "broker": account.broker,
                       "currency": account.currency},
            )
        return account

    def list_accounts(self) -> List[Account]:
        return self.repos.accounts.list()

    def resolve_account(self, reference) -> Account:
        return self.repos.accounts.resolve(reference)

    def add_instrument(self, symbol: str, name: Optional[str] = None,
                       sector: Optional[str] = None, industry: Optional[str] = None):
        with sqlite_db.transaction(self.context.connection):
            instrument = self.repos.instruments.upsert(symbol, name, sector, industry)
            self.repos.audit.record(
                action="INSTRUMENT_UPSERTED", entity_type="instrument",
                entity_id=instrument.id,
                after={"symbol": instrument.symbol, "name": instrument.name,
                       "sector": instrument.sector},
            )
        return instrument

    def list_instruments(self):
        return self.repos.instruments.list()

    # ---- ledger ----------------------------------------------------------

    def record_cash(self, account_reference, transaction_type: str, amount,
                    transaction_date=None, fees="0", note: Optional[str] = None,
                    allow_duplicate: bool = False) -> ledger.Transaction:
        """Record a DEPOSIT or WITHDRAW. A withdrawal may not overdraw cash."""
        account = self.resolve_account(account_reference)
        transaction = ledger.build_cash_transaction(
            transaction_type.upper(), account.id, amount,
            transaction_date=transaction_date, fees=fees, note=note,
        )
        return self._persist(account, transaction, allow_duplicate)

    def record_trade(self, account_reference, transaction_type: str, symbol: str, qty, price,
                     transaction_date=None, commission="0", fees="0",
                     note: Optional[str] = None, allow_duplicate: bool = False,
                     sector: Optional[str] = None) -> ledger.Transaction:
        """Record a BUY or SELL, rejecting a SELL that exceeds holdings."""
        account = self.resolve_account(account_reference)
        symbol = ledger.normalize_symbol(symbol)
        instrument = self.repos.instruments.upsert(symbol, sector=sector)
        transaction = ledger.build_trade_transaction(
            transaction_type.upper(), account.id, symbol, qty, price,
            transaction_date=transaction_date, commission=commission, fees=fees,
            note=note, instrument_id=instrument.id,
        )
        return self._persist(account, transaction, allow_duplicate)

    def _persist(self, account: Account, transaction: ledger.Transaction,
                 allow_duplicate: bool) -> ledger.Transaction:
        """Validate against current holdings, then persist with an audit entry."""
        state = self.state_for_account(account.id)
        before = {"cash": to_text(state.cash),
                  "quantity": to_text(state.quantity_of(transaction.symbol))
                  if transaction.symbol else None}

        # Raises PortfolioError (oversell, unheld symbol) before anything is written.
        projected = portfolio.apply_transaction(state.copy(), transaction)
        if transaction.transaction_type in (ledger.WITHDRAW, ledger.BUY) and projected.cash < 0:
            raise portfolio.PortfolioError(
                f"insufficient cash: balance {to_text(state.cash)} cannot cover "
                f"{to_text(-transaction.cash_amount)}"
            )

        with sqlite_db.transaction(self.context.connection):
            stored = self.repos.transactions.add(transaction, allow_duplicate=allow_duplicate)
            self.repos.audit.record(
                action=f"TRANSACTION_{stored.transaction_type}",
                entity_type="transaction", entity_id=stored.id,
                before=before,
                after={"cash": to_text(projected.cash),
                       "quantity": to_text(projected.quantity_of(stored.symbol))
                       if stored.symbol else None,
                       "amount": to_text(stored.cash_amount)},
                reason=stored.note,
            )
        return stored

    # ---- prices ----------------------------------------------------------

    def set_price(self, symbol: str, price, price_date=None, source: str = "manual",
                  source_url: Optional[str] = None) -> PriceMark:
        symbol = ledger.normalize_symbol(symbol)
        with sqlite_db.transaction(self.context.connection):
            instrument = self.repos.instruments.upsert(symbol)
            mark = self.repos.prices.set_price(
                instrument.id, symbol, price,
                ledger.normalize_date(price_date), source, source_url,
            )
            self.repos.audit.record(
                action="PRICE_SET", entity_type="instrument", entity_id=instrument.id,
                actor_type="human",
                after={"symbol": symbol, "price": to_text(mark.price),
                       "price_date": mark.price_date, "source": source},
            )
        return mark

    def price_history(self, symbol: str, limit: int = 20) -> List[PriceMark]:
        return self.repos.prices.history(symbol, limit)

    # ---- deterministic views --------------------------------------------

    def state_for_account(self, account_id: int) -> portfolio.PortfolioState:
        """Rebuild one account's holdings from its stored transactions."""
        transactions = self.repos.transactions.list_for_account(account_id)
        return portfolio.rebuild(transactions, account_id=account_id)

    def consolidated_state(self) -> portfolio.PortfolioState:
        """Consolidated holdings across every account."""
        return portfolio.merge(
            self.state_for_account(account.id) for account in self.list_accounts()
        )

    def marks_for(self, state: portfolio.PortfolioState,
                  as_of: Optional[str] = None) -> Dict[str, PriceMark]:
        symbols = [position.symbol for position in state.open_positions()]
        return self.repos.prices.marks_for(symbols, as_of)

    def valuation(self, account_reference=None, as_of: Optional[str] = None) -> portfolio.Valuation:
        """Priced view of one account, or of every account when omitted."""
        as_of = as_of or date.today().isoformat()
        if account_reference is None:
            state = self.consolidated_state()
            names = {account.id: account.name for account in self.list_accounts()}
        else:
            account = self.resolve_account(account_reference)
            state = self.state_for_account(account.id)
            names = {account.id: account.name}
        valuation = portfolio.value(
            state, self.marks_for(state, as_of), as_of=as_of,
            stale_after_days=self.config.stale_price_after_days,
        )
        valuation.account_names = names
        return valuation

    def rules(self) -> risk.PortfolioRules:
        return risk.PortfolioRules.from_config(self.config.portfolio_rules)

    def snapshot(self, account_reference=None, as_of: Optional[str] = None) -> dict:
        """Immutable snapshot used as research-run input (DATA_MODEL §8)."""
        as_of = as_of or date.today().isoformat()
        if account_reference is None:
            state = self.consolidated_state()
        else:
            state = self.state_for_account(self.resolve_account(account_reference).id)
        valuation = self.valuation(account_reference, as_of)
        payload = portfolio.snapshot(valuation, state)
        rules = self.rules()
        payload["risk_limits"] = rules.to_dict()
        payload["rule_violations"] = [v.to_dict() for v in risk.evaluate(valuation, rules)]
        payload["data_quality_score"] = risk.data_quality_score(valuation)
        return payload

    # ---- executions ------------------------------------------------------

    def record_execution(self, transaction_id: int, human_decision_id: Optional[int] = None,
                         note: Optional[str] = None) -> int:
        """Link a real broker transaction the user already recorded to a decision."""
        transaction = self.repos.transactions.get(transaction_id)
        if human_decision_id is not None:
            self.repos.decisions.get(human_decision_id)
        with sqlite_db.transaction(self.context.connection):
            execution_id = self.repos.executions.add(transaction.id, human_decision_id, note)
            self.repos.audit.record(
                action="EXECUTION_RECORDED", entity_type="execution", entity_id=execution_id,
                after={"transaction_id": transaction.id,
                       "human_decision_id": human_decision_id},
                reason=note,
            )
        return execution_id
