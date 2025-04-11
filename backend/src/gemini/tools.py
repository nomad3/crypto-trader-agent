import json
import logging
from typing import Dict, List, Any, Literal, Optional
import time # For uptime calculation
from pydantic import BaseModel, ValidationError, Field # For validation
from sqlalchemy.orm import Session # To type hint DB session

# Import DB session factory and CRUD operations
from ..persistence import crud, database, models
from ..persistence.models import AgentStatusEnum, StrategyTypeEnum
# Import agent manager (still used for runtime state)
from ..core import agent_manager

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Pydantic Models for Config Validation ---
# Define models to validate the 'config' dict passed to create_agent

class ArbitrageConfigModel(BaseModel):
    pair_1: str = Field(..., min_length=1)
    pair_2: str = Field(..., min_length=1)
    pair_3: str = Field(..., min_length=1)
    min_profit_pct: float = Field(..., gt=0)
    trade_amount_usd: float = Field(..., gt=0)

class GridConfigModel(BaseModel):
    symbol: str = Field(..., min_length=1)
    lower_price: float = Field(..., gt=0)
    upper_price: float = Field(..., gt=0)
    grid_levels: int = Field(..., gt=1)
    order_amount_usd: float = Field(..., gt=0)

    def model_post_init(self, __context: Any) -> None:
        # Example of cross-field validation
        if self.lower_price >= self.upper_price:
            raise ValueError("lower_price must be less than upper_price")

# --- Helper Function for Error Responses ---
# Keep this as is, but note agent_id might be the DB int ID now in some contexts
def _error_response(agent_id: Optional[Any], message: str, status_code: int = 400) -> Dict[str, Any]:
    """Standardized error response format."""
    logging.warning(f"Tool Error (Agent ID: {agent_id}): {message}")
    response = {"status": "error", "message": message}
    if agent_id is not None: # Check explicitly for None
        response["agent_id"] = agent_id # Return the ID passed, could be int or other identifier
    # status_code is for potential internal use or logging, not directly returned by tool usually
    return response


# --- Agent Management Tools (Updated for DB) ---
# --- Agent Management Tools (Updated for DB & Groups) ---
# These functions accept a db Session. The interaction layer provides it.

def create_trading_agent(
    db: Session,
    name: str,
    strategy_type: Literal["arbitrage", "grid"],
    config: Dict[str, Any],
    group_id: Optional[int] = None # Added optional group_id
) -> Dict[str, Any]:
    """
    Creates a new trading agent instance with a specified name, strategy, and configuration.

    Args:
        name: A unique name for the agent.
        strategy_type: The type of trading strategy to use ('arbitrage' or 'grid').
        config: A dictionary containing strategy-specific configuration parameters.
                For 'arbitrage': e.g., {"pair_1": "BTCUSDT", "pair_2": "ETHBTC", "pair_3": "ETHUSDT", "min_profit_pct": 0.1, "trade_amount_usd": 100}
                For 'grid': e.g., {"symbol": "BTCUSDT", "lower_price": 60000, "upper_price": 70000, "grid_levels": 10, "order_amount_usd": 50}

    Returns:
        A dictionary containing the new agent's ID and initial status (e.g., 'created', 'inactive').
        Example: {"agent_id": "agent-123", "status": "created"}
    """
    """
    Creates a new trading agent instance. (State-Modifying)
    Validates configuration and optionally assigns to a group.
    """
    logging.info(f"Tool Call: create_trading_agent(name='{name}', strategy='{strategy_type}', group_id={group_id})")
    # db session is passed in
    try:
        # --- Input Validation & Sanitization ---
        if not name or len(name) > 100:
             return _error_response(None, "Invalid agent name provided (empty or too long).")

        # Convert string strategy type to Enum for DB
        try:
            db_strategy_type = StrategyTypeEnum(strategy_type)
        except ValueError:
             return _error_response(None, f"Invalid strategy type: {strategy_type}. Must be 'grid' or 'arbitrage'.")

        # Pydantic config validation
        if db_strategy_type == StrategyTypeEnum.ARBITRAGE:
            ArbitrageConfigModel(**config)
        elif db_strategy_type == StrategyTypeEnum.GRID:
            GridConfigModel(**config)
        # No else needed due to Enum conversion check above

        # --- Persistence ---
        db_agent = crud.create_agent(
            db, name=name, strategy_type=db_strategy_type, config=config, group_id=group_id
        )
        logging.info(f"Agent '{name}' created with DB ID: {db_agent.id}, GroupID: {group_id}")
        return {
            "agent_id": db_agent.id, # Return DB ID
            "status": "created",
            "message": f"Agent '{name}' created successfully with ID {db_agent.id}."
            + (f" in group {db_agent.group_id}" if db_agent.group_id else "")
        }

    except ValidationError as e:
        error_details = e.errors()
        error_msg = f"Invalid configuration for {strategy_type} strategy: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})"
        return _error_response(None, error_msg)
    except ValueError as e: # Catches config validation or group not found errors
         return _error_response(None, str(e))
    except Exception as e:
        logging.exception(f"Error in create_trading_agent: {e}")
        return _error_response(None, f"An unexpected error occurred: {str(e)}", 500)
    # No db.close() here - managed by caller


# --- IMPORTANT ID Handling Note ---
# The functions below now expect the *database integer ID* as `agent_id`.
# Gemini might be called with a name or a previously returned ID.
# The interaction layer or API needs to handle mapping user-friendly names/IDs
# to the internal database ID before calling these tools if necessary.
# For now, we assume Gemini provides the correct integer ID.

def start_trading_agent(db: Session, agent_id: int) -> Dict[str, Any]: # Added db
    """
    Starts a previously created and configured trading agent.

    Args:
        agent_id: The unique identifier of the agent to start.

    Returns:
        A dictionary confirming the action and the agent's new status (e.g., 'starting', 'running', 'error').
        Example: {"agent_id": "agent-123", "status": "starting", "message": "Agent start initiated."}
                 {"agent_id": "agent-456", "status": "error", "message": "Agent not found."}
    """
    """
    Starts a previously created trading agent. (State-Modifying)
    Interacts with the agent manager and updates DB status.
    """
    logging.info(f"Tool Call: start_trading_agent(agent_id={agent_id})")
    # db session is now passed in
    try:
        # --- Validation and Checks ---
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.")

        # Use Enum for status comparison
        if db_agent.status == AgentStatusEnum.RUNNING:
             return _error_response(agent_id, "Agent is already running.")
        # Check runtime manager consistency
        if agent_manager.is_agent_running(str(agent_id)): # Manager uses string IDs for now
             logging.warning(f"Inconsistency: Agent manager shows {agent_id} running, but DB status is {db_agent.status.value}")
             crud.update_agent_status(db, agent_id, AgentStatusEnum.RUNNING, "Status corrected from manager state")
             return _error_response(agent_id, "Agent is already running (status corrected).")

        # --- Initiate Start Process ---
        # Pass necessary info to the manager
        success = agent_manager.start_agent_process(
            agent_id=str(agent_id), # Manager uses string IDs
            strategy_type=db_agent.strategy_type.value,
            config=db_agent.config
        )

        if success:
            # Update DB status to 'starting'. Agent process should update later.
            crud.update_agent_status(db, agent_id, AgentStatusEnum.STARTING)
            logging.info(f"Agent {agent_id} start initiated.")
            return {"agent_id": agent_id, "status": AgentStatusEnum.STARTING.value, "message": f"Agent {agent_id} start initiated."}
        else:
            # Agent manager failed (e.g., race condition, internal error)
            current_status = crud.get_agent_by_id(db, agent_id).status.value # Re-fetch status
            return _error_response(agent_id, f"Failed to initiate agent start via manager (current DB status: {current_status}).")

    except Exception as e:
        logging.exception(f"Error in start_trading_agent for {agent_id}: {e}")
        # Attempt to update DB status to error
        try:
            crud.update_agent_status(db, agent_id, AgentStatusEnum.ERROR, f"Failed to start: {str(e)}")
        except Exception as db_err:
             logging.error(f"Failed to update agent {agent_id} status to ERROR after start failure: {db_err}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    # No db.close() here - managed by caller


def stop_trading_agent(db: Session, agent_id: int) -> Dict[str, Any]: # Added db
    """
    Stops a currently running trading agent.

    Args:
        agent_id: The unique identifier of the agent to stop.

    Returns:
        A dictionary confirming the action and the agent's new status (e.g., 'stopping', 'stopped', 'error').
        Example: {"agent_id": "agent-123", "status": "stopping", "message": "Agent stop initiated."}
    """
    """
    Stops a currently running trading agent. (State-Modifying)
    Interacts with the agent manager and updates DB status.
    """
    logging.info(f"Tool Call: stop_trading_agent(agent_id={agent_id})")
    # db session is now passed in
    try:
        # --- Validation and Checks ---
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.")

        # Check DB status - allow stopping running, starting, or errored agents
        can_stop_status = [AgentStatusEnum.RUNNING, AgentStatusEnum.STARTING, AgentStatusEnum.ERROR]
        if db_agent.status not in can_stop_status:
             # If DB says not running/starting/error, check manager just in case
             if not agent_manager.is_agent_running(str(agent_id)):
                 return _error_response(agent_id, f"Agent is not in a stoppable state (status: {db_agent.status.value}).")
             else:
                 logging.warning(f"Inconsistency: Agent manager shows {agent_id} running, but DB status is {db_agent.status.value}. Proceeding with stop.")

        # --- Initiate Stop Process ---
        success = agent_manager.stop_agent_process(str(agent_id)) # Manager uses string IDs

        if success:
            # Update DB status to 'stopping'. Agent process should update later.
            crud.update_agent_status(db, agent_id, AgentStatusEnum.STOPPING)
            logging.info(f"Agent {agent_id} stop initiated.")
            return {"agent_id": agent_id, "status": AgentStatusEnum.STOPPING.value, "message": f"Agent {agent_id} stop initiated."}
        else:
            # Agent manager failed (e.g., not running according to manager)
            current_status = crud.get_agent_by_id(db, agent_id).status.value # Re-fetch status
            return _error_response(agent_id, f"Failed to initiate agent stop via manager (current DB status: {current_status}). It might not be running according to the manager.")

    except Exception as e:
        logging.exception(f"Error in stop_trading_agent for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    # No db.close() here - managed by caller


def get_agent_status(db: Session, agent_id: int) -> Dict[str, Any]: # Added db
    """
    Retrieves the current status and a basic performance summary for a specific agent.

    Args:
        agent_id: The unique identifier of the agent.

    Returns:
        A dictionary containing the agent's status (e.g., 'running', 'stopped', 'error'),
        configuration summary, and basic performance metrics (e.g., PnL, uptime).
        Example: {"agent_id": "agent-123", "name": "My Grid Bot", "strategy": "grid", "status": "running", "uptime_hours": 10.5, "current_pnl_usd": 15.75}
                 {"agent_id": "agent-789", "status": "error", "message": "Agent not found."}
    """
    """
    Retrieves the current status and basic summary for a specific agent. (Read-Only)
    Reads data from the database. Performs consistency check with runtime manager.
    """
    logging.info(f"Tool Call: get_agent_status(agent_id={agent_id})")
    # db session is now passed in
    try:
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.", 404)

        agent_status = db_agent.status
        agent_status_message = db_agent.status_message

        # --- Consistency Check with Agent Manager ---
        is_running_in_manager = agent_manager.is_agent_running(str(agent_id))

        if agent_status == AgentStatusEnum.RUNNING and not is_running_in_manager:
            logging.warning(f"Status Inconsistency: Agent {agent_id} has DB status 'running' but not found in agent manager. Updating status to 'error'.")
            updated_agent = crud.update_agent_status(db, agent_id, AgentStatusEnum.ERROR, "Agent process not found by manager")
            if updated_agent:
                agent_status = updated_agent.status
                agent_status_message = updated_agent.status_message
        elif agent_status != AgentStatusEnum.RUNNING and is_running_in_manager:
             logging.warning(f"Status Inconsistency: Agent {agent_id} has DB status '{agent_status.value}' but IS found in agent manager. Updating status to 'running'.")
             updated_agent = crud.update_agent_status(db, agent_id, AgentStatusEnum.RUNNING, "Status corrected from manager state")
             if updated_agent:
                 agent_status = updated_agent.status
                 agent_status_message = updated_agent.status_message # Should be cleared

        # --- Prepare Response ---
        response = {
            "agent_id": db_agent.id,
            "name": db_agent.name,
            "strategy": db_agent.strategy_type.value,
            "status": agent_status.value,
            "config_summary": db_agent.config, # Return full config
        }
        if agent_status == AgentStatusEnum.RUNNING:
             run_info = agent_manager.get_running_agent_info(str(agent_id))
             if run_info and run_info.get("start_time"):
                 uptime_seconds = time.time() - run_info["start_time"]
                 response["uptime_hours"] = round(uptime_seconds / 3600, 2)

        # Add PnL summary (using placeholder calculation)
        pnl_summary = crud.calculate_agent_pnl_summary(db, agent_id)
        response["current_pnl_usd"] = pnl_summary.get("realized_pnl_total_usd")

        if agent_status_message:
            response["message"] = agent_status_message

        return response

    except Exception as e:
        logging.exception(f"Error in get_agent_status for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    # No db.close() here - managed by caller


def list_trading_agents(db: Session) -> List[Dict[str, Any]]: # Added db
    """
    Lists all configured trading agents and their basic status.

    Returns:
        A list of dictionaries, each representing an agent with its ID, name, strategy, and status.
        Example: [
            {"agent_id": "agent-123", "name": "BTC Grid", "strategy": "grid", "status": "running"},
            {"agent_id": "agent-456", "name": "ETH Arb", "strategy": "arbitrage", "status": "stopped"}
        ]
    """
    """
    Lists all configured trading agents and their basic status. (Read-Only)
    Reads data from the database.
    """
    logging.info(f"Tool Call: list_trading_agents()")
    # db session is now passed in
    try:
        db_agents = crud.get_agents(db, limit=500) # Limit number listed for safety
        agent_list = [
            {
                "agent_id": agent.id, # Use DB ID
                "name": agent.name,
                "strategy": agent.strategy_type.value,
                "status": agent.status.value,
            }
            for agent in db_agents
        ]
        return agent_list
    except Exception as e:
        logging.exception(f"Error in list_trading_agents: {e}")
        # Returning an error structure might be better if Gemini can handle it,
        # but for now, return empty list on error as before.
        return [] # Return empty list, error logged
    # No db.close() here - managed by caller


def delete_trading_agent(db: Session, agent_id: int) -> Dict[str, Any]: # Added db
    """
    Deletes a trading agent's configuration and stops it if running. This action is irreversible.

    Args:
        agent_id: The unique identifier of the agent to delete.

    Returns:
        A dictionary confirming the deletion or reporting an error.
        Example: {"agent_id": "agent-123", "deleted": True, "message": "Agent successfully deleted."}
                 {"agent_id": "agent-456", "deleted": False, "message": "Agent not found."}
    """
    """
    Deletes a trading agent's configuration and stops it if running. (State-Modifying, Destructive)
    Requires stopping the agent first via the agent manager. Deletes from DB.
    """
    logging.info(f"Tool Call: delete_trading_agent(agent_id={agent_id})")
    # db session is now passed in
    try:
        # --- Validation and Checks ---
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.", 404)

        # --- Stop Agent if Running ---
        agent_status = db_agent.status
        is_running = agent_manager.is_agent_running(str(agent_id))
        if agent_status == AgentStatusEnum.RUNNING or is_running:
            logging.info(f"Agent {agent_id} is running or managed as running. Attempting to stop before deletion.")
            stop_success = agent_manager.stop_agent_process(str(agent_id))
            if not stop_success:
                 logging.warning(f"Attempted to stop agent {agent_id} before deletion, but stop command failed (might be already stopped by manager).")
            else:
                 # Update status to stopping, though deletion will happen immediately after
                 crud.update_agent_status(db, agent_id, AgentStatusEnum.STOPPING)
                 logging.info(f"Stop initiated for agent {agent_id}. Proceeding with deletion.")
                 # Note: In a real system, might need a delay or confirmation before deleting DB record

        # --- Delete from Persistence ---
        deleted = crud.delete_agent(db, agent_id)
        if deleted:
            logging.info(f"Agent {agent_id} data successfully deleted from DB.")
            return {"agent_id": agent_id, "deleted": True, "message": f"Agent {agent_id} successfully deleted."}
        else:
            # Should not happen if agent was found initially
            return _error_response(agent_id, "Agent found initially but failed to delete from database.", 500)

    except Exception as e:
        logging.exception(f"Error in delete_trading_agent for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    # No db.close() here - managed by caller


# --- Performance Analysis Tools (Updated for DB) ---

def get_detailed_performance(
    db: Session, # Added db
    agent_id: int,
    time_period: Optional[Literal["1h", "6h", "24h", "7d", "all"]] = "24h"
) -> Dict[str, Any]:
    """
    Fetches detailed trade history and calculated Key Performance Indicators (KPIs) for a specific agent over a given time period.

    Args:
        agent_id: The unique identifier of the agent.
        time_period: The time period for which to fetch performance data. Defaults to '24h'.
                     Options: '1h', '6h', '24h', '7d', 'all'.

    Returns:
        A dictionary containing detailed performance data including trade list, PnL, win rate, Sharpe ratio (if applicable), etc.
        Example: {
            "agent_id": "agent-123",
            "time_period": "24h",
            "total_pnl_usd": 25.50,
            "win_rate_pct": 65.0,
            "total_trades": 50,
            "sharpe_ratio": 1.2, # Example KPI
            "trades": [
                {"timestamp": "...", "symbol": "BTCUSDT", "side": "buy", "price": 65000, "qty": 0.001, "pnl": 5.0},
                {"timestamp": "...", "symbol": "BTCUSDT", "side": "sell", "price": 65100, "qty": 0.001, "pnl": -2.0},
                # ... more trades
            ]
        }
        Returns an error message if the agent is not found.
    """
    """
    Fetches detailed performance for a specific agent. (Read-Only)
    Retrieves trade history from DB and calculates KPIs (placeholders).
    """
    logging.info(f"Tool Call: get_detailed_performance(agent_id={agent_id}, period='{time_period}')")
    # db session is now passed in
    try:
        # --- Validation ---
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.", 404)

        # --- Data Retrieval & Calculation (Placeholders) ---
        # TODO: Implement time_period filtering in crud.get_trades_for_agent
        trades = crud.get_trades_for_agent(db, agent_id, limit=5000) # Get more trades for calculation

        # TODO: Implement actual KPI calculations based on trades
        total_pnl = sum(t.pnl_usd for t in trades if t.pnl_usd is not None) # Assumes pnl_usd is stored/calculated per trade
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.pnl_usd is not None and t.pnl_usd > 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Format trades for response (convert Trade objects to dicts)
        trade_list = [
            {
                "timestamp": t.timestamp.isoformat(),
                "symbol": t.symbol,
                "side": t.side,
                "price": t.price,
                "quantity": t.quantity,
                "order_id": t.order_id,
                "pnl_usd": t.pnl_usd
            } for t in trades[-50:] # Return last 50 for display
        ]

        if not trades and db_agent.status != AgentStatusEnum.RUNNING:
             return {
                 "agent_id": agent_id, "time_period": time_period,
                 "message": "No trade data found. Agent is not running.", "trades": []
             }

        return {
            "agent_id": agent_id,
            "time_period": time_period,
            "total_pnl_usd": round(total_pnl, 2),
            "win_rate_pct": round(win_rate, 1),
            "total_trades": total_trades,
            "sharpe_ratio": 0.0, # Placeholder
            "trades": trade_list,
            "message": f"Displaying last {len(trade_list)} of {total_trades} trades." if total_trades > 50 else None
        }

    except Exception as e:
        logging.exception(f"Error in get_detailed_performance for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    # No db.close() here - managed by caller


def get_pnl_summary(db: Session, agent_id: int) -> Dict[str, Any]: # Added db
    """
    Returns the current Profit and Loss (PnL) summary for a specific agent.

    Args:
        agent_id: The unique identifier of the agent.

    Returns:
        A dictionary with key PnL figures (e.g., total realized PnL, unrealized PnL, PnL today).
        Example: {
            "agent_id": "agent-123",
            "realized_pnl_total_usd": 150.20,
            "unrealized_pnl_usd": -5.10,
            "pnl_24h_usd": 15.75
        }
        Returns an error message if the agent is not found.
    """
    """
    Returns the current PnL summary for a specific agent. (Read-Only)
    Uses placeholder calculation from DB CRUD layer.
    """
    logging.info(f"Tool Call: get_pnl_summary(agent_id={agent_id})")
    # db session is now passed in
    try:
        # --- Validation ---
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.", 404)

        # --- Calculation (Placeholder from CRUD) ---
        summary = crud.calculate_agent_pnl_summary(db, agent_id)

        if not summary:
             return _error_response(agent_id, "Could not calculate PnL summary.")

        # Return structure includes agent_id for clarity, even though summary might have it
        return {
            "agent_id": agent_id,
            **summary
        }

    except Exception as e:
        logging.exception(f"Error in get_pnl_summary for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    # No db.close() here - managed by caller


# --- Agent Group Tools ---

def create_agent_group(db: Session, name: str, description: Optional[str] = None) -> Dict[str, Any]:
    """Creates a new group for organizing agents."""
    logging.info(f"Tool Call: create_agent_group(name='{name}')")
    try:
        db_group = crud.create_agent_group(db, name=name, description=description)
        return {
            "group_id": db_group.id,
            "name": db_group.name,
            "description": db_group.description,
            "message": f"Group '{name}' created successfully with ID {db_group.id}."
        }
    except ValueError as e: # Catches duplicate name
        return _error_response(None, str(e), 409)
    except Exception as e:
        logging.exception(f"Error creating agent group '{name}': {e}")
        return _error_response(None, f"An unexpected error occurred: {str(e)}", 500)

def get_agent_groups(db: Session) -> List[Dict[str, Any]]:
    """Lists all available agent groups."""
    logging.info("Tool Call: get_agent_groups()")
    try:
        groups = crud.get_agent_groups(db, limit=500) # Limit results
        return [
            {"group_id": g.id, "name": g.name, "description": g.description}
            for g in groups
        ]
    except Exception as e:
        logging.exception(f"Error listing agent groups: {e}")
        return [] # Return empty list on error

def assign_agent_to_group(db: Session, agent_id: int, group_id: int) -> Dict[str, Any]:
    """Assigns an existing agent to an existing group."""
    logging.info(f"Tool Call: assign_agent_to_group(agent_id={agent_id}, group_id={group_id})")
    try:
        # crud.update_agent handles checks for agent/group existence
        updated_agent = crud.update_agent(db, agent_id=agent_id, group_id=group_id)
        if not updated_agent:
             # Should be caught by ValueError below, but defensive check
             return _error_response(agent_id, "Agent not found.", 404)
        return {
            "agent_id": agent_id,
            "group_id": group_id,
            "message": f"Agent {agent_id} successfully assigned to group {group_id}."
        }
    except ValueError as e: # Catches agent or group not found from crud.update_agent
        return _error_response(agent_id, str(e), 404)
    except Exception as e:
        logging.exception(f"Error assigning agent {agent_id} to group {group_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)

def remove_agent_from_group(db: Session, agent_id: int) -> Dict[str, Any]:
    """Removes an agent from its current group."""
    logging.info(f"Tool Call: remove_agent_from_group(agent_id={agent_id})")
    try:
        # crud.update_agent handles checks for agent existence
        updated_agent = crud.update_agent(db, agent_id=agent_id, clear_group=True)
        if not updated_agent:
             return _error_response(agent_id, "Agent not found.", 404)
        return {
            "agent_id": agent_id,
            "group_id": None,
            "message": f"Agent {agent_id} successfully removed from its group."
        }
    except Exception as e:
        logging.exception(f"Error removing agent {agent_id} from group: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)

def get_group_performance_summary(db: Session, group_id: int) -> Dict[str, Any]:
    """Retrieves an aggregated performance summary for all agents within a specific group."""
    logging.info(f"Tool Call: get_group_performance_summary(group_id={group_id})")
    try:
        # Check if group exists first
        group = crud.get_agent_group_by_id(db, group_id)
        if not group:
            return _error_response(group_id, f"Agent group with ID {group_id} not found.", 404)

        summary = crud.get_group_performance_summary(db, group_id)
        # Add group name to the summary for context
        summary["group_name"] = group.name
        return summary
    except Exception as e:
        logging.exception(f"Error getting performance summary for group {group_id}: {e}")
        return _error_response(group_id, f"An unexpected error occurred: {str(e)}", 500)


# --- Helper to get all tool definitions for Gemini ---

# Update get_tool_definitions to include new group performance tool

def get_tool_definitions() -> List[callable]:
    """Returns a list of function objects to be used as tools."""
    # Define which functions are exposed as tools
    agent_read_tools = [
        get_agent_status,
        list_trading_agents,
        get_detailed_performance,
        get_pnl_summary,
    ]
    agent_modify_tools = [
        create_trading_agent, # Now includes group_id
        start_trading_agent,
        stop_trading_agent,
        delete_trading_agent,
        assign_agent_to_group,
        remove_agent_from_group,
        # TODO: Add update_agent tool?
    ]
    group_read_tools = [
        get_agent_groups,
        get_group_performance_summary, # New read tool
    ]
    group_modify_tools = [
        create_agent_group,
        # TODO: Add update_agent_group, delete_agent_group tools?
    ]

    # Combine based on safety flag
    read_only_tools = agent_read_tools + group_read_tools
    state_modifying_tools = agent_modify_tools + group_modify_tools

    # --- Incremental Adoption ---
    ENABLE_STATE_MODIFICATION = True # Set to False initially for safety

    if ENABLE_STATE_MODIFICATION:
        logging.warning("State-modifying Gemini tools are ENABLED.")
        all_tools = read_only_tools + state_modifying_tools
    else:
        logging.warning("State-modifying Gemini tools are DISABLED. Only read-only operations allowed via Gemini.")
        all_tools = read_only_tools

    # Filter out functions that don't have the 'db' parameter (if any were added without it)
    # Although currently all defined tools require 'db'
    final_tools = [func for func in all_tools if 'db' in inspect.signature(func).parameters]
    if len(final_tools) != len(all_tools):
         logging.warning("Some defined tools were excluded because they don't accept a 'db' session parameter.")

    return final_tools

# Map function names to functions for easy lookup during execution
# Need to import inspect here
import inspect
AVAILABLE_TOOLS = {func.__name__: func for func in get_tool_definitions()}
