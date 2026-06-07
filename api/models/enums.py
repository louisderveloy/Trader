"""
Validation enums for API request parameters.

These enums provide strict validation for query parameters and request bodies,
preventing invalid data from being processed by the application.
"""

from enum import Enum


class TradeSide(str, Enum):
    """Trading side/direction."""
    BUY = "buy"
    SELL = "sell"
    LONG = "long"
    SHORT = "short"


class TradeEnvironment(str, Enum):
    """Trading environment."""
    TESTNET = "testnet"
    LIVE = "live"
    PAPER = "paper"
    BACKTEST = "backtest"


class RunStatus(str, Enum):
    """Run execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    """Order execution status."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class ErrorSeverity(str, Enum):
    """Error severity level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SignalDecision(str, Enum):
    """Signal decision type."""
    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    EXIT = "exit"
    SKIP = "skip"


class PositionSizeMode(str, Enum):
    """Position sizing mode."""
    FIXED = "fixed"
    CONFIDENCE = "confidence"
    RISK_ATR = "risk_atr"


class StopLossMode(str, Enum):
    """Stop-loss calculation mode."""
    ATR = "atr"
    FIXED = "fixed"


class TakeProfitMode(str, Enum):
    """Take-profit calculation mode."""
    ATR = "atr"
    FIXED = "fixed"


# Valid indicator names for weights validation
VALID_INDICATORS = {
    "ema",
    "macd",
    "rsi",
    "stoch_rsi",
    "bollinger",
    "atr",
    "obv",
    "fear_greed",
    "user_indicator",
}
