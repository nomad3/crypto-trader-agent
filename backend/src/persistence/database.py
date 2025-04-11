import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from decouple import config # Using python-decouple for config
import logging

log = logging.getLogger(__name__)

# --- Database Configuration ---
# Determine DB type and construct URL if not explicitly set
DB_TYPE = config("DB_TYPE", default="sqlite") # Add DB_TYPE to .env, default to sqlite

if DB_TYPE == "postgres":
    POSTGRES_USER = config("POSTGRES_USER", default="user")
    POSTGRES_PASSWORD = config("POSTGRES_PASSWORD", default="password")
    POSTGRES_HOST = config("POSTGRES_HOST", default="db") # Default to docker service name
    POSTGRES_PORT = config("POSTGRES_PORT", default="5432")
    POSTGRES_DB = config("POSTGRES_DB", default="trading_db")
    # Construct the DATABASE_URL for PostgreSQL
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    log.info(f"Using PostgreSQL database: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    engine_args = {} # No special args needed for psycopg2 usually
    is_sqlite = False
elif DB_TYPE == "sqlite":
    # Default to SQLite relative to the backend directory for simplicity
    # Use DATABASE_URL environment variable to override
    DATABASE_URL = config("DATABASE_URL", default="sqlite:///./backend/trading_agents.db")
    log.info(f"Using SQLite database: {DATABASE_URL}")
    # For SQLite, need connect_args to handle multi-threading if using threads for agents
    engine_args = {"connect_args": {"check_same_thread": False}}
    is_sqlite = True
else:
    raise ValueError(f"Unsupported DB_TYPE: {DB_TYPE}. Use 'postgres' or 'sqlite'.")


# --- Engine Creation ---
try:
    engine = create_engine(DATABASE_URL, **engine_args)
except ImportError as e:
     if "psycopg2" in str(e):
         log.error("psycopg2 not installed. Please install it: pip install psycopg2-binary")
     raise e

# --- Session Factory ---
# autocommit=False and autoflush=False are standard practices for web applications
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Dependency for FastAPI ---
def get_db():
    """
    FastAPI dependency that provides a database session per request.
    Ensures the session is always closed, even if errors occur.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Database Initialization / Migration ---
# Using Alembic is preferred for production to manage schema changes.
# init_db() is okay for initial setup/testing.
def init_db():
    """
    Creates database tables based on the models.
    WARNING: Use Alembic for production schema management.
    """
    from .models import Base # Import Base here to avoid circular imports
    log.info("Attempting to initialize database tables...")
    log.info(f"Database URL used: {DATABASE_URL}") # Log the actual URL being used
    # Add a check to prevent running on existing DB without care
    # if not database_exists(engine.url): # Requires sqlalchemy-utils
    #     create_database(engine.url)
    try:
        Base.metadata.create_all(bind=engine)
        log.info("Database tables created successfully (if they didn't exist).")
    except Exception as e:
        log.exception(f"Error creating database tables: {e}")
        # Don't raise here, allow application to potentially handle it
        # raise

# --- Alembic Setup (Manual Steps Required) ---
# 1. Install alembic: pip install alembic
# 2. Initialize alembic: alembic init alembic
# 3. Edit alembic.ini: set sqlalchemy.url = %(DATABASE_URL)s
# 4. Edit alembic/env.py:
#    - import sys, os; sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))) # Add project root to path
#    - from src.persistence.models import Base # Import your models' Base
#    - target_metadata = Base.metadata
# 5. Create initial migration: alembic revision --autogenerate -m "Initial migration"
# 6. Apply migration: alembic upgrade head
# ------------------------------------------------

# If running this file directly, offer to initialize (for dev)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log.info("Running database initialization directly...")
    # Add confirmation step?
    confirm = input("Initialize DB? This will create tables if they don't exist. (y/N): ")
    if confirm.lower() == 'y':
        init_db()
    else:
        log.info("Database initialization skipped.")
