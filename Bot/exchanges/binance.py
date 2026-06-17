"""Binance exchange connector implementation.

This module provides the concrete implementation of ExchangeBase for Binance exchange.
Supports both testnet and mainnet.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from binance import AsyncClient
from binance.exceptions import BinanceAPIException, BinanceRequestException

from exchanges.base import ExchangeBase
from exchanges.exceptions import (
    ConnectionError,
    AuthenticationError,
    ExchangeError,
    InsufficientBalanceError,
    InvalidSymbolError,
    InvalidTimeframeError,
    OrderNotFoundError,
    OrderRejectError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class BinanceExchange(ExchangeBase):
    """Binance exchange connector.

    Implements ExchangeBase for Binance exchange using python-binance library.
    Supports both testnet and mainnet environments.

    Attributes:
        client: AsyncClient instance from python-binance.
        testnet: Whether using testnet or mainnet.
    """

    # Binance timeframe mapping
    TIMEFRAME_MAP = {
        "1m": AsyncClient.KLINE_INTERVAL_1MINUTE,
        "3m": AsyncClient.KLINE_INTERVAL_3MINUTE,
        "5m": AsyncClient.KLINE_INTERVAL_5MINUTE,
        "15m": AsyncClient.KLINE_INTERVAL_15MINUTE,
        "30m": AsyncClient.KLINE_INTERVAL_30MINUTE,
        "1h": AsyncClient.KLINE_INTERVAL_1HOUR,
        "2h": AsyncClient.KLINE_INTERVAL_2HOUR,
        "4h": AsyncClient.KLINE_INTERVAL_4HOUR,
        "6h": AsyncClient.KLINE_INTERVAL_6HOUR,
        "8h": AsyncClient.KLINE_INTERVAL_8HOUR,
        "12h": AsyncClient.KLINE_INTERVAL_12HOUR,
        "1d": AsyncClient.KLINE_INTERVAL_1DAY,
        "3d": AsyncClient.KLINE_INTERVAL_3DAY,
        "1w": AsyncClient.KLINE_INTERVAL_1WEEK,
        "1M": AsyncClient.KLINE_INTERVAL_1MONTH,
    }

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """Initialize Binance connector.

        Args:
            api_key: Binance API key.
            api_secret: Binance API secret.
            testnet: If True, use testnet. If False, use mainnet.
        """
        super().__init__(api_key, api_secret, testnet)
        self.client: Optional[AsyncClient] = None
        self._symbol_info_cache: Dict[str, Dict[str, Any]] = {}
        logger.info(
            f"Binance connector initialized (testnet={testnet})",
            extra={"testnet": testnet},
        )

    async def connect(self) -> None:
        """Establish connection to Binance.

        Creates AsyncClient and verifies credentials by fetching account info.

        Raises:
            ConnectionError: If connection fails.
            AuthenticationError: If API credentials are invalid.
        """
        try:
            if self.testnet:
                self.client = await AsyncClient.create(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    testnet=True,
                )
                logger.info("Connected to Binance testnet")
            else:
                self.client = await AsyncClient.create(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                )
                logger.info("Connected to Binance mainnet")

            # Verify credentials by fetching account info
            await self.client.get_account()
            logger.info("Binance credentials verified")

        except BinanceAPIException as e:
            if e.code in [-2014, -2015]:  # Invalid API key or signature
                logger.error(f"Binance authentication failed: {e.message}")
                raise AuthenticationError(f"Invalid Binance API credentials: {e.message}")
            else:
                logger.error(f"Binance API error during connection: {e.message}")
                raise ConnectionError(f"Binance connection failed: {e.message}")
        except BinanceRequestException as e:
            logger.error(f"Binance request error during connection: {e}")
            raise ConnectionError(f"Binance connection failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Binance connection: {e}")
            raise ConnectionError(f"Binance connection failed: {e}")

    async def disconnect(self) -> None:
        """Close connection to Binance.

        Closes the AsyncClient session.
        """
        if self.client:
            await self.client.close_connection()
            self.client = None
            logger.info("Disconnected from Binance")

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch historical OHLCV candles from Binance.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            timeframe: Candle timeframe (e.g., "15m", "1h", "1d").
            limit: Maximum number of candles (default 500, max 1000).
            start_time: Start time for historical data (optional).
            end_time: End time for historical data (optional).

        Returns:
            List of candle dictionaries with normalized data.

        Raises:
            InvalidSymbolError: If symbol is invalid.
            InvalidTimeframeError: If timeframe is invalid.
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        # Normalize inputs
        symbol = self.normalize_symbol(symbol)
        binance_timeframe = self.normalize_timeframe(timeframe)

        # Validate limit
        if limit > 1000:
            logger.warning(f"Limit {limit} exceeds Binance max (1000), capping to 1000")
            limit = 1000

        try:
            # Prepare kwargs for get_klines
            kwargs = {
                "symbol": symbol,
                "interval": binance_timeframe,
                "limit": limit,
            }

            if start_time:
                kwargs["startTime"] = int(start_time.timestamp() * 1000)
            if end_time:
                kwargs["endTime"] = int(end_time.timestamp() * 1000)

            # Fetch klines from Binance
            klines = await self.client.get_klines(**kwargs)

            # Normalize to standard format
            candles = []
            for kline in klines:
                candles.append(
                    {
                        "time": datetime.fromtimestamp(kline[0] / 1000, tz=timezone.utc),
                        "open": Decimal(kline[1]),
                        "high": Decimal(kline[2]),
                        "low": Decimal(kline[3]),
                        "close": Decimal(kline[4]),
                        "volume": Decimal(kline[5]),
                    }
                )

            logger.debug(
                f"Fetched {len(candles)} candles for {symbol} {timeframe}",
                extra={"symbol": symbol, "timeframe": timeframe, "count": len(candles)},
            )
            return candles

        except BinanceAPIException as e:
            if e.code == -1121:  # Invalid symbol
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            else:
                logger.error(f"Binance API error fetching candles: {e.message}")
                raise ExchangeError(f"Failed to fetch candles: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error fetching candles: {e}")
            raise ExchangeError(f"Failed to fetch candles: {e}")

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker data for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").

        Returns:
            Dictionary with normalized ticker data.

        Raises:
            InvalidSymbolError: If symbol is invalid.
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        symbol = self.normalize_symbol(symbol)

        try:
            ticker = await self.client.get_ticker(symbol=symbol)
            orderbook = await self.client.get_orderbook_ticker(symbol=symbol)

            return {
                "symbol": symbol,
                "last_price": Decimal(ticker["lastPrice"]),
                "bid": Decimal(orderbook["bidPrice"]),
                "ask": Decimal(orderbook["askPrice"]),
                "volume_24h": Decimal(ticker["volume"]),
                "timestamp": datetime.fromtimestamp(
                    ticker["closeTime"] / 1000, tz=timezone.utc
                ),
            }

        except BinanceAPIException as e:
            if e.code == -1121:
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            else:
                logger.error(f"Binance API error fetching ticker: {e.message}")
                raise ExchangeError(f"Failed to fetch ticker: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error fetching ticker: {e}")
            raise ExchangeError(f"Failed to fetch ticker: {e}")

    async def get_balance(self, asset: str) -> Dict[str, Decimal]:
        """Get balance for a specific asset.

        Args:
            asset: Asset symbol (e.g., "USDT", "BTC").

        Returns:
            Dictionary with balance data.

        Raises:
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        try:
            account = await self.client.get_account()

            # Find asset in balances
            for balance in account["balances"]:
                if balance["asset"] == asset.upper():
                    free = Decimal(balance["free"])
                    locked = Decimal(balance["locked"])
                    return {
                        "free": free,
                        "locked": locked,
                        "total": free + locked,
                    }

            # Asset not found, return zeros
            return {
                "free": Decimal("0"),
                "locked": Decimal("0"),
                "total": Decimal("0"),
            }

        except BinanceAPIException as e:
            logger.error(f"Binance API error fetching balance: {e.message}")
            raise ExchangeError(f"Failed to fetch balance: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error fetching balance: {e}")
            raise ExchangeError(f"Failed to fetch balance: {e}")

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        post_only: bool = True,
    ) -> Dict[str, Any]:
        """Place a limit order on Binance.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            side: Order side ("buy" or "sell").
            quantity: Order quantity.
            price: Limit price.
            post_only: If True, order will only be maker (default True).

        Returns:
            Dictionary with order data.

        Raises:
            InvalidSymbolError: If symbol is invalid.
            InsufficientBalanceError: If balance is insufficient.
            OrderRejectError: If exchange rejects the order.
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        symbol = self.normalize_symbol(symbol)
        side = side.upper()

        try:
            # Get symbol info for precision rules
            symbol_info = await self.get_symbol_info(symbol)

            # Format quantity and price according to exchange rules
            formatted_quantity = self._format_quantity(quantity, symbol_info["lot_size_step"])
            formatted_price = self._format_price(price, symbol_info["price_tick"])

            logger.debug(
                f"Formatted order: qty {quantity} -> {formatted_quantity}, "
                f"price {price} -> {formatted_price}"
            )

            # Create order params
            # For post-only, use LIMIT_MAKER type (no timeInForce needed)
            # For regular limit, use LIMIT type with GTC timeInForce
            if post_only:
                params = {
                    "symbol": symbol,
                    "side": side,
                    "type": "LIMIT_MAKER",  # Post-only, will reject if matches immediately
                    "quantity": formatted_quantity,
                    "price": formatted_price,
                }
            else:
                params = {
                    "symbol": symbol,
                    "side": side,
                    "type": "LIMIT",
                    "quantity": formatted_quantity,
                    "price": formatted_price,
                    "timeInForce": "GTC",  # Good-Til-Canceled
                }

            logger.debug(f"Placing order with params: {params}")
            order = await self.client.create_order(**params)
            logger.debug(f"Binance limit order response: {order}")

            return self._normalize_order(order)

        except BinanceAPIException as e:
            if e.code == -1121:
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            elif e.code == -2010:
                raise InsufficientBalanceError(f"Insufficient balance: {e.message}")
            elif e.code in [-1013, -1111, -2011]:  # Order rejected
                raise OrderRejectError(f"Order rejected: {e.message}")
            elif e.code == -1003:  # Rate limit
                raise RateLimitError(f"Rate limit exceeded: {e.message}")
            else:
                logger.error(f"Binance API error placing limit order: {e.message}")
                raise ExchangeError(f"Failed to place limit order: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error placing limit order: {e}")
            raise ExchangeError(f"Failed to place limit order: {e}")

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
    ) -> Dict[str, Any]:
        """Place a market order on Binance.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            side: Order side ("buy" or "sell").
            quantity: Order quantity.

        Returns:
            Dictionary with order data.

        Raises:
            InvalidSymbolError: If symbol is invalid.
            InsufficientBalanceError: If balance is insufficient.
            OrderRejectError: If exchange rejects the order.
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        symbol = self.normalize_symbol(symbol)
        side = side.upper()

        try:
            # Get symbol info for precision rules
            symbol_info = await self.get_symbol_info(symbol)

            # Format quantity according to exchange rules
            formatted_quantity = self._format_quantity(quantity, symbol_info["lot_size_step"])

            logger.debug(f"Formatted market order quantity: {quantity} -> {formatted_quantity}")

            params = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": formatted_quantity,
            }

            logger.debug(f"Placing market order with params: {params}")
            order = await self.client.create_order(**params)
            logger.debug(f"Binance market order response: {order}")

            return self._normalize_order(order)

        except BinanceAPIException as e:
            if e.code == -1121:
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            elif e.code == -2010:
                raise InsufficientBalanceError(f"Insufficient balance: {e.message}")
            elif e.code in [-1013, -1111, -2011]:
                raise OrderRejectError(f"Order rejected: {e.message}")
            elif e.code == -1003:
                raise RateLimitError(f"Rate limit exceeded: {e.message}")
            else:
                logger.error(f"Binance API error placing market order: {e.message}")
                raise ExchangeError(f"Failed to place market order: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error placing market order: {e}")
            raise ExchangeError(f"Failed to place market order: {e}")

    async def place_oco_sell_order(
        self,
        symbol: str,
        quantity: Decimal,
        take_profit_price: Decimal,
        stop_price: Decimal,
        stop_limit_price: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Place a One-Cancels-Other SELL order (exchange-side SL + TP for a LONG).

        See ExchangeBase.place_oco_sell_order for the contract. The take-profit is
        a LIMIT leg at ``take_profit_price``; the stop-loss is a STOP_LOSS_LIMIT leg
        triggered at ``stop_price`` with limit ``stop_limit_price`` (defaults to the
        trigger price).
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        symbol = self.normalize_symbol(symbol)
        if stop_limit_price is None:
            stop_limit_price = stop_price

        try:
            symbol_info = await self.get_symbol_info(symbol)
            fmt_qty = self._format_quantity(quantity, symbol_info["lot_size_step"])
            tick = symbol_info["price_tick"]
            fmt_tp = self._format_price(take_profit_price, tick)
            fmt_stop = self._format_price(stop_price, tick)
            fmt_stop_limit = self._format_price(stop_limit_price, tick)

            params = {
                "symbol": symbol,
                "side": "SELL",
                "quantity": fmt_qty,
                "price": fmt_tp,                 # take-profit limit leg
                "stopPrice": fmt_stop,           # stop trigger
                "stopLimitPrice": fmt_stop_limit,  # stop-loss limit once triggered
                "stopLimitTimeInForce": "GTC",
            }

            logger.debug(f"Placing OCO sell order with params: {params}")
            result = await self.client.create_oco_order(**params)
            logger.debug(f"Binance OCO order response: {result}")

            order_reports = result.get("orderReports", []) or result.get("orders", [])
            leg_order_ids = [str(o["orderId"]) for o in order_reports if o.get("orderId") is not None]

            return {
                "order_list_id": str(result.get("orderListId")),
                "leg_order_ids": leg_order_ids,
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
            }

        except BinanceAPIException as e:
            if e.code == -1121:
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            elif e.code == -2010:
                raise InsufficientBalanceError(f"Insufficient balance: {e.message}")
            elif e.code in [-1013, -1111, -2011]:
                raise OrderRejectError(f"OCO order rejected: {e.message}")
            elif e.code == -1003:
                raise RateLimitError(f"Rate limit exceeded: {e.message}")
            else:
                logger.error(f"Binance API error placing OCO order: {e.message}")
                raise ExchangeError(f"Failed to place OCO order: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error placing OCO order: {e}")
            raise ExchangeError(f"Failed to place OCO order: {e}")

    async def cancel_oco_order(self, symbol: str, leg_order_id: str) -> Dict[str, Any]:
        """Cancel a resting OCO order by one of its leg order IDs.

        Cancelling either leg cancels the whole OCO pair on Binance, so this
        delegates to the regular cancel_order path (already battle-tested).
        """
        return await self.cancel_order(symbol, leg_order_id)

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Cancel an open order on Binance.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            order_id: Exchange order ID.

        Returns:
            Dictionary with cancellation confirmation.

        Raises:
            InvalidSymbolError: If symbol is invalid.
            OrderNotFoundError: If order doesn't exist.
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        symbol = self.normalize_symbol(symbol)

        try:
            result = await self.client.cancel_order(symbol=symbol, orderId=int(order_id))

            return {
                "order_id": str(result["orderId"]),
                "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc),
            }

        except BinanceAPIException as e:
            if e.code == -1121:
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            elif e.code == -2011:  # Order not found
                raise OrderNotFoundError(f"Order {order_id} not found")
            else:
                logger.error(f"Binance API error cancelling order: {e.message}")
                raise ExchangeError(f"Failed to cancel order: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error cancelling order: {e}")
            raise ExchangeError(f"Failed to cancel order: {e}")

    async def get_order_status(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Get status of an order on Binance.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            order_id: Exchange order ID.

        Returns:
            Dictionary with order status.

        Raises:
            InvalidSymbolError: If symbol is invalid.
            OrderNotFoundError: If order doesn't exist.
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        symbol = self.normalize_symbol(symbol)

        try:
            order = await self.client.get_order(symbol=symbol, orderId=int(order_id))
            return self._normalize_order(order)

        except BinanceAPIException as e:
            if e.code == -1121:
                raise InvalidSymbolError(f"Invalid symbol: {symbol}")
            elif e.code == -2013:  # Order not found
                raise OrderNotFoundError(f"Order {order_id} not found")
            else:
                logger.error(f"Binance API error fetching order status: {e.message}")
                raise ExchangeError(f"Failed to fetch order status: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error fetching order status: {e}")
            raise ExchangeError(f"Failed to fetch order status: {e}")

    async def get_open_orders(
        self, symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all open orders on Binance.

        Args:
            symbol: Optional trading pair to filter by.

        Returns:
            List of order dictionaries.

        Raises:
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        try:
            if symbol:
                symbol = self.normalize_symbol(symbol)
                orders = await self.client.get_open_orders(symbol=symbol)
            else:
                orders = await self.client.get_open_orders()

            return [self._normalize_order(order) for order in orders]

        except BinanceAPIException as e:
            logger.error(f"Binance API error fetching open orders: {e.message}")
            raise ExchangeError(f"Failed to fetch open orders: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error fetching open orders: {e}")
            raise ExchangeError(f"Failed to fetch open orders: {e}")

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol format to Binance format.

        Args:
            symbol: Symbol in any format (e.g., "BTC/USDT", "BTCUSDT").

        Returns:
            Symbol in Binance format (e.g., "BTCUSDT").
        """
        # Remove slashes and convert to uppercase
        return symbol.replace("/", "").replace("-", "").upper()

    def normalize_timeframe(self, timeframe: str) -> str:
        """Normalize timeframe format to Binance format.

        Args:
            timeframe: Timeframe in standard format (e.g., "15m", "1h", "1d").

        Returns:
            Binance timeframe constant.

        Raises:
            InvalidTimeframeError: If timeframe is not supported.
        """
        if timeframe not in self.TIMEFRAME_MAP:
            raise InvalidTimeframeError(
                f"Invalid timeframe: {timeframe}. "
                f"Supported: {', '.join(self.TIMEFRAME_MAP.keys())}"
            )
        return self.TIMEFRAME_MAP[timeframe]

    def _normalize_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Binance order response to standard format.

        Args:
            order: Raw order data from Binance API.

        Returns:
            Normalized order dictionary.
        """
        # Log raw order for debugging
        logger.debug(f"Normalizing order response: {order}")

        # Map Binance status to our status
        status_map = {
            "NEW": "pending",
            "PARTIALLY_FILLED": "pending",
            "FILLED": "filled",
            "CANCELED": "cancelled",
            "PENDING_CANCEL": "pending",
            "REJECTED": "rejected",
            "EXPIRED": "cancelled",
        }

        # Get status with fallback
        binance_status = order.get("status", "UNKNOWN")
        status = status_map.get(binance_status, "unknown")

        filled_qty = Decimal(order.get("executedQty", "0"))
        total_qty = Decimal(order.get("origQty", "0"))

        # Calculate average fill price
        filled_price = None
        if filled_qty > 0:
            cumulative_quote = Decimal(order.get("cummulativeQuoteQty", "0"))
            filled_price = cumulative_quote / filled_qty if filled_qty > 0 else None

        # Handle missing fields gracefully
        try:
            order_id = str(order["orderId"])
        except KeyError:
            logger.error(f"Order response missing orderId: {order}")
            raise

        return {
            "order_id": order_id,
            "symbol": order.get("symbol", ""),
            "side": order.get("side", "").lower(),
            "type": order.get("type", "").lower(),
            "quantity": total_qty,
            "price": Decimal(order["price"]) if order.get("price") else None,
            "filled_quantity": filled_qty,
            "filled_price": filled_price,
            "status": status,
            "created_at": datetime.fromtimestamp(order.get("time", 0) / 1000, tz=timezone.utc) if order.get("time") else datetime.now(timezone.utc),
            "updated_at": datetime.fromtimestamp(order.get("updateTime", 0) / 1000, tz=timezone.utc) if order.get("updateTime") else datetime.now(timezone.utc),
        }

    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Get symbol trading rules and precision info from Binance.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").

        Returns:
            Dictionary with symbol filters and precision info.

        Raises:
            ExchangeError: If Binance API returns an error.
        """
        if not self.client:
            raise ConnectionError("Not connected to Binance. Call connect() first.")

        symbol = self.normalize_symbol(symbol)

        # Check cache first
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]

        try:
            exchange_info = await self.client.get_exchange_info()

            for s in exchange_info["symbols"]:
                if s["symbol"] == symbol:
                    # Extract key filters
                    info = {
                        "symbol": symbol,
                        "base_asset": s["baseAsset"],
                        "quote_asset": s["quoteAsset"],
                        "base_asset_precision": s["baseAssetPrecision"],
                        "quote_asset_precision": s["quoteAssetPrecision"],
                    }

                    # Extract LOT_SIZE filter (quantity precision)
                    for f in s["filters"]:
                        if f["filterType"] == "LOT_SIZE":
                            info["lot_size_min"] = Decimal(f["minQty"])
                            info["lot_size_max"] = Decimal(f["maxQty"])
                            info["lot_size_step"] = Decimal(f["stepSize"])
                        elif f["filterType"] == "PRICE_FILTER":
                            info["price_min"] = Decimal(f["minPrice"])
                            info["price_max"] = Decimal(f["maxPrice"])
                            info["price_tick"] = Decimal(f["tickSize"])

                    # Cache it
                    self._symbol_info_cache[symbol] = info
                    logger.debug(f"Cached symbol info for {symbol}: {info}")
                    return info

            raise InvalidSymbolError(f"Symbol {symbol} not found in exchange info")

        except BinanceAPIException as e:
            logger.error(f"Binance API error fetching symbol info: {e.message}")
            raise ExchangeError(f"Failed to fetch symbol info: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error fetching symbol info: {e}")
            raise ExchangeError(f"Failed to fetch symbol info: {e}")

    def _format_quantity(self, quantity: Decimal, step_size: Decimal) -> str:
        """Format quantity according to Binance LOT_SIZE step size.

        Args:
            quantity: Raw quantity value.
            step_size: Step size from symbol LOT_SIZE filter.

        Returns:
            Formatted quantity string.
        """
        # Calculate precision from step_size
        # step_size examples: 0.00001000 -> 5 decimals, 1.00000000 -> 0 decimals
        step_str = f"{step_size:.8f}".rstrip('0')
        if '.' in step_str:
            precision = len(step_str.split('.')[1])
        else:
            precision = 0

        # Round down to step_size (never round up to avoid exceeding balance)
        # quantity_rounded = floor(quantity / step_size) * step_size
        from decimal import ROUND_DOWN
        quantity_rounded = (quantity / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size

        # Format to precision (remove trailing zeros)
        formatted = f"{quantity_rounded:.{precision}f}".rstrip('0').rstrip('.')

        return formatted

    def _format_price(self, price: Decimal, tick_size: Decimal) -> str:
        """Format price according to Binance PRICE_FILTER tick size.

        Args:
            price: Raw price value.
            tick_size: Tick size from symbol PRICE_FILTER filter.

        Returns:
            Formatted price string.
        """
        # Calculate precision from tick_size
        tick_str = f"{tick_size:.8f}".rstrip('0')
        if '.' in tick_str:
            precision = len(tick_str.split('.')[1])
        else:
            precision = 0

        # Round to nearest tick_size
        from decimal import ROUND_HALF_UP
        price_rounded = (price / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick_size

        # Format to precision (remove trailing zeros)
        formatted = f"{price_rounded:.{precision}f}".rstrip('0').rstrip('.')

        return formatted
