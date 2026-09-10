"""Codex CLI adapter — the only module that knows Codex command details."""

from __future__ import annotations

import json
from typing import List

from .base_adapter import AgentAdapter


class CodexAdapter(AgentAdapter):
    """Non-interactive Codex CLI execution with the prompt supplied on stdin."""

    provider = "codex"

    @classmethod
    def default_command(cls) -> List[str]:
        # `codex exec` is the non-interactive entry point; `-` reads the prompt
        # from stdin. Overridable via config so a CLI change needs no code edit.
        return ["codex", "exec", "--skip-git-repo-check", "-"]

    def normalize_output(self, stdout: str) -> str:
        """Collapse a Codex JSONL event stream down to its assistant messages.

        Plain (non-JSONL) output is returned unchanged; the shared validator
        handles fenced blocks and embedded objects.
        """
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return stdout

        messages: List[str] = []
        saw_event = False
        for line in lines:
            if not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            saw_event = True
            for key in ("last_agent_message", "agent_message", "text", "message", "content"):
                value = event.get(key)
                if isinstance(value, str) and value.strip():
                    messages.append(value)
                    break
            else:
                message = event.get("msg")
                if isinstance(message, dict):
                    for key in ("message", "text", "last_agent_message"):
                        value = message.get(key)
                        if isinstance(value, str) and value.strip():
                            messages.append(value)
                            break

        if saw_event and messages:
            # Later messages are more likely to hold the final answer.
            return "\n".join(reversed(messages))
        return stdout
