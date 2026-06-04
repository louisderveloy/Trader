"""
Unit tests for backtesting types.

Tests all dataclasses, enums, and type validation in the backtesting module.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from backtesting.types import (
    BacktestMode,
    OrderType,
    TradeDirection,
    BacktestConfig,
    BacktestTrade,
    BacktestMetrics,
    BacktestResult,
    CoherenceResult
)


class TestEnums:
    """Test enum definitions."""

    def test_backtest_mode_values(self):
        """Test BacktestMode enum values."""
        assert BacktestMode.VECTORBT == "vectorbt"
        assert BacktestMode.EVENT_DRIVEN == "event_driven"

    def test_order_type_values(self):
        """Test OrderType enum values."""
        assert OrderType.LIMIT == "limit"
        assert OrderType.MARKET == "market"

    def test_trade_direction_values(self):
        """Test TradeDirection enum values."""
        assert TradeDirection.LONG == "long"
        assert TradeDirection.SHORT == "short"


class TestBacktestConfig:
    """Test BacktestConfig dataclass."""

    def test_minimal_config(self):
        """Test creating config with minimal required fields."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 12, 31, tzinfo=timezone.utc)

        config = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=Decimal("10000")
        )

        assert config.start_date == start
        assert config.end_date == end
        assert config.initial_capital == Decimal("10000")
        assert config.symbol == "BTC/USDT"
        assert config.timeframe == "15m"
        assert config.commission_rate == Decimal("0.001")

    def test_full_config(self):
        """Test creating config with all fields."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 12, 31, tzinfo=timezone.utc)
        weights_id = uuid4()

        config = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=Decimal("10000"),
            max_position_size=Decimal("1000"),
            symbol="ETH/USDT",
            timeframe="1h",
            commission_rate=Decimal("0.002"),
            slippage_pct=Decimal("0.003"),
            limit_order_timeout_minutes=60,
            max_slippage_pct=Decimal("0.005"),
            strategy_params={"entry_threshold": 0.5},
            weights_set_id=weights_id,
            weights={"ema": 0.2, "macd": 0.3}
        )

        assert config.symbol == "ETH/USDT"
        assert config.timeframe == "1h"
        assert config.limit_order_timeout_minutes == 60
        assert config.weights_set_id == weights_id

    def test_config_to_dict(self):
        """Test converting config to dict."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 12, 31, tzinfo=timezone.utc)

        config = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=Decimal("10000")
        )

        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict["start_date"] == start.isoformat()
        assert config_dict["end_date"] == end.isoformat()
        assert config_dict["initial_capital"] == 10000.0
        assert config_dict["symbol"] == "BTC/USDT"


class TestBacktestTrade:
    """Test BacktestTrade dataclass."""

    def test_minimal_trade(self):
        """Test creating trade with required fields."""
        entry_time = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)

        trade = BacktestTrade(
            trade_number=1,
            direction=TradeDirection.LONG,
            entry_time=entry_time,
            entry_price=Decimal("42000"),
            entry_order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            exit_time=exit_time,
            exit_price=Decimal("42500"),
            exit_order_type=OrderType.MARKET,
            exit_reason="take_profit"
        )

        assert trade.trade_number == 1
        assert trade.direction == TradeDirection.LONG
        assert trade.entry_price == Decimal("42000")
        assert trade.exit_price == Decimal("42500")
        assert trade.quantity == Decimal("0.1")

    def test_trade_duration_calculation(self):
        """Test automatic duration calculation."""
        entry_time = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 11, 30, tzinfo=timezone.utc)  # 90 minutes later

        trade = BacktestTrade(
            trade_number=1,
            direction=TradeDirection.LONG,
            entry_time=entry_time,
            entry_price=Decimal("42000"),
            entry_order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            exit_time=exit_time,
            exit_price=Decimal("42500"),
            exit_order_type=OrderType.MARKET,
            exit_reason="take_profit"
        )

        assert trade.duration_minutes == 90

    def test_trade_with_stops(self):
        """Test trade with stop-loss and take-profit."""
        entry_time = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)

        trade = BacktestTrade(
            trade_number=1,
            direction=TradeDirection.LONG,
            entry_time=entry_time,
            entry_price=Decimal("42000"),
            entry_order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            exit_time=exit_time,
            exit_price=Decimal("42500"),
            exit_order_type=OrderType.MARKET,
            exit_reason="take_profit",
            stop_loss_price=Decimal("41500"),
            take_profit_price=Decimal("42500")
        )

        assert trade.stop_loss_price == Decimal("41500")
        assert trade.take_profit_price == Decimal("42500")

    def test_trade_pnl_fields(self):
        """Test trade P&L fields."""
        entry_time = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)

        trade = BacktestTrade(
            trade_number=1,
            direction=TradeDirection.LONG,
            entry_time=entry_time,
            entry_price=Decimal("42000"),
            entry_order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            exit_time=exit_time,
            exit_price=Decimal("42500"),
            exit_order_type=OrderType.MARKET,
            exit_reason="take_profit",
            gross_pnl=Decimal("50"),
            commission_paid=Decimal("8.5"),
            slippage_cost=Decimal("1.5"),
            net_pnl=Decimal("40"),
            return_pct=Decimal("0.95")
        )

        assert trade.gross_pnl == Decimal("50")
        assert trade.commission_paid == Decimal("8.5")
        assert trade.slippage_cost == Decimal("1.5")
        assert trade.net_pnl == Decimal("40")
        assert trade.return_pct == Decimal("0.95")

    def test_trade_to_dict(self):
        """Test converting trade to dict."""
        entry_time = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)

        trade = BacktestTrade(
            trade_number=1,
            direction=TradeDirection.LONG,
            entry_time=entry_time,
            entry_price=Decimal("42000"),
            entry_order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            exit_time=exit_time,
            exit_price=Decimal("42500"),
            exit_order_type=OrderType.MARKET,
            exit_reason="take_profit"
        )

        trade_dict = trade.to_dict()

        assert isinstance(trade_dict, dict)
        assert trade_dict["trade_number"] == 1
        assert trade_dict["direction"] == "long"
        assert trade_dict["entry_price"] == 42000.0
        assert trade_dict["exit_price"] == 42500.0


class TestBacktestMetrics:
    """Test BacktestMetrics dataclass."""

    def test_default_metrics(self):
        """Test creating metrics with defaults."""
        metrics = BacktestMetrics()

        assert metrics.total_return == Decimal("0")
        assert metrics.total_pnl == Decimal("0")
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.sharpe_ratio == 0.0

    def test_full_metrics(self):
        """Test creating metrics with all fields."""
        metrics = BacktestMetrics(
            total_return=Decimal("15.5"),
            total_pnl=Decimal("1550"),
            final_capital=Decimal("11550"),
            total_trades=50,
            winning_trades=30,
            losing_trades=20,
            win_rate=60.0,
            avg_win=Decimal("75"),
            avg_loss=Decimal("-30"),
            largest_win=Decimal("200"),
            largest_loss=Decimal("-80"),
            profit_factor=1.5,
            sharpe_ratio=1.8,
            sortino_ratio=2.1,
            max_drawdown=Decimal("500"),
            max_drawdown_pct=5.0,
            calmar_ratio=3.1,
            exposure_time_pct=45.0,
            avg_trade_duration_minutes=120,
            buy_and_hold_return=Decimal("12.0"),
            buy_and_hold_pnl=Decimal("1200"),
            excess_return=Decimal("3.5")
        )

        assert metrics.total_trades == 50
        assert metrics.win_rate == 60.0
        assert metrics.sharpe_ratio == 1.8
        assert metrics.profit_factor == 1.5

    def test_metrics_to_dict(self):
        """Test converting metrics to dict."""
        metrics = BacktestMetrics(
            total_return=Decimal("15.5"),
            total_pnl=Decimal("1550"),
            total_trades=50
        )

        metrics_dict = metrics.to_dict()

        assert isinstance(metrics_dict, dict)
        assert metrics_dict["total_return"] == 15.5
        assert metrics_dict["total_pnl"] == 1550.0
        assert metrics_dict["total_trades"] == 50


class TestBacktestResult:
    """Test BacktestResult dataclass."""

    def test_minimal_result(self):
        """Test creating result with defaults."""
        result = BacktestResult()

        assert result.mode == BacktestMode.VECTORBT
        assert result.success is True
        assert result.trades == []
        assert result.metrics is None

    def test_full_result(self):
        """Test creating result with all fields."""
        run_id = uuid4()
        now = datetime.now(timezone.utc)
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )
        metrics = BacktestMetrics(total_trades=10)

        result = BacktestResult(
            run_id=run_id,
            mode=BacktestMode.EVENT_DRIVEN,
            timestamp=now,
            config=config,
            trades=[],
            metrics=metrics,
            success=True,
            error_message=None,
            execution_time_seconds=123.45,
            candles_processed=1000
        )

        assert result.run_id == run_id
        assert result.mode == BacktestMode.EVENT_DRIVEN
        assert result.config == config
        assert result.metrics == metrics
        assert result.execution_time_seconds == 123.45
        assert result.candles_processed == 1000

    def test_failed_result(self):
        """Test creating a failed result."""
        result = BacktestResult(
            success=False,
            error_message="Database connection failed"
        )

        assert result.success is False
        assert result.error_message == "Database connection failed"

    def test_result_to_dict(self):
        """Test converting result to dict."""
        result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            success=True,
            candles_processed=1000
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["mode"] == "vectorbt"
        assert result_dict["success"] is True
        assert result_dict["candles_processed"] == 1000


class TestCoherenceResult:
    """Test CoherenceResult dataclass."""

    def test_coherent_result(self):
        """Test creating coherent result."""
        vbt_result = BacktestResult(mode=BacktestMode.VECTORBT)
        ed_result = BacktestResult(mode=BacktestMode.EVENT_DRIVEN)

        coherence = CoherenceResult(
            vectorbt_result=vbt_result,
            event_driven_result=ed_result,
            pnl_difference_pct=1.5,
            is_coherent=True,
            tolerance_pct=2.0
        )

        assert coherence.is_coherent is True
        assert coherence.pnl_difference_pct == 1.5
        assert coherence.tolerance_pct == 2.0

    def test_incoherent_result(self):
        """Test creating incoherent result."""
        vbt_result = BacktestResult(mode=BacktestMode.VECTORBT)
        ed_result = BacktestResult(mode=BacktestMode.EVENT_DRIVEN)

        coherence = CoherenceResult(
            vectorbt_result=vbt_result,
            event_driven_result=ed_result,
            pnl_difference_pct=5.2,
            is_coherent=False,
            tolerance_pct=2.0,
            differences={"pnl": {"diff_pct": 5.2}}
        )

        assert coherence.is_coherent is False
        assert coherence.pnl_difference_pct == 5.2
        assert "pnl" in coherence.differences

    def test_coherence_to_dict(self):
        """Test converting coherence result to dict."""
        vbt_result = BacktestResult(mode=BacktestMode.VECTORBT)
        ed_result = BacktestResult(mode=BacktestMode.EVENT_DRIVEN)

        coherence = CoherenceResult(
            vectorbt_result=vbt_result,
            event_driven_result=ed_result,
            pnl_difference_pct=1.5,
            is_coherent=True
        )

        coherence_dict = coherence.to_dict()

        assert isinstance(coherence_dict, dict)
        assert coherence_dict["is_coherent"] is True
        assert coherence_dict["pnl_difference_pct"] == 1.5
        assert "vectorbt_result" in coherence_dict
        assert "event_driven_result" in coherence_dict
