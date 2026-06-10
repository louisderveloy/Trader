"""
Unit tests for the RunSupervisor command validation and argv building.

These cover the supervisor's independent allowlist (defense in depth): the layer
that re-validates run_commands payloads before any subprocess is spawned, so a
malicious or malformed payload cannot inject CLI flags (security review #1/#16).
"""

import pytest

from runs.supervisor import (
    CommandValidationError,
    _build_argv,
    _validate_start_params,
)


# ==========================================
# _validate_start_params
# ==========================================


def _backtest_params(**overrides):
    params = {
        "run_type": "backtest",
        "symbol": "BTCUSDC",
        "timeframe": "15m",
        "start_date": "2024-01-01",
        "end_date": "2024-06-01",
        "initial_capital": 10000.0,
        "engine": "vectorbt",
        "save": True,
    }
    params.update(overrides)
    return params


def test_valid_backtest_params_pass():
    clean = _validate_start_params(_backtest_params())
    assert clean["run_type"] == "backtest"
    assert clean["symbol"] == "BTCUSDC"
    assert clean["save"] is True


def test_valid_paper_params_pass():
    clean = _validate_start_params({"run_type": "paper", "symbol": "BTCUSDC", "timeframe": "1h"})
    assert clean == {"run_type": "paper", "symbol": "BTCUSDC", "timeframe": "1h"}


def test_valid_live_params_require_boolean_testnet():
    clean = _validate_start_params(
        {"run_type": "live", "symbol": "BTCUSDC", "timeframe": "15m", "testnet": True}
    )
    assert clean["testnet"] is True


def test_usdt_symbol_rejected():
    # USDT is not authorised (EU); only USDC pairs are allowed.
    with pytest.raises(CommandValidationError):
        _validate_start_params(_backtest_params(symbol="BTCUSDT"))


def test_lowercase_symbol_normalized():
    # Symbols are case-insensitive: lowercase is upper-cased then allowlisted.
    clean = _validate_start_params(_backtest_params(symbol="btcusdc"))
    assert clean["symbol"] == "BTCUSDC"


def test_flag_like_symbol_rejected():
    # Argument-injection attempt: a value that argparse would read as a flag.
    # Membership in the configured allowlist makes this impossible.
    with pytest.raises(CommandValidationError):
        _validate_start_params(_backtest_params(symbol="--confirm"))


def test_symbol_not_in_allowlist_rejected():
    # Well-formed USDC pair that is not in AVAILABLE_SYMBOLS (default BTCUSDC).
    with pytest.raises(CommandValidationError):
        _validate_start_params(_backtest_params(symbol="ETHUSDC"))


def test_available_symbols_env_extends_allowlist(monkeypatch):
    monkeypatch.setenv("AVAILABLE_SYMBOLS", "BTCUSDC,ETHUSDC")
    clean = _validate_start_params(_backtest_params(symbol="ETHUSDC"))
    assert clean["symbol"] == "ETHUSDC"


def test_invalid_timeframe_rejected():
    with pytest.raises(CommandValidationError):
        _validate_start_params(_backtest_params(timeframe="7m"))


def test_invalid_run_type_rejected():
    with pytest.raises(CommandValidationError):
        _validate_start_params({"run_type": "optimize", "symbol": "BTCUSDC", "timeframe": "15m"})


def test_invalid_engine_rejected():
    with pytest.raises(CommandValidationError):
        _validate_start_params(_backtest_params(engine="rm -rf"))


def test_bad_dates_rejected():
    with pytest.raises(CommandValidationError):
        _validate_start_params(_backtest_params(start_date="2024/01/01"))


def test_bad_weights_set_id_rejected():
    with pytest.raises(CommandValidationError):
        _validate_start_params(_backtest_params(weights_set_id="not-a-uuid"))


def test_valid_weights_set_id_accepted():
    clean = _validate_start_params(
        _backtest_params(weights_set_id="123e4567-e89b-12d3-a456-426614174000")
    )
    assert clean["weights_set_id"] == "123e4567-e89b-12d3-a456-426614174000"


def test_negative_capital_rejected():
    with pytest.raises(CommandValidationError):
        _validate_start_params(_backtest_params(initial_capital=-5))


def test_live_without_testnet_rejected():
    with pytest.raises(CommandValidationError):
        _validate_start_params({"run_type": "live", "symbol": "BTCUSDC", "timeframe": "15m"})


# ==========================================
# _build_argv
# ==========================================


def test_build_argv_backtest_no_shell_and_has_run_id():
    clean = _validate_start_params(_backtest_params())
    argv = _build_argv(42, clean)
    assert argv[1:4] == ["-m", "main", "backtest"]
    assert "--run-id" in argv and "42" in argv
    assert "--save" in argv
    assert "--start-date" in argv and "2024-01-01" in argv
    # Symbol is passed as an exact, separate argv entry (never interpolated).
    assert "--symbol" in argv and "BTCUSDC" in argv


def test_build_argv_live_testnet_includes_flags():
    clean = _validate_start_params(
        {"run_type": "live", "symbol": "BTCUSDC", "timeframe": "15m", "testnet": True}
    )
    argv = _build_argv(7, clean)
    assert "--testnet" in argv
    # No interactive TTY: always pre-confirm (bot only honours it on mainnet).
    assert "--confirm" in argv


def test_build_argv_live_mainnet_confirms_without_testnet_flag():
    clean = _validate_start_params(
        {"run_type": "live", "symbol": "BTCUSDC", "timeframe": "15m", "testnet": False}
    )
    argv = _build_argv(8, clean)
    assert "--testnet" not in argv
    assert "--confirm" in argv


def test_build_argv_paper_minimal():
    clean = _validate_start_params({"run_type": "paper", "symbol": "BTCUSDC", "timeframe": "15m"})
    argv = _build_argv(9, clean)
    assert "paper" in argv
    assert "--run-id" in argv and "9" in argv
    assert "--testnet" not in argv
    assert "--confirm" not in argv
