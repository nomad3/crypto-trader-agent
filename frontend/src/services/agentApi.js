import axios from 'axios';

// Use environment variable for API base URL
// Default to localhost for local development outside Docker
// In Docker Compose, this can be overridden or the Nginx proxy used
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';
// Note: If using Nginx proxy in frontend container (see frontend/Dockerfile example),
// the frontend might just call '/api/...' and Nginx handles routing to 'http://backend:8000/...'

console.log("API Base URL:", API_BASE_URL); // For debugging

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    // Add Authorization header if implementing authentication
    // 'Authorization': `Bearer ${getToken()}`
  },
});

// --- Agent Management ---

export const listAgents = async () => {
  try {
    const response = await apiClient.get('/agents');
    return response.data; // Expects: List[Dict[str, Any]]
  } catch (error) {
    console.error("Error listing agents:", error.response?.data || error.message);
    throw error; // Re-throw for component error handling
  }
};

export const createAgent = async (name, strategyType, config) => {
  try {
    const payload = { name, strategy_type: strategyType, config };
    const response = await apiClient.post('/agents', payload);
    return response.data; // Expects: AgentActionResponse
  } catch (error) {
    console.error("Error creating agent:", error.response?.data || error.message);
    throw error;
  }
};

export const getAgentStatus = async (agentId) => {
  try {
    const response = await apiClient.get(`/agents/${agentId}/status`);
    return response.data; // Expects: Dict[str, Any] (Agent Status Details)
  } catch (error) {
    console.error(`Error getting status for agent ${agentId}:`, error.response?.data || error.message);
    throw error;
  }
};

export const startAgent = async (agentId) => {
  try {
    const response = await apiClient.post(`/agents/${agentId}/start`);
    return response.data; // Expects: AgentActionResponse
  } catch (error) {
    console.error(`Error starting agent ${agentId}:`, error.response?.data || error.message);
    throw error;
  }
};

export const stopAgent = async (agentId) => {
  try {
    const response = await apiClient.post(`/agents/${agentId}/stop`);
    return response.data; // Expects: AgentActionResponse
  } catch (error) {
    console.error(`Error stopping agent ${agentId}:`, error.response?.data || error.message);
    throw error;
  }
};

export const deleteAgent = async (agentId) => {
  try {
    const response = await apiClient.delete(`/agents/${agentId}`);
    return response.data; // Expects: AgentActionResponse
  } catch (error) {
    console.error(`Error deleting agent ${agentId}:`, error.response?.data || error.message);
    throw error;
  }
};

// --- Performance Data ---

export const getAgentPerformance = async (agentId, timePeriod = '24h') => {
  try {
    const response = await apiClient.get(`/agents/${agentId}/performance`, {
      params: { time_period: timePeriod },
    });
    return response.data; // Expects: PerformanceResponse
  } catch (error) {
    console.error(`Error getting performance for agent ${agentId}:`, error.response?.data || error.message);
    throw error;
  }
};

export const getAgentPnlSummary = async (agentId) => {
  try {
    const response = await apiClient.get(`/agents/${agentId}/pnl`);
    return response.data; // Expects: PnlSummaryResponse
  } catch (error) {
    console.error(`Error getting PnL summary for agent ${agentId}:`, error.response?.data || error.message);
    throw error;
  }
};

// --- Gemini Interaction ---

export const sendGeminiCommand = async (prompt) => {
  try {
    const payload = { prompt };
    const response = await apiClient.post('/gemini/command', payload);
    return response.data; // Expects: GeminiResponse
  } catch (error) {
    console.error("Error sending command to Gemini:", error.response?.data || error.message);
    // Return the error structure from the API if available
    return { error: error.response?.data?.detail || error.message || "Unknown error" };
  }
};

// --- Helper for Auth (Example) ---
// const getToken = () => {
//   return localStorage.getItem('authToken');
// };
