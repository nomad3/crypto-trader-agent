import React from 'react';
import { Typography } from 'antd';
import AgentList from '../components/AgentList'; // Re-use the existing component sketch

const { Title } = Typography;

const AgentDashboard = () => {
  return (
    <div>
      <Title level={2}>Agent Dashboard</Title>
      <p>Overview of all trading agents.</p>
      {/* We can reuse the AgentList component created earlier */}
      <AgentList />
    </div>
  );
};

export default AgentDashboard;
