import logging
from typing import Dict, Any, List, Optional, Tuple # Import Tuple
from sqlalchemy.orm import Session
import pandas as pd
from sklearn.linear_model import LinearRegression # Example ML model
import numpy as np # For array manipulation

from ..persistence import crud, models
from ..communication.redis_pubsub import CommunicationBus, LEARNING_MODULE_CHANNEL, GROUP_UPDATES_CHANNEL

log = logging.getLogger(__name__)

class PerformanceAnalyzer:
    """
    Placeholder class for analyzing agent/group performance and suggesting improvements.
    In a real system, this would involve complex statistical analysis or ML models.
    """
    def __init__(self, db_session: Session, comm_bus: CommunicationBus):
        self.db = db_session
        self.comm_bus = comm_bus
        log.info("PerformanceAnalyzer initialized.")

    def _get_trade_dataframe(self, agent_id: int, limit: int = 1000) -> Optional[pd.DataFrame]:
        """Helper to fetch trades and convert to a Pandas DataFrame."""
        try:
            trades: List[models.Trade] = crud.get_trades_for_agent(self.db, agent_id, limit=limit)
            if not trades:
                return None
            # Convert list of Trade objects to DataFrame
            trade_data = [
                {
                    "timestamp": t.timestamp, "symbol": t.symbol, "side": t.side,
                    "price": t.price, "quantity": t.quantity, "pnl_usd": t.pnl_usd
                } for t in trades if t.pnl_usd is not None # Only include trades with PnL for analysis
            ]
            if not trade_data: # Check if any trades had PnL
                 return None
            df = pd.DataFrame(trade_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values(by='timestamp').set_index('timestamp')
            return df
        except Exception as e:
            log.exception(f"Error fetching or processing trades for agent {agent_id}: {e}")
            return None

    def analyze_agent_performance(self, agent_id: int) -> Tuple[str, Optional[Dict]]:
        """
        Analyzes individual agent performance using basic ML (Linear Regression on PnL).
        Returns analysis summary and optional suggestion.
        """
        log.info(f"Analyzing performance for agent {agent_id}...")
        analysis_summary = f"Analysis for agent {agent_id}: "
        suggestion = None

        df = self._get_trade_dataframe(agent_id, limit=500) # Get recent trades with PnL

        if df is None or df.empty:
            analysis_summary += "No recent trade data with PnL found for analysis."
            log.warning(analysis_summary)
            return analysis_summary, suggestion

        # --- Basic PnL Trend Analysis (Example) ---
        try:
            # Calculate cumulative PnL
            df['cumulative_pnl'] = df['pnl_usd'].cumsum()
            # Create a time feature (e.g., seconds since first trade)
            df['time_elapsed'] = (df.index - df.index.min()).total_seconds()

            # Simple Linear Regression on cumulative PnL vs time
            X = df[['time_elapsed']] # Feature: time
            y = df['cumulative_pnl'] # Target: cumulative PnL

            if len(X) < 2: # Need at least 2 points for regression
                 analysis_summary += "Insufficient data points for trend analysis."
            else:
                model = LinearRegression()
                model.fit(X, y)
                slope = model.coef_[0] # PnL change per second
                intercept = model.intercept_

                analysis_summary += f"Cumulative PnL trend (slope: {slope:.6f} USD/sec). "

                # --- Generate Suggestion (Example based on trend) ---
                # VERY basic example: if slope is negative, suggest review
                if slope < -0.0001: # Arbitrary threshold for negative trend
                    suggestion_text = f"Negative PnL trend detected (slope={slope:.6f} USD/sec). Recommend reviewing agent parameters or market conditions."
                    suggestion = {"agent_id": agent_id, "suggestion": suggestion_text, "details": {"pnl_slope": slope}}
                    analysis_summary += "Negative trend detected. "
                else:
                    analysis_summary += "Trend appears stable or positive. "

        except Exception as e:
            log.exception(f"Error during ML analysis for agent {agent_id}: {e}")
            analysis_summary += f"Error during analysis: {e}. "

        log.info(analysis_summary)
        if suggestion:
             log.warning(f"Suggestion generated for agent {agent_id}: {suggestion['suggestion']}")
             # --- Publish Suggestion (Testing Phase - DO NOT AUTO-APPLY) ---
             if self.comm_bus and self.comm_bus.is_ready():
                 self.comm_bus.publish(LEARNING_MODULE_CHANNEL, {"type": "suggestion", "payload": suggestion})
                 log.info(f"Published suggestion for agent {agent_id} to {LEARNING_MODULE_CHANNEL}")

        return analysis_summary, suggestion

    def analyze_group_performance(self, group_id: int) -> Tuple[str, Optional[Dict]]:
        """Analyzes aggregated group performance."""
        log.info(f"Analyzing performance for group {group_id}...")
        analysis_summary = f"Analysis for group {group_id}: "
        insight = None

        agents_in_group = crud.get_agents_in_group(self.db, group_id)
        if not agents_in_group:
            analysis_summary += "No agents found in this group."
            log.warning(analysis_summary)
            return analysis_summary, insight

        all_trades_df_list = []
        agent_ids = [agent.id for agent in agents_in_group]

        for agent_id in agent_ids:
            df = self._get_trade_dataframe(agent_id, limit=500)
            if df is not None:
                df['agent_id'] = agent_id # Add agent_id for grouping
                all_trades_df_list.append(df)

        if not all_trades_df_list:
            analysis_summary += "No trade data found for any agent in the group."
            log.warning(analysis_summary)
            return analysis_summary, insight

        # Combine data from all agents
        group_df = pd.concat(all_trades_df_list)
        group_df = group_df.sort_index()

        # --- Group Analysis Examples (Placeholders) ---
        try:
            # Calculate overall group PnL
            total_group_pnl = group_df['pnl_usd'].sum()
            analysis_summary += f"Total realized PnL: {total_group_pnl:.2f} USD. "

            # Compare agent performance within the group
            pnl_by_agent = group_df.groupby('agent_id')['pnl_usd'].sum()
            analysis_summary += f"PnL by agent: {pnl_by_agent.to_dict()}. "
            best_agent = pnl_by_agent.idxmax()
            worst_agent = pnl_by_agent.idxmin()
            analysis_summary += f"Best performer: Agent {best_agent}, Worst performer: Agent {worst_agent}. "

            # --- Generate Group Insight (Placeholder) ---
            insight_text = f"Group {group_id} analysis: Total PnL {total_group_pnl:.2f}. Agent {best_agent} performing best."
            insight = {"group_id": group_id, "insight": insight_text, "details": {"total_pnl": total_group_pnl, "pnl_by_agent": pnl_by_agent.to_dict()}}

        except Exception as e:
            log.exception(f"Error during group analysis for group {group_id}: {e}")
            analysis_summary += f"Error during group analysis: {e}. "


        log.info(analysis_summary)
        if insight:
             log.info(f"Insight generated for group {group_id}: {insight['insight']}")
             # --- Publish Insight (Testing Phase) ---
             if self.comm_bus and self.comm_bus.is_ready():
                 self.comm_bus.publish(GROUP_UPDATES_CHANNEL, {"type": "insight", "payload": insight})
                 log.info(f"Published insight for group {group_id} to {GROUP_UPDATES_CHANNEL}")

        return analysis_summary, insight

    def run_periodic_analysis(self):
        """Placeholder for a method that could be run periodically (e.g., via scheduler)."""
        log.info("Running periodic performance analysis...")
        # Example: Analyze all active groups or agents with recent activity
        # groups = crud.get_agent_groups(self.db)
        # for group in groups:
        #     self.analyze_group_performance(group.id)
        # agents = crud.get_agents(self.db) # Filter for active/relevant agents
        # for agent in agents:
        #     self.analyze_agent_performance(agent.id)
        log.info("Periodic analysis finished (placeholder).")

# --- Conceptual Integration ---
# This analyzer could be run:
# - Periodically via a scheduler (like APScheduler).
# - Triggered by events on the CommunicationBus (e.g., after N trades).
# - On-demand via an API endpoint.
