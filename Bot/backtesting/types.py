"""
Backtesting type definitions.

This module defines all core types, enums, and dataclasses used by the backtesting engine
for both vectorbt and custom event-driven backtesting implementations.
"""

from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from uuid import UUID


class BacktestMode(str, Enum):
    """Backtesting engine mode."""

    VECTORBT = "vectorbt"  # Fast vectorized backtest (for Optuna optimization)
    EVENT_DRIVEN = "event_driven"  # Custom event-driven (exact live simulation)


class OrderType(str, Enum):
    """Order type for backtest."""

    LIMIT = "limit"  # Limit order
    MARKET = "market"  # Market order


class TradeDirection(str, Enum):
    """Trade direction."""

    LONG = "long"  # Long position
    SHORT = "short"  # Short position (future extension)


@dataclass
class BacktestConfig:
    """
    Configuration for backtesting runs.

    Contains all parameters needed to run a backtest including date range,
    initial capital, fees, slippage, and strategy configuration.
    """

    # Time period
    start_date: datetime
    end_date: datetime

    # Capital and risk
    initial_capital: Decimal
    max_position_size: Optional[Decimal] = None  # Max USDT per position (None = no limit)

    # Trading parameters
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"

    # Costs
    commission_rate: Decimal = Decimal("0.001")  # 0.1% Binance default
    slippage_pct: Decimal = Decimal("0.002")  # 0.2% default slippage

    # Order execution (event-driven only)
    limit_order_timeout_minutes: int = 30  # Timeout before fallback to market
    max_slippage_pct: Decimal = Decimal("0.002")  # Max 0.2% slippage

    # Strategy configuration (passed through to strategy engine)
    strategy_params: Dict[str, Any] = field(default_factory=dict)

    # Weights configuration
    weights_set_id: Optional[UUID] = None  # Active weights set for this backtest
    weights: Optional[Dict[str, float]] = None  # Manual weights override

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": float(self.initial_capital),
            "max_position_size": float(self.max_position_size) if self.max_position_size else None,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "commission_rate": float(self.commission_rate),
            "slippage_pct": float(self.slippage_pct),
            "limit_order_timeout_minutes": self.limit_order_timeout_minutes,
            "max_slippage_pct": float(self.max_slippage_pct),
            "strategy_params": self.strategy_params,
            "weights_set_id": str(self.weights_set_id) if self.weights_set_id else None,
            "weights": self.weights
        }


@dataclass
class BacktestTrade:
    """
    Represents a completed trade during backtesting.

    Contains all information about a trade including entry/exit prices,
    timestamps, P&L, fees, and metadata.
    """

    # Trade identification
    trade_number: int  # Sequential trade number in this backtest
    direction: TradeDirection

    # Entry
    entry_time: datetime
    entry_price: Decimal
    entry_order_type: OrderType
    quantity: Decimal

    # Exit
    exit_time: datetime
    exit_price: Decimal
    exit_order_type: OrderType
    exit_reason: str  # "take_profit", "stop_loss", "signal", "end_of_period"

    # Stop-loss and take-profit levels
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None

    # Performance
    gross_pnl: Decimal = Decimal("0")  # P&L before fees
    commission_paid: Decimal = Decimal("0")  # Total commission paid
    slippage_cost: Decimal = Decimal("0")  # Cost due to slippage
    net_pnl: Decimal = Decimal("0")  # P&L after fees and slippage
    return_pct: Decimal = Decimal("0")  # Return percentage on position size

    # Metadata
    weighted_score_entry: Optional[float] = None  # Strategy score at entry
    weighted_score_exit: Optional[float] = None  # Strategy score at exit
    duration_minutes: Optional[int] = None

    def __post_init__(self):
        """Calculate derived fields after initialization."""
        if self.duration_minutes is None and self.entry_time and self.exit_time:
            self.duration_minutes = int((self.exit_time - self.entry_time).total_seconds() / 60)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "trade_number": self.trade_number,
            "direction": self.direction.value,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": float(self.entry_price),
            "entry_order_type": self.entry_order_type.value,
            "quantity": float(self.quantity),
            "exit_time": self.exit_time.isoformat(),
            "exit_price": float(self.exit_price),
            "exit_order_type": self.exit_order_type.value,
            "exit_reason": self.exit_reason,
            "stop_loss_price": float(self.stop_loss_price) if self.stop_loss_price else None,
            "take_profit_price": float(self.take_profit_price) if self.take_profit_price else None,
            "gross_pnl": float(self.gross_pnl),
            "commission_paid": float(self.commission_paid),
            "slippage_cost": float(self.slippage_cost),
            "net_pnl": float(self.net_pnl),
            "return_pct": float(self.return_pct),
            "weighted_score_entry": self.weighted_score_entry,
            "weighted_score_exit": self.weighted_score_exit,
            "duration_minutes": self.duration_minutes
        }


@dataclass
class BacktestMetrics:
    """
    Performance metrics for a backtest run.

    Contains all standard metrics: Sharpe, Sortino, drawdown, win rate,
    profit factor, exposure, and comparison vs buy-and-hold.
    """

    # Basic performance
    total_return: Decimal = Decimal("0")  # Total return percentage
    total_pnl: Decimal = Decimal("0")  # Total P&L in USDT
    final_capital: Decimal = Decimal("0")  # Final capital after all trades

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0  # Percentage of winning trades

    # Profit/Loss statistics
    avg_win: Decimal = Decimal("0")  # Average winning trade P&L
    avg_loss: Decimal = Decimal("0")  # Average losing trade P&L (negative)
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")
    profit_factor: float = 0.0  # Total wins / abs(total losses)

    # Risk metrics
    sharpe_ratio: float = 0.0  # Annualized Sharpe ratio
    sortino_ratio: float = 0.0  # Annualized Sortino ratio (downside deviation)
    max_drawdown: Decimal = Decimal("0")  # Maximum drawdown in USDT
    max_drawdown_pct: float = 0.0  # Maximum drawdown percentage
    calmar_ratio: float = 0.0  # Total return / max drawdown

    # Exposure
    exposure_time_pct: float = 0.0  # % of time in position
    avg_trade_duration_minutes: Optional[int] = None

    # Buy-and-hold comparison
    buy_and_hold_return: Decimal = Decimal("0")  # B&H return percentage
    buy_and_hold_pnl: Decimal = Decimal("0")  # B&H P&L in USDT
    excess_return: Decimal = Decimal("0")  # Strategy return - B&H return

    # Equity curve
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)  # [{timestamp, capital}, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "total_return": float(self.total_return),
            "total_pnl": float(self.total_pnl),
            "final_capital": float(self.final_capital),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "avg_win": float(self.avg_win),
            "avg_loss": float(self.avg_loss),
            "largest_win": float(self.largest_win),
            "largest_loss": float(self.largest_loss),
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": float(self.max_drawdown),
            "max_drawdown_pct": self.max_drawdown_pct,
            "calmar_ratio": self.calmar_ratio,
            "exposure_time_pct": self.exposure_time_pct,
            "avg_trade_duration_minutes": self.avg_trade_duration_minutes,
            "buy_and_hold_return": float(self.buy_and_hold_return),
            "buy_and_hold_pnl": float(self.buy_and_hold_pnl),
            "excess_return": float(self.excess_return),
            "equity_curve": self.equity_curve
        }


@dataclass
class BacktestResult:
    """
    Complete result from a backtest run.

    Contains configuration, trades, metrics, and metadata for a complete
    backtesting run. This is the primary output from both backtesting engines.
    """

    # Identification
    run_id: Optional[UUID] = None  # Database run_id if persisted
    mode: BacktestMode = BacktestMode.VECTORBT
    timestamp: datetime = field(default_factory=lambda: datetime.now())

    # Configuration
    config: Optional[BacktestConfig] = None

    # Results
    trades: List[BacktestTrade] = field(default_factory=list)
    metrics: Optional[BacktestMetrics] = None

    # Performance summary (quick access)
    success: bool = True  # False if backtest failed
    error_message: Optional[str] = None

    # Execution metadata
    execution_time_seconds: float = 0.0
    candles_processed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "run_id": str(self.run_id) if self.run_id else None,
            "mode": self.mode.value,
            "timestamp": self.timestamp.isoformat(),
            "config": self.config.to_dict() if self.config else None,
            "trades": [t.to_dict() for t in self.trades],
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "success": self.success,
            "error_message": self.error_message,
            "execution_time_seconds": self.execution_time_seconds,
            "candles_processed": self.candles_processed
        }


@dataclass
class CoherenceResult:
    """
    Result from comparing two backtest runs for coherence.

    Used to validate that vectorbt and event-driven backtests
    produce results within acceptable tolerance (<2% P&L difference).
    """

    vectorbt_result: BacktestResult
    event_driven_result: BacktestResult

    # Comparison metrics
    pnl_difference_pct: float = 0.0  # Percentage difference in P&L
    is_coherent: bool = True  # True if difference < 2%
    tolerance_pct: float = 2.0  # Tolerance threshold

    # Detailed differences
    differences: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "vectorbt_result": self.vectorbt_result.to_dict(),
            "event_driven_result": self.event_driven_result.to_dict(),
            "pnl_difference_pct": self.pnl_difference_pct,
            "is_coherent": self.is_coherent,
            "tolerance_pct": self.tolerance_pct,
            "differences": self.differences
        }
