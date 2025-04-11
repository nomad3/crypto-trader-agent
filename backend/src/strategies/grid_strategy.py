import logging
import time
import math
from decimal import Decimal, ROUND_DOWN, ROUND_UP # For precise calculations
from typing import Dict, Any, List, Optional, Tuple

from .base_strategy import BaseStrategy, StrategyConfigError, BinanceAPIException
from ..persistence.models import AgentStatusEnum

log = logging.getLogger(__name__)

# Constants (could be moved to config or symbol info)
ORDER_STATUS_FILLED = 'FILLED'
ORDER_STATUS_NEW = 'NEW'
ORDER_STATUS_PARTIALLY_FILLED = 'PARTIALLY_FILLED'
ORDER_STATUS_CANCELED = 'CANCELED'
ORDER_STATUS_REJECTED = 'REJECTED'
ORDER_STATUS_EXPIRED = 'EXPIRED'

class GridStrategy(BaseStrategy):
    """
    Implements a basic grid trading strategy.

    Places buy orders below the current price and sell orders above,
    aiming to profit from price fluctuations within a defined range.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.strategy_name = "GridStrategy" # Override for logging
        self.symbol: str = ""
        self.lower_price: Decimal = Decimal(0)
        self.upper_price: Decimal = Decimal(0)
        self.grid_levels: int = 0
        self.order_amount_usd: Decimal = Decimal(0)
        self.grid_lines: List[Decimal] = []
        self.step_size: Decimal = Decimal(0)
        self.last_price: Optional[Decimal] = None

        # Runtime state (simple in-memory tracking for MVP)
        self.open_buy_orders: Dict[str, Dict] = {} # {clientOrderId: order_details}
        self.open_sell_orders: Dict[str, Dict] = {} # {clientOrderId: order_details}

        self._validate_and_set_config()
        log.info(f"[{self.strategy_name}-{self.agent_id}] Initialized for {self.symbol} "
                 f"Range: {self.lower_price}-{self.upper_price}, Levels: {self.grid_levels}, "
                 f"Order USD: {self.order_amount_usd}")

    def _validate_and_set_config(self):
        """Validates required configuration parameters."""
        required_keys = ["symbol", "lower_price", "upper_price", "grid_levels", "order_amount_usd"]
        for key in required_keys:
            if key not in self.config:
                raise StrategyConfigError(f"Missing required config key: {key}")

        self.symbol = self.config["symbol"]
        try:
            self.lower_price = Decimal(str(self.config["lower_price"]))
            self.upper_price = Decimal(str(self.config["upper_price"]))
            self.grid_levels = int(self.config["grid_levels"])
            self.order_amount_usd = Decimal(str(self.config["order_amount_usd"]))
        except (ValueError, TypeError) as e:
            raise StrategyConfigError(f"Invalid numeric config value: {e}")

        if self.lower_price >= self.upper_price:
            raise StrategyConfigError("lower_price must be less than upper_price")
        if self.grid_levels < 2:
            raise StrategyConfigError("grid_levels must be at least 2")
        if self.order_amount_usd <= 0:
             raise StrategyConfigError("order_amount_usd must be positive")

        # Calculate grid lines (simple linear grid for MVP)
        self.step_size = (self.upper_price - self.lower_price) / Decimal(self.grid_levels - 1)
        self.grid_lines = [self.lower_price + i * self.step_size for i in range(self.grid_levels)]
        log.debug(f"[{self.strategy_name}-{self.agent_id}] Calculated grid lines: {self.grid_lines}")

        # TODO: Fetch symbol info from Binance (min order size, price/qty precision) and validate config against it.

    def _get_current_price(self) -> Optional[Decimal]:
        """Fetches and returns the current market price."""
        try:
            price_float = self.binance_client.get_current_price(self.symbol)
            if price_float is not None:
                self.last_price = Decimal(str(price_float))
                log.debug(f"[{self.strategy_name}-{self.agent_id}] Current price for {self.symbol}: {self.last_price}")
                return self.last_price
            else:
                log.warning(f"[{self.strategy_name}-{self.agent_id}] Could not fetch price for {self.symbol}")
                return None
        except Exception as e:
            log.exception(f"[{self.strategy_name}-{self.agent_id}] Error fetching price: {e}")
            return None

    def _place_initial_orders(self):
        """Places the initial grid of buy and sell orders."""
        log.info(f"[{self.strategy_name}-{self.agent_id}] Placing initial grid orders...")
        current_price = self._get_current_price()
        if current_price is None:
            log.error(f"[{self.strategy_name}-{self.agent_id}] Cannot place initial orders without current price.")
            self._update_status(AgentStatusEnum.ERROR, "Failed to get initial price")
            self._stop_event.set() # Stop the agent
            return

        # Cancel any existing open orders for this agent first (safety measure)
        self._cancel_all_open_orders()
        time.sleep(1) # Small delay after cancelling

        # Determine quantity based on USD amount and price level
        # TODO: Use proper precision from symbol info
        qty_precision = 8 # Placeholder

        for price in self.grid_lines:
            if self._stop_event.is_set(): return # Check if stopped during placement

            order_qty = (self.order_amount_usd / price).quantize(Decimal(f'1e-{qty_precision}'), rounding=ROUND_DOWN)
            # TODO: Check against min/max order size from symbol info

            if order_qty <= 0:
                 log.warning(f"[{self.strategy_name}-{self.agent_id}] Calculated order quantity is zero or less for price {price}. Skipping.")
                 continue

            price_str = f"{price:.8f}" # TODO: Use price precision from symbol info

            if price < current_price:
                # Place BUY order
                log.debug(f"[{self.strategy_name}-{self.agent_id}] Placing BUY @ {price_str}, Qty: {order_qty}")
                order = self.binance_client.create_limit_order(
                    symbol=self.symbol, side='BUY', quantity=float(order_qty), price=float(price)
                )
                if order:
                    self.open_buy_orders[order['clientOrderId']] = order # Track open order
                else:
                    log.error(f"[{self.strategy_name}-{self.agent_id}] Failed to place BUY order at {price_str}")
                    # Consider stopping or retrying based on error

            elif price > current_price:
                # Place SELL order
                log.debug(f"[{self.strategy_name}-{self.agent_id}] Placing SELL @ {price_str}, Qty: {order_qty}")
                order = self.binance_client.create_limit_order(
                    symbol=self.symbol, side='SELL', quantity=float(order_qty), price=float(price)
                )
                if order:
                    self.open_sell_orders[order['clientOrderId']] = order # Track open order
                else:
                    log.error(f"[{self.strategy_name}-{self.agent_id}] Failed to place SELL order at {price_str}")

            time.sleep(0.2) # Small delay between orders to avoid rate limits

        log.info(f"[{self.strategy_name}-{self.agent_id}] Initial grid placement complete. Buys: {len(self.open_buy_orders)}, Sells: {len(self.open_sell_orders)}")

    def _check_and_replace_orders(self):
        """Checks status of open orders and places opposing orders when filled."""
        log.debug(f"[{self.strategy_name}-{self.agent_id}] Checking open orders...")
        if not self.open_buy_orders and not self.open_sell_orders:
             log.warning(f"[{self.strategy_name}-{self.agent_id}] No open orders found. Re-placing initial grid.")
             # This might happen if all orders were cancelled or filled unexpectedly
             self._place_initial_orders()
             return

        # Combine orders for checking (create copies to avoid modifying during iteration)
        orders_to_check = list(self.open_buy_orders.values()) + list(self.open_sell_orders.values())

        for order in orders_to_check:
            if self._stop_event.is_set(): return
            order_id = order.get('orderId')
            client_order_id = order.get('clientOrderId')
            if not order_id or not client_order_id: continue # Skip if missing IDs

            try:
                # Query order status from Binance
                # TODO: Implement get_order method in binance_client
                # order_status = self.binance_client.get_order(symbol=self.symbol, orderId=order_id)
                # For MVP - simulate checking status (replace with actual API call)
                order_status = self._simulate_get_order_status(order)
                time.sleep(0.1) # Small delay

                if not order_status:
                    log.warning(f"[{self.strategy_name}-{self.agent_id}] Could not get status for order {order_id}. Skipping.")
                    continue

                status = order_status.get('status')
                log.debug(f"[{self.strategy_name}-{self.agent_id}] Order {order_id} status: {status}")

                if status == ORDER_STATUS_FILLED:
                    log.info(f"[{self.strategy_name}-{self.agent_id}] Order FILLED: {order['side']} {order['origQty']} @ {order['price']}")

                    # --- PnL Calculation (Simplified Example) ---
                    trade_pnl: Optional[float] = None
                    try:
                        filled_qty = Decimal(order_status.get('executedQty', '0'))
                        filled_price = Decimal(order_status.get('price', '0')) # Price level of the filled order
                        commission = Decimal(order_status.get('commission', '0') or '0')
                        # TODO: Handle commission asset conversion to quote asset (USD)

                        if order['side'] == 'SELL' and filled_qty > 0:
                            # Assume this SELL closes a previous BUY at the grid level below
                            # WARNING: Highly simplified, needs proper position/cost basis tracking
                            buy_price_level = filled_price - self.step_size
                            # Calculate approximate PnL for this pair of trades
                            pnl = (filled_price - buy_price_level) * filled_qty - commission # Simplified PnL
                            trade_pnl = float(pnl)
                            log.info(f"[{self.strategy_name}-{self.agent_id}] Calculated PnL for sell @ {filled_price}: {trade_pnl:.4f} USD (Simplified)")
                        elif order['side'] == 'BUY':
                             # PnL is typically realized on the closing (SELL) trade in this simple model
                             pass

                    except Exception as pnl_err:
                         log.error(f"[{self.strategy_name}-{self.agent_id}] Error calculating PnL for order {order_id}: {pnl_err}")

                    # Record the filled trade, passing the calculated PnL
                    self._record_trade(order_status, pnl_usd=trade_pnl) # Pass full status dict and PnL

                    # Remove from open orders tracking
                    if order['side'] == 'BUY':
                        self.open_buy_orders.pop(client_order_id, None)
                        # Place corresponding SELL order one grid level up
                        filled_price = Decimal(order['price'])
                        sell_price = filled_price + self.step_size
                        if sell_price <= self.upper_price:
                             self._place_single_order('SELL', sell_price, Decimal(order['origQty']))
                        else:
                             log.info(f"[{self.strategy_name}-{self.agent_id}] Buy filled at {filled_price}, but next sell level {sell_price} is above upper bound. Not placing sell.")
                    else: # SELL filled
                        self.open_sell_orders.pop(client_order_id, None)
                        # Place corresponding BUY order one grid level down
                        filled_price = Decimal(order['price'])
                        buy_price = filled_price - self.step_size
                        if buy_price >= self.lower_price:
                             self._place_single_order('BUY', buy_price, Decimal(order['origQty']))
                        else:
                             log.info(f"[{self.strategy_name}-{self.agent_id}] Sell filled at {filled_price}, but next buy level {buy_price} is below lower bound. Not placing buy.")

                elif status in [ORDER_STATUS_CANCELED, ORDER_STATUS_REJECTED, ORDER_STATUS_EXPIRED]:
                    log.warning(f"[{self.strategy_name}-{self.agent_id}] Order {order_id} is {status}. Removing from tracking.")
                    # Remove from tracking, might need logic to replace it depending on strategy
                    if order['side'] == 'BUY':
                        self.open_buy_orders.pop(client_order_id, None)
                    else:
                        self.open_sell_orders.pop(client_order_id, None)
                    # TODO: Consider logic to replace cancelled/expired orders to maintain grid density

            except Exception as e:
                log.exception(f"[{self.strategy_name}-{self.agent_id}] Error checking order {order_id}: {e}")

    def _place_single_order(self, side: str, price: Decimal, quantity: Decimal):
        """Places a single limit order and tracks it."""
        if self._stop_event.is_set(): return

        # TODO: Use precision from symbol info
        price_str = f"{price:.8f}"
        qty_str = f"{quantity:.8f}"
        log.info(f"[{self.strategy_name}-{self.agent_id}] Placing single order: {side} {qty_str} {self.symbol} @ {price_str}")

        order = self.binance_client.create_limit_order(
            symbol=self.symbol, side=side, quantity=float(quantity), price=float(price)
        )

        if order:
            client_order_id = order['clientOrderId']
            if side == 'BUY':
                self.open_buy_orders[client_order_id] = order
            else:
                self.open_sell_orders[client_order_id] = order
            log.info(f"[{self.strategy_name}-{self.agent_id}] Single {side} order placed: ID {order['orderId']}")
        else:
            log.error(f"[{self.strategy_name}-{self.agent_id}] Failed to place single {side} order at {price_str}")
            # Consider retry logic or raising an alert/error status

    def _cancel_all_open_orders(self):
        """Cancels all tracked open orders for this agent."""
        log.warning(f"[{self.strategy_name}-{self.agent_id}] Cancelling all open orders...")
        orders_to_cancel = list(self.open_buy_orders.values()) + list(self.open_sell_orders.values())
        self.open_buy_orders.clear()
        self.open_sell_orders.clear()

        cancelled_count = 0
        failed_count = 0
        for order in orders_to_cancel:
             if self._stop_event.is_set(): return
             order_id = order.get('orderId')
             if not order_id: continue
             try:
                 result = self.binance_client.cancel_order(symbol=self.symbol, order_id=order_id)
                 if result:
                     log.info(f"[{self.strategy_name}-{self.agent_id}] Cancelled order {order_id}")
                     cancelled_count += 1
                 else:
                      log.warning(f"[{self.strategy_name}-{self.agent_id}] Failed to cancel order {order_id} (maybe already filled/cancelled?)")
                      failed_count += 1
                 time.sleep(0.1) # Avoid rate limits
             except Exception as e:
                 log.exception(f"[{self.strategy_name}-{self.agent_id}] Error cancelling order {order_id}: {e}")
                 failed_count += 1

        log.warning(f"[{self.strategy_name}-{self.agent_id}] Order cancellation finished. Cancelled: {cancelled_count}, Failed/Not Found: {failed_count}")


    def _run_logic(self):
        """Core logic loop for the grid strategy."""
        # Check open orders and replace filled ones
        self._check_and_replace_orders()

        # Optional: Add logic to adjust grid if price moves significantly out of range,
        # or to re-evaluate grid density/parameters periodically.

        # Optional: Check overall PnL or risk limits
        # summary = crud.calculate_agent_pnl_summary(self.db, self.agent_id)
        # if summary.get('realized_pnl_total_usd', 0) < some_stop_loss_threshold:
        #     log.warning(f"[{self.strategy_name}-{self.agent_id}] Stop loss triggered. Stopping agent.")
        #     self.stop()


    # --- Overrides ---

    def start(self):
        """Starts the strategy: places initial orders then runs the loop."""
        if self._thread is not None and self._thread.is_alive():
            log.warning(f"[{self.strategy_name}-{self.agent_id}] Strategy thread already running.")
            return

        log.info(f"[{self.strategy_name}-{self.agent_id}] Starting strategy...")
        self._update_status(AgentStatusEnum.STARTING)

        # Perform initial setup in the main thread before starting the loop thread
        try:
            self._place_initial_orders()
            # If initial placement fails and sets stop_event, don't start the thread
            if self._stop_event.is_set():
                 log.error(f"[{self.strategy_name}-{self.agent_id}] Failed during initial order placement. Not starting run loop.")
                 # Status should already be ERROR
                 return
        except Exception as e:
             log.exception(f"[{self.strategy_name}-{self.agent_id}] Error during initial order placement: {e}")
             self._update_status(AgentStatusEnum.ERROR, f"Initial placement failed: {str(e)[:100]}")
             return # Don't start thread

        # Start the background monitoring loop
        super().start() # Calls the base class start which creates/starts the thread

    def stop(self):
        """Stops the strategy: signals the loop and cancels open orders."""
        log.warning(f"[{self.strategy_name}-{self.agent_id}] Initiating strategy stop...")
        # Signal the run loop thread to stop first
        super().stop() # Calls the base class stop which sets the event

        # Cancel remaining open orders after signaling stop
        # Do this in the main thread (or a separate cleanup task)
        # Needs its own error handling
        try:
             self._cancel_all_open_orders()
        except Exception as e:
             log.exception(f"[{self.strategy_name}-{self.agent_id}] Error during final order cancellation on stop: {e}")
             # Don't change status here, let the run loop finish setting final status

        log.warning(f"[{self.strategy_name}-{self.agent_id}] Stop process initiated.")


    # --- Simulation Helper (Remove in production) ---
    def _simulate_get_order_status(self, order: Dict) -> Optional[Dict]:
         """Simulates checking order status. Replace with actual API call."""
         # Basic simulation: ~10% chance of being filled
         import random
         if random.random() < 0.1:
             log.debug(f"[SIMULATE] Order {order.get('orderId')} marked as FILLED")
             # Return a structure similar to Binance get_order response
             return {
                 **order, # Copy original details
                 "status": ORDER_STATUS_FILLED,
                 "executedQty": order.get('origQty'),
                 "cummulativeQuoteQty": str(Decimal(order.get('price')) * Decimal(order.get('origQty'))),
                 # Add other fields as needed
             }
         else:
             # Assume still NEW otherwise
             return {**order, "status": ORDER_STATUS_NEW}
