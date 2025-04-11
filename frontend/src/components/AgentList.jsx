import React, { useState, useEffect } from 'react';
import { listAgents, startAgent, stopAgent, deleteAgent } from '../services/agentApi';
// import { Button, Table, Tag, Space, message, Popconfirm } from 'antd'; // Example UI library

const AgentList = () => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // Add state for row-specific loading if using a UI library like Ant Design
  // const [actionLoading, setActionLoading] = useState({}); // e.g., { "agent-123": true }

  const fetchAgents = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAgents();
      // Ensure data is always an array, even if API returns null/undefined on error/empty
      setAgents(Array.isArray(data) ? data : []);
    } catch (err) {
      setError('Failed to load agents.');
      // message.error('Failed to load agents.');
      console.error(err);
      setAgents([]); // Set to empty array on error
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  const handleStart = async (agentId) => {
    // setActionLoading(prev => ({ ...prev, [agentId]: true }));
    try {
      const result = await startAgent(agentId);
      // message.success(result.message || `Agent ${agentId} start initiated.`);
      console.log(`Start result for ${agentId}:`, result);
      fetchAgents(); // Refresh list
    } catch (err) {
      // message.error(`Failed to start agent ${agentId}: ${err.response?.data?.detail || err.message}`);
      console.error(`Start error for ${agentId}:`, err);
    } finally {
      // setActionLoading(prev => ({ ...prev, [agentId]: false }));
    }
  };

  const handleStop = async (agentId) => {
    // setActionLoading(prev => ({ ...prev, [agentId]: true }));
     try {
      const result = await stopAgent(agentId);
      // message.success(result.message || `Agent ${agentId} stop initiated.`);
      console.log(`Stop result for ${agentId}:`, result);
      fetchAgents(); // Refresh list
    } catch (err) {
      // message.error(`Failed to stop agent ${agentId}: ${err.response?.data?.detail || err.message}`);
      console.error(`Stop error for ${agentId}:`, err);
    } finally {
      // setActionLoading(prev => ({ ...prev, [agentId]: false }));
    }
  };

   const handleDelete = async (agentId) => {
     // Consider adding a confirmation dialog here before proceeding
     // setActionLoading(prev => ({ ...prev, [agentId]: true }));
     try {
      const result = await deleteAgent(agentId);
      // message.success(result.message || `Agent ${agentId} deleted.`);
      console.log(`Delete result for ${agentId}:`, result);
      fetchAgents(); // Refresh list
    } catch (err) {
      // message.error(`Failed to delete agent ${agentId}: ${err.response?.data?.detail || err.message}`);
      console.error(`Delete error for ${agentId}:`, err);
    } finally {
      // setActionLoading(prev => ({ ...prev, [agentId]: false }));
    }
  };

  // --- Render Logic (Example using simple HTML table) ---
  if (loading) return <p>Loading agents...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;

  return (
    <div>
      <h2>Trading Agents</h2>
      {/* Add a button to navigate to Agent Creation Form */}
      {/* <Button type="primary" onClick={() => navigate('/create-agent')}>Create New Agent</Button> */}
      <table border="1" style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Strategy</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {agents.length === 0 ? (
            <tr>
              <td colSpan="5" style={{ textAlign: 'center' }}>No agents found.</td>
            </tr>
          ) : (
            agents.map((agent) => (
              <tr key={agent.agent_id}>
                <td>{agent.agent_id}</td>
                <td>{agent.name}</td>
                <td>{agent.strategy}</td>
                <td>
                  {/* Use Tags or similar for better status visualization */}
                  <span style={{ color: agent.status === 'running' ? 'green' : agent.status === 'error' ? 'red' : 'orange' }}>
                    {agent.status}
                  </span>
                </td>
                <td>
                  {/* Use Space or similar for layout */}
                  {/* Add loading indicators to buttons if using actionLoading state */}
                  <button
                    onClick={() => handleStart(agent.agent_id)}
                    disabled={agent.status === 'running' /* || actionLoading[agent.agent_id] */}
                  >
                    Start
                  </button>
                  <button
                    onClick={() => handleStop(agent.agent_id)}
                    disabled={agent.status !== 'running' /* || actionLoading[agent.agent_id] */}
                  >
                    Stop
                  </button>
                  {/* Wrap delete in Popconfirm if using Ant Design */}
                  {/* <Popconfirm title="Are you sure?" onConfirm={() => handleDelete(agent.agent_id)}> */}
                    <button
                      onClick={() => handleDelete(agent.agent_id)}
                      /* disabled={actionLoading[agent.agent_id]} */
                      style={{ color: 'red', marginLeft: '5px' }}
                    >
                      Delete
                    </button>
                  {/* </Popconfirm> */}
                  {/* Add button/link to Agent Detail View */}
                  {/* <Button onClick={() => navigate(`/agents/${agent.agent_id}`)}>Details</Button> */}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};

export default AgentList;
