"""Repositories — the only place that knows SQL for the domain tables.

Application services depend on these classes; CLI code never writes SQL itself.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional

from ..domain import ledger
from ..domain.money import ZERO, money, quantity, to_decimal, to_text
from ..domain.portfolio import PriceMark
from .sqlite_db import utc_now


class DuplicateTransactionError(ValueError):
    """A transaction with the same fingerprint already exists."""


class NotFoundError(LookupError):
    """A referenced record does not exist."""


def _json(value) -> Optional[str]:
    return None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _unjson(value):
    return None if value is None else json.loads(value)


@dataclass
class Account:
    id: int
    name: str
    broker: Optional[str]
    currency: str
    status: str
    created_at: str
    updated_at: str


@dataclass
class Instrument:
    id: int
    symbol: str
    name: Optional[str]
    exchange: str
    sector: Optional[str]
    industry: Optional[str]
    currency: str
    trading_status: str


class BaseRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection


class AccountRepository(BaseRepository):
    def add(self, name: str, broker: Optional[str] = None, currency: str = "EGP") -> Account:
        name = name.strip()
        if not name:
            raise ValueError("account name must not be empty")
        now = utc_now()
        try:
            cursor = self.connection.execute(
                "INSERT INTO accounts (name, broker, currency, status, created_at, updated_at)"
                " VALUES (?, ?, ?, 'ACTIVE', ?, ?)",
                (name, broker, currency.upper(), now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"account {name!r} already exists") from exc
        return self.get(cursor.lastrowid)

    def get(self, account_id: int) -> Account:
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"account {account_id} not found")
        return Account(**dict(row))

    def get_by_name(self, name: str) -> Account:
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE name = ? COLLATE NOCASE", (name.strip(),)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"account {name!r} not found")
        return Account(**dict(row))

    def resolve(self, reference) -> Account:
        """Look up an account by numeric id or by name."""
        if isinstance(reference, int):
            return self.get(reference)
        text = str(reference).strip()
        if text.isdigit():
            return self.get(int(text))
        return self.get_by_name(text)

    def list(self) -> List[Account]:
        rows = self.connection.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        return [Account(**dict(row)) for row in rows]


class InstrumentRepository(BaseRepository):
    def upsert(
        self,
        symbol: str,
        name: Optional[str] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        exchange: str = "EGX",
        currency: str = "EGP",
    ) -> Instrument:
        symbol = ledger.normalize_symbol(symbol)
        now = utc_now()
        existing = self.connection.execute(
            "SELECT * FROM instruments WHERE symbol = ?", (symbol,)
        ).fetchone()
        if existing is None:
            self.connection.execute(
                "INSERT INTO instruments (symbol, name, exchange, sector, industry, currency,"
                " trading_status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)",
                (symbol, name, exchange, sector, industry, currency.upper(), now, now),
            )
        else:
            self.connection.execute(
                "UPDATE instruments SET name = COALESCE(?, name), sector = COALESCE(?, sector),"
                " industry = COALESCE(?, industry), updated_at = ? WHERE symbol = ?",
                (name, sector, industry, now, symbol),
            )
        return self.get_by_symbol(symbol)

    def get_by_symbol(self, symbol: str) -> Instrument:
        row = self.connection.execute(
            "SELECT id, symbol, name, exchange, sector, industry, currency, trading_status"
            " FROM instruments WHERE symbol = ?",
            (ledger.normalize_symbol(symbol),),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"instrument {symbol!r} not found")
        return Instrument(**dict(row))

    def list(self) -> List[Instrument]:
        rows = self.connection.execute(
            "SELECT id, symbol, name, exchange, sector, industry, currency, trading_status"
            " FROM instruments ORDER BY symbol"
        ).fetchall()
        return [Instrument(**dict(row)) for row in rows]


class TransactionRepository(BaseRepository):
    def _next_sequence(self) -> int:
        row = self.connection.execute("SELECT COALESCE(MAX(sequence), 0) FROM transactions").fetchone()
        return int(row[0]) + 1

    def add(self, transaction: ledger.Transaction, allow_duplicate: bool = False) -> ledger.Transaction:
        """Persist a validated transaction.

        The fingerprint index makes repeated imports idempotent (DATA_MODEL §7).
        A genuine repeat of an identical manual entry requires
        ``allow_duplicate=True``, which records an explicit occurrence suffix
        rather than silently weakening duplicate protection.
        """
        fingerprint = transaction.fingerprint()
        if self.find_by_fingerprint(fingerprint) is not None:
            if not allow_duplicate:
                raise DuplicateTransactionError(
                    "an identical transaction already exists "
                    f"(fingerprint {fingerprint}); pass allow_duplicate to record a repeat"
                )
            occurrence = 2
            while self.find_by_fingerprint(f"{fingerprint}#{occurrence}") is not None:
                occurrence += 1
            fingerprint = f"{fingerprint}#{occurrence}"

        sequence = self._next_sequence()
        now = utc_now()
        cursor = self.connection.execute(
            "INSERT INTO transactions (account_id, portfolio_id, transaction_type, instrument_id,"
            " symbol, quantity, unit_price, cash_amount, commission, fees, transaction_date,"
            " external_reference, source, note, fingerprint, sequence,"
            " supersedes_transaction_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                transaction.account_id,
                transaction.portfolio_id,
                transaction.transaction_type,
                transaction.instrument_id,
                transaction.symbol,
                to_text(transaction.quantity),
                to_text(transaction.unit_price),
                to_text(transaction.cash_amount),
                to_text(transaction.commission),
                to_text(transaction.fees),
                transaction.transaction_date,
                transaction.external_reference,
                transaction.source,
                transaction.note,
                fingerprint,
                sequence,
                transaction.supersedes_transaction_id,
                now,
            ),
        )
        return self.get(cursor.lastrowid)

    def find_by_fingerprint(self, fingerprint: str) -> Optional[ledger.Transaction]:
        row = self.connection.execute(
            "SELECT * FROM transactions WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        return None if row is None else self._to_transaction(row)

    def get(self, transaction_id: int) -> ledger.Transaction:
        row = self.connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"transaction {transaction_id} not found")
        return self._to_transaction(row)

    def list_for_account(self, account_id: int, include_superseded: bool = False) -> List[ledger.Transaction]:
        sql = "SELECT * FROM transactions WHERE account_id = ?"
        if not include_superseded:
            sql += " AND superseded_by_transaction_id IS NULL"
        sql += " ORDER BY transaction_date, sequence, id"
        rows = self.connection.execute(sql, (account_id,)).fetchall()
        return [self._to_transaction(row) for row in rows]

    def list_all(self, include_superseded: bool = False) -> List[ledger.Transaction]:
        sql = "SELECT * FROM transactions"
        if not include_superseded:
            sql += " WHERE superseded_by_transaction_id IS NULL"
        sql += " ORDER BY transaction_date, sequence, id"
        return [self._to_transaction(row) for row in self.connection.execute(sql).fetchall()]

    def mark_superseded(self, original_id: int, replacement_id: int) -> None:
        """Link a correcting record to the original; history is never deleted."""
        self.connection.execute(
            "UPDATE transactions SET superseded_by_transaction_id = ? WHERE id = ?",
            (replacement_id, original_id),
        )

    @staticmethod
    def _to_transaction(row: sqlite3.Row) -> ledger.Transaction:
        return ledger.Transaction(
            id=row["id"],
            account_id=row["account_id"],
            portfolio_id=row["portfolio_id"],
            transaction_type=row["transaction_type"],
            instrument_id=row["instrument_id"],
            symbol=row["symbol"],
            quantity=quantity(row["quantity"]),
            unit_price=money(row["unit_price"]),
            cash_amount=money(row["cash_amount"]),
            commission=money(row["commission"]),
            fees=money(row["fees"]),
            transaction_date=row["transaction_date"],
            external_reference=row["external_reference"],
            source=row["source"],
            note=row["note"],
            sequence=row["sequence"],
            supersedes_transaction_id=row["supersedes_transaction_id"],
            superseded_by_transaction_id=row["superseded_by_transaction_id"],
            created_at=row["created_at"],
        )


class PriceRepository(BaseRepository):
    def set_price(
        self,
        instrument_id: int,
        symbol: str,
        price,
        price_date: str,
        source: str = "manual",
        source_url: Optional[str] = None,
    ) -> PriceMark:
        symbol = ledger.normalize_symbol(symbol)
        close = money(price, "price")
        if close <= 0:
            raise ValueError("price must be > 0")
        price_date = ledger.normalize_date(price_date)
        now = utc_now()
        self.connection.execute(
            "INSERT INTO price_snapshots (instrument_id, symbol, price_date, close_price,"
            " source, source_url, retrieved_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (instrument_id, price_date, source) DO UPDATE SET"
            " close_price = excluded.close_price, source_url = excluded.source_url,"
            " retrieved_at = excluded.retrieved_at",
            (instrument_id, symbol, price_date, to_text(close), source, source_url, now),
        )
        return PriceMark(
            symbol=symbol, price=close, price_date=price_date, source=source, retrieved_at=now
        )

    def latest_mark(self, symbol: str, as_of: Optional[str] = None) -> Optional[PriceMark]:
        """Latest snapshot on or before ``as_of`` (documented pricing policy)."""
        symbol = ledger.normalize_symbol(symbol)
        if as_of:
            row = self.connection.execute(
                "SELECT * FROM price_snapshots WHERE symbol = ? AND price_date <= ?"
                " ORDER BY price_date DESC, id DESC LIMIT 1",
                (symbol, as_of),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT * FROM price_snapshots WHERE symbol = ?"
                " ORDER BY price_date DESC, id DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return PriceMark(
            symbol=row["symbol"],
            price=money(row["close_price"]),
            price_date=row["price_date"],
            source=row["source"],
            retrieved_at=row["retrieved_at"],
        )

    def marks_for(self, symbols: Iterable[str], as_of: Optional[str] = None) -> dict:
        marks = {}
        for symbol in symbols:
            mark = self.latest_mark(symbol, as_of)
            if mark is not None:
                marks[mark.symbol] = mark
        return marks

    def history(self, symbol: str, limit: int = 20) -> List[PriceMark]:
        rows = self.connection.execute(
            "SELECT * FROM price_snapshots WHERE symbol = ?"
            " ORDER BY price_date DESC, id DESC LIMIT ?",
            (ledger.normalize_symbol(symbol), limit),
        ).fetchall()
        return [
            PriceMark(
                symbol=row["symbol"],
                price=money(row["close_price"]),
                price_date=row["price_date"],
                source=row["source"],
                retrieved_at=row["retrieved_at"],
            )
            for row in rows
        ]


class ResearchRunRepository(BaseRepository):
    def create(
        self,
        run_id: str,
        question: str,
        status: str,
        contract_version: str,
        account_id: Optional[int] = None,
        scope_type: str = "ACCOUNT",
        scope_reference: Optional[str] = None,
        mode: str = "live",
        chair_provider: Optional[str] = None,
        artifact_dir: Optional[str] = None,
    ) -> dict:
        self.connection.execute(
            "INSERT INTO research_runs (id, created_at, question, scope_type, scope_reference,"
            " account_id, status, mode, chair_provider, contract_version, artifact_dir)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, utc_now(), question, scope_type, scope_reference, account_id,
                status, mode, chair_provider, contract_version, artifact_dir,
            ),
        )
        return self.get(run_id)

    def set_snapshot(self, run_id: str, snapshot: dict) -> None:
        self.connection.execute(
            "UPDATE research_runs SET portfolio_snapshot_json = ? WHERE id = ?",
            (_json(snapshot), run_id),
        )

    def set_status(self, run_id: str, status: str, error: Optional[str] = None,
                   completed: bool = False) -> None:
        self.connection.execute(
            "UPDATE research_runs SET status = ?, error = ?,"
            " completed_at = CASE WHEN ? THEN ? ELSE completed_at END WHERE id = ?",
            (status, error, 1 if completed else 0, utc_now(), run_id),
        )

    def get(self, run_id: str) -> dict:
        row = self.connection.execute(
            "SELECT * FROM research_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"research run {run_id} not found")
        record = dict(row)
        record["portfolio_snapshot"] = _unjson(record.pop("portfolio_snapshot_json"))
        return record

    def find(self, prefix: str) -> dict:
        """Resolve a run by full id or unique prefix."""
        rows = self.connection.execute(
            "SELECT id FROM research_runs WHERE id = ? OR id LIKE ? ORDER BY created_at DESC",
            (prefix, f"{prefix}%"),
        ).fetchall()
        if not rows:
            raise NotFoundError(f"research run {prefix!r} not found")
        exact = [row["id"] for row in rows if row["id"] == prefix]
        if exact:
            return self.get(exact[0])
        if len(rows) > 1:
            raise NotFoundError(f"run prefix {prefix!r} is ambiguous ({len(rows)} matches)")
        return self.get(rows[0]["id"])

    def list(self, limit: int = 20, account_id: Optional[int] = None) -> List[dict]:
        sql = "SELECT * FROM research_runs"
        params: list = []
        if account_id is not None:
            sql += " WHERE account_id = ?"
            params.append(account_id)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(sql, params).fetchall()
        result = []
        for row in rows:
            record = dict(row)
            record["portfolio_snapshot"] = _unjson(record.pop("portfolio_snapshot_json"))
            result.append(record)
        return result


class AgentRunRepository(BaseRepository):
    def record(
        self,
        research_run_id: str,
        provider: str,
        role: str,
        stage: str,
        status: str,
        input_hash: str,
        started_at: str,
        completed_at: Optional[str] = None,
        duration_seconds: Optional[str] = None,
        parsed_output: Optional[dict] = None,
        validation_errors: Optional[list] = None,
        raw_output_path: Optional[str] = None,
        exit_code: Optional[int] = None,
        stderr_excerpt: Optional[str] = None,
        failure_kind: Optional[str] = None,
        session_reference: Optional[str] = None,
        cost: Optional[str] = None,
        token_usage: Optional[dict] = None,
    ) -> int:
        cursor = self.connection.execute(
            "INSERT INTO agent_runs (research_run_id, agent_provider, agent_role, stage,"
            " session_reference, started_at, completed_at, duration_seconds, status, failure_kind,"
            " input_hash, raw_output_path, parsed_output_json, validation_errors, exit_code,"
            " stderr_excerpt, cost, token_usage)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                research_run_id, provider, role, stage, session_reference, started_at,
                completed_at, duration_seconds, status, failure_kind, input_hash,
                raw_output_path, _json(parsed_output), _json(validation_errors), exit_code,
                stderr_excerpt, cost, _json(token_usage),
            ),
        )
        return cursor.lastrowid

    def list_for_run(self, research_run_id: str) -> List[dict]:
        rows = self.connection.execute(
            "SELECT * FROM agent_runs WHERE research_run_id = ? ORDER BY id",
            (research_run_id,),
        ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["parsed_output"] = _unjson(record.pop("parsed_output_json"))
            record["validation_errors"] = _unjson(record["validation_errors"])
            record["token_usage"] = _unjson(record["token_usage"])
            records.append(record)
        return records


class DisagreementRepository(BaseRepository):
    def add(self, research_run_id: str, topic: str, codex_position: Optional[str],
            claude_position: Optional[str], materiality: str = "unknown",
            evidence: Optional[list] = None) -> int:
        cursor = self.connection.execute(
            "INSERT INTO disagreements (research_run_id, topic, codex_position, claude_position,"
            " materiality, resolution_status, evidence_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?)",
            (research_run_id, topic, codex_position, claude_position, materiality,
             _json(evidence), utc_now()),
        )
        return cursor.lastrowid

    def list_for_run(self, research_run_id: str) -> List[dict]:
        rows = self.connection.execute(
            "SELECT * FROM disagreements WHERE research_run_id = ? ORDER BY id",
            (research_run_id,),
        ).fetchall()
        return [dict(row) for row in rows]


class SimulationRepository(BaseRepository):
    def add(self, simulation_type: str, input_payload: dict, output_payload: dict,
            engine_version: str, account_id: Optional[int] = None,
            research_run_id: Optional[str] = None) -> int:
        cursor = self.connection.execute(
            "INSERT INTO simulations (research_run_id, account_id, simulation_type, input_json,"
            " output_json, engine_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (research_run_id, account_id, simulation_type, _json(input_payload),
             _json(output_payload), engine_version, utc_now()),
        )
        return cursor.lastrowid

    def list_for_run(self, research_run_id: str) -> List[dict]:
        rows = self.connection.execute(
            "SELECT * FROM simulations WHERE research_run_id = ? ORDER BY id", (research_run_id,)
        ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["input"] = _unjson(record.pop("input_json"))
            record["output"] = _unjson(record.pop("output_json"))
            records.append(record)
        return records


class RecommendationRepository(BaseRepository):
    def add(self, research_run_id: str, rank: int, action: str, symbol: Optional[str] = None,
            confidence: Optional[int] = None, data_quality_score: Optional[int] = None,
            current_weight_pct: Optional[str] = None, suggested_weight_pct: Optional[str] = None,
            thesis_summary: Optional[str] = None, counterargument: Optional[str] = None,
            invalidators: Optional[list] = None, risks: Optional[list] = None,
            portfolio_effect: Optional[dict] = None, evidence: Optional[list] = None,
            instrument_id: Optional[int] = None) -> int:
        cursor = self.connection.execute(
            "INSERT INTO recommendations (research_run_id, rank, instrument_id, symbol, action,"
            " confidence, data_quality_score, current_weight_pct, suggested_weight_pct,"
            " thesis_summary, counterargument, invalidators_json, risks_json,"
            " portfolio_effect_json, evidence_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (research_run_id, rank, instrument_id, symbol, action, confidence,
             data_quality_score, current_weight_pct, suggested_weight_pct, thesis_summary,
             counterargument, _json(invalidators), _json(risks), _json(portfolio_effect),
             _json(evidence), utc_now()),
        )
        return cursor.lastrowid

    def list_for_run(self, research_run_id: str) -> List[dict]:
        rows = self.connection.execute(
            "SELECT * FROM recommendations WHERE research_run_id = ? ORDER BY rank",
            (research_run_id,),
        ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            for key in ("invalidators", "risks", "portfolio_effect", "evidence"):
                record[key] = _unjson(record.pop(f"{key}_json"))
            records.append(record)
        return records

    def get(self, recommendation_id: int) -> dict:
        row = self.connection.execute(
            "SELECT * FROM recommendations WHERE id = ?", (recommendation_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"recommendation {recommendation_id} not found")
        return dict(row)


class DecisionRepository(BaseRepository):
    def add(self, research_run_id: str, decision: str, recommendation_id: Optional[int] = None,
            modified_action: Optional[str] = None, note: Optional[str] = None) -> int:
        cursor = self.connection.execute(
            "INSERT INTO human_decisions (research_run_id, recommendation_id, decision,"
            " modified_action, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (research_run_id, recommendation_id, decision, modified_action, note, utc_now()),
        )
        return cursor.lastrowid

    def get(self, decision_id: int) -> dict:
        row = self.connection.execute(
            "SELECT * FROM human_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"human decision {decision_id} not found")
        return dict(row)

    def list_for_run(self, research_run_id: str) -> List[dict]:
        rows = self.connection.execute(
            "SELECT * FROM human_decisions WHERE research_run_id = ? ORDER BY id",
            (research_run_id,),
        ).fetchall()
        return [dict(row) for row in rows]


class ExecutionRepository(BaseRepository):
    def add(self, transaction_id: int, human_decision_id: Optional[int] = None,
            note: Optional[str] = None) -> int:
        cursor = self.connection.execute(
            "INSERT INTO executions (human_decision_id, transaction_id, recorded_at, note)"
            " VALUES (?, ?, ?, ?)",
            (human_decision_id, transaction_id, utc_now(), note),
        )
        return cursor.lastrowid

    def list_for_decision(self, human_decision_id: int) -> List[dict]:
        rows = self.connection.execute(
            "SELECT * FROM executions WHERE human_decision_id = ? ORDER BY id",
            (human_decision_id,),
        ).fetchall()
        return [dict(row) for row in rows]


class AuditRepository(BaseRepository):
    def record(self, action: str, entity_type: str, entity_id=None, actor_type: str = "human",
               actor_reference: Optional[str] = None, before: Optional[dict] = None,
               after: Optional[dict] = None, reason: Optional[str] = None) -> int:
        cursor = self.connection.execute(
            "INSERT INTO audit_log (created_at, actor_type, actor_reference, action, entity_type,"
            " entity_id, before_json, after_json, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (utc_now(), actor_type, actor_reference, action, entity_type,
             None if entity_id is None else str(entity_id), _json(before), _json(after), reason),
        )
        return cursor.lastrowid

    def list(self, limit: int = 50, entity_type: Optional[str] = None) -> List[dict]:
        sql = "SELECT * FROM audit_log"
        params: list = []
        if entity_type:
            sql += " WHERE entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in self.connection.execute(sql, params).fetchall()]


class Repositories:
    """Container giving application services one handle to every repository."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.accounts = AccountRepository(connection)
        self.instruments = InstrumentRepository(connection)
        self.transactions = TransactionRepository(connection)
        self.prices = PriceRepository(connection)
        self.research_runs = ResearchRunRepository(connection)
        self.agent_runs = AgentRunRepository(connection)
        self.disagreements = DisagreementRepository(connection)
        self.simulations = SimulationRepository(connection)
        self.recommendations = RecommendationRepository(connection)
        self.decisions = DecisionRepository(connection)
        self.executions = ExecutionRepository(connection)
        self.audit = AuditRepository(connection)
