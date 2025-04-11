import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tag, Button, Space, Popconfirm, message, Tooltip } from 'antd';
import { PlayCircleOutlined, StopOutlined, DeleteOutlined, EyeOutlined, LoadingOutlined } from '@ant-design/icons';
import { listAgents, startAgent, stopAgent, deleteAgent } from '../services/agentApi'; // Keep API calls for later

// --- Mock Data ---
const mockAgents = [
  { agent_id: 101, name: 'BTC Grid Master', strategy: 'grid', group_id: 1, status: 'running', pnl_usd: 125.50, total_investment_usd: 1000 },
  { agent_id: 102, name: 'ETH Scalper V2', strategy: 'grid', group_id: 1, status: 'stopped', pnl_usd: -30.15, total_investment_usd: 500 },
  { agent_id: 103, name: 'SOL Arb Finder', strategy: 'arbitrage', group_id: null, status: 'error', pnl_usd: 0, total_investment_usd: 2000 },
  { agent_id: 104, name: 'DOGE YOLO Bot', strategy: 'grid', group_id: 2, status: 'created', pnl_usd: 0, total_investment_usd: 100 },
  { agent_id: 105, name: 'Stable Grid', strategy: 'grid', group_id: 1, status: 'starting', pnl_usd: 5.80, total_investment_usd: 1500 },
];
// --- End Mock Data ---


const getStatusColor = (status) => {
  switch (status) {
    case 'running': return 'green';
    case 'starting':
    case 'stopping': return 'blue';
    case 'stopped': return 'orange';
    case 'created': return 'default';
    case 'error': return 'red';
    default: return 'default';
  }
};

const AgentList = () => {
  const [agents, setAgents] = useState(mockAgents); // Initialize with mock data
  const [loading, setLoading] = useState(false); // Keep loading state for potential future API integration
  const [actionLoading, setActionLoading] = useState({}); // Track loading state per agent action
  const navigate = useNavigate();

  // --- Comment out API fetching for now ---
  // const fetchAgents = useCallback(async () => {
  //   setLoading(true);
  //   setActionLoading({}); // Clear action loading states on refresh
  //   try {
  //     const data = await listAgents();
  //     setAgents(Array.isArray(data) ? data : []);
  //   } catch (err) {
  //     message.error('Failed to load agents.');
  //     console.error("List agents error:", err);
  //     setAgents([]);
  //   } finally {
  //     setLoading(false);
  //   }
  // }, []);

  // useEffect(() => {
  //   // fetchAgents(); // Don't fetch on mount when using mock data
  //   // Optional: Set up polling to refresh agent status periodically
  //   // const interval = setInterval(fetchAgents, 15000); // Refresh every 15 seconds
  //   // return () => clearInterval(interval);
  // }, [fetchAgents]);
  // --- End Comment out API fetching ---

  // Keep handleAction, but it won't actually call the API for now
  // Modify it to simulate success/failure and update mock data if desired
  const handleAction = async (agentId, actionFn, successMsg, errorMsg) => {
     setActionLoading(prev => ({ ...prev, [agentId]: true }));
     console.log(`Simulating action ${actionFn.name} for agent ${agentId}`);
     // Simulate API call delay
     await new Promise(resolve => setTimeout(resolve, 750));

     // Simulate success/failure (can make this random or based on action)
     const success = Math.random() > 0.2; // 80% success rate for simulation

     if (success) {
       message.success(successMsg);
       // Simulate state change in mock data
       setAgents(prevAgents => prevAgents.map(agent => {
         if (agent.agent_id === agentId) {
           if (actionFn === startAgent) return { ...agent, status: 'running' };
           if (actionFn === stopAgent) return { ...agent, status: 'stopped' };
           if (actionFn === deleteAgent) return null; // Mark for removal
         }
         return agent;
       }).filter(agent => agent !== null)); // Remove deleted agent
     } else {
       message.error(errorMsg);
     }

     setActionLoading(prev => ({ ...prev, [agentId]: false }));

    // Original API call logic (commented out)
    /* setActionLoading(prev => ({ ...prev, [agentId]: true }));
    try {
      const result = await actionFn(agentId);
      if (result && (result.status === 'starting' || result.status === 'stopping' || result.deleted === true)) {
        message.success(result.message || successMsg);
        // Optimistic update or just refresh after a short delay
        setTimeout(fetchAgents, 1000); // Refresh list after 1s
      } else {
         // Handle cases where the action might fail silently or return unexpected status
         message.error(result?.message || errorMsg);
         setActionLoading(prev => ({ ...prev, [agentId]: false })); // Turn off loading on error
      }
    } catch (err) {
      console.error(`${errorMsg} error:`, err);
      message.error(err.response?.data?.detail || err.message || errorMsg);
      setActionLoading(prev => ({ ...prev, [agentId]: false })); // Turn off loading on error
    } */
    // Loading state will be cleared on next fetchAgents call
  };

  const columns = [
    { title: 'ID', dataIndex: 'agent_id', key: 'agent_id', sorter: (a, b) => a.agent_id - b.agent_id, },
    { title: 'Name', dataIndex: 'name', key: 'name', sorter: (a, b) => a.name.localeCompare(b.name), },
    { title: 'Strategy', dataIndex: 'strategy', key: 'strategy', },
    { title: 'Group ID', dataIndex: 'group_id', key: 'group_id', render: (groupId) => groupId ?? '-', },
    {
      title: 'Profit (USDT)',
      dataIndex: 'pnl_usd',
      key: 'pnl_usd',
      render: (pnl) => (
        <span style={{ color: pnl > 0 ? '#52c41a' : pnl < 0 ? '#f5222d' : 'inherit' }}>
          {pnl?.toFixed(2) ?? '-'}
        </span>
      ),
      sorter: (a, b) => (a.pnl_usd ?? 0) - (b.pnl_usd ?? 0),
    },
    {
      title: 'Margin (%)',
      key: 'margin_pct',
      render: (_, record) => {
        const pnl = record.pnl_usd;
        const investment = record.total_investment_usd;
        if (pnl === null || pnl === undefined || !investment || investment === 0) {
          return '-';
        }
        const margin = (pnl / investment) * 100;
        return (
          <span style={{ color: margin > 0 ? '#52c41a' : margin < 0 ? '#f5222d' : 'inherit' }}>
            {margin.toFixed(2)}%
          </span>
        );
      },
      sorter: (a, b) => {
         const marginA = (a.pnl_usd ?? 0) / (a.total_investment_usd || 1); // Avoid division by zero
         const marginB = (b.pnl_usd ?? 0) / (b.total_investment_usd || 1);
         return marginA - marginB;
      }
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status) => <Tag color={getStatusColor(status)}>{status?.toUpperCase()}</Tag>,
      filters: [
        { text: 'Running', value: 'running' },
        { text: 'Stopped', value: 'stopped' },
        { text: 'Error', value: 'error' },
        { text: 'Starting', value: 'starting' },
        { text: 'Stopping', value: 'stopping' },
        { text: 'Created', value: 'created' },
      ],
      onFilter: (value, record) => record.status.indexOf(value) === 0,
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => {
        const isLoading = actionLoading[record.agent_id];
        const isRunning = record.status === 'running';
        const isStopped = record.status === 'stopped' || record.status === 'created' || record.status === 'error';
        const isTransitioning = record.status === 'starting' || record.status === 'stopping';

        return (
          <Space size="small">
            <Tooltip title="Start Agent">
              <Button
                type="primary"
                icon={isLoading ? <LoadingOutlined /> : <PlayCircleOutlined />}
                onClick={() => handleAction(record.agent_id, startAgent, 'Start initiated.', 'Failed to start agent.')}
                disabled={!isStopped || isLoading}
                size="small"
              />
            </Tooltip>
            <Tooltip title="Stop Agent">
              <Button
                icon={isLoading ? <LoadingOutlined /> : <StopOutlined />}
                onClick={() => handleAction(record.agent_id, stopAgent, 'Stop initiated.', 'Failed to stop agent.')}
                disabled={!isRunning || isLoading}
                danger
                size="small"
              />
            </Tooltip>
             <Tooltip title="View Details">
               <Button
                 icon={<EyeOutlined />}
                 onClick={() => navigate(`/agents/${record.agent_id}`)}
                 size="small"
               />
             </Tooltip>
            <Popconfirm
              title="Delete Agent?"
              description={`Are you sure you want to delete agent ${record.agent_id} (${record.name})? This action is irreversible.`}
              onConfirm={() => handleAction(record.agent_id, deleteAgent, 'Agent deleted.', 'Failed to delete agent.')}
              okText="Yes, Delete"
              cancelText="No"
              okButtonProps={{ danger: true }}
            >
              <Button
                icon={isLoading ? <LoadingOutlined /> : <DeleteOutlined />}
                danger
                disabled={isLoading || isTransitioning} // Disable delete during transitions
                size="small"
              />
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={agents}
      rowKey="agent_id"
      loading={loading}
      size="small"
      pagination={{ pageSize: 10 }}
      scroll={{ x: 800 }} // Enable horizontal scroll on smaller screens
    />
  );
};

export default AgentList;
