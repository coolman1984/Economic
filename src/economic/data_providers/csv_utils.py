"""Small shared CSV-reading helpers used by every file-based provider.

Kept separate so each provider file stays focused on its own domain shape.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Dict, List

from .base import ProviderError, SOURCE_UNAVAILABLE, EMPTY_RESULT, MALFORMED_SCHEMA


def read_rows(path: Path, required_columns: List[str]) -> List[Dict[str, str]]:
    """Return header-normalized rows from a CSV file, or raise ProviderError.

    Eager, not lazy: every check (missing file, empty file, bad header) runs
    immediately so a caller gets a ``ProviderError`` at the call site, not on
    first iteration. Files handled here are small, personal, local exports —
    materializing them is fine and removes a generator-laziness footgun.

    Column names are matched case-insensitively and stripped of whitespace.
    Extra columns are ignored; missing required columns fail the whole file
    (a schema problem, not a row problem — every row would be broken).
    """
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise ProviderError(SOURCE_UNAVAILABLE, f"file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ProviderError(SOURCE_UNAVAILABLE, f"cannot read {path}: {exc}") from exc

    if not text.strip():
        raise ProviderError(EMPTY_RESULT, f"{path} is empty")

    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise ProviderError(MALFORMED_SCHEMA, f"{path} has no header row")

    normalized_fields = {(f or "").strip().lower(): f for f in reader.fieldnames}
    missing = [c for c in required_columns if c.lower() not in normalized_fields]
    if missing:
        raise ProviderError(
            MALFORMED_SCHEMA,
            f"{path} is missing required column(s): {', '.join(missing)} "
            f"(found: {', '.join(reader.fieldnames)})",
        )

    rows = []
    for raw_row in reader:
        row = {}
        for key, value in raw_row.items():
            if key is None:
                continue
            row[key.strip().lower()] = (value or "").strip()
        rows.append(row)

    if not rows:
        raise ProviderError(EMPTY_RESULT, f"{path} has a header but no data rows")
    return rows


def file_hash(path: Path) -> str:
    """SHA-256 of a file's bytes, for integrity/provenance and dedup."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
