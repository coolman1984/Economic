"""Shared adapter boundary for external AI CLIs.

Everything provider-specific (executable name, flags, output envelope) lives in a
subclass. The orchestrator only ever sees an ``AgentResponse``.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from . import contracts, validators

# Normalized failure states (AGENT_ORCHESTRATION §12).
OK = "ok"
EXECUTABLE_MISSING = "executable_missing"
TIMEOUT = "timeout"
NON_ZERO_EXIT = "non_zero_exit"
EMPTY_OUTPUT = "empty_output"
MALFORMED_OUTPUT = "malformed_output"
CONTRACT_VIOLATION = "contract_violation"
DISABLED = "disabled"
LAUNCH_ERROR = "launch_error"

FAILURE_KINDS = (
    EXECUTABLE_MISSING, TIMEOUT, NON_ZERO_EXIT, EMPTY_OUTPUT, MALFORMED_OUTPUT,
    CONTRACT_VIOLATION, DISABLED, LAUNCH_ERROR,
)

STDERR_EXCERPT_LIMIT = 2000


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class AgentResponse:
    """One adapter invocation: process facts plus validated contract output."""

    provider: str
    role: str
    stage: str
    contract: str
    ok: bool
    failure_kind: Optional[str] = None
    data: Optional[dict] = None
    validation_errors: List[str] = field(default_factory=list)
    raw_output: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    input_hash: str = ""
    command: List[str] = field(default_factory=list)
    session_reference: Optional[str] = None

    @property
    def status(self) -> str:
        return "SUCCESS" if self.ok else "FAILED"

    @property
    def stderr_excerpt(self) -> str:
        return self.stderr[:STDERR_EXCERPT_LIMIT]

    def error_message(self) -> str:
        if self.ok:
            return ""
        parts = [self.failure_kind or "unknown_failure"]
        if self.validation_errors:
            parts.append("; ".join(self.validation_errors))
        elif self.stderr_excerpt.strip():
            parts.append(self.stderr_excerpt.strip().splitlines()[-1])
        return ": ".join(parts)


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    exit_code: Optional[int]
    failure_kind: Optional[str]


class AgentAdapter:
    """Base class for a provider CLI adapter."""

    provider = "base"

    def __init__(self, command: Optional[List[str]] = None, timeout_seconds: int = 300,
                 enabled: bool = True, cwd: Optional[str] = None):
        self.command = list(command or self.default_command())
        self.timeout_seconds = int(timeout_seconds)
        self.enabled = enabled
        self.cwd = cwd

    # ---- provider hooks -------------------------------------------------

    @classmethod
    def default_command(cls) -> List[str]:
        raise NotImplementedError

    @property
    def executable(self) -> str:
        return self.command[0] if self.command else ""

    def version_command(self) -> List[str]:
        return [self.executable, "--version"]

    def normalize_output(self, stdout: str) -> str:
        """Hook for providers that wrap the answer in an envelope."""
        return stdout

    # ---- capability checks ----------------------------------------------

    def executable_path(self) -> Optional[str]:
        return shutil.which(self.executable) if self.executable else None

    def is_available(self) -> bool:
        return self.enabled and self.executable_path() is not None

    def version(self) -> Optional[str]:
        """Best-effort version string; None when the CLI cannot be queried."""
        if self.executable_path() is None:
            return None
        try:
            completed = subprocess.run(
                self.version_command(), capture_output=True, text=True, timeout=20
            )
        except (OSError, subprocess.SubprocessError):
            return None
        output = (completed.stdout or completed.stderr or "").strip()
        return output.splitlines()[0] if output else None

    def doctor(self) -> dict:
        """Structured health report used by the ``doctor`` CLI command."""
        path = self.executable_path()
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "executable": self.executable,
            "path": path,
            "available": self.is_available(),
            "version": self.version() if path else None,
            "command": list(self.command),
            "timeout_seconds": self.timeout_seconds,
        }

    # ---- execution -------------------------------------------------------

    def _execute(self, prompt: str, timeout_seconds: Optional[int] = None) -> ProcessResult:
        """Run the CLI non-interactively with the prompt on stdin."""
        if not self.enabled:
            return ProcessResult("", f"{self.provider} adapter is disabled by configuration",
                                 None, DISABLED)
        if self.executable_path() is None:
            return ProcessResult("", f"{self.executable!r} was not found on PATH", None,
                                 EXECUTABLE_MISSING)
        timeout = int(timeout_seconds or self.timeout_seconds)
        try:
            completed = subprocess.run(
                self.command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.cwd,
            )
        except subprocess.TimeoutExpired:
            return ProcessResult("", f"timed out after {timeout}s", None, TIMEOUT)
        except OSError as exc:
            return ProcessResult("", f"failed to launch {self.executable}: {exc}", None,
                                 LAUNCH_ERROR)
        if completed.returncode != 0:
            return ProcessResult(completed.stdout or "", completed.stderr or "",
                                 completed.returncode, NON_ZERO_EXIT)
        return ProcessResult(completed.stdout or "", completed.stderr or "",
                             completed.returncode, None)

    def run(self, prompt: str, contract: str, role: str, stage: str,
            timeout_seconds: Optional[int] = None) -> AgentResponse:
        """Execute the provider and validate its output against ``contract``.

        A failure here can never touch portfolio state: this method has no
        database access and returns a plain result object.
        """
        started_at = _utc_now()
        started = time.monotonic()
        input_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        process = self._execute(prompt, timeout_seconds)
        duration = round(time.monotonic() - started, 3)

        response = AgentResponse(
            provider=self.provider,
            role=role,
            stage=stage,
            contract=contract,
            ok=False,
            failure_kind=process.failure_kind,
            raw_output=process.stdout,
            stderr=process.stderr,
            exit_code=process.exit_code,
            started_at=started_at,
            completed_at=_utc_now(),
            duration_seconds=duration,
            input_hash=input_hash,
            command=list(self.command),
        )

        if process.failure_kind is not None:
            return response

        normalized = self.normalize_output(process.stdout)
        if not normalized.strip():
            response.failure_kind = EMPTY_OUTPUT
            return response

        validation = validators.parse_and_validate(normalized, contract)
        if not validation.ok:
            response.failure_kind = (
                MALFORMED_OUTPUT
                if any("no JSON object" in error for error in validation.errors)
                else CONTRACT_VIOLATION
            )
            response.validation_errors = validation.errors
            return response

        response.ok = True
        response.failure_kind = None
        response.data = validation.data
        return response
