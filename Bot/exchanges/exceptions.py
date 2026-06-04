"""Custom exceptions for exchange connectors."""


class ExchangeError(Exception):
    """Base exception for all exchange-related errors."""

    pass


class ConnectionError(ExchangeError):
    """Raised when connection to exchange fails."""

    pass


class AuthenticationError(ExchangeError):
    """Raised when API credentials are invalid."""

    pass


class InsufficientBalanceError(ExchangeError):
    """Raised when balance is insufficient for an operation."""

    pass


class OrderNotFoundError(ExchangeError):
    """Raised when an order cannot be found."""

    pass


class InvalidSymbolError(ExchangeError):
    """Raised when a trading symbol is invalid."""

    pass


class InvalidTimeframeError(ExchangeError):
    """Raised when a timeframe is invalid."""

    pass


class RateLimitError(ExchangeError):
    """Raised when exchange rate limit is exceeded."""

    pass


class OrderRejectError(ExchangeError):
    """Raised when an order is rejected by the exchange."""

    pass
