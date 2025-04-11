import logging
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError # For handling unique constraints

from . import models
from .models import Agent, Trade, AgentGroup, AgentStatusEnum, StrategyTypeEnum

# --- Agent CRUD ---

def get_agent_by_id(db: Session, agent_id: int) -> Optional[models.Agent]:
    """Retrieves an agent by its primary key ID."""
    return db.query(models.Agent).filter(models.Agent.id == agent_id).first()

def get_agents(db: Session, skip: int = 0, limit: int = 100) -> List[models.Agent]:
    """Retrieves a list of agents with pagination."""
    return db.query(models.Agent).offset(skip).limit(limit).all()

def create_agent(db: Session, name: str, strategy_type: StrategyTypeEnum, config: Dict[str, Any], group_id: Optional[int] = None) -> models.Agent:
    """Creates a new agent record in the database, optionally assigning to a group."""
    # Check if group exists if group_id is provided
    if group_id is not None:
        db_group = get_agent_group_by_id(db, group_id)
        if not db_group:
            # Or raise a specific exception?
            raise ValueError(f"AgentGroup with id {group_id} not found.")

    db_agent = models.Agent(
        name=name,
        strategy_type=strategy_type,
        config=config,
        status=AgentStatusEnum.CREATED,
        group_id=group_id # Assign group_id
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    logging.info(f"Agent created in DB: ID={db_agent.id}, Name='{name}', GroupID={group_id}")
    return db_agent

def update_agent(db: Session, agent_id: int, name: Optional[str] = None, config: Optional[Dict[str, Any]] = None, group_id: Optional[int] = None, clear_group: bool = False) -> Optional[models.Agent]:
    """Updates an agent's details (name, config, group assignment)."""
    db_agent = get_agent_by_id(db, agent_id)
    if not db_agent:
        logging.warning(f"Attempted to update non-existent agent ID: {agent_id}")
        return None

    updated = False
    if name is not None:
        db_agent.name = name
        updated = True
    if config is not None:
        # TODO: Add validation for the new config based on agent's strategy type
        db_agent.config = config
        updated = True

    if clear_group:
         if db_agent.group_id is not None:
             logging.info(f"Removing agent {agent_id} from group {db_agent.group_id}")
             db_agent.group_id = None
             updated = True
    elif group_id is not None:
        # Check if group exists
        db_group = get_agent_group_by_id(db, group_id)
        if not db_group:
            raise ValueError(f"AgentGroup with id {group_id} not found.")
        if db_agent.group_id != group_id:
             logging.info(f"Assigning agent {agent_id} to group {group_id}")
             db_agent.group_id = group_id
             updated = True

    if updated:
        db.commit()
        db.refresh(db_agent)
        logging.info(f"Agent updated in DB: ID={agent_id}")
    return db_agent


def update_agent_status(db: Session, agent_id: int, status: AgentStatusEnum, message: Optional[str] = None) -> Optional[models.Agent]:
    """Updates the status and optional message of an agent."""
    db_agent = get_agent_by_id(db, agent_id)
    if db_agent:
        db_agent.status = status
        db_agent.status_message = message # Update or clear message
        db.commit()
        db.refresh(db_agent)
        logging.info(f"Agent status updated in DB: ID={agent_id}, Status={status.value}")
        return db_agent
    logging.warning(f"Attempted to update status for non-existent agent ID: {agent_id}")
    return None

def delete_agent(db: Session, agent_id: int) -> bool:
    """Deletes an agent record from the database."""
    db_agent = get_agent_by_id(db, agent_id)
    if db_agent:
        db.delete(db_agent)
        db.commit()
        logging.info(f"Agent deleted from DB: ID={agent_id}")
        return True
    logging.warning(f"Attempted to delete non-existent agent ID: {agent_id}")
    return False

def get_agents_in_group(db: Session, group_id: int) -> List[models.Agent]:
    """Retrieves all agents belonging to a specific group."""
    return db.query(models.Agent).filter(models.Agent.group_id == group_id).all()


# --- Agent Group CRUD ---

def get_agent_group_by_id(db: Session, group_id: int) -> Optional[models.AgentGroup]:
    """Retrieves an agent group by its primary key ID."""
    return db.query(models.AgentGroup).filter(models.AgentGroup.id == group_id).first()

def get_agent_group_by_name(db: Session, name: str) -> Optional[models.AgentGroup]:
    """Retrieves an agent group by its unique name."""
    return db.query(models.AgentGroup).filter(models.AgentGroup.name == name).first()

def get_agent_groups(db: Session, skip: int = 0, limit: int = 100) -> List[models.AgentGroup]:
    """Retrieves a list of agent groups with pagination."""
    return db.query(models.AgentGroup).offset(skip).limit(limit).all()

def create_agent_group(db: Session, name: str, description: Optional[str] = None) -> models.AgentGroup:
    """Creates a new agent group record."""
    if not name:
        raise ValueError("Group name cannot be empty.")
    db_group = models.AgentGroup(name=name, description=description)
    try:
        db.add(db_group)
        db.commit()
        db.refresh(db_group)
        logging.info(f"AgentGroup created in DB: ID={db_group.id}, Name='{name}'")
        return db_group
    except IntegrityError: # Catch unique constraint violation for name
        db.rollback()
        logging.warning(f"Failed to create AgentGroup: Name '{name}' already exists.")
        raise ValueError(f"AgentGroup with name '{name}' already exists.")
    except Exception as e:
        db.rollback()
        logging.exception(f"Database error creating AgentGroup '{name}': {e}")
        raise

def update_agent_group(db: Session, group_id: int, name: Optional[str] = None, description: Optional[str] = None) -> Optional[models.AgentGroup]:
    """Updates an agent group's details."""
    db_group = get_agent_group_by_id(db, group_id)
    if not db_group:
        logging.warning(f"Attempted to update non-existent AgentGroup ID: {group_id}")
        return None

    updated = False
    if name is not None:
        # Check if new name already exists
        existing = get_agent_group_by_name(db, name)
        if existing and existing.id != group_id:
             raise ValueError(f"AgentGroup with name '{name}' already exists.")
        db_group.name = name
        updated = True
    if description is not None:
        db_group.description = description
        updated = True

    if updated:
        try:
            db.commit()
            db.refresh(db_group)
            logging.info(f"AgentGroup updated in DB: ID={group_id}")
        except IntegrityError: # Catch unique constraint violation for name on update
            db.rollback()
            logging.warning(f"Failed to update AgentGroup {group_id}: Name '{name}' already exists.")
            raise ValueError(f"AgentGroup with name '{name}' already exists.")
        except Exception as e:
            db.rollback()
            logging.exception(f"Database error updating AgentGroup {group_id}: {e}")
            raise
    return db_group

def delete_agent_group(db: Session, group_id: int) -> bool:
    """Deletes an agent group. Fails if group contains agents."""
    # Use joinedload to efficiently check for agents
    db_group = db.query(models.AgentGroup).options(joinedload(models.AgentGroup.agents)).filter(models.AgentGroup.id == group_id).first()

    if not db_group:
        logging.warning(f"Attempted to delete non-existent AgentGroup ID: {group_id}")
        return False

    if db_group.agents:
        logging.warning(f"Cannot delete AgentGroup {group_id} ('{db_group.name}') because it contains agents.")
        raise ValueError(f"Cannot delete group '{db_group.name}' as it is not empty.")

    try:
        db.delete(db_group)
        db.commit()
        logging.info(f"AgentGroup deleted from DB: ID={group_id}, Name='{db_group.name}'")
        return True
    except Exception as e:
        db.rollback()
        logging.exception(f"Database error deleting AgentGroup {group_id}: {e}")
        raise


# --- Group Performance ---

def get_group_performance_summary(db: Session, group_id: int) -> Dict[str, Any]:
    """Calculates aggregated performance summary for all agents in a group."""
    agents_in_group = get_agents_in_group(db, group_id)
    if not agents_in_group:
        return {"message": "No agents found in this group.", "total_agents": 0}

    total_realized_pnl = 0.0
    total_trades_all_agents = 0
    # More complex metrics would require iterating through individual agent trades or pre-aggregated data
    # For MVP, we use the placeholder agent summary calculation

    agent_pnl_summaries = []
    for agent in agents_in_group:
        summary = calculate_agent_pnl_summary(db, agent.id) # Uses placeholder calc
        agent_pnl_summaries.append(summary)
        total_realized_pnl += summary.get("realized_pnl_total_usd", 0.0)
        # Need a way to get total trades per agent if not in summary
        # trades = get_trades_for_agent(db, agent.id, limit=100000) # Potentially very slow
        # total_trades_all_agents += len(trades)

    # Placeholder for aggregated metrics
    # TODO: Implement more sophisticated aggregation (avg win rate, Sharpe, etc.)
    return {
        "group_id": group_id,
        "total_agents": len(agents_in_group),
        "aggregated_realized_pnl_usd": round(total_realized_pnl, 2),
        # "total_trades": total_trades_all_agents, # Example
        "message": "Note: PnL calculations are based on placeholder logic."
    }


# --- Trade CRUD ---

def create_trade(db: Session, agent_id: int, trade_data: Dict[str, Any]) -> models.Trade:
    """Creates a new trade record associated with an agent."""
    # TODO: Add validation for trade_data fields
    db_trade = models.Trade(
        agent_id=agent_id,
        symbol=trade_data.get("symbol"),
        order_id=trade_data.get("orderId"), # Match Binance naming
        client_order_id=trade_data.get("clientOrderId"),
        side=trade_data.get("side"),
        price=float(trade_data.get("price", 0.0)),
        quantity=float(trade_data.get("executedQty", 0.0)),
        quote_quantity=float(trade_data.get("cummulativeQuoteQty", 0.0)),
        commission=float(trade_data.get("commission", 0.0) or 0.0), # Handle None
        commission_asset=trade_data.get("commissionAsset"),
        timestamp=func.now() # Or use timestamp from trade_data if available/reliable
        # pnl_usd needs calculation, perhaps later or via trigger/separate process
    )
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    logging.debug(f"Trade recorded in DB for Agent ID {agent_id}: OrderID={db_trade.order_id}")
    return db_trade

def get_trades_for_agent(db: Session, agent_id: int, skip: int = 0, limit: int = 1000) -> List[models.Trade]:
    """Retrieves trades for a specific agent, ordered by timestamp descending."""
    # TODO: Add time_period filtering based on timestamp column
    return db.query(models.Trade)\
             .filter(models.Trade.agent_id == agent_id)\
             .order_by(models.Trade.timestamp.desc())\
             .offset(skip)\
             .limit(limit)\
             .all()

# --- Performance Calculation Helpers (Placeholders) ---

def calculate_agent_pnl_summary(db: Session, agent_id: int) -> Dict[str, Any]:
    """Placeholder for calculating PnL summary from trades in DB."""
    # This needs a proper implementation based on trade history and potentially current positions
    trades = get_trades_for_agent(db, agent_id, limit=10000) # Get recent trades
    realized_pnl = sum(t.pnl_usd for t in trades if t.pnl_usd is not None) # Needs pnl_usd to be calculated/stored

    # Placeholder values
    return {
        "realized_pnl_total_usd": round(realized_pnl, 2),
        "unrealized_pnl_usd": 0.0, # Requires position tracking
        "pnl_24h_usd": 0.0 # Requires time filtering and calculation
    }
