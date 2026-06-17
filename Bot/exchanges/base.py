"""Abstract base class for exchange connectors.

All exchange implementations must inherit from ExchangeBase and implement
all abstract methods. This ensures a consistent interface across different
exchanges (Binance, future exchanges, etc.).
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import datetime


class ExchangeBase(ABC):
    """Abstract base class for cryptocurrency exchange connectors.

    This class defines the interface that all exchange connectors must implement.
    It ensures consistent behavior across different exchanges and allows for easy
    swapping of exchange backends.

    Attributes:
        testnet: Whether the connector is using testnet or mainnet.
        api_key: API key for authentication.
        api_secret: API secret for authentication.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """Initialize exchange connector.

        Args:
            api_key: Exchange API key.
            api_secret: Exchange API secret.
            testnet: If True, use testnet. If False, use mainnet.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the exchange.

        This should initialize the client, verify credentials, and perform
        any necessary setup. Should raise an exception if connection fails.

        Raises:
            ConnectionError: If connection to exchange fails.
            AuthenticationError: If API credentials are invalid.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the exchange.

        Clean up resources, close websocket connections, etc.
        """
        pass

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch historical OHLCV candles.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            timeframe: Candle timeframe (e.g., "15m", "1h", "1d").
            limit: Maximum number of candles to fetch (default 500).
            start_time: Start time for historical data (optional).
            end_time: End time for historical data (optional).

        Returns:
            List of candle dictionaries with keys:
                - time: datetime (UTC)
                - open: Decimal
                - high: Decimal
                - low: Decimal
                - close: Decimal
                - volume: Decimal

        Raises:
            ValueError: If symbol or timeframe is invalid.
            ExchangeError: If exchange API returns an error.
        """
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker data for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").

        Returns:
            Dictionary with ticker data:
                - symbol: str
                - last_price: Decimal
                - bid: Decimal
                - ask: Decimal
                - volume_24h: Decimal
                - timestamp: datetime

        Raises:
            ValueError: If symbol is invalid.
            ExchangeError: If exchange API returns an error.
        """
        pass

    @abstractmethod
    async def get_balance(self, asset: str) -> Dict[str, Decimal]:
        """Get balance for a specific asset.

        Args:
            asset: Asset symbol (e.g., "USDT", "BTC").

        Returns:
            Dictionary with balance data:
                - free: Decimal (available balance)
                - locked: Decimal (balance in orders)
                - total: Decimal (free + locked)

        Raises:
            ValueError: If asset is invalid.
            ExchangeError: If exchange API returns an error.
        """
        pass

    @abstractmethod
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        post_only: bool = True,
    ) -> Dict[str, Any]:
        """Place a limit order.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            side: Order side ("buy" or "sell").
            quantity: Order quantity.
            price: Limit price.
            post_only: If True, order will only be maker (default True).

        Returns:
            Dictionary with order data:
                - order_id: str (exchange order ID)
                - symbol: str
                - side: str
                - type: str ("limit")
                - quantity: Decimal
                - price: Decimal
                - status: str ("pending", "filled", "cancelled", "rejected")
                - created_at: datetime

        Raises:
            ValueError: If parameters are invalid.
            InsufficientBalanceError: If balance is insufficient.
            ExchangeError: If exchange rejects the order.
        """
        pass

    @abstractmethod
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
    ) -> Dict[str, Any]:
        """Place a market order.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            side: Order side ("buy" or "sell").
            quantity: Order quantity.

        Returns:
            Dictionary with order data (same format as place_limit_order).

        Raises:
            ValueError: If parameters are invalid.
            InsufficientBalanceError: If balance is insufficient.
            ExchangeError: If exchange rejects the order.
        """
        pass

    @abstractmethod
    async def place_oco_sell_order(
        self,
        symbol: str,
        quantity: Decimal,
        take_profit_price: Decimal,
        stop_price: Decimal,
        stop_limit_price: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Place a One-Cancels-Other SELL order (exchange-side SL + TP for a LONG).

        Combines a take-profit limit order and a stop-loss stop-limit order. When
        one fills the exchange cancels the other automatically — exchange-resident
        protection that holds even if the bot process is down.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            quantity: Quantity to sell (the open position size).
            take_profit_price: Limit price of the take-profit leg (above current price).
            stop_price: Trigger price of the stop-loss leg (below current price).
            stop_limit_price: Limit price once the stop triggers. Defaults to
                ``stop_price`` (a slightly lower value reduces non-fill risk).

        Returns:
            Dictionary with:
                - order_list_id: str (OCO list identifier)
                - leg_order_ids: list[str] (the two leg order IDs)
                - status: str
                - created_at: datetime

        Raises:
            ValueError: If parameters are invalid.
            ExchangeError: If the exchange rejects the OCO order.
        """
        pass

    @abstractmethod
    async def cancel_oco_order(self, symbol: str, leg_order_id: str) -> Dict[str, Any]:
        """Cancel a resting OCO order by one of its leg order IDs.

        Cancelling either leg of an OCO cancels the whole pair on Binance.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            leg_order_id: Exchange order ID of either OCO leg.

        Returns:
            Dictionary with cancellation confirmation.

        Raises:
            OrderNotFoundError: If the order no longer exists (already filled/cancelled).
            ExchangeError: If cancellation fails.
        """
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Cancel an open order.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            order_id: Exchange order ID.

        Returns:
            Dictionary with cancellation confirmation:
                - order_id: str
                - status: str ("cancelled")
                - cancelled_at: datetime

        Raises:
            ValueError: If order_id is invalid.
            OrderNotFoundError: If order doesn't exist.
            ExchangeError: If cancellation fails.
        """
        pass

    @abstractmethod
    async def get_order_status(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Get status of an order.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            order_id: Exchange order ID.

        Returns:
            Dictionary with order status:
                - order_id: str
                - symbol: str
                - side: str
                - type: str
                - quantity: Decimal
                - price: Decimal (for limit orders)
                - filled_quantity: Decimal
                - filled_price: Decimal (average fill price)
                - status: str
                - created_at: datetime
                - updated_at: datetime

        Raises:
            ValueError: If order_id is invalid.
            OrderNotFoundError: If order doesn't exist.
            ExchangeError: If exchange API returns an error.
        """
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all open orders.

        Args:
            symbol: Optional trading pair to filter by.

        Returns:
            List of order dictionaries (same format as get_order_status).

        Raises:
            ExchangeError: If exchange API returns an error.
        """
        pass

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol format to exchange-specific format.

        Args:
            symbol: Symbol in standard format (e.g., "BTC/USDT").

        Returns:
            Symbol in exchange format (e.g., "BTCUSDT" for Binance).
        """
        pass

    @abstractmethod
    def normalize_timeframe(self, timeframe: str) -> str:
        """Normalize timeframe format to exchange-specific format.

        Args:
            timeframe: Timeframe in standard format (e.g., "15m", "1h", "1d").

        Returns:
            Timeframe in exchange format.
        """
        pass
