"""Adapter behaviour: timeouts, failures, and provider output normalization."""

import json
import subprocess

import pytest

from economic.agents import base_adapter, contracts
from economic.agents.claude_adapter import ClaudeAdapter
from economic.agents.codex_adapter import CodexAdapter
from economic.agents.mock_adapter import MockAdapter

ANALYSIS = {
    "status": "complete",
    "portfolio_view": "fine",
    "recommendations": [{"symbol": "COMI", "action": "HOLD", "confidence": 50,
                         "thesis": "no change"}],
}


def test_missing_executable_is_reported_not_raised():
    adapter = CodexAdapter(command=["definitely-not-a-real-binary-xyz", "exec"])
    assert not adapter.is_available()
    response = adapter.run("prompt", contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
    assert not response.ok
    assert response.failure_kind == base_adapter.EXECUTABLE_MISSING


def test_disabled_adapter_never_launches_a_process():
    adapter = CodexAdapter(enabled=False)
    response = adapter.run("prompt", contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
    assert not response.ok and response.failure_kind == base_adapter.DISABLED


def test_timeout_is_enforced_and_normalized():
    # `sleep` ignores stdin and outlives the timeout.
    adapter = CodexAdapter(command=["sleep", "10"], timeout_seconds=1)
    response = adapter.run("prompt", contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
    assert not response.ok
    assert response.failure_kind == base_adapter.TIMEOUT
    assert "timed out" in response.stderr
    assert response.duration_seconds < 8


def test_non_zero_exit_is_captured_with_stderr():
    adapter = CodexAdapter(command=["sh", "-c", "echo boom >&2; exit 3"])
    response = adapter.run("prompt", contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
    assert not response.ok
    assert response.failure_kind == base_adapter.NON_ZERO_EXIT
    assert response.exit_code == 3
    assert "boom" in response.stderr


def test_empty_output_is_a_failure():
    adapter = CodexAdapter(command=["true"])
    response = adapter.run("prompt", contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
    assert not response.ok and response.failure_kind == base_adapter.EMPTY_OUTPUT


def test_malformed_output_is_rejected():
    adapter = CodexAdapter(command=["sh", "-c", "echo 'just some prose, no json'"])
    response = adapter.run("prompt", contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
    assert not response.ok and response.failure_kind == base_adapter.MALFORMED_OUTPUT
    assert response.data is None


def test_valid_json_that_breaks_the_contract_is_a_contract_violation():
    adapter = CodexAdapter(command=["sh", "-c", "echo '{\"status\": \"complete\"}'"])
    response = adapter.run("prompt", contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
    assert not response.ok
    assert response.failure_kind == base_adapter.CONTRACT_VIOLATION
    assert response.validation_errors


def test_prompt_is_delivered_on_stdin():
    adapter = CodexAdapter(command=["cat"])
    payload = json.dumps(ANALYSIS)
    response = adapter.run(payload, contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
    assert response.ok, response.validation_errors
    assert response.input_hash


def test_claude_envelope_is_unwrapped():
    adapter = ClaudeAdapter()
    envelope = json.dumps({"type": "result", "result": json.dumps(ANALYSIS)})
    assert json.loads(adapter.normalize_output(envelope))["status"] == "complete"


def test_claude_plain_output_passes_through():
    adapter = ClaudeAdapter()
    assert adapter.normalize_output("plain text") == "plain text"


def test_codex_event_stream_is_collapsed_to_messages():
    adapter = CodexAdapter()
    stream = "\n".join([
        json.dumps({"type": "started"}),
        json.dumps({"type": "agent_message", "text": json.dumps(ANALYSIS)}),
    ])
    assert "recommendations" in adapter.normalize_output(stream)


def test_doctor_reports_availability_without_running_the_model():
    report = CodexAdapter(command=["definitely-not-a-real-binary-xyz"]).doctor()
    assert report["provider"] == "codex"
    assert report["available"] is False
    assert report["path"] is None


def test_mock_adapter_produces_contract_valid_output_offline():
    adapter = MockAdapter("codex")
    response = adapter.run("no context here", contracts.INDEPENDENT_ANALYSIS,
                           "analyst", "STAGE")
    assert response.ok, response.validation_errors
    assert "MOCK" in response.data["portfolio_view"]


def test_mock_adapter_can_simulate_any_failure_state():
    for kind in (base_adapter.TIMEOUT, base_adapter.NON_ZERO_EXIT,
                 base_adapter.EXECUTABLE_MISSING):
        response = MockAdapter("codex", failure_kind=kind).run(
            "prompt", contracts.INDEPENDENT_ANALYSIS, "analyst", "STAGE")
        assert not response.ok and response.failure_kind == kind
