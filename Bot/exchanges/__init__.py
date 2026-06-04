"""Exchange connectors for trading bot.

This module provides abstract base class and concrete implementations
for cryptocurrency exchange connectivity.
"""

from exchanges.base import ExchangeBase
from exchanges.binance import BinanceExchange
from exchanges.exceptions import (
    ExchangeError,
    ConnectionError,
    AuthenticationError,
    InsufficientBalanceError,
    InvalidSymbolError,
    InvalidTimeframeError,
    OrderNotFoundError,
    OrderRejectError,
    RateLimitError,
)

__all__ = [
    "ExchangeBase",
    "BinanceExchange",
    "ExchangeError",
    "ConnectionError",
    "AuthenticationError",
    "InsufficientBalanceError",
    "InvalidSymbolError",
    "InvalidTimeframeError",
    "OrderNotFoundError",
    "OrderRejectError",
    "RateLimitError",
]
