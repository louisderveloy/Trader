"""
Unit tests for backtesting metrics calculation.

Tests all metric calculations with known inputs and expected outputs.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from decimal import Decimal

from backtesting.types import BacktestTrade, BacktestConfig, TradeDirection, OrderType
from backtesting.metrics import (
    calculate_metrics,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_max_drawdown,
    build_equity_curve,
    calculate_trade_statistics
)


class TestCalculateReturns:
    """Test calculate_returns function."""

    def test_simple_returns(self):
        """Test calculating returns from equity curve."""
        equity_curve = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=5, freq='1H'),
            'capital': [10000, 10100, 10050, 10200, 10150]
        })

        returns = calculate_returns(equity_curve)

        # First return should be NaN (removed), then percentage changes
        assert len(returns) == 5
        assert pd.isna(returns.iloc[0]) or returns.iloc[0] == 0.0  # First value
        assert abs(returns.iloc[1] - 0.01) < 0.0001  # 1% gain
        assert returns.iloc[2] < 0  # Loss

    def test_empty_equity_curve(self):
        """Test with empty equity curve."""
        equity_curve = pd.DataFrame()
        returns = calculate_returns(equity_curve)

        assert returns.empty

    def test_no_capital_column(self):
        """Test with missing capital column."""
        equity_curve = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=5, freq='1H'),
            'value': [10000, 10100, 10050, 10200, 10150]
        })

        returns = calculate_returns(equity_curve)

        assert returns.empty


class TestCalculateSharpeRatio:
    """Test calculate_sharpe_ratio function."""

    def test_positive_sharpe(self):
        """Test calculating Sharpe ratio with positive returns."""
        # Create returns with positive trend
        returns = pd.Series([0.01, 0.015, 0.008, 0.012, 0.011] * 20)  # 100 periods

        sharpe = calculate_sharpe_ratio(returns)

        # Should be positive for consistently positive returns
        assert sharpe > 0

    def test_negative_sharpe(self):
        """Test calculating Sharpe ratio with negative returns."""
        # Create returns with negative trend
        returns = pd.Series([-0.01, -0.015, -0.008, -0.012, -0.011] * 20)

        sharpe = calculate_sharpe_ratio(returns)

        # Should be negative for consistently negative returns
        assert sharpe < 0

    def test_zero_std_dev(self):
        """Test with zero standard deviation (all returns identical)."""
        returns = pd.Series([0.01] * 100)

        sharpe = calculate_sharpe_ratio(returns)

        # Should return 0 when std dev is 0
        assert sharpe == 0.0

    def test_empty_returns(self):
        """Test with empty returns series."""
        returns = pd.Series(dtype=float)

        sharpe = calculate_sharpe_ratio(returns)

        assert sharpe == 0.0

    def test_single_return(self):
        """Test with only one return."""
        returns = pd.Series([0.01])

        sharpe = calculate_sharpe_ratio(returns)

        # Not enough data to calculate
        assert sharpe == 0.0


class TestCalculateSortinoRatio:
    """Test calculate_sortino_ratio function."""

    def test_positive_sortino(self):
        """Test calculating Sortino ratio with mostly positive returns."""
        # Mixed returns but more positive than negative
        returns = pd.Series([0.02, 0.01, -0.005, 0.015, 0.01, -0.003] * 20)

        sortino = calculate_sortino_ratio(returns)

        # Should be positive
        assert sortino > 0

    def test_only_positive_returns(self):
        """Test with only positive returns (no downside)."""
        returns = pd.Series([0.01, 0.015, 0.02] * 20)

        sortino = calculate_sortino_ratio(returns)

        # Should return 0 (no downside deviation)
        assert sortino == 0.0

    def test_only_negative_returns(self):
        """Test with only negative returns."""
        returns = pd.Series([-0.01, -0.015, -0.02] * 20)

        sortino = calculate_sortino_ratio(returns)

        # Should be negative
        assert sortino < 0

    def test_empty_returns(self):
        """Test with empty returns series."""
        returns = pd.Series(dtype=float)

        sortino = calculate_sortino_ratio(returns)

        assert sortino == 0.0


class TestCalculateMaxDrawdown:
    """Test calculate_max_drawdown function."""

    def test_no_drawdown(self):
        """Test with only increasing equity (no drawdown)."""
        equity_curve = pd.DataFrame({
            'capital': [10000, 10100, 10200, 10300, 10400]
        })

        max_dd_usdt, max_dd_pct = calculate_max_drawdown(equity_curve)

        assert max_dd_usdt == 0.0
        assert max_dd_pct == 0.0

    def test_simple_drawdown(self):
        """Test with simple drawdown."""
        equity_curve = pd.DataFrame({
            'capital': [10000, 11000, 10500, 10000, 10500]
        })

        max_dd_usdt, max_dd_pct = calculate_max_drawdown(equity_curve)

        # Max drawdown should be from 11000 to 10000 = 1000 USDT = 9.09%
        assert abs(max_dd_usdt - 1000.0) < 1.0
        assert abs(max_dd_pct - 9.09) < 0.1

    def test_multiple_drawdowns(self):
        """Test with multiple drawdowns (should return largest)."""
        equity_curve = pd.DataFrame({
            'capital': [10000, 11000, 10500, 12000, 10000, 11000]
        })

        max_dd_usdt, max_dd_pct = calculate_max_drawdown(equity_curve)

        # Max drawdown should be from 12000 to 10000 = 2000 USDT
        assert abs(max_dd_usdt - 2000.0) < 1.0

    def test_empty_equity_curve(self):
        """Test with empty equity curve."""
        equity_curve = pd.DataFrame()

        max_dd_usdt, max_dd_pct = calculate_max_drawdown(equity_curve)

        assert max_dd_usdt == 0.0
        assert max_dd_pct == 0.0


class TestBuildEquityCurve:
    """Test build_equity_curve function."""

    def test_no_trades(self):
        """Test building equity curve with no trades."""
        initial_capital = Decimal("10000")
        candles = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=5, freq='1H'),
            'close': [42000, 42100, 42050, 42200, 42150]
        })

        equity_curve = build_equity_curve([], initial_capital, candles)

        assert len(equity_curve) == 5
        # All capital values should equal initial capital
        assert all(equity_curve['capital'] == float(initial_capital))

    def test_with_trades(self):
        """Test building equity curve with trades."""
        initial_capital = Decimal("10000")
        candles = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=5, freq='1H'),
            'close': [42000, 42100, 42050, 42200, 42150]
        })

        # Create a winning trade
        trade = BacktestTrade(
            trade_number=1,
            direction=TradeDirection.LONG,
            entry_time=candles.iloc[1]['timestamp'],
            entry_price=Decimal("42100"),
            entry_order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            exit_time=candles.iloc[3]['timestamp'],
            exit_price=Decimal("42200"),
            exit_order_type=OrderType.MARKET,
            exit_reason="take_profit",
            net_pnl=Decimal("10")  # $10 profit
        )

        equity_curve = build_equity_curve([trade], initial_capital, candles)

        assert len(equity_curve) == 5
        # Capital before trade exit should be initial
        assert equity_curve.iloc[0]['capital'] == float(initial_capital)
        assert equity_curve.iloc[1]['capital'] == float(initial_capital)
        # Capital after trade exit should include profit
        assert equity_curve.iloc[3]['capital'] == float(initial_capital + Decimal("10"))
        assert equity_curve.iloc[4]['capital'] == float(initial_capital + Decimal("10"))

    def test_empty_candles(self):
        """Test with empty candles DataFrame."""
        equity_curve = build_equity_curve([], Decimal("10000"), pd.DataFrame())

        assert equity_curve.empty


class TestCalculateTradeStatistics:
    """Test calculate_trade_statistics function."""

    def test_no_trades(self):
        """Test with no trades."""
        stats = calculate_trade_statistics([])

        assert stats["total"] == 0
        assert stats["winning"] == 0
        assert stats["losing"] == 0
        assert stats["win_rate"] == 0.0

    def test_only_winning_trades(self):
        """Test with only winning trades."""
        trades = [
            BacktestTrade(
                trade_number=i + 1,
                direction=TradeDirection.LONG,
                entry_time=datetime(2024, 1, 1, 10 + i, 0, tzinfo=timezone.utc),
                entry_price=Decimal("42000"),
                entry_order_type=OrderType.MARKET,
                quantity=Decimal("0.1"),
                exit_time=datetime(2024, 1, 1, 11 + i, 0, tzinfo=timezone.utc),
                exit_price=Decimal("42100"),
                exit_order_type=OrderType.MARKET,
                exit_reason="take_profit",
                net_pnl=Decimal("10"),
                duration_minutes=60
            )
            for i in range(5)
        ]

        stats = calculate_trade_statistics(trades)

        assert stats["total"] == 5
        assert stats["winning"] == 5
        assert stats["losing"] == 0
        assert stats["win_rate"] == 100.0
        assert stats["avg_win"] == 10.0
        assert stats["avg_loss"] == 0.0

    def test_mixed_trades(self):
        """Test with mixed winning and losing trades."""
        trades = [
            # 3 winning trades
            BacktestTrade(
                trade_number=1, direction=TradeDirection.LONG,
                entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                entry_price=Decimal("42000"), entry_order_type=OrderType.MARKET,
                quantity=Decimal("0.1"),
                exit_time=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
                exit_price=Decimal("42100"), exit_order_type=OrderType.MARKET,
                exit_reason="take_profit", net_pnl=Decimal("20"), duration_minutes=60
            ),
            BacktestTrade(
                trade_number=2, direction=TradeDirection.LONG,
                entry_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
                entry_price=Decimal("42000"), entry_order_type=OrderType.MARKET,
                quantity=Decimal("0.1"),
                exit_time=datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
                exit_price=Decimal("42100"), exit_order_type=OrderType.MARKET,
                exit_reason="take_profit", net_pnl=Decimal("30"), duration_minutes=60
            ),
            BacktestTrade(
                trade_number=3, direction=TradeDirection.LONG,
                entry_time=datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc),
                entry_price=Decimal("42000"), entry_order_type=OrderType.MARKET,
                quantity=Decimal("0.1"),
                exit_time=datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc),
                exit_price=Decimal("42100"), exit_order_type=OrderType.MARKET,
                exit_reason="take_profit", net_pnl=Decimal("10"), duration_minutes=60
            ),
            # 2 losing trades
            BacktestTrade(
                trade_number=4, direction=TradeDirection.LONG,
                entry_time=datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc),
                entry_price=Decimal("42000"), entry_order_type=OrderType.MARKET,
                quantity=Decimal("0.1"),
                exit_time=datetime(2024, 1, 1, 17, 0, tzinfo=timezone.utc),
                exit_price=Decimal("41900"), exit_order_type=OrderType.MARKET,
                exit_reason="stop_loss", net_pnl=Decimal("-15"), duration_minutes=60
            ),
            BacktestTrade(
                trade_number=5, direction=TradeDirection.LONG,
                entry_time=datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc),
                entry_price=Decimal("42000"), entry_order_type=OrderType.MARKET,
                quantity=Decimal("0.1"),
                exit_time=datetime(2024, 1, 1, 19, 0, tzinfo=timezone.utc),
                exit_price=Decimal("41900"), exit_order_type=OrderType.MARKET,
                exit_reason="stop_loss", net_pnl=Decimal("-5"), duration_minutes=60
            ),
        ]

        stats = calculate_trade_statistics(trades)

        assert stats["total"] == 5
        assert stats["winning"] == 3
        assert stats["losing"] == 2
        assert stats["win_rate"] == 60.0
        assert abs(stats["avg_win"] - 20.0) < 0.1  # (20+30+10)/3
        assert abs(stats["avg_loss"] - (-10.0)) < 0.1  # (-15-5)/2
        assert stats["largest_win"] == 30.0
        assert stats["largest_loss"] == -15.0
        assert stats["avg_duration_minutes"] == 60


class TestCalculatePercentageDifference:
    """Test calculate_percentage_difference helper function."""

    def test_positive_difference(self):
        """Test calculating positive percentage difference."""
        from backtesting.coherence import calculate_percentage_difference

        diff = calculate_percentage_difference(100.0, 110.0)

        assert abs(diff - 10.0) < 0.01  # 10% increase

    def test_negative_difference(self):
        """Test calculating negative percentage difference."""
        from backtesting.coherence import calculate_percentage_difference

        diff = calculate_percentage_difference(100.0, 90.0)

        assert abs(diff - (-10.0)) < 0.01  # 10% decrease

    def test_zero_baseline(self):
        """Test with zero baseline value."""
        from backtesting.coherence import calculate_percentage_difference

        diff = calculate_percentage_difference(0.0, 50.0)

        assert diff == 100.0  # Special case for zero baseline

    def test_both_zero(self):
        """Test with both values zero."""
        from backtesting.coherence import calculate_percentage_difference

        diff = calculate_percentage_difference(0.0, 0.0)

        assert diff == 0.0
