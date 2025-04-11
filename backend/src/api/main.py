import logging
import time # For agent detail consistency check
from fastapi import FastAPI, HTTPException, Body, Query, Depends, status
from fastapi.middleware.cors import CORSMiddleware # Import CORS Middleware
from fastapi.security import OAuth2PasswordBearer # Example for Auth
from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Any, Optional, Literal

# Configure basic logging (if not already configured elsewhere)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Import functions from other modules
# Import the Gemini interaction layer
from ..gemini.interaction import process_natural_language_request
# Import DB session dependency, CRUD functions, and models
from ..persistence import crud, models
from ..persistence.database import get_db
from ..persistence.models import AgentStatusEnum, StrategyTypeEnum, AgentGroup # Import Enums & Models
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError # For catching DB errors
# Import agent manager for start/stop actions
from ..core import agent_manager
# Import tools for validation models
from ..gemini import tools
# Import Learning/Communication components
from ..learning.analyzer import PerformanceAnalyzer
from ..communication.redis_pubsub import CommunicationBus
from contextlib import asynccontextmanager # For lifespan events

# --- Temp Singleton for CommBus (Replace with proper lifespan management) ---
# This should ideally be managed via FastAPI lifespan events for cleaner setup/teardown
try:
    temp_comm_bus_instance = CommunicationBus()
except Exception as e:
    logging.error(f"Failed to initialize CommunicationBus singleton: {e}")
    temp_comm_bus_instance = None


# --- Lifespan Event Handler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    logging.info("Application startup: Initializing database...")
    try:
        # Import init_db here to avoid potential circular imports at module level
        from ..persistence.database import init_db
        init_db() # Create tables if they don't exist
        logging.info("Database initialization check complete.")
    except Exception as e:
        logging.exception("Database initialization failed during startup!")
        # Depending on severity, you might want to prevent startup
    yield
    # Code to run on shutdown (optional)
    logging.info("Application shutdown.")
    if temp_comm_bus_instance:
        temp_comm_bus_instance.stop_listener() # Gracefully stop Redis listener


# --- Security (Authentication Placeholder - Keep for reference but disable in endpoints) ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # Dummy token URL

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Placeholder dependency for protected endpoints."""
    # In a real app, validate the token and return the user object/ID
    # For now, just simulate a valid user if token exists
    if not token:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Simulate user lookup
    user = {"username": "testuser", "id": "user123"} # Dummy user
    logging.info(f"Authenticated user: {user['username']}")
    return user

# --- Pydantic Models for API Request/Response ---

class AgentConfigBase(BaseModel):
    """Base model for agent configurations."""
    pass

# Reuse validation models from tools.py
class ArbitrageConfig(tools.ArbitrageConfigModel):
    """Configuration specific to the Arbitrage strategy."""
    pass # Fields are inherited

class GridConfig(tools.GridConfigModel):
    """Configuration specific to the Grid strategy."""
    pass # Fields are inherited

class CreateAgentRequest(BaseModel):
    """Request body for creating a new agent."""
    name: str = Field(..., description="Unique name for the agent")
    strategy_type: Literal["arbitrage", "grid"] = Field(..., description="Type of strategy")
    config: Dict[str, Any] = Field(..., description="Strategy-specific configuration dictionary")
    group_id: Optional[int] = Field(None, description="Optional ID of the group to assign the agent to")

class UpdateAgentRequest(BaseModel):
     """Request body for updating an agent."""
     name: Optional[str] = Field(None, description="New name for the agent")
     config: Optional[Dict[str, Any]] = Field(None, description="New configuration dictionary (must match strategy type)")
     group_id: Optional[int] = Field(None, description="ID of the group to assign the agent to")
     clear_group: Optional[bool] = Field(False, description="Set to true to remove agent from its current group")


class AgentStatusResponse(BaseModel):
    """Response model for individual agent status (subset of tool response)."""
    agent_id: int # Use integer ID now
    name: str
    strategy: str
    status: str
    uptime_hours: Optional[float] = None
    current_pnl_usd: Optional[float] = None
    config_summary: Optional[Dict[str, Any]] = None
    message: Optional[str] = None # For errors or info

# AgentListResponse is implicitly List[AgentBasicInfo] now based on list_agents tool
class AgentBasicInfo(BaseModel):
     """Basic agent info for list view."""
     agent_id: int # Use integer ID now
     name: str
     strategy: str
     status: str
     group_id: Optional[int] = None # Add group ID

class AgentDetailResponse(BaseModel):
     """Detailed agent info."""
     agent_id: int
     name: str
     strategy: str
     status: str
     config: Dict[str, Any]
     group_id: Optional[int] = None
     status_message: Optional[str] = None
     created_at: Optional[Any] = None # Using Any for datetime flexibility
     updated_at: Optional[Any] = None
     uptime_hours: Optional[float] = None
     pnl_summary: Optional[Dict[str, Any]] = None


class AgentActionResponse(BaseModel):
    """Generic response for actions like start, stop, delete, create."""
    agent_id: str # Keep as string for response consistency? Or int? Let's use int.
    status: Optional[str] = None
    message: str
    deleted: Optional[bool] = None # For delete confirmation

class PerformanceResponse(BaseModel):
    """Response model for detailed performance data."""
    agent_id: int
    time_period: Optional[str] = None
    data: Optional[Dict[str, Any]] = None # Contains the detailed performance dict
    message: Optional[str] = None # For errors

class PnlSummaryResponse(BaseModel):
    """Response model for PnL summary."""
    agent_id: int # Use int ID
    summary: Optional[Dict[str, Any]] = None # Contains the PnL summary dict
    message: Optional[str] = None # For errors

class GeminiRequest(BaseModel):
    """Request body for the Gemini command endpoint."""
    prompt: str

class GeminiResponse(BaseModel):
    """Response body for the Gemini command endpoint."""
    response: Optional[str] = None
    error: Optional[str] = None

# --- Group Models ---
class AgentGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None

class AgentGroupCreate(AgentGroupBase):
    pass

class AgentGroupUpdate(AgentGroupBase):
     name: Optional[str] = Field(None, min_length=1, max_length=100) # Allow partial updates
     description: Optional[str] = None

class AgentGroupResponse(AgentGroupBase):
    id: int
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    # Optionally include agents list here, but can be large
    # agents: List[AgentBasicInfo] = []

    class Config:
        orm_mode = True # Enable ORM mode for automatic mapping

# --- Analysis Models ---
class AnalysisResponse(BaseModel):
    status: str
    analysis_summary: Optional[str] = None
    suggestion_or_insight: Optional[Dict] = None
    error: Optional[str] = None


# --- FastAPI App Initialization ---
# Add notes about backtesting and risks
API_DESCRIPTION = """
API for managing and monitoring crypto trading agents, with optional Gemini integration.

**WARNING:**
*   This system is for demonstration purposes. **Do NOT run with real funds without extensive backtesting and understanding the risks.**
*   Trading involves significant risk. Past performance is not indicative of future results.
*   AI (Gemini) integration is experimental. Use with extreme caution, especially functions that modify state or execute trades. Start with read-only functions.
*   Ensure secure handling of API keys (Binance, Gemini). Use environment variables or a secrets manager.
*   Be mindful of API rate limits for both Binance and Gemini.
"""

app = FastAPI(
    title="Crypto Trading Agent API",
    description=API_DESCRIPTION,
    version="0.1.0",
    # Add security scheme definitions if using OpenAPI docs with auth
    # security=[{"oauth2_scheme": []}] # Example
    lifespan=lifespan # Register the lifespan handler
)

# --- CORS Middleware Configuration ---
# Allow requests from the frontend development server origin
origins = [
    "http://localhost:3000", # React Vite dev server
    "http://localhost",      # Sometimes needed depending on browser/setup
    # Add other origins if needed (e.g., your deployed frontend URL)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Allow cookies if using them for auth
    allow_methods=["*"],    # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],    # Allow all headers
)


# --- API Endpoints ---
# Add rate limiting dependencies if needed (e.g., using slowapi)
# Add security dependencies (Depends(get_current_user)) to protected routes

# TODO: Add rate limiting (e.g., using slowapi)

# --- Agent Endpoints ---

@app.post("/agents", response_model=AgentActionResponse, status_code=status.HTTP_201_CREATED, tags=["Agents"])
async def api_create_agent(
    agent_data: CreateAgentRequest,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db) # Inject DB session
):
    """
    Create a new trading agent, optionally assigning it to a group.
    Validates input and uses CRUD operations to save to DB.
    """
    # logging.info(f"User {current_user['username']} creating agent '{agent_data.name}', group={agent_data.group_id}")
    logging.info(f"Creating agent '{agent_data.name}', group={agent_data.group_id}") # Log without user
    # --- Validation ---
    try:
        # Validate config based on strategy type (using models defined in this file now)
        if agent_data.strategy_type == StrategyTypeEnum.ARBITRAGE.value:
            ArbitrageConfig(**agent_data.config)
        elif agent_data.strategy_type == StrategyTypeEnum.GRID.value:
            GridConfig(**agent_data.config)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported strategy type: {agent_data.strategy_type}")

        db_strategy_type = StrategyTypeEnum(agent_data.strategy_type)

    except ValidationError as e:
        # Handle Pydantic validation errors
        error_details = e.errors()
        error_msg = f"Invalid configuration: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
    except ValueError as e: # Catches invalid enum or GridConfig validation
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # --- Create Agent via CRUD ---
    try:
        db_agent = crud.create_agent(
            db,
            name=agent_data.name,
            strategy_type=db_strategy_type,
            config=agent_data.config,
            group_id=agent_data.group_id # Pass group_id
        )
        return AgentActionResponse(
            agent_id=str(db_agent.id), # Return ID as string
            status=db_agent.status.value,
            message=f"Agent '{db_agent.name}' created successfully with ID {db_agent.id}."
            + (f" in group {db_agent.group_id}" if db_agent.group_id else "")
        )
    except ValueError as e: # Catch specific error from CRUD (e.g., group not found)
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logging.exception(f"Database error creating agent '{agent_data.name}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error creating agent.")


@app.get("/agents", response_model=List[AgentBasicInfo], tags=["Agents"])
async def api_list_agents(
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db), # Inject DB session
    skip: int = 0,
    limit: int = 100
):
    """
    List all configured trading agents with pagination.
    """
    # logging.info(f"User {current_user['username']} listing agents (skip={skip}, limit={limit})")
    logging.info(f"Listing agents (skip={skip}, limit={limit})") # Log without user
    try:
        db_agents = crud.get_agents(db, skip=skip, limit=limit)
        response_agents = []
        for agent in db_agents:
            # Calculate PnL summary for each agent
            pnl_summary = crud.calculate_agent_pnl_summary(db, agent.id)
            response_agents.append(
                AgentBasicInfo(
                    agent_id=agent.id,
                    name=agent.name,
                    strategy=agent.strategy_type.value,
                    status=agent.status.value,
                    group_id=agent.group_id,
                    # Add PnL data to the response model if needed, or handle on frontend
                    # For now, we'll rely on the frontend mock data, but this shows where to add it
                    # pnl_usd=pnl_summary.get("realized_pnl_total_usd"),
                    # total_investment_usd=crud.get_agent_investment(db, agent.id) # Hypothetical function
                )
            )
        return response_agents
    except Exception as e:
        logging.exception(f"Database error listing agents: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error listing agents.")


# Use path parameter type hint for automatic validation
@app.get("/agents/{agent_id}", response_model=AgentDetailResponse, tags=["Agents"]) # Use specific response model
async def api_get_agent_details(agent_id: int, db: Session = Depends(get_db)): # Removed current_user
    """
    Get detailed status and information for a specific agent.
    Performs consistency check with runtime manager.
    """
    # logging.info(f"User {current_user['username']} getting details for agent {agent_id}")
    logging.info(f"Getting details for agent {agent_id}") # Log without user
    db_agent = crud.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")

    agent_status = db_agent.status
    agent_status_message = db_agent.status_message
    uptime_hours = None

    # --- Consistency Check with Agent Manager ---
    try:
        is_running_in_manager = agent_manager.is_agent_running(str(agent_id))
        if agent_status == AgentStatusEnum.RUNNING and not is_running_in_manager:
            logging.warning(f"API Status Inconsistency: Agent {agent_id} has DB status 'running' but not found in agent manager. Updating status to 'error'.")
            updated_agent = crud.update_agent_status(db, agent_id, AgentStatusEnum.ERROR, "Agent process not found by manager")
            if updated_agent:
                agent_status = updated_agent.status
                agent_status_message = updated_agent.status_message
        elif agent_status != AgentStatusEnum.RUNNING and is_running_in_manager:
             logging.warning(f"API Status Inconsistency: Agent {agent_id} has DB status '{agent_status.value}' but IS found in agent manager. Updating status to 'running'.")
             updated_agent = crud.update_agent_status(db, agent_id, AgentStatusEnum.RUNNING, "Status corrected from manager state")
             if updated_agent:
                 agent_status = updated_agent.status
                 agent_status_message = updated_agent.status_message # Should be cleared

        # Calculate uptime if running
        if agent_status == AgentStatusEnum.RUNNING:
             run_info = agent_manager.get_running_agent_info(str(agent_id))
             if run_info and run_info.get("start_time"):
                 uptime_seconds = time.time() - run_info["start_time"]
                 uptime_hours = round(uptime_seconds / 3600, 2)

    except Exception as e:
         # Log error during consistency check but proceed with returning DB data
         logging.error(f"Error during agent status consistency check for {agent_id}: {e}")

    # --- Prepare Response ---
    try:
        pnl_summary = crud.calculate_agent_pnl_summary(db, agent_id)
    except Exception as e:
         logging.error(f"Error calculating PnL summary for agent {agent_id}: {e}")
         pnl_summary = {"error": "Failed to calculate PnL"}

    # Map DB model to response model
    return AgentDetailResponse(
        agent_id=db_agent.id,
        name=db_agent.name,
        strategy=db_agent.strategy_type.value,
        status=agent_status.value, # Use potentially corrected status
        config=db_agent.config,
        group_id=db_agent.group_id,
        status_message=agent_status_message, # Use potentially corrected message
        created_at=db_agent.created_at,
        updated_at=db_agent.updated_at,
        uptime_hours=uptime_hours,
        pnl_summary=pnl_summary
    )

# Add PUT endpoint for updating agent details
@app.put("/agents/{agent_id}", response_model=AgentDetailResponse, tags=["Agents"])
async def api_update_agent(
    agent_id: int,
    agent_update: UpdateAgentRequest,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """
    Update an agent's details (name, config, group assignment).
    Cannot change strategy type. Config updates require validation.
    """
    # logging.info(f"User {current_user['username']} updating agent {agent_id} with data: {agent_update.dict(exclude_unset=True)}")
    logging.info(f"Updating agent {agent_id} with data: {agent_update.dict(exclude_unset=True)}") # Log without user
    db_agent = crud.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")

    # Validate config if provided
    if agent_update.config:
        try:
            # Need to access the enum member, not its value for comparison
            if db_agent.strategy_type == StrategyTypeEnum.ARBITRAGE:
                ArbitrageConfig(**agent_update.config)
            elif db_agent.strategy_type == StrategyTypeEnum.GRID:
                GridConfig(**agent_update.config)
            # No need to check for other types as agent already exists with valid type
        except ValidationError as e:
            error_details = e.errors()
            error_msg = f"Invalid configuration update: {error_details[0]['msg']} (field: {error_details[0]['loc'][0]})"
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
        except ValueError as e:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Prevent updating if agent is running? Or allow? For now, allow.
    # if db_agent.status == AgentStatusEnum.RUNNING:
    #     raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot update a running agent. Stop it first.")

    try:
        updated_agent = crud.update_agent(
            db=db,
            agent_id=agent_id,
            name=agent_update.name,
            config=agent_update.config,
            group_id=agent_update.group_id,
            clear_group=agent_update.clear_group
        )
        if not updated_agent:
             # Should have been caught by get_agent_by_id, but defensive check
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found during update.")

        # Return the updated agent details (similar to GET details)
        # Re-fetch details to ensure consistency after update
        # Need to pass placeholder user or remove dependency from called function too
        # For now, just return the updated_agent directly (might lack some calculated fields like uptime)
        # A better approach would be a dedicated function/mapper for response generation
        # return await api_get_agent_details(agent_id=agent_id, db=db) # This still needs current_user if not removed there
        return updated_agent # Return the direct ORM object (FastAPI handles serialization)

    except ValueError as e: # Catch specific errors from CRUD (e.g., group not found)
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logging.exception(f"Database error updating agent {agent_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error updating agent.")


@app.post("/agents/{agent_id}/start", response_model=AgentActionResponse, tags=["Agents"])
async def api_start_agent(agent_id: int, db: Session = Depends(get_db)): # Removed current_user
    """
    Start a specific trading agent.
    Uses agent_manager to start process and CRUD to update status.
    """
    # logging.info(f"User {current_user['username']} attempting to start agent {agent_id}")
    logging.info(f"Attempting to start agent {agent_id}") # Log without user
    db_agent = crud.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")

    if db_agent.status == AgentStatusEnum.RUNNING:
         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent is already running.")
    if agent_manager.is_agent_running(str(agent_id)):
         logging.warning(f"API Start: Correcting DB status for agent {agent_id} which is running in manager.")
         crud.update_agent_status(db, agent_id, AgentStatusEnum.RUNNING, "Status corrected from manager state")
         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent is already running (status corrected).")

    # --- Initiate Start Process ---
    try:
        success = agent_manager.start_agent_process(
            agent_id=str(agent_id),
            strategy_type=db_agent.strategy_type.value,
            config=db_agent.config
        )
        if success:
            updated_agent = crud.update_agent_status(db, agent_id, AgentStatusEnum.STARTING)
            logging.info(f"Agent {agent_id} start initiated via API.")
            return AgentActionResponse(
                agent_id=str(agent_id),
                status=AgentStatusEnum.STARTING.value,
                message=f"Agent {agent_id} start initiated."
            )
        else:
            # Agent manager failed (e.g., race condition?)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate agent start via manager.")
    except Exception as e:
        logging.exception(f"Error starting agent {agent_id} process: {e}")
        crud.update_agent_status(db, agent_id, AgentStatusEnum.ERROR, f"Failed to start: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error starting agent process: {str(e)}")


@app.post("/agents/{agent_id}/stop", response_model=AgentActionResponse, tags=["Agents"])
async def api_stop_agent(agent_id: int, db: Session = Depends(get_db)): # Removed current_user
    """
    Stop a specific trading agent.
    Uses agent_manager to stop process and CRUD to update status.
    """
    # logging.info(f"User {current_user['username']} attempting to stop agent {agent_id}")
    logging.info(f"Attempting to stop agent {agent_id}") # Log without user
    db_agent = crud.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")

    can_stop_status = [AgentStatusEnum.RUNNING, AgentStatusEnum.STARTING, AgentStatusEnum.ERROR]
    if db_agent.status not in can_stop_status and not agent_manager.is_agent_running(str(agent_id)):
         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Agent is not in a stoppable state (status: {db_agent.status.value}).")

    # --- Initiate Stop Process ---
    try:
        success = agent_manager.stop_agent_process(str(agent_id))
        if success:
            updated_agent = crud.update_agent_status(db, agent_id, AgentStatusEnum.STOPPING)
            logging.info(f"Agent {agent_id} stop initiated via API.")
            return AgentActionResponse(
                agent_id=str(agent_id),
                status=AgentStatusEnum.STOPPING.value,
                message=f"Agent {agent_id} stop initiated."
            )
        else:
             # If manager says it wasn't running, but DB state was stoppable, maybe just update DB?
             if db_agent.status in can_stop_status:
                 logging.warning(f"Agent manager reported agent {agent_id} not running during stop, but DB status was {db_agent.status.value}. Updating DB status to STOPPED.")
                 crud.update_agent_status(db, agent_id, AgentStatusEnum.STOPPED, "Stopped via API after manager reported not running")
                 return AgentActionResponse(agent_id=str(agent_id), status=AgentStatusEnum.STOPPED.value, message="Agent likely already stopped; status updated.")
             else:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate agent stop via manager.")
    except Exception as e:
        logging.exception(f"Error stopping agent {agent_id} process: {e}")
        # Consider setting status to ERROR if stop fails unexpectedly?
        # crud.update_agent_status(db, agent_id, AgentStatusEnum.ERROR, f"Failed to stop: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error stopping agent process: {str(e)}")


@app.delete("/agents/{agent_id}", response_model=AgentActionResponse, tags=["Agents"])
async def api_delete_agent(agent_id: int, db: Session = Depends(get_db)): # Removed current_user
    """
    Delete a specific trading agent.
    Stops the agent process first, then deletes from DB.
    """
    # logging.warning(f"User {current_user['username']} attempting to DELETE agent {agent_id}")
    logging.warning(f"Attempting to DELETE agent {agent_id}") # Log without user
    db_agent = crud.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")

    # --- Stop Agent if Running ---
    try:
        if agent_manager.is_agent_running(str(agent_id)) or db_agent.status in [AgentStatusEnum.RUNNING, AgentStatusEnum.STARTING]:
            logging.info(f"Stopping agent {agent_id} before deletion.")
            agent_manager.stop_agent_process(str(agent_id))
            # Update status briefly? Or just proceed to delete?
            # crud.update_agent_status(db, agent_id, AgentStatusEnum.STOPPING)
            # time.sleep(0.5) # Small delay? Risky. Better if stop_agent_process was synchronous/blocking.
    except Exception as stop_err:
         # Log error but proceed with deletion attempt
         logging.error(f"Error stopping agent {agent_id} during delete: {stop_err}. Proceeding with DB deletion.")

    # --- Delete from Persistence ---
    try:
        deleted = crud.delete_agent(db, agent_id)
        if deleted:
            logging.info(f"Agent {agent_id} data successfully deleted from DB via API.")
            return AgentActionResponse(
                agent_id=str(agent_id),
                deleted=True,
                message=f"Agent {agent_id} successfully deleted."
            )
        else:
            # Should not happen if agent was found initially
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Agent found initially but failed to delete from database.")
    except Exception as e:
        logging.exception(f"Database error deleting agent {agent_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error deleting agent: {str(e)}")


@app.get("/agents/{agent_id}/performance", response_model=PerformanceResponse, tags=["Performance"])
async def api_get_performance(
    agent_id: int,
    time_period: Optional[Literal["1h", "6h", "24h", "7d", "all"]] = Query("24h", description="Time period for performance data"),
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """
    Get detailed performance data (trades, KPIs) for a specific agent.
    """
    # logging.info(f"User {current_user['username']} getting performance for agent {agent_id}, period {time_period}")
    logging.info(f"Getting performance for agent {agent_id}, period {time_period}") # Log without user
    db_agent = crud.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")

    try:
        # TODO: Implement actual KPI calculations and time filtering in CRUD
        trades = crud.get_trades_for_agent(db, agent_id, limit=5000) # Get recent trades

        # Placeholder calculations
        total_pnl = sum(t.pnl_usd for t in trades if t.pnl_usd is not None)
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.pnl_usd is not None and t.pnl_usd > 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        trade_list = [
            {
                "timestamp": t.timestamp.isoformat(), "symbol": t.symbol, "side": t.side,
                "price": t.price, "quantity": t.quantity, "order_id": t.order_id, "pnl_usd": t.pnl_usd
            } for t in trades[-100:] # Limit response size
        ]

        performance_data = {
            "total_pnl_usd": round(total_pnl, 2),
            "win_rate_pct": round(win_rate, 1),
            "total_trades": total_trades,
            "sharpe_ratio": 0.0, # Placeholder
            "trades": trade_list,
        }

        return PerformanceResponse(
            agent_id=agent_id, # Return int ID
            time_period=time_period,
            data=performance_data,
            message=f"Displaying last {len(trade_list)} trades." if total_trades > 100 else None
        )
    except Exception as e:
        logging.exception(f"Error calculating performance for agent {agent_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error calculating performance: {str(e)}")


@app.get("/agents/{agent_id}/pnl", response_model=PnlSummaryResponse, tags=["Performance"])
async def api_get_pnl(agent_id: int, db: Session = Depends(get_db)): # Removed current_user
    """
    Get the PnL summary for a specific agent.
    """
    # logging.info(f"User {current_user['username']} getting PnL summary for agent {agent_id}")
    logging.info(f"Getting PnL summary for agent {agent_id}") # Log without user
    db_agent = crud.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")

    try:
        summary = crud.calculate_agent_pnl_summary(db, agent_id)
        if not summary:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not calculate PnL summary.")

        # return PnlSummaryResponse(agent_id=str(agent_id), summary=summary) # Keep agent_id as string here? Let's make it int
        return PnlSummaryResponse(agent_id=agent_id, summary=summary)
    except Exception as e:
        logging.exception(f"Error calculating PnL summary for agent {agent_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error calculating PnL summary: {str(e)}")


# --- Agent Group Endpoints ---

@app.post("/groups", response_model=AgentGroupResponse, status_code=status.HTTP_201_CREATED, tags=["Groups"])
async def api_create_agent_group(
    group_data: AgentGroupCreate,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """Create a new agent group."""
    # logging.info(f"User {current_user['username']} creating agent group '{group_data.name}'")
    logging.info(f"Creating agent group '{group_data.name}'") # Log without user
    try:
        db_group = crud.create_agent_group(db, name=group_data.name, description=group_data.description)
        return db_group # Pydantic automatically handles conversion due to orm_mode=True
    except ValueError as e: # Handles duplicate name error from CRUD
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logging.exception(f"Database error creating agent group '{group_data.name}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error creating agent group.")

@app.get("/groups", response_model=List[AgentGroupResponse], tags=["Groups"])
async def api_list_agent_groups(
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all agent groups."""
    # logging.info(f"User {current_user['username']} listing agent groups (skip={skip}, limit={limit})")
    logging.info(f"Listing agent groups (skip={skip}, limit={limit})") # Log without user
    try:
        groups = crud.get_agent_groups(db, skip=skip, limit=limit)
        return groups
    except Exception as e:
        logging.exception(f"Database error listing agent groups: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error listing agent groups.")

@app.get("/groups/{group_id}", response_model=AgentGroupResponse, tags=["Groups"])
async def api_get_agent_group(
    group_id: int,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """Get details for a specific agent group."""
    # logging.info(f"User {current_user['username']} getting details for group {group_id}")
    logging.info(f"Getting details for group {group_id}") # Log without user
    db_group = crud.get_agent_group_by_id(db, group_id)
    if not db_group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent group with ID {group_id} not found")
    return db_group

@app.put("/groups/{group_id}", response_model=AgentGroupResponse, tags=["Groups"])
async def api_update_agent_group(
    group_id: int,
    group_update: AgentGroupUpdate,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """Update an agent group's details (name, description)."""
    # logging.info(f"User {current_user['username']} updating group {group_id} with data: {group_update.dict(exclude_unset=True)}")
    logging.info(f"Updating group {group_id} with data: {group_update.dict(exclude_unset=True)}") # Log without user
    try:
        updated_group = crud.update_agent_group(
            db, group_id=group_id, name=group_update.name, description=group_update.description
        )
        if not updated_group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent group with ID {group_id} not found")
        return updated_group
    except ValueError as e: # Handles duplicate name error from CRUD
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logging.exception(f"Database error updating agent group {group_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error updating agent group.")

@app.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Groups"])
async def api_delete_agent_group(
    group_id: int,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """Delete an agent group. Fails if the group contains agents."""
    # logging.warning(f"User {current_user['username']} attempting to DELETE agent group {group_id}")
    logging.warning(f"Attempting to DELETE agent group {group_id}") # Log without user
    try:
        deleted = crud.delete_agent_group(db, group_id)
        if not deleted:
            # Should be caught by CRUD check, but defensive
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent group with ID {group_id} not found")
        # No content to return on successful delete
    except ValueError as e: # Catches "group not empty" error from CRUD
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logging.exception(f"Database error deleting agent group {group_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error deleting agent group.")


@app.get("/groups/{group_id}/agents", response_model=List[AgentBasicInfo], tags=["Groups"])
async def api_list_agents_in_group(
    group_id: int,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """List all agents belonging to a specific group."""
    # logging.info(f"User {current_user['username']} listing agents for group {group_id}")
    logging.info(f"Listing agents for group {group_id}") # Log without user
    # Check if group exists first
    db_group = crud.get_agent_group_by_id(db, group_id)
    if not db_group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent group with ID {group_id} not found")

    try:
        db_agents = crud.get_agents_in_group(db, group_id=group_id)
        return [
            AgentBasicInfo(
                agent_id=agent.id, name=agent.name, strategy=agent.strategy_type.value,
                status=agent.status.value, group_id=agent.group_id
            ) for agent in db_agents
        ]
    except Exception as e:
        logging.exception(f"Database error listing agents for group {group_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error listing agents for group.")

@app.get("/groups/{group_id}/performance", response_model=Dict[str, Any], tags=["Groups", "Performance"])
async def api_get_group_performance(
    group_id: int,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """Get aggregated performance summary for a specific agent group."""
    # logging.info(f"User {current_user['username']} getting performance summary for group {group_id}")
    logging.info(f"Getting performance summary for group {group_id}") # Log without user
    # Check if group exists first
    db_group = crud.get_agent_group_by_id(db, group_id)
    if not db_group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent group with ID {group_id} not found")

    try:
        summary = crud.get_group_performance_summary(db, group_id=group_id)
        return summary # Return the summary dict directly
    except Exception as e:
        logging.exception(f"Error calculating performance summary for group {group_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error calculating group performance summary.")


# --- Learning / Analysis Endpoints (Testing Phase) ---

class AnalysisResponse(BaseModel):
    status: str
    analysis_summary: Optional[str] = None
    suggestion_or_insight: Optional[Dict] = None
    error: Optional[str] = None

@app.post("/analysis/agent/{agent_id}", response_model=AnalysisResponse, tags=["Analysis (Testing)"])
async def trigger_agent_analysis(
    agent_id: int,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """Manually trigger performance analysis for a specific agent."""
    # logging.info(f"User {current_user['username']} triggering analysis for agent {agent_id}")
    logging.info(f"Triggering analysis for agent {agent_id}") # Log without user
    db_agent = crud.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")

    if not temp_comm_bus_instance or not temp_comm_bus_instance.is_ready():
         # Analyze anyway, but log that suggestions won't be published
         logging.warning(f"Comm bus not ready, analysis for agent {agent_id} will run without publishing.")

    try:
        # Instantiate analyzer with current session and comm bus
        analyzer = PerformanceAnalyzer(db_session=db, comm_bus=temp_comm_bus_instance)
        summary, suggestion = analyzer.analyze_agent_performance(agent_id)
        return AnalysisResponse(status="completed", analysis_summary=summary, suggestion_or_insight=suggestion)
    except Exception as e:
        logging.exception(f"Error during manual analysis trigger for agent {agent_id}: {e}")
        return AnalysisResponse(status="error", error=str(e))


@app.post("/analysis/group/{group_id}", response_model=AnalysisResponse, tags=["Analysis (Testing)"])
async def trigger_group_analysis(
    group_id: int,
    # current_user: dict = Depends(get_current_user), # Temporarily remove auth
    db: Session = Depends(get_db)
):
    """Manually trigger performance analysis for a specific agent group."""
    # logging.info(f"User {current_user['username']} triggering analysis for group {group_id}")
    logging.info(f"Triggering analysis for group {group_id}") # Log without user
    db_group = crud.get_agent_group_by_id(db, group_id)
    if not db_group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent group with ID {group_id} not found")

    if not temp_comm_bus_instance or not temp_comm_bus_instance.is_ready():
         logging.warning(f"Comm bus not ready, analysis for group {group_id} will run without publishing.")

    try:
        analyzer = PerformanceAnalyzer(db_session=db, comm_bus=temp_comm_bus_instance)
        summary, insight = analyzer.analyze_group_performance(group_id)
        return AnalysisResponse(status="completed", analysis_summary=summary, suggestion_or_insight=insight)
    except Exception as e:
        logging.exception(f"Error during manual analysis trigger for group {group_id}: {e}")
        return AnalysisResponse(status="error", error=str(e))


# --- Optional Gemini Interaction Endpoint ---
# This endpoint still uses the interaction layer which calls tools directly.
# For consistency, this could be refactored to resolve agent names/IDs to DB IDs
# and then call specific CRUD/manager functions based on Gemini's intent,
# passing the DB session. But keeping as is for now to demonstrate the original flow.

@app.post("/gemini/command", response_model=GeminiResponse, tags=["Gemini"])
async def handle_gemini_command(request: GeminiRequest): # Removed current_user
    """
    (Optional) Endpoint to process natural language commands via the Gemini interaction layer. Requires authentication.
    **WARNING:** This endpoint allows Gemini to call tools that might modify state. Ensure `ENABLE_STATE_MODIFICATION` in `tools.py` is set appropriately.
    The interaction layer currently creates its own DB sessions for tool execution.
    *** NOTE: Gemini tool functionality is temporarily disabled due to library schema issues. ***
    """
    # Immediately return error indicating disabled functionality
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Gemini command processing is temporarily disabled due to tool schema generation issues."
    )

    # --- Original Logic (kept below, but unreachable) ---
    # logging.info(f"User {current_user['username']} sending Gemini command: '{request.prompt}'")
    logging.info(f"Received Gemini command (disabled): '{request.prompt}'") # Log without user
    # TODO: Consider adding logic here or in interaction layer to map user-friendly names
    # (e.g., "my btc bot") from the prompt to the correct agent DB ID before calling tools.

    try:
        # The interaction layer handles calling Gemini and executing tools
        result = await process_natural_language_request(request.prompt)

        # Check for errors returned by the interaction layer or the tools it called
        if "error" in result:
            error_msg = result["error"]
            # Determine appropriate status code based on error type
            if "blocked by Gemini" in error_msg:
                 status_code = status.HTTP_400_BAD_REQUEST
            elif "unknown or disabled tool" in error_msg:
                 status_code = status.HTTP_501_NOT_IMPLEMENTED
            elif "not found" in error_msg.lower(): # Agent not found by tool
                 status_code = status.HTTP_404_NOT_FOUND
            elif "invalid configuration" in error_msg.lower():
                 status_code = status.HTTP_400_BAD_REQUEST
            elif "already running" in error_msg.lower() or "not running" in error_msg.lower():
                 status_code = status.HTTP_409_CONFLICT
            else: # Default to internal server error for unexpected issues
                 status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            raise HTTPException(status_code=status_code, detail=error_msg)

        # Success: return the final text response from Gemini
        return GeminiResponse(response=result.get("response"))

    except HTTPException as http_exc:
        # Re-raise exceptions from Depends or explicitly raised above
        raise http_exc
    except Exception as e:
        # Catch any other unexpected errors during the process
        logging.exception(f"Unexpected error processing Gemini command for user {current_user['username']}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process Gemini command: {str(e)}")


# --- Root Endpoint ---
@app.get("/", tags=["Root"])
async def api_read_root():
    return {"message": "Welcome to the Crypto Trading Agent API"}

# --- Running the server (for local development) ---
# Use uvicorn: uvicorn backend.src.api.main:app --reload --port 8000
