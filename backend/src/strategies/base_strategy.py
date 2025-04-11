import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
import json # For parsing messages

from ..core.binance_client import BinanceClientWrapper
from ..persistence import crud, database, models
from ..persistence.models import AgentStatusEnum
# Import communication bus
from ..communication.redis_pubsub import CommunicationBus, AGENT_EVENTS_CHANNEL, GROUP_UPDATES_CHANNEL, LEARNING_MODULE_CHANNEL

log = logging.getLogger(__name__)

class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(self, agent_id: int, config: Dict[str, Any], db_session: Session, binance_client: BinanceClientWrapper, comm_bus: Optional[CommunicationBus] = None):
        self.agent_id = agent_id
        self.config = config # Initial config
        self.db: Session = db_session
        self.binance_client = binance_client
        self.comm_bus = comm_bus # Optional communication bus instance

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.strategy_name = self.__class__.__name__
        self.current_parameters = config.copy() # Store runtime parameters separately

        log.info(f"[{self.strategy_name}-{self.agent_id}] Initializing strategy.")

        if not self.binance_client or not self.binance_client.is_ready():
             log.error(f"[{self.strategy_name}-{self.agent_id}] Binance client not ready. Strategy cannot run.")
             # Update status immediately if client fails on init
             self._update_status(AgentStatusEnum.ERROR, "Binance client initialization failed")
             raise ConnectionError("Binance client not ready") # Prevent strategy start

    def _update_status(self, status: AgentStatusEnum, message: Optional[str] = None):
        """Helper to update agent status in the database."""
        try:
            crud.update_agent_status(self.db, self.agent_id, status, message)
            log.info(f"[{self.strategy_name}-{self.agent_id}] Status updated to {status.value}" + (f": {message}" if message else ""))
        except Exception as e:
            log.exception(f"[{self.strategy_name}-{self.agent_id}] CRITICAL: Failed to update agent status to {status.value} in DB: {e}")
            # This is serious, as the agent state might be inconsistent

    def _record_trade(self, trade_data: Dict[str, Any]):
        """Helper to record a trade in the database."""
        # Basic validation
        if not trade_data or not trade_data.get('orderId'):
            log.warning(f"[{self.strategy_name}-{self.agent_id}] Attempted to record invalid trade data: {trade_data}")
            return
        try:
            # TODO: Calculate PnL for the trade before saving (complex, requires tracking fills/positions)
            trade_data['pnl_usd'] = None # Placeholder
            crud.create_trade(self.db, self.agent_id, trade_data)
            log.info(f"[{self.strategy_name}-{self.agent_id}] Trade recorded: OrderID {trade_data.get('orderId')}")

            # Publish trade event (optional)
            if self.comm_bus and self.comm_bus.is_ready():
                 event_data = {
                     "type": "trade_executed",
                     "agent_id": self.agent_id,
                     "group_id": crud.get_agent_by_id(self.db, self.agent_id).group_id, # Fetch group ID
                     "payload": trade_data # Send Binance order data
                 }
                 self.comm_bus.publish(AGENT_EVENTS_CHANNEL, event_data)

        except Exception as e:
            log.exception(f"[{self.strategy_name}-{self.agent_id}] Failed to record trade in DB: {e}")

    @abstractmethod
    def _run_logic(self):
        """The core trading logic loop specific to the strategy."""
        pass

    @abstractmethod
    def _adapt_parameters(self, new_params: Dict[str, Any]):
        """Applies updated parameters received from learning module/comm bus."""
        # Example: self.current_parameters.update(new_params)
        # Re-calculate grid lines, adjust order sizes etc. based on new params
        log.info(f"[{self.strategy_name}-{self.agent_id}] Adapting parameters (placeholder): {new_params}")
        pass

    def _handle_comm_message(self, message_data: Dict[str, Any]):
        """Handles messages received on subscribed communication channels."""
        log.debug(f"[{self.strategy_name}-{self.agent_id}] Received message: {message_data}")
        msg_type = message_data.get("type")
        payload = message_data.get("payload")

        if not msg_type or not payload:
            log.warning(f"[{self.strategy_name}-{self.agent_id}] Received invalid message format.")
            return

        # --- Placeholder Logic for Handling Messages ---
        if msg_type == "parameter_update" and payload.get("agent_id") == self.agent_id:
            log.info(f"[{self.strategy_name}-{self.agent_id}] Received parameter update suggestion: {payload.get('params')}")
            # TODO: Add validation and safety checks before applying
            # self._adapt_parameters(payload.get('params', {}))
        elif msg_type == "group_signal" and payload.get("group_id") == crud.get_agent_by_id(self.db, self.agent_id).group_id:
             log.info(f"[{self.strategy_name}-{self.agent_id}] Received group signal: {payload.get('signal')}")
             # TODO: Implement logic based on group signals (e.g., pause trading, adjust risk)
        else:
             log.debug(f"[{self.strategy_name}-{self.agent_id}] Ignoring irrelevant message type '{msg_type}' or target.")


    def _run_loop(self):
        """Internal method that runs the strategy logic in a loop."""
        log.info(f"[{self.strategy_name}-{self.agent_id}] Starting run loop.")

        # --- Subscribe to relevant communication channels ---
        if self.comm_bus and self.comm_bus.is_ready():
             # Subscribe to messages targeted at this agent or its group
             self.comm_bus.subscribe(LEARNING_MODULE_CHANNEL, self._handle_comm_message)
             # Potentially subscribe to GROUP_UPDATES_CHANNEL as well if needed
             # self.comm_bus.subscribe(GROUP_UPDATES_CHANNEL, self._handle_comm_message)
        else:
             log.warning(f"[{self.strategy_name}-{self.agent_id}] Communication bus not available. Running without inter-agent communication/learning.")

        self._update_status(AgentStatusEnum.RUNNING)
        try:
            while not self._stop_event.is_set():
                # --- Core Logic Execution ---
                try:
                    self._run_logic()
                except BinanceAPIException as e: # Catch specific Binance errors if defined
                     log.error(f"[{self.strategy_name}-{self.agent_id}] Binance API Error in run loop: {e}. Status Code: {getattr(e, 'status_code', 'N/A')}, Message: {getattr(e, 'message', str(e))}")
                     # Decide on action: retry, stop, update status?
                     status_code = getattr(e, 'status_code', None)
                     if status_code == 429: # Rate limit
                         log.warning(f"[{self.strategy_name}-{self.agent_id}] Rate limited. Sleeping for 60s.")
                         time.sleep(60)
                     elif status_code == 418: # IP Banned
                          log.critical(f"[{self.strategy_name}-{self.agent_id}] IP Banned by Binance! Stopping agent.")
                          self._update_status(AgentStatusEnum.ERROR, f"IP Banned by Binance: {getattr(e, 'message', str(e))}")
                          self._stop_event.set() # Signal stop
                     else:
                          # Other API errors, maybe retry after a short delay
                          log.warning(f"[{self.strategy_name}-{self.agent_id}] Retrying after API error.")
                          time.sleep(10)
                except Exception as e:
                    log.exception(f"[{self.strategy_name}-{self.agent_id}] Unhandled exception in strategy logic: {e}")
                    self._update_status(AgentStatusEnum.ERROR, f"Unhandled exception: {str(e)[:200]}")
                    # Consider stopping the agent on unhandled errors
                    break # Exit loop on critical error

                # Check stop event again before sleeping
                if self._stop_event.is_set():
                    break

                # --- Sleep ---
                # Use current_parameters which might be adapted
                loop_interval = self.current_parameters.get("loop_interval_seconds", 10)
                time.sleep(loop_interval)

        except Exception as e:
             # Catch errors during loop setup/teardown (e.g., initial comm_bus subscription)
             log.exception(f"[{self.strategy_name}-{self.agent_id}] Critical error in run loop execution: {e}")
             self._update_status(AgentStatusEnum.ERROR, f"Critical loop error: {str(e)[:200]}")
        finally:
            log.info(f"[{self.strategy_name}-{self.agent_id}] Run loop finishing...")
            # Determine final status based on whether stop was requested or an error occurred
            final_status = AgentStatusEnum.STOPPED if self._stop_event.is_set() else AgentStatusEnum.ERROR
            self._update_status(final_status, "Run loop terminated")
            # Close the dedicated DB session for this thread
            if self.db:
                 self.db.close()
                 log.info(f"[{self.strategy_name}-{self.agent_id}] DB session closed.")
            # Note: CommBus listener thread is managed separately and not stopped here.

    def start(self):
        """Starts the strategy execution in a separate thread."""
        if self._thread is not None and self._thread.is_alive():
            log.warning(f"[{self.strategy_name}-{self.agent_id}] Strategy thread already running.")
            return

        log.info(f"[{self.strategy_name}-{self.agent_id}] Creating and starting strategy thread.")
        self._stop_event.clear()
        # Ensure the target is the internal loop runner
        self._thread = threading.Thread(target=self._run_loop, name=f"{self.strategy_name}-{self.agent_id}", daemon=True)
        self._thread.start()

    def stop(self):
        """Signals the strategy execution thread to stop."""
        if self._thread is None or not self._thread.is_alive():
            log.warning(f"[{self.strategy_name}-{self.agent_id}] Strategy thread is not running or already stopped.")
            # Ensure status is updated if thread died unexpectedly
            current_status = crud.get_agent_by_id(self.db, self.agent_id).status
            if current_status not in [AgentStatusEnum.STOPPED, AgentStatusEnum.STOPPING]:
                 self._update_status(AgentStatusEnum.STOPPED, "Stop requested but thread not found/alive")
            return

        log.info(f"[{self.strategy_name}-{self.agent_id}] Signaling strategy thread to stop.")
        self._stop_event.set()
        # Optional: Wait for thread to finish with a timeout
        # self._thread.join(timeout=30)
        # if self._thread.is_alive():
        #     log.warning(f"[{self.strategy_name}-{self.agent_id}] Strategy thread did not stop within timeout.")
        # else:
        #     log.info(f"[{self.strategy_name}-{self.agent_id}] Strategy thread stopped.")

# --- Custom Exceptions ---
class StrategyConfigError(ValueError):
    """Custom exception for strategy configuration errors."""
    pass

class BinanceAPIException(Exception):
     """Custom exception wrapper for Binance API errors."""
     def __init__(self, status_code, message):
         self.status_code = status_code
         self.message = message
         super().__init__(f"Binance API Error: Status Code {status_code}, Message: {message}")
