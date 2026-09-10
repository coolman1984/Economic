"""Turn raw CLI output into a validated contract payload.

Provider CLIs wrap answers differently (plain text, fenced code, a JSON envelope
with the answer in a ``result`` field, or a stream of JSON lines). This module
tolerates those *shapes* while refusing to treat invalid JSON as valid analysis.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple

from . import contracts

FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)

# Keys used by provider envelopes to carry the assistant's final text.
ENVELOPE_TEXT_KEYS = ("result", "response", "text", "content", "message", "output", "last_message")


class ExtractionError(ValueError):
    """No JSON object could be recovered from the provider output."""


def _balanced_objects(text: str) -> List[str]:
    """Yield every top-level ``{...}`` block, respecting strings and escapes."""
    blocks: List[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    blocks.append(text[start : index + 1])
                    start = -1
    return blocks


def _candidate_payloads(text: str) -> List[Any]:
    """Every JSON object we can parse out of ``text``, most specific first."""
    candidates: List[Any] = []

    def try_load(raw: str) -> None:
        raw = raw.strip()
        if not raw:
            return
        try:
            candidates.append(json.loads(raw))
        except json.JSONDecodeError:
            return

    try_load(text)
    for fenced in FENCE_RE.findall(text):
        try_load(fenced)
    for block in _balanced_objects(text):
        try_load(block)
    # JSON-lines streams: keep each parsable line too.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try_load(stripped)
    return candidates


def _unwrap(payload: Any, depth: int = 0) -> List[Any]:
    """Expand a provider envelope into the payloads it may be carrying."""
    if depth > 4 or not isinstance(payload, dict):
        return [payload]
    results = [payload]
    for key in ENVELOPE_TEXT_KEYS:
        inner = payload.get(key)
        if isinstance(inner, str):
            for candidate in _candidate_payloads(inner):
                results.extend(_unwrap(candidate, depth + 1))
        elif isinstance(inner, dict):
            results.extend(_unwrap(inner, depth + 1))
        elif isinstance(inner, list):
            for item in inner:
                if isinstance(item, dict):
                    results.extend(_unwrap(item, depth + 1))
                elif isinstance(item, str):
                    for candidate in _candidate_payloads(item):
                        results.extend(_unwrap(candidate, depth + 1))
    return results


def extract_payloads(raw_output: str) -> List[Any]:
    """All plausible contract payloads contained in raw provider output."""
    if not raw_output or not raw_output.strip():
        return []
    payloads: List[Any] = []
    for candidate in _candidate_payloads(raw_output):
        for unwrapped in _unwrap(candidate):
            if unwrapped not in payloads:
                payloads.append(unwrapped)
    return payloads


def parse_and_validate(raw_output: str, contract: str) -> contracts.ValidationResult:
    """Recover a payload from ``raw_output`` and validate it against ``contract``.

    The first payload that satisfies the contract wins. If none does, the result
    carries the errors from the closest attempt so failures stay diagnosable.
    """
    payloads = extract_payloads(raw_output)
    if not payloads:
        return contracts.ValidationResult(
            contract, False, None, ["no JSON object found in provider output"]
        )

    best: Optional[contracts.ValidationResult] = None
    for payload in payloads:
        result = contracts.validate(contract, payload)
        if result.ok:
            return result
        if not isinstance(payload, dict):
            continue
        if best is None or len(result.errors) < len(best.errors):
            best = result

    if best is None:
        return contracts.ValidationResult(
            contract, False, None, ["provider output contained no JSON object"]
        )
    return best
