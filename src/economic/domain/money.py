"""Exact decimal arithmetic helpers.

Financial truth is deterministic (ADR-002), so every amount and quantity is a
``Decimal`` parsed from a string. Floats never touch accounting values.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")

MONEY_PLACES = Decimal("0.0001")
QTY_PLACES = Decimal("0.00000001")
DISPLAY_PLACES = Decimal("0.01")


class AmountError(ValueError):
    """Raised when a value cannot be interpreted as an exact decimal amount."""


def to_decimal(value, field: str = "value") -> Decimal:
    """Parse ``value`` into a Decimal, rejecting floats and non-finite input."""
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, bool):
        raise AmountError(f"{field} must be a number, got a boolean")
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            raise AmountError(f"{field} must not be empty")
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:
            raise AmountError(f"{field} is not a valid number: {value!r}") from exc
    elif isinstance(value, float):
        # A float has already lost precision; require the caller to pass a string.
        raise AmountError(f"{field} must be given as a string or Decimal, not a float")
    else:
        raise AmountError(f"{field} has unsupported type {type(value).__name__}")

    if not parsed.is_finite():
        raise AmountError(f"{field} must be a finite number")
    return parsed


def money(value, field: str = "amount") -> Decimal:
    """Parse and normalize a cash amount to the stored money precision."""
    return to_decimal(value, field).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def quantity(value, field: str = "quantity") -> Decimal:
    """Parse and normalize an instrument quantity to the stored quantity precision."""
    return to_decimal(value, field).quantize(QTY_PLACES, rounding=ROUND_HALF_UP)


def normalize(value: Decimal) -> Decimal:
    """Trim trailing zeros without switching to scientific notation."""
    normalized = value.normalize()
    sign, digits, exponent = normalized.as_tuple()
    if isinstance(exponent, int) and exponent > 0:
        normalized = normalized.quantize(Decimal(1))
    return normalized


def to_text(value: Decimal) -> str:
    """Serialize a Decimal for SQLite/JSON storage (exact, human readable)."""
    return format(normalize(value), "f")


def display(value: Decimal, places: Decimal = DISPLAY_PLACES) -> str:
    """Format a Decimal for terminal output."""
    return format(value.quantize(places, rounding=ROUND_HALF_UP), "f")


def pct(part: Decimal, whole: Decimal) -> Decimal:
    """Percentage of ``part`` within ``whole``; zero when ``whole`` is zero."""
    if whole == 0:
        return ZERO
    return (part / whole * Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
