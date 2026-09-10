"""CLI smoke tests: the commands a user actually types."""

import json

import pytest

from economic.cli.main import main


@pytest.fixture
def run(home, capsys, monkeypatch):
    monkeypatch.setenv("ECONOMIC_MOCK", "1")

    def invoke(*argv, expect: int = 0):
        code = main(["--home", str(home), *argv])
        captured = capsys.readouterr()
        assert code == expect, f"{argv} -> exit {code}\n{captured.out}\n{captured.err}"
        return captured

    return invoke


def json_run(run, *argv, expect: int = 0):
    return json.loads(run(*argv, "--json", expect=expect).out)


def test_init_and_doctor(run):
    assert "Economic initialized" in run("init").out
    doctor = json_run(run, "doctor")
    assert doctor["database"]["integrity"] == "ok"
    assert {agent["provider"] for agent in doctor["agents"]} == {"codex", "claude"}


def test_the_documented_walkthrough(run):
    run("init")
    run("account", "add", "--name", "Main", "--broker", "EFG")
    run("cash", "deposit", "--account", "Main", "--amount", "100000",
        "--date", "2026-01-01")
    run("trade", "buy", "--account", "Main", "--symbol", "COMI", "--qty", "100",
        "--price", "50", "--commission", "10", "--date", "2026-01-02")
    run("trade", "buy", "--account", "Main", "--symbol", "COMI", "--qty", "100",
        "--price", "60", "--commission", "10", "--date", "2026-01-03")
    run("trade", "sell", "--account", "Main", "--symbol", "COMI", "--qty", "100",
        "--price", "70", "--commission", "10", "--date", "2026-01-04")
    run("price", "set", "--symbol", "COMI", "--price", "75", "--date", "2026-01-05")

    portfolio = json_run(run, "portfolio", "show", "--account", "Main",
                         "--as-of", "2026-01-05")
    position = portfolio["positions"][0]
    assert position["quantity"] == "100"
    assert position["average_cost"] == "55.1"
    assert position["realized_pnl"] == "1480"
    assert position["unrealized_pnl"] == "1990"
    assert portfolio["cash"] == "95970"
    assert portfolio["total_equity"] == "103470"


def test_oversell_is_rejected_at_the_cli(run):
    run("init")
    run("account", "add", "--name", "Main")
    run("cash", "deposit", "--account", "Main", "--amount", "10000")
    run("trade", "buy", "--account", "Main", "--symbol", "COMI", "--qty", "10", "--price", "50")
    captured = run("trade", "sell", "--account", "Main", "--symbol", "COMI",
                   "--qty", "11", "--price", "50", expect=1)
    assert "only 10 held" in captured.err


def test_simulation_does_not_change_the_ledger(run):
    run("init")
    run("account", "add", "--name", "Main")
    run("cash", "deposit", "--account", "Main", "--amount", "100000")
    run("trade", "buy", "--account", "Main", "--symbol", "COMI", "--qty", "100", "--price", "50")
    run("price", "set", "--symbol", "COMI", "--price", "60")

    before = json_run(run, "portfolio", "show", "--account", "Main")
    result = json_run(run, "simulate", "--account", "Main", "--action", "BUY",
                      "--symbol", "COMI", "--qty", "100", "--price", "60")
    after = json_run(run, "portfolio", "show", "--account", "Main")

    assert result["ok"] is True
    assert result["after"]["quantity"] == "200"
    assert before == after


def test_committee_decide_and_history_round_trip(run):
    run("init")
    run("account", "add", "--name", "Main")
    run("cash", "deposit", "--account", "Main", "--amount", "100000")
    run("trade", "buy", "--account", "Main", "--symbol", "COMI", "--qty", "100", "--price", "50")
    run("price", "set", "--symbol", "COMI", "--price", "60")

    committee = json_run(run, "committee", "--question", "What now?",
                         "--account", "Main", "--mock")
    run_id = committee["run"]["id"]
    assert committee["run"]["status"] == "READY_FOR_HUMAN"

    history = json_run(run, "history")
    assert history[0]["id"] == run_id

    decision = json_run(run, "decide", "--run", run_id[:18], "--decision", "APPROVE")
    assert decision["decision"] == "APPROVE"
    assert decision["created_transaction"] is False

    reloaded = json_run(run, "run", "show", run_id)
    assert reloaded["run"]["status"] == "HUMAN_APPROVED"
    assert reloaded["decisions"][0]["decision"] == "APPROVE"

    audit = json_run(run, "audit")
    assert any(entry["action"] == "HUMAN_DECISION" for entry in audit)


def test_doctor_warns_when_only_one_provider_is_available(run, monkeypatch):
    run("init")
    report = json_run(run, "doctor", "--mock")
    assert report["committee_would_be_degraded"] is False   # both mocks available
    assert report["min_data_quality_for_action"] == 50


def test_the_cli_labels_a_degraded_committee(run, home, monkeypatch):
    """A user reading the terminal must see that no second agent checked this."""
    from economic.agents import base_adapter
    from economic.agents.mock_adapter import MockAdapter
    from economic.application import research_service as research_module

    monkeypatch.setattr(research_module, "build_adapters", lambda *a, **k: {
        "codex": MockAdapter("codex", failure_kind=base_adapter.TIMEOUT),
        "claude": MockAdapter("claude")})

    run("init")
    run("account", "add", "--name", "Main")
    run("cash", "deposit", "--account", "Main", "--amount", "100000")
    run("trade", "buy", "--account", "Main", "--symbol", "COMI", "--qty", "100", "--price", "50")
    run("price", "set", "--symbol", "COMI", "--price", "60")

    output = run("committee", "--question", "What now?", "--account", "Main", "--mock").out
    assert "DEGRADED COMMITTEE" in output
    assert "NOT a full dual-agent review" in output
    assert "agreement not measurable" in output

    listing = run("history").out
    assert "DEGRADED" in listing

    run_id = json_run(run, "history")[0]["id"]
    decided = run("decide", "--run", run_id, "--decision", "HOLD").out
    assert "DEGRADED committee" in decided


def test_demo_seed_uses_clearly_fictional_symbols(run):
    run("init")
    summary = json_run(run, "demo", "seed")
    assert summary["transactions"] > 0
    instruments = json_run(run, "instrument", "list")
    assert all(item["symbol"].startswith("ZZDEMO") for item in instruments)
    assert all("fictional" in (item["name"] or "") for item in instruments)


def test_market_import_and_trace_round_trip(run, tmp_path):
    run("init")
    instruments = tmp_path / "instruments.csv"
    instruments.write_text(
        "symbol,name,sector,isin,source_name,source_url\n"
        "COMI,Commercial International Bank (Egypt) S.A.E.,Banks,EGS60121C018,"
        "stockanalysis.com,https://stockanalysis.com/quote/egx/COMI/\n"
    )
    prices = tmp_path / "prices.csv"
    prices.write_text(
        "symbol,date,close,source_name,source_url\n"
        "COMI,2026-09-08,74.25,EGX prices page,https://www.egx.com.eg/en/prices.aspx\n"
    )

    r1 = json_run(run, "market", "import-instruments", "--file", str(instruments))
    assert r1["ok"] is True and r1["inserted"] == 1
    r2 = json_run(run, "market", "import-prices", "--file", str(prices))
    assert r2["ok"] is True and r2["inserted"] == 1

    trace = json_run(run, "market", "trace", "--symbol", "COMI")
    assert trace["instrument"]["isin"] == "EGS60121C018"
    assert trace["prices"][0]["source"] == "EGX prices page"

    history = json_run(run, "market", "history")
    assert len(history) == 2
    assert all(entry["ok"] for entry in history)


def test_market_import_failure_is_a_clean_error_not_a_traceback(run, tmp_path):
    run("init")
    captured = run("market", "import-prices", "--file", str(tmp_path / "missing.csv"),
                   expect=1)
    assert "file not found" in captured.out
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err


def test_unknown_account_reports_a_clear_error(run):
    run("init")
    captured = run("portfolio", "show", "--account", "Nope", expect=1)
    assert "not found" in captured.err
