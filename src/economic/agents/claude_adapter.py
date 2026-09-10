"""Claude Code CLI adapter — the only module that knows Claude command details."""

from __future__ import annotations

import json
from typing import List

from .base_adapter import AgentAdapter


class ClaudeAdapter(AgentAdapter):
    """Non-interactive Claude Code execution using its structured output mode."""

    provider = "claude"

    @classmethod
    def default_command(cls) -> List[str]:
        # `-p` is print/non-interactive mode; the JSON envelope carries the
        # assistant's answer in `result`. Overridable via config.
        return ["claude", "-p", "--output-format", "json"]

    def normalize_output(self, stdout: str) -> str:
        """Unwrap Claude's JSON envelope when present, otherwise pass through."""
        text = stdout.strip()
        if not text:
            return stdout
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError:
            return stdout
        if isinstance(envelope, dict):
            for key in ("result", "response", "text", "content"):
                value = envelope.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return stdout
