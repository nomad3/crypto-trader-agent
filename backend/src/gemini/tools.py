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


# --- Agent Management Tools (Updated for DB & Groups) ---
# These functions will be called by the interaction layer,
# which will provide the necessary DB session internally.
# Signatures here MUST NOT include the 'db' parameter for Gemini schema generation.

def create_trading_agent(
    name: str,
    strategy_type: Literal["arbitrage", "grid"],
    config: Dict[str, Any],
    group_id: Optional[int] = None # Added optional group_id
) -> Dict[str, Any]:
    """
    Creates a new trading agent instance. (State-Modifying)
    Validates configuration and optionally assigns to a group.

    Args:
        name: A unique name for the agent.
        strategy_type: The type of trading strategy ('arbitrage' or 'grid').
        config: Strategy-specific configuration parameters.
        group_id: Optional ID of the group to assign the agent to.

    Returns:
        A dictionary with agent_id, status, and message.
    """
    logging.info(f"Tool Call: create_trading_agent(name='{name}', strategy='{strategy_type}', group_id={group_id})")
    db: Session = next(database.get_db()) # Create session internally for execution
    try:
        # --- Input Validation & Sanitization ---
        if not name or len(name) > 100:
             return _error_response(None, "Invalid agent name provided (empty or too long).")

        try:
            db_strategy_type = StrategyTypeEnum(strategy_type)
        except ValueError:
             return _error_response(None, f"Invalid strategy type: {strategy_type}. Must be 'grid' or 'arbitrage'.")

        if db_strategy_type == StrategyTypeEnum.ARBITRAGE:
            ArbitrageConfigModel(**config)
        elif db_strategy_type == StrategyTypeEnum.GRID:
            GridConfigModel(**config)

        # --- Persistence ---
        db_agent = crud.create_agent(
            db, name=name, strategy_type=db_strategy_type, config=config, group_id=group_id
        )
        logging.info(f"Agent '{name}' created with DB ID: {db_agent.id}, GroupID: {group_id}")
        return {
            "agent_id": db_agent.id,
            "status": "created",
            "message": f"Agent '{name}' created successfully with ID {db_agent.id}."
            + (f" in group {db_agent.group_id}" if db_agent.group_id else "")
        }
    except ValidationError as e:
        error_details = e.errors()
        error_msg = f"Invalid configuration for {strategy_type} strategy: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})"
        return _error_response(None, error_msg)
    except ValueError as e:
         return _error_response(None, str(e))
    except Exception as e:
        logging.exception(f"Error in create_trading_agent: {e}")
        return _error_response(None, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close() # Ensure session is closed


# --- IMPORTANT ID Handling Note ---
# The functions below now expect the *database integer ID* as `agent_id`.
# Gemini might be called with a name or a previously returned ID.
# The interaction layer or API needs to handle mapping user-friendly names/IDs
# to the internal database ID before calling these tools if necessary.
# For now, we assume Gemini provides the correct integer ID.

def start_trading_agent(agent_id: int) -> Dict[str, Any]:
    """
    Starts a previously created trading agent. (State-Modifying)
    Interacts with the agent manager and updates DB status.

     Args:
        agent_id: The database ID of the agent to start.
    """
    logging.info(f"Tool Call: start_trading_agent(agent_id={agent_id})")
    db: Session = next(database.get_db())
    try:
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.")

        if db_agent.status == AgentStatusEnum.RUNNING:
             return _error_response(agent_id, "Agent is already running.")
        if agent_manager.is_agent_running(str(agent_id)):
             logging.warning(f"Inconsistency: Agent manager shows {agent_id} running, but DB status is {db_agent.status.value}")
             crud.update_agent_status(db, agent_id, AgentStatusEnum.RUNNING, "Status corrected from manager state")
             return _error_response(agent_id, "Agent is already running (status corrected).")

        success = agent_manager.start_agent_process(
            agent_id=str(agent_id),
            strategy_type=db_agent.strategy_type.value,
            config=db_agent.config
        )
        if success:
            crud.update_agent_status(db, agent_id, AgentStatusEnum.STARTING)
            logging.info(f"Agent {agent_id} start initiated.")
            return {"agent_id": agent_id, "status": AgentStatusEnum.STARTING.value, "message": f"Agent {agent_id} start initiated."}
        else:
            current_status = crud.get_agent_by_id(db, agent_id).status.value
            return _error_response(agent_id, f"Failed to initiate agent start via manager (current DB status: {current_status}).")
    except Exception as e:
        logging.exception(f"Error in start_trading_agent for {agent_id}: {e}")
        try:
            crud.update_agent_status(db, agent_id, AgentStatusEnum.ERROR, f"Failed to start: {str(e)}")
        except Exception as db_err:
             logging.error(f"Failed to update agent {agent_id} status to ERROR after start failure: {db_err}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()


def stop_trading_agent(agent_id: int) -> Dict[str, Any]:
    """
    Stops a currently running trading agent. (State-Modifying)
    Interacts with the agent manager and updates DB status.

     Args:
        agent_id: The database ID of the agent to stop.
    """
    logging.info(f"Tool Call: stop_trading_agent(agent_id={agent_id})")
    db: Session = next(database.get_db())
    try:
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.")

        can_stop_status = [AgentStatusEnum.RUNNING, AgentStatusEnum.STARTING, AgentStatusEnum.ERROR]
        if db_agent.status not in can_stop_status:
             if not agent_manager.is_agent_running(str(agent_id)):
                 return _error_response(agent_id, f"Agent is not in a stoppable state (status: {db_agent.status.value}).")
             else:
                 logging.warning(f"Inconsistency: Agent manager shows {agent_id} running, but DB status is {db_agent.status.value}. Proceeding with stop.")

        success = agent_manager.stop_agent_process(str(agent_id))
        if success:
            crud.update_agent_status(db, agent_id, AgentStatusEnum.STOPPING)
            logging.info(f"Agent {agent_id} stop initiated.")
            return {"agent_id": agent_id, "status": AgentStatusEnum.STOPPING.value, "message": f"Agent {agent_id} stop initiated."}
        else:
            current_status = crud.get_agent_by_id(db, agent_id).status.value
            return _error_response(agent_id, f"Failed to initiate agent stop via manager (current DB status: {current_status}). It might not be running according to the manager.")
    except Exception as e:
        logging.exception(f"Error in stop_trading_agent for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()


def get_agent_status(agent_id: int) -> Dict[str, Any]:
    """
    Retrieves the current status and basic summary for a specific agent. (Read-Only)
    Reads data from the database and performs consistency check with runtime manager.

     Args:
        agent_id: The database ID of the agent to query.
    """
    logging.info(f"Tool Call: get_agent_status(agent_id={agent_id})")
    db: Session = next(database.get_db())
    try:
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.", 404)

        agent_status = db_agent.status
        agent_status_message = db_agent.status_message

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
                 agent_status_message = updated_agent.status_message

        response = {
            "agent_id": db_agent.id, "name": db_agent.name,
            "strategy": db_agent.strategy_type.value, "status": agent_status.value,
            "config_summary": db_agent.config,
        }
        if agent_status == AgentStatusEnum.RUNNING:
             run_info = agent_manager.get_running_agent_info(str(agent_id))
             if run_info and run_info.get("start_time"):
                 uptime_seconds = time.time() - run_info["start_time"]
                 response["uptime_hours"] = round(uptime_seconds / 3600, 2)

        pnl_summary = crud.calculate_agent_pnl_summary(db, agent_id)
        response["current_pnl_usd"] = pnl_summary.get("realized_pnl_total_usd")
        if agent_status_message: response["message"] = agent_status_message
        return response
    except Exception as e:
        logging.exception(f"Error in get_agent_status for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()


def list_trading_agents() -> List[Dict[str, Any]]:
    """
    Lists all configured trading agents and their basic status. (Read-Only)
    Reads data from the database.
    """
    logging.info(f"Tool Call: list_trading_agents()")
    db: Session = next(database.get_db())
    try:
        db_agents = crud.get_agents(db, limit=500)
        agent_list = [
            {"agent_id": agent.id, "name": agent.name, "strategy": agent.strategy_type.value, "status": agent.status.value}
            for agent in db_agents
        ]
        return agent_list
    except Exception as e:
        logging.exception(f"Error in list_trading_agents: {e}")
        return []
    finally:
         if db: db.close()


def delete_trading_agent(agent_id: int) -> Dict[str, Any]:
    """
    Deletes a trading agent's configuration and stops it if running. (State-Modifying, Destructive)
    Requires stopping the agent first via the agent manager. Deletes from DB.

     Args:
        agent_id: The database ID of the agent to delete.
    """
    logging.info(f"Tool Call: delete_trading_agent(agent_id={agent_id})")
    db: Session = next(database.get_db())
    try:
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.", 404)

        agent_status = db_agent.status
        is_running = agent_manager.is_agent_running(str(agent_id))
        if agent_status == AgentStatusEnum.RUNNING or is_running:
            logging.info(f"Agent {agent_id} is running or managed as running. Attempting to stop before deletion.")
            stop_success = agent_manager.stop_agent_process(str(agent_id))
            if not stop_success:
                 logging.warning(f"Attempted to stop agent {agent_id} before deletion, but stop command failed.")
            else:
                 crud.update_agent_status(db, agent_id, AgentStatusEnum.STOPPING)
                 logging.info(f"Stop initiated for agent {agent_id}. Proceeding with deletion.")

        deleted = crud.delete_agent(db, agent_id)
        if deleted:
            logging.info(f"Agent {agent_id} data successfully deleted from DB.")
            return {"agent_id": agent_id, "deleted": True, "message": f"Agent {agent_id} successfully deleted."}
        else:
            return _error_response(agent_id, "Agent found initially but failed to delete from database.", 500)
    except Exception as e:
        logging.exception(f"Error in delete_trading_agent for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()


# --- Performance Analysis Tools (Updated for DB) ---

def get_detailed_performance(
    agent_id: int,
    time_period: Optional[Literal["1h", "6h", "24h", "7d", "all"]] = "24h"
) -> Dict[str, Any]:
    """
    Fetches detailed performance for a specific agent. (Read-Only)
    Retrieves trade history from DB and calculates KPIs (placeholders).

     Args:
        agent_id: The database ID of the agent.
        time_period: The time period for performance data.
    """
    logging.info(f"Tool Call: get_detailed_performance(agent_id={agent_id}, period='{time_period}')")
    db: Session = next(database.get_db())
    try:
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.", 404)

        trades = crud.get_trades_for_agent(db, agent_id, limit=5000)
        total_pnl = sum(t.pnl_usd for t in trades if t.pnl_usd is not None)
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.pnl_usd is not None and t.pnl_usd > 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        trade_list = [
            {"timestamp": t.timestamp.isoformat(), "symbol": t.symbol, "side": t.side, "price": t.price, "quantity": t.quantity, "order_id": t.order_id, "pnl_usd": t.pnl_usd}
            for t in trades[-50:]
        ]
        if not trades and db_agent.status != AgentStatusEnum.RUNNING:
             return {"agent_id": agent_id, "time_period": time_period, "message": "No trade data found. Agent is not running.", "trades": []}
        return {
            "agent_id": agent_id, "time_period": time_period,
            "total_pnl_usd": round(total_pnl, 2), "win_rate_pct": round(win_rate, 1),
            "total_trades": total_trades, "sharpe_ratio": 0.0, # Placeholder
            "trades": trade_list, "message": f"Displaying last {len(trade_list)} of {total_trades} trades." if total_trades > 50 else None
        }
    except Exception as e:
        logging.exception(f"Error in get_detailed_performance for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()


def get_pnl_summary(agent_id: int) -> Dict[str, Any]:
    """
    Returns the current PnL summary for a specific agent. (Read-Only)
    Uses placeholder calculation from DB CRUD layer.

     Args:
        agent_id: The database ID of the agent.
    """
    logging.info(f"Tool Call: get_pnl_summary(agent_id={agent_id})")
    db: Session = next(database.get_db())
    try:
        db_agent = crud.get_agent_by_id(db, agent_id)
        if not db_agent:
            return _error_response(agent_id, "Agent not found.", 404)

        summary = crud.calculate_agent_pnl_summary(db, agent_id)
        if not summary:
             return _error_response(agent_id, "Could not calculate PnL summary.")
        return {"agent_id": agent_id, **summary}
    except Exception as e:
        logging.exception(f"Error in get_pnl_summary for {agent_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()


# --- Agent Group Tools ---

def create_agent_group(name: str, description: Optional[str] = None) -> Dict[str, Any]:
    """Creates a new group for organizing agents."""
    logging.info(f"Tool Call: create_agent_group(name='{name}')")
    db: Session = next(database.get_db())
    try:
        db_group = crud.create_agent_group(db, name=name, description=description)
        return {"group_id": db_group.id, "name": db_group.name, "description": db_group.description, "message": f"Group '{name}' created successfully with ID {db_group.id}."}
    except ValueError as e:
        return _error_response(None, str(e), 409)
    except Exception as e:
        logging.exception(f"Error creating agent group '{name}': {e}")
        return _error_response(None, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()

def get_agent_groups() -> List[Dict[str, Any]]:
    """Lists all available agent groups."""
    logging.info("Tool Call: get_agent_groups()")
    db: Session = next(database.get_db())
    try:
        groups = crud.get_agent_groups(db, limit=500)
        return [{"group_id": g.id, "name": g.name, "description": g.description} for g in groups]
    except Exception as e:
        logging.exception(f"Error listing agent groups: {e}")
        return []
    finally:
         if db: db.close()

def assign_agent_to_group(agent_id: int, group_id: int) -> Dict[str, Any]:
    """Assigns an existing agent to an existing group."""
    logging.info(f"Tool Call: assign_agent_to_group(agent_id={agent_id}, group_id={group_id})")
    db: Session = next(database.get_db())
    try:
        updated_agent = crud.update_agent(db, agent_id=agent_id, group_id=group_id)
        if not updated_agent:
             return _error_response(agent_id, "Agent not found.", 404)
        return {"agent_id": agent_id, "group_id": group_id, "message": f"Agent {agent_id} successfully assigned to group {group_id}."}
    except ValueError as e:
        return _error_response(agent_id, str(e), 404)
    except Exception as e:
        logging.exception(f"Error assigning agent {agent_id} to group {group_id}: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()

def remove_agent_from_group(agent_id: int) -> Dict[str, Any]:
    """Removes an agent from its current group."""
    logging.info(f"Tool Call: remove_agent_from_group(agent_id={agent_id})")
    db: Session = next(database.get_db())
    try:
        updated_agent = crud.update_agent(db, agent_id=agent_id, clear_group=True)
        if not updated_agent:
             return _error_response(agent_id, "Agent not found.", 404)
        return {"agent_id": agent_id, "group_id": None, "message": f"Agent {agent_id} successfully removed from its group."}
    except Exception as e:
        logging.exception(f"Error removing agent {agent_id} from group: {e}")
        return _error_response(agent_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()

def get_group_performance_summary(group_id: int) -> Dict[str, Any]:
    """Retrieves an aggregated performance summary for all agents within a specific group."""
    logging.info(f"Tool Call: get_group_performance_summary(group_id={group_id})")
    db: Session = next(database.get_db())
    try:
        group = crud.get_agent_group_by_id(db, group_id)
        if not group:
            return _error_response(group_id, f"Agent group with ID {group_id} not found.", 404)
        summary = crud.get_group_performance_summary(db, group_id)
        summary["group_name"] = group.name
        return summary
    except Exception as e:
        logging.exception(f"Error getting performance summary for group {group_id}: {e}")
        return _error_response(group_id, f"An unexpected error occurred: {str(e)}", 500)
    finally:
         if db: db.close()


# --- Helper to get all tool definitions for Gemini ---
# Returns Python function objects for automatic schema generation by the library.
# Excludes functions known to cause schema generation issues.

def get_tool_definitions() -> List[callable]:
    """Returns a list of function objects to be used as tools, excluding problematic ones."""
    # Define which functions are exposed as tools
    agent_read_tools = [
        get_agent_status,
        list_trading_agents,
        get_detailed_performance,
        get_pnl_summary,
    ]
    agent_modify_tools = [
        # Exclude create_trading_agent due to schema issues with 'config' dict
        # create_trading_agent,
        start_trading_agent,
        stop_trading_agent,
        delete_trading_agent,
        assign_agent_to_group,
        remove_agent_from_group,
    ]
    group_read_tools = [
        get_agent_groups,
        get_group_performance_summary,
    ]
    group_modify_tools = [
        create_agent_group,
    ]

    # Combine based on safety flag
    read_only = agent_read_tools + group_read_tools
    state_modifying = agent_modify_tools + group_modify_tools

    ENABLE_STATE_MODIFICATION = True # Keep flag for enabling/disabling

    if ENABLE_STATE_MODIFICATION:
        logging.warning("State-modifying Gemini tools are ENABLED (excluding create_trading_agent).")
        final_tools = read_only + state_modifying
    else:
        logging.warning("State-modifying Gemini tools are DISABLED. Only read-only operations allowed via Gemini.")
        final_tools = read_only

    # Log the excluded tools
    if create_trading_agent not in final_tools:
         logging.warning("Tool 'create_trading_agent' is excluded from Gemini tools due to schema generation issues.")

    return final_tools

# Map function names (strings) to the actual Python functions for execution
# Include ALL functions here, even those excluded from Gemini tools,
# as they might be called internally or via direct API calls.
AVAILABLE_FUNCTIONS = {
    "create_trading_agent": create_trading_agent,
    "start_trading_agent": start_trading_agent,
    "stop_trading_agent": stop_trading_agent,
    "get_agent_status": get_agent_status,
    "list_trading_agents": list_trading_agents,
    "delete_trading_agent": delete_trading_agent,
    "get_detailed_performance": get_detailed_performance,
    "get_pnl_summary": get_pnl_summary,
    "create_agent_group": create_agent_group,
    "get_agent_groups": get_agent_groups,
    "assign_agent_to_group": assign_agent_to_group,
    "remove_agent_from_group": remove_agent_from_group,
    "get_group_performance_summary": get_group_performance_summary,
}

# No longer need manual gemini_tool_config
