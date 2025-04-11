import React from 'react';
import { useParams } from 'react-router-dom';
import { Typography } from 'antd';

const { Title } = Typography;

const AgentDetailPage = () => {
  const { agentId } = useParams(); // Get agentId from URL

  // TODO: Fetch agent details using agentId via agentApi.js
  // TODO: Display configuration, performance charts, trade history, controls

  return (
    <div>
      <Title level={2}>Agent Detail: {agentId}</Title>
      <p>Details, performance, and controls for agent {agentId} will be shown here.</p>
      {/* Add components for displaying details, charts, trade table, etc. */}
    </div>
  );
};

export default AgentDetailPage;
