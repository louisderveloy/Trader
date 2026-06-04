"""
Unit tests for backtesting coherence validation.

Tests the validation logic that ensures vectorbt and event-driven
backtests produce consistent results within tolerance.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from backtesting.types import (
    BacktestResult,
    BacktestMetrics,
    BacktestMode,
    BacktestConfig
)
from backtesting.coherence import (
    validate_coherence,
    generate_coherence_report,
    compare_trades,
    COHERENCE_TOLERANCE_PCT
)


class TestValidateCoherence:
    """Test validate_coherence function."""

    def test_coherent_results(self):
        """Test validating two coherent backtest results."""
        # Create config
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        # Create vectorbt result
        vbt_metrics = BacktestMetrics(
            total_pnl=Decimal("1000"),
            total_return=Decimal("10.0"),
            total_trades=50,
            win_rate=60.0,
            sharpe_ratio=1.5
        )
        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            metrics=vbt_metrics,
            success=True
        )

        # Create event-driven result (within 2% tolerance)
        ed_metrics = BacktestMetrics(
            total_pnl=Decimal("1015"),  # 1.5% difference
            total_return=Decimal("10.15"),
            total_trades=50,
            win_rate=60.0,
            sharpe_ratio=1.5
        )
        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            metrics=ed_metrics,
            success=True
        )

        # Validate coherence
        coherence = validate_coherence(vbt_result, ed_result)

        assert coherence.is_coherent is True
        assert abs(coherence.pnl_difference_pct) < COHERENCE_TOLERANCE_PCT

    def test_incoherent_results(self):
        """Test validating two incoherent backtest results."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        # Create vectorbt result
        vbt_metrics = BacktestMetrics(
            total_pnl=Decimal("1000"),
            total_return=Decimal("10.0"),
            total_trades=50
        )
        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            metrics=vbt_metrics,
            success=True
        )

        # Create event-driven result (>2% difference)
        ed_metrics = BacktestMetrics(
            total_pnl=Decimal("1050"),  # 5% difference
            total_return=Decimal("10.5"),
            total_trades=48
        )
        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            metrics=ed_metrics,
            success=True
        )

        # Validate coherence
        coherence = validate_coherence(vbt_result, ed_result)

        assert coherence.is_coherent is False
        assert abs(coherence.pnl_difference_pct) > COHERENCE_TOLERANCE_PCT

    def test_negative_pnl_coherence(self):
        """Test coherence with negative P&L."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        # Both results with negative P&L
        vbt_metrics = BacktestMetrics(
            total_pnl=Decimal("-1000"),
            total_return=Decimal("-10.0")
        )
        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            metrics=vbt_metrics,
            success=True
        )

        ed_metrics = BacktestMetrics(
            total_pnl=Decimal("-1015"),  # 1.5% difference
            total_return=Decimal("-10.15")
        )
        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            metrics=ed_metrics,
            success=True
        )

        coherence = validate_coherence(vbt_result, ed_result)

        # Should still be coherent
        assert coherence.is_coherent is True

    def test_custom_tolerance(self):
        """Test coherence with custom tolerance."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        vbt_metrics = BacktestMetrics(total_pnl=Decimal("1000"))
        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            metrics=vbt_metrics,
            success=True
        )

        # 3% difference
        ed_metrics = BacktestMetrics(total_pnl=Decimal("1030"))
        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            metrics=ed_metrics,
            success=True
        )

        # Should be incoherent with 2% tolerance
        coherence_2pct = validate_coherence(vbt_result, ed_result, tolerance_pct=2.0)
        assert coherence_2pct.is_coherent is False

        # Should be coherent with 5% tolerance
        coherence_5pct = validate_coherence(vbt_result, ed_result, tolerance_pct=5.0)
        assert coherence_5pct.is_coherent is True

    def test_failed_backtest(self):
        """Test coherence with failed backtest."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            success=False,
            error_message="Database error"
        )

        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            success=True
        )

        coherence = validate_coherence(vbt_result, ed_result)

        # Should be incoherent due to failed backtest
        assert coherence.is_coherent is False
        assert "error" in coherence.differences

    def test_missing_metrics(self):
        """Test coherence with missing metrics."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            success=True,
            metrics=None  # Missing metrics
        )

        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            success=True,
            metrics=BacktestMetrics(total_pnl=Decimal("1000"))
        )

        coherence = validate_coherence(vbt_result, ed_result)

        # Should be incoherent due to missing metrics
        assert coherence.is_coherent is False

    def test_wrong_mode_order(self):
        """Test with wrong mode order (should raise error)."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        # Both with same mode
        result1 = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            success=True
        )

        result2 = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            success=True
        )

        # Should raise ValueError
        with pytest.raises(ValueError):
            validate_coherence(result1, result2)

    def test_detailed_differences(self):
        """Test that detailed differences are calculated."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        vbt_metrics = BacktestMetrics(
            total_pnl=Decimal("1000"),
            total_return=Decimal("10.0"),
            total_trades=50,
            win_rate=60.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=5.0,
            profit_factor=1.8
        )
        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            metrics=vbt_metrics,
            success=True
        )

        ed_metrics = BacktestMetrics(
            total_pnl=Decimal("1015"),
            total_return=Decimal("10.15"),
            total_trades=48,
            win_rate=62.0,
            sharpe_ratio=1.6,
            max_drawdown_pct=4.8,
            profit_factor=1.9
        )
        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            metrics=ed_metrics,
            success=True
        )

        coherence = validate_coherence(vbt_result, ed_result)

        # Check that all metrics are compared
        assert "pnl" in coherence.differences
        assert "total_return" in coherence.differences
        assert "total_trades" in coherence.differences
        assert "win_rate" in coherence.differences
        assert "sharpe_ratio" in coherence.differences
        assert "max_drawdown_pct" in coherence.differences
        assert "profit_factor" in coherence.differences


class TestGenerateCoherenceReport:
    """Test generate_coherence_report function."""

    def test_coherent_report(self):
        """Test generating report for coherent results."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        vbt_metrics = BacktestMetrics(total_pnl=Decimal("1000"))
        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            metrics=vbt_metrics,
            success=True
        )

        ed_metrics = BacktestMetrics(total_pnl=Decimal("1015"))
        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            metrics=ed_metrics,
            success=True
        )

        coherence = validate_coherence(vbt_result, ed_result)
        report = generate_coherence_report(coherence)

        assert isinstance(report, str)
        assert "COHERENCE VALIDATION REPORT" in report
        assert "✅ COHERENT" in report
        assert "P&L COMPARISON" in report

    def test_incoherent_report(self):
        """Test generating report for incoherent results."""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        vbt_metrics = BacktestMetrics(total_pnl=Decimal("1000"))
        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            metrics=vbt_metrics,
            success=True
        )

        ed_metrics = BacktestMetrics(total_pnl=Decimal("1050"))  # 5% difference
        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            metrics=ed_metrics,
            success=True
        )

        coherence = validate_coherence(vbt_result, ed_result)
        report = generate_coherence_report(coherence)

        assert "❌ INCOHERENT" in report
        assert "⚠️  INVESTIGATION REQUIRED" in report
        assert "Possible causes:" in report


class TestCompareTrades:
    """Test compare_trades function."""

    def test_same_trade_count(self):
        """Test comparing results with same trade count."""
        from backtesting.types import BacktestTrade, TradeDirection, OrderType

        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        # Create identical trades for both
        trade1 = BacktestTrade(
            trade_number=1,
            direction=TradeDirection.LONG,
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=Decimal("42000"),
            entry_order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            exit_time=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
            exit_price=Decimal("42100"),
            exit_order_type=OrderType.MARKET,
            exit_reason="take_profit",
            net_pnl=Decimal("10")
        )

        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            trades=[trade1],
            success=True
        )

        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            trades=[trade1],
            success=True
        )

        comparison = compare_trades(vbt_result, ed_result)

        assert comparison["vectorbt_trade_count"] == 1
        assert comparison["event_driven_trade_count"] == 1
        assert comparison["trade_count_match"] is True
        assert len(comparison["trades"]) == 1

    def test_different_trade_count(self):
        """Test comparing results with different trade counts."""
        from backtesting.types import BacktestTrade, TradeDirection, OrderType

        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        trade1 = BacktestTrade(
            trade_number=1, direction=TradeDirection.LONG,
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=Decimal("42000"), entry_order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            exit_time=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
            exit_price=Decimal("42100"), exit_order_type=OrderType.MARKET,
            exit_reason="take_profit", net_pnl=Decimal("10")
        )

        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            trades=[trade1],
            success=True
        )

        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            trades=[],  # No trades
            success=True
        )

        comparison = compare_trades(vbt_result, ed_result)

        assert comparison["vectorbt_trade_count"] == 1
        assert comparison["event_driven_trade_count"] == 0
        assert comparison["trade_count_match"] is False

    def test_trade_differences_calculated(self):
        """Test that trade-by-trade differences are calculated."""
        from backtesting.types import BacktestTrade, TradeDirection, OrderType

        config = BacktestConfig(
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            initial_capital=Decimal("10000")
        )

        trade_vbt = BacktestTrade(
            trade_number=1, direction=TradeDirection.LONG,
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=Decimal("42000"), entry_order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            exit_time=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
            exit_price=Decimal("42100"), exit_order_type=OrderType.MARKET,
            exit_reason="take_profit", net_pnl=Decimal("10")
        )

        trade_ed = BacktestTrade(
            trade_number=1, direction=TradeDirection.LONG,
            entry_time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=Decimal("42005"),  # Slightly different
            entry_order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            exit_time=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
            exit_price=Decimal("42105"),  # Slightly different
            exit_order_type=OrderType.MARKET,
            exit_reason="take_profit", net_pnl=Decimal("10.5")  # Slightly different
        )

        vbt_result = BacktestResult(
            mode=BacktestMode.VECTORBT,
            config=config,
            trades=[trade_vbt],
            success=True
        )

        ed_result = BacktestResult(
            mode=BacktestMode.EVENT_DRIVEN,
            config=config,
            trades=[trade_ed],
            success=True
        )

        comparison = compare_trades(vbt_result, ed_result)

        # Check that differences are calculated
        trade_comp = comparison["trades"][0]
        assert "differences" in trade_comp
        assert "pnl_difference" in trade_comp["differences"]
        assert "pnl_difference_pct" in trade_comp["differences"]
        assert "entry_price_difference" in trade_comp["differences"]
        assert "exit_price_difference" in trade_comp["differences"]
