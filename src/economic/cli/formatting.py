"""Terminal rendering helpers. Presentation only — no calculations here."""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Sequence

from ..domain.money import display, to_text


def table(headers: Sequence[str], rows: Sequence[Sequence[str]],
          align_right: Optional[Sequence[int]] = None) -> str:
    """Render a simple fixed-width table."""
    align_right = set(align_right or [])
    columns = len(headers)
    widths = [len(str(header)) for header in headers]
    text_rows = []
    for row in rows:
        cells = [("" if cell is None else str(cell)) for cell in row]
        cells += [""] * (columns - len(cells))
        text_rows.append(cells)
        for index, cell in enumerate(cells[:columns]):
            widths[index] = max(widths[index], len(cell))

    def render(cells: Sequence[str]) -> str:
        parts = []
        for index in range(columns):
            cell = cells[index]
            parts.append(cell.rjust(widths[index]) if index in align_right
                         else cell.ljust(widths[index]))
        return "  ".join(parts).rstrip()

    lines = [render([str(h) for h in headers]),
             "  ".join("-" * width for width in widths)]
    lines.extend(render(cells) for cells in text_rows)
    return "\n".join(lines)


def heading(text: str) -> str:
    return f"\n{text}\n{'=' * len(text)}"


def money_cell(value: Optional[Decimal]) -> str:
    return "-" if value is None else display(value)


def qty_cell(value: Optional[Decimal]) -> str:
    return "-" if value is None else to_text(value)


def bullets(items: Sequence[str], indent: str = "  - ", limit: int = 12) -> List[str]:
    lines = [f"{indent}{item}" for item in list(items)[:limit]]
    remaining = len(items) - limit
    if remaining > 0:
        lines.append(f"{indent}... and {remaining} more")
    return lines
