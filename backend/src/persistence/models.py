from sqlalchemy import (
    Column, Integer, String, Float, DateTime, JSON, Enum as SQLAlchemyEnum, ForeignKey, Text
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum
import uuid # For potential UUID group IDs

Base = declarative_base()

# --- Enums ---
class AgentStatusEnum(enum.Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

class StrategyTypeEnum(enum.Enum):
    GRID = "grid"
    ARBITRAGE = "arbitrage"
    # Add other strategies here

# --- Tables ---

class AgentGroup(Base):
    __tablename__ = "agent_groups"

    id = Column(Integer, primary_key=True, index=True)
    # Alternatively use UUID: id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to Agents
    agents = relationship("Agent", back_populates="group")

    def __repr__(self):
        return f"<AgentGroup(id={self.id}, name='{self.name}')>"


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    strategy_type = Column(SQLAlchemyEnum(StrategyTypeEnum), nullable=False)
    # Store config as JSON.
    config = Column(JSON, nullable=False)
    status = Column(SQLAlchemyEnum(AgentStatusEnum), default=AgentStatusEnum.CREATED, nullable=False)
    status_message = Column(Text, nullable=True)

    # Foreign Key to AgentGroup (nullable)
    group_id = Column(Integer, ForeignKey("agent_groups.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    group = relationship("AgentGroup", back_populates="agents")
    trades = relationship("Trade", back_populates="agent", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Agent(id={self.id}, name='{self.name}', group={self.group_id}, strategy='{self.strategy_type.value}', status='{self.status.value}')>"


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), nullable=False, index=True)
    symbol = Column(String, index=True)
    order_id = Column(String, unique=True, index=True) # Binance order ID
    client_order_id = Column(String, index=True) # Optional client order ID
    side = Column(String) # e.g., BUY, SELL
    price = Column(Float)
    quantity = Column(Float)
    quote_quantity = Column(Float) # e.g., USDT value
    commission = Column(Float, nullable=True)
    commission_asset = Column(String, nullable=True)
    pnl_usd = Column(Float, nullable=True) # Calculated PnL for this trade
    # Add other relevant fields from Binance execution reports

    agent = relationship("Agent", back_populates="trades")

    def __repr__(self):
        return f"<Trade(id={self.id}, agent_id={self.agent_id}, symbol='{self.symbol}', side='{self.side}', price={self.price}, qty={self.quantity})>"

# Consider adding models for:
# - Positions (if strategies hold positions)
# - PerformanceSnapshots (periodically calculated KPIs)
