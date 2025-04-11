import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from decouple import config
from typing import Optional, Dict, List, Any

# Configure logging
log = logging.getLogger(__name__)

class BinanceClientWrapper:
    """Handles interactions with the Binance API."""

    def __init__(self):
        self.api_key = config("BINANCE_API_KEY", default=None)
        self.secret_key = config("BINANCE_SECRET_KEY", default=None)

        if not self.api_key or not self.secret_key:
            log.error("Binance API Key or Secret Key not configured in environment.")
            # In a real app, might prevent instantiation or raise specific config error
            self.client = None
        else:
            try:
                # Consider adding testnet=True parameter if using Binance testnet
                self.client = Client(self.api_key, self.secret_key)
                # Test connection
                self.client.ping()
                log.info("Binance client initialized and connection successful.")
            except BinanceAPIException as e:
                log.error(f"Binance API connection error: {e}")
                self.client = None
            except Exception as e:
                log.error(f"Error initializing Binance client: {e}")
                self.client = None

    def is_ready(self) -> bool:
        """Check if the client was initialized successfully."""
        return self.client is not None

    def get_symbol_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Gets the latest price ticker for a symbol."""
        if not self.is_ready(): return None
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            log.debug(f"Ticker for {symbol}: {ticker}")
            return ticker
        except BinanceAPIException as e:
            log.error(f"Binance API error getting ticker for {symbol}: {e}")
            return None
        except Exception as e:
            log.exception(f"Unexpected error getting ticker for {symbol}: {e}")
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Gets the current price for a symbol."""
        ticker = self.get_symbol_ticker(symbol)
        if ticker and 'price' in ticker:
            try:
                return float(ticker['price'])
            except (ValueError, TypeError):
                log.error(f"Could not convert ticker price to float for {symbol}: {ticker['price']}")
                return None
        return None

    def create_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> Optional[Dict[str, Any]]:
        """Creates a limit order (BUY or SELL)."""
        if not self.is_ready(): return None
        try:
            # Format price and quantity according to symbol filters (precision, min/max qty) - IMPORTANT for production
            # For MVP, we assume parameters are pre-validated/formatted
            log.info(f"Placing limit order: {side} {quantity} {symbol} @ {price}")
            order = self.client.create_order(
                symbol=symbol,
                side=side, # 'BUY' or 'SELL'
                type=Client.ORDER_TYPE_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC, # Good 'Til Canceled
                quantity=quantity,
                price=f'{price:.8f}' # Format price string appropriately
            )
            log.info(f"Order placed successfully: {order}")
            return order
        except BinanceAPIException as e:
            log.error(f"Binance API error creating order ({side} {quantity} {symbol} @ {price}): {e}")
            return None
        except BinanceOrderException as e:
            log.error(f"Binance order error creating order ({side} {quantity} {symbol} @ {price}): {e}")
            return None
        except Exception as e:
            log.exception(f"Unexpected error creating order: {e}")
            return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gets open orders for a specific symbol or all symbols."""
        if not self.is_ready(): return []
        try:
            params = {"symbol": symbol} if symbol else {}
            open_orders = self.client.get_open_orders(**params)
            log.debug(f"Found {len(open_orders)} open orders for {symbol or 'all symbols'}.")
            return open_orders
        except BinanceAPIException as e:
            log.error(f"Binance API error getting open orders for {symbol or 'all symbols'}: {e}")
            return []
        except Exception as e:
            log.exception(f"Unexpected error getting open orders: {e}")
            return []

    def cancel_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Cancels an existing order."""
        if not self.is_ready(): return None
        try:
            log.info(f"Cancelling order: {symbol} / {order_id}")
            result = self.client.cancel_order(symbol=symbol, orderId=order_id)
            log.info(f"Order cancellation result: {result}")
            return result
        except BinanceAPIException as e:
            log.error(f"Binance API error cancelling order {order_id} for {symbol}: {e}")
            # Check if error indicates order already filled/cancelled
            if e.code == -2011: # Order filled or cancelled code
                 log.warning(f"Order {order_id} likely already filled or cancelled.")
                 # Consider returning a specific status or the error itself
                 return {"status": "NOT_FOUND", "message": str(e)}
            return None
        except BinanceOrderException as e:
             log.error(f"Binance order error cancelling order {order_id} for {symbol}: {e}")
             return None
        except Exception as e:
            log.exception(f"Unexpected error cancelling order: {e}")
            return None

    def get_asset_balance(self, asset: str) -> Optional[Dict[str, Any]]:
        """Gets the balance for a specific asset."""
        if not self.is_ready(): return None
        try:
            balance = self.client.get_asset_balance(asset=asset)
            log.debug(f"Balance for {asset}: {balance}")
            return balance
        except BinanceAPIException as e:
            log.error(f"Binance API error getting balance for {asset}: {e}")
            return None
        except Exception as e:
            log.exception(f"Unexpected error getting balance for {asset}: {e}")
            return None

# Singleton instance (optional, manage lifecycle appropriately in your app)
# binance_client = BinanceClientWrapper()
