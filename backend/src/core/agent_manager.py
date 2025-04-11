# Manages running agent strategy instances (threads)

import time
import threading
import logging
from typing import Dict, Any, Optional, Type, List # Import List
from sqlalchemy.orm import Session

# Import necessary components
from ..strategies.base_strategy import BaseStrategy
from ..strategies.grid_strategy import GridStrategy
# from ..strategies.arbitrage_strategy import ArbitrageStrategy
from ..persistence import database
from .binance_client import BinanceClientWrapper
# Import communication bus
from ..communication.redis_pubsub import CommunicationBus

log = logging.getLogger(__name__)

# --- Strategy Mapping ---
# Maps strategy type string to the corresponding class
STRATEGY_MAP: Dict[str, Type[BaseStrategy]] = {
    "grid": GridStrategy,
    # "arbitrage": ArbitrageStrategy,
}

# --- Runtime Agent Store ---
# Stores references to running strategy instances and threads
# Key: agent_id (string representation of DB int ID)
# Value: {"instance": BaseStrategy, "thread": threading.Thread, "start_time": float, "comm_bus": CommunicationBus}
_running_agents: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

# --- Shared Services ---
# Create a single client instance to be shared by all agents
# Ensure API keys are loaded via decouple/dotenv before this is instantiated
# Handle potential initialization failure
try:
    binance_client_instance = BinanceClientWrapper()
    if not binance_client_instance.is_ready():
        log.critical("Agent Manager: Failed to initialize shared Binance Client. Agents requiring it will fail to start.")
        # Optionally raise an error to prevent app startup if Binance client is essential
        # raise RuntimeError("Failed to initialize Binance Client")
except Exception as e:
     log.critical(f"Agent Manager: Exception during shared Binance Client initialization: {e}")
     binance_client_instance = None

# Create a single communication bus instance (optional, could be managed elsewhere)
try:
    comm_bus_instance = CommunicationBus()
    if not comm_bus_instance.is_ready():
         log.warning("Agent Manager: Communication Bus failed to connect to Redis. Inter-agent features disabled.")
         comm_bus_instance = None # Set to None if not ready
except Exception as e:
     log.critical(f"Agent Manager: Exception during Communication Bus initialization: {e}")
     comm_bus_instance = None


def start_agent_process(agent_id: str, strategy_type: str, config: Dict[str, Any]) -> bool:
    """
    Instantiates and starts the strategy thread for a given agent.
    Returns True if start initiated successfully, False otherwise.
    """
    with _lock:
        if agent_id in _running_agents:
            log.warning(f"Agent Manager: Agent {agent_id} is already running.")
            return False

        log.info(f"Agent Manager: Attempting to start agent {agent_id} (Strategy: {strategy_type})...")

        # Get the strategy class
        StrategyClass = STRATEGY_MAP.get(strategy_type)
        if not StrategyClass:
            log.error(f"Agent Manager: Unknown strategy type '{strategy_type}' for agent {agent_id}.")
            return False

        if not binance_client_instance or not binance_client_instance.is_ready():
             log.error(f"Agent Manager: Cannot start agent {agent_id}, shared Binance client is not available.")
             return False

        # Create a new DB session specifically for this agent thread
        # Each thread needs its own session
        db_session: Session = next(database.get_db())

        try:
            # Instantiate the strategy
            strategy_instance = StrategyClass(
                agent_id=int(agent_id),
                config=config,
                db_session=db_session,
                binance_client=binance_client_instance,
                comm_bus=comm_bus_instance # Pass shared comm bus instance
            )

            # Start the strategy's run loop in a new thread
            # The start method now handles thread creation internally
            strategy_instance.start() # This creates and starts the thread

            # Store the instance and thread info
            _running_agents[agent_id] = {
                "instance": strategy_instance,
                "thread": strategy_instance._thread,
                "start_time": time.time(),
                "strategy_type": strategy_type,
                "comm_bus": comm_bus_instance # Store reference if needed later
            }
            log.info(f"Agent Manager: Strategy thread for agent {agent_id} started.")
            # Note: Status is updated to STARTING by API/Tool, then RUNNING/ERROR by the strategy thread itself.
            return True

        except ConnectionError as e:
             log.error(f"Agent Manager: Connection error during strategy init for agent {agent_id}: {e}")
             db_session.close() # Clean up session if init fails
             return False
        except Exception as e:
            log.exception(f"Agent Manager: Failed to instantiate or start strategy for agent {agent_id}: {e}")
            db_session.close() # Clean up session if init fails
            # Optionally update agent status to ERROR here? Or let API handle it.
            return False


def stop_agent_process(agent_id: str) -> bool:
    """
    Signals the strategy thread for a given agent to stop.
    Returns True if stop signal sent successfully, False otherwise.
    """
    with _lock:
        agent_info = _running_agents.get(agent_id)
        if not agent_info or not agent_info.get("instance"):
            log.warning(f"Agent Manager: Agent {agent_id} not found or no instance available for stopping.")
            # Check if thread object exists but instance doesn't (shouldn't happen)
            if agent_id in _running_agents:
                 _running_agents.pop(agent_id, None) # Clean up inconsistent entry
            return False

        log.info(f"Agent Manager: Signaling stop for agent {agent_id}...")
        strategy_instance: BaseStrategy = agent_info["instance"]

        try:
            # Call the strategy's stop method (which sets the event)
            strategy_instance.stop()

            # Remove from running agents dict *after* signaling stop
            # The thread itself will update final DB status and close its session
            _running_agents.pop(agent_id, None)
            log.info(f"Agent Manager: Stop signal sent to agent {agent_id} and removed from active tracking.")
            # Note: We don't join the thread here to avoid blocking the API request.
            # The thread should handle its own cleanup and final status update.
            return True
        except Exception as e:
            log.exception(f"Agent Manager: Error signaling stop for agent {agent_id}: {e}")
            # Attempt to remove from tracking anyway
            _running_agents.pop(agent_id, None)
            return False


def is_agent_running(agent_id: str) -> bool:
    """Checks if the agent is actively tracked by the manager."""
    with _lock:
        agent_info = _running_agents.get(agent_id)
        # Also check if the thread associated is still alive
        if agent_info and agent_info.get("thread") and agent_info["thread"].is_alive():
            return True
        elif agent_info:
             # Thread died unexpectedly? Clean up.
             log.warning(f"Agent Manager: Agent {agent_id} found in tracking but thread is not alive. Cleaning up.")
             _running_agents.pop(agent_id, None)
             # DB status should be updated to ERROR by the thread's exception handler ideally,
             # but we could force an update here if needed.
        return False


def get_running_agent_info(agent_id: str) -> Optional[Dict[str, Any]]:
    """Gets runtime information about a tracked agent (doesn't check thread status)."""
    with _lock:
        # Return a copy to prevent external modification
        return _running_agents.get(agent_id, {}).copy()


def get_all_running_agent_ids() -> List[str]:
    """Gets a list of IDs of all agents actively tracked by the manager."""
    # Check thread aliveness during listing for cleanup
    running_ids = []
    stale_ids = []
    with _lock:
        for agent_id, agent_info in _running_agents.items():
             thread = agent_info.get("thread")
             if thread and thread.is_alive():
                 running_ids.append(agent_id)
             else:
                 stale_ids.append(agent_id)

        # Cleanup stale entries
        if stale_ids:
             log.warning(f"Agent Manager: Cleaning up stale entries for non-alive threads: {stale_ids}")
             for stale_id in stale_ids:
                 _running_agents.pop(stale_id, None)
                 # TODO: Consider updating DB status to ERROR for these stale agents

    return running_ids
