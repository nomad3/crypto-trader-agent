# Crypto Trading Agent Platform with Gemini Integration

## Overview

This project provides the backend infrastructure and foundational frontend components for a system to create, manage, and monitor cryptocurrency trading agents operating on the Binance exchange. It features integration with Google's Gemini Pro API for natural language agent management and leverages a modular architecture for strategies and components. The system is containerized using Docker Compose for ease of deployment and dependency management.

**Core Goal:** To build a flexible platform allowing users to deploy and manage algorithmic trading agents, with AI-powered interaction capabilities and a foundation for future collaborative learning among agents.

**Current Status:** MVP (Minimum Viable Product) with core features implemented, including agent/group management, a functional Grid Trading strategy, basic ML analysis placeholders, and Gemini integration for control/reporting. **This is NOT production-ready and requires significant further development, testing (especially backtesting), and security hardening before use with real funds.**

## Key Features

1.  **Agent Management:**
    *   Create, configure, start, stop, and delete individual trading agents.
    *   Supports multiple strategy types (currently Grid Trading implemented, Arbitrage planned).
    *   Agent configurations and state are persisted in a PostgreSQL database.
2.  **Agent Groups:**
    *   Create and manage groups (teams) of agents.
    *   Assign agents to groups for organizational purposes and future collaborative features.
    *   Retrieve basic aggregated performance summaries for groups.
3.  **Trading Strategies:**
    *   **Grid Trading:** Implemented basic high-frequency grid trading logic (`strategies/grid_strategy.py`). Places buy/sell orders within a defined price range. (Requires further refinement for production).
    *   **Arbitrage:** Placeholder for Market-Neutral Arbitrage strategy.
    *   Modular design (`strategies/base_strategy.py`) allows for adding new strategies.
4.  **Gemini Pro Integration:**
    *   Natural Language Control: Users can interact with the system using natural language commands (via API endpoint `/gemini/command` or potentially a frontend interface) to manage agents and query status/performance.
    *   Function Calling: Leverages Gemini's function calling capability to translate natural language requests into specific backend actions (defined in `gemini/tools.py`).
    *   Interaction Layer: `gemini/interaction.py` handles communication with the Gemini API, including providing tool definitions and executing requested function calls.
5.  **Performance Tracking:**
    *   Basic trade logging to the database (`models.Trade`).
    *   API endpoints to retrieve individual agent performance details and PnL summaries (placeholder calculations).
    *   API endpoint to retrieve aggregated group performance summary (placeholder calculations).
6.  **Machine Learning Capabilities (Testing Phase):**
    *   **Analysis:** `learning/analyzer.py` includes basic performance analysis examples using Pandas and Scikit-learn (e.g., PnL trend via Linear Regression).
    *   **Suggestion Generation:** The analyzer can generate simple suggestions based on its analysis (e.g., "review parameters due to negative trend").
    *   **Communication:** Suggestions are published to a Redis channel (`LEARNING_MODULE_CHANNEL`) via the `CommunicationBus` (`communication/redis_pubsub.py`).
    *   **Non-Intrusive:** Strategies currently only *log* received suggestions/messages (`_handle_comm_message` in `base_strategy.py`). **No automatic parameter adaptation based on ML suggestions is implemented in this MVP.** This keeps the ML features observational.
7.  **API:**
    *   RESTful API built with FastAPI (`api/main.py`).
    *   Provides endpoints for frontend interaction (agent/group CRUD, start/stop, performance data).
    *   Includes placeholder authentication (`Depends(get_current_user)`).
    *   Interactive API documentation available via Swagger UI (`/docs`) and ReDoc (`/redoc`).
8.  **Containerization:**
    *   Dockerfiles provided for backend (`backend/Dockerfile`) and frontend (`frontend/Dockerfile`).
    *   `docker-compose.yml` orchestrates the backend, frontend (Nginx), PostgreSQL database, and Redis services.

## Architecture & Logic

*   **Backend (Python/FastAPI):**
    *   Serves the REST API for the frontend and Gemini interaction.
    *   Uses SQLAlchemy ORM for database interaction with PostgreSQL.
    *   `core/agent_manager.py`: Manages the lifecycle of running agent strategies using basic Python `threading`. Instantiates strategy classes and injects dependencies (DB session, Binance client, Comm bus).
    *   `strategies/`: Contains strategy implementations inheriting from `BaseStrategy`. Each running strategy executes its logic in a separate thread.
    *   `persistence/`: Defines database models (`models.py`), connection/session logic (`database.py`), and CRUD operations (`crud.py`).
    *   `gemini/`: Handles interaction with the Google Gemini API (`interaction.py`) and defines the functions exposed as tools (`tools.py`).
    *   `communication/`: Implements the Redis Pub/Sub communication bus (`redis_pubsub.py`) for potential future inter-agent/learning communication.
    *   `learning/`: Contains the placeholder performance analyzer (`analyzer.py`) with basic ML examples.
*   **Frontend (React Stub):**
    *   Basic React components (`AgentList`, `GeminiChatInterface`) and an API service (`agentApi.js`) are provided as placeholders.
    *   Served as static files via Nginx in the Docker setup. Requires full implementation.
*   **Database (PostgreSQL):** Persists agent configurations, group information, and trade history. Managed by Docker Compose.
*   **Communication (Redis):** Provides a Pub/Sub mechanism for potential event-driven interactions between agents and the learning module. Managed by Docker Compose.
*   **AI (Gemini Pro):** Used as an interface layer for natural language commands, translating them into specific, predefined backend function calls (tools). It does *not* directly execute trades or complex strategy logic itself.

## Tools & Libraries Used

*   **Backend:** Python 3.10+, FastAPI, Uvicorn, SQLAlchemy, Psycopg2-binary, python-binance, google-generativeai, python-decouple, Redis, Pandas, Scikit-learn
*   **Frontend:** React (stub), Axios, Serve (for dev)
*   **Database:** PostgreSQL
*   **Communication:** Redis
*   **Containerization:** Docker, Docker Compose
*   **AI:** Google Gemini Pro API

## Docker Setup & Usage

This project uses Docker Compose to manage the application services (backend, frontend, database, communication bus).

**Prerequisites:**
*   Docker Desktop (or Docker Engine + Docker Compose) installed and running.

**Configuration:**
1.  Copy the `.env.example` file in the project root to a new file named `.env`.
    ```bash
    cp .env.example .env
    ```
2.  Edit the `.env` file and replace the placeholder values for `BINANCE_API_KEY`, `BINANCE_SECRET_KEY`, and `GEMINI_API_KEY` with your actual credentials.
3.  Review the database credentials (`POSTGRES_...`) and `DB_TYPE` in `.env`. The defaults are configured to work with the included `docker-compose.yml`.

**Building & Running:**
1.  Open a terminal in the project root directory (where `docker-compose.yml` is located).
2.  Run the following command to build the images and start the containers:
    ```bash
    docker-compose up --build
    ```
    *   Add the `-d` flag (`docker-compose up --build -d`) to run in detached mode (in the background).
3.  The first time you run this, Docker will download the base images (Python, Node, Postgres, Redis, Nginx) and build the application images. This may take a few minutes.
4.  The backend service will attempt to connect to the PostgreSQL and Redis services. Healthchecks ensure the backend waits until the database and Redis are ready.

**Accessing Services:**
*   **Frontend:** Open your web browser and navigate to `http://localhost:3000`. (Note: Frontend requires implementation).
*   **Backend API Docs:** Navigate to `http://localhost:8000/docs` for Swagger UI or `http://localhost:8000/redoc` for ReDoc.
*   **PostgreSQL Database:** Can be accessed externally (if needed for debugging) on `localhost:5432` using the credentials from the `.env` file (default: user/password, db: trading_db).
*   **Redis:** Can be accessed externally (if needed) on `localhost:6379`.

**Stopping Services:**
1.  If running in the foreground, press `Ctrl+C` in the terminal where `docker-compose up` is running.
2.  If running in detached mode (`-d`), navigate to the project root directory in your terminal and run:
    ```bash
    docker-compose down
    ```
    *   Add the `-v` flag (`docker-compose down -v`) to also remove the named volumes (like `postgres_data`), effectively deleting the database data. Use with caution.

**Logs:**
*   If running in the foreground, logs from all services are streamed to the terminal.
*   If running in detached mode, view logs using:
    ```bash
    docker-compose logs -f # Stream logs
    docker-compose logs backend # View logs for a specific service
    ```

## Machine Learning Capabilities (Testing Phase)

The `learning/analyzer.py` module introduces basic ML capabilities focused on performance analysis.

*   **Data Preparation:** It fetches trade data for an agent or group using `crud` functions and converts it into a Pandas DataFrame.
*   **Analysis Example:** A simple Linear Regression model from `scikit-learn` is used to analyze the trend of cumulative PnL over time for individual agents. This is a basic example to demonstrate feasibility.
*   **Suggestion Generation:** Based on the analysis (e.g., detecting a negative PnL slope), placeholder suggestions are generated (e.g., recommending parameter review).
*   **Communication:** These suggestions are published as messages to the `LEARNING_MODULE_CHANNEL` on the Redis communication bus.
*   **Non-Intrusive:** Crucially, the trading strategies (`base_strategy.py`) are currently configured only to *listen* for messages on relevant channels (`_handle_comm_message`) and *log* them. **They do not automatically apply suggestions or adapt parameters.** This ensures the ML component is purely observational and doesn't interfere with the core trading logic in this MVP stage.
*   **Manual Trigger:** API endpoints (`/analysis/...`) are provided to manually trigger these analysis functions for testing and observation.

**Future Development:** To make this feature fully functional would require:
*   Developing more sophisticated analysis models (e.g., time series analysis, anomaly detection, reinforcement learning).
*   Defining clear protocols for communication messages (suggestions, insights, signals).
*   Implementing robust logic within strategies (`_adapt_parameters`) to safely validate and apply parameter changes based on received messages.
*   Creating mechanisms to trigger analysis automatically (e.g., scheduling, event-based).
