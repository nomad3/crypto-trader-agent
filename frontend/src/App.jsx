import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, Outlet } from 'react-router-dom';
import { Layout, Menu, ConfigProvider, theme, Typography, Space } from 'antd';
import { DashboardOutlined, RobotOutlined, GroupOutlined, ExperimentOutlined, MessageOutlined, SettingOutlined } from '@ant-design/icons';

// Import placeholder components (replace with actual implementations later)
import AgentDashboard from './pages/AgentDashboard'; // New component for dashboard/list
import AgentDetailPage from './pages/AgentDetailPage'; // Placeholder
import CreateAgentPage from './pages/CreateAgentPage'; // Placeholder
import AgentGroupsPage from './pages/AgentGroupsPage'; // Placeholder
import GeminiChatPage from './pages/GeminiChatPage'; // Wrapper for GeminiChatInterface

const { Header, Content, Footer, Sider } = Layout;
const { Title } = Typography;

// --- Placeholder Page Components ---
// TODO: Move these to separate files in pages/ directory
// const AgentDetailPage = () => <div>Agent Detail Page (TODO)</div>;
// const CreateAgentPage = () => <div>Create Agent Page (TODO)</div>;
// const AgentGroupsPage = () => <div>Agent Groups Page (TODO)</div>;
// const GeminiChatPage = () => <div>Gemini Chat Page (TODO)</div>;

// --- Main App Layout ---
const AppLayout = () => {
  const [collapsed, setCollapsed] = useState(false);
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  // Define menu items
  const menuItems = [
    { key: '1', icon: <DashboardOutlined />, label: <Link to="/">Dashboard</Link> },
    { key: '2', icon: <RobotOutlined />, label: <Link to="/agents/create">Create Agent</Link> },
    { key: '3', icon: <GroupOutlined />, label: <Link to="/groups">Groups</Link> },
    { key: '4', icon: <MessageOutlined />, label: <Link to="/gemini">Gemini Chat</Link> },
    // Add more items for analysis, settings etc. later
    // { key: '5', icon: <ExperimentOutlined />, label: <Link to="/analysis">Analysis</Link> },
    // { key: '6', icon: <SettingOutlined />, label: <Link to="/settings">Settings</Link> },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={(value) => setCollapsed(value)}>
        <div style={{ height: 32, margin: 16, background: 'rgba(255, 255, 255, 0.2)', textAlign: 'center', lineHeight: '32px', color: 'white', fontWeight: 'bold', borderRadius: '4px' }}>
          {collapsed ? 'CA' : 'Crypto Agent'}
        </div>
        <Menu theme="dark" defaultSelectedKeys={['1']} mode="inline" items={menuItems} />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 16px', background: colorBgContainer, display: 'flex', alignItems: 'center' }}>
           <Title level={4} style={{ margin: 0 }}>Trading Agent Platform</Title>
        </Header>
        <Content style={{ margin: '16px' }}>
          <div
            style={{
              padding: 24,
              minHeight: 360,
              background: colorBgContainer,
              borderRadius: borderRadiusLG,
            }}
          >
            {/* Nested routes will render here */}
            <Outlet />
          </div>
        </Content>
        <Footer style={{ textAlign: 'center' }}>
          Crypto Trader Agent ©{new Date().getFullYear()} - MVP
        </Footer>
      </Layout>
    </Layout>
  );
};


// --- App Router ---
function App() {
  return (
    <ConfigProvider
      theme={{
        // Use dark theme similar to Binance
        algorithm: theme.darkAlgorithm,
        token: {
          // Customize tokens if needed
          // colorPrimary: '#F0B90B', // Binance yellow
        },
      }}
    >
      <Router>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            {/* Index route for the dashboard */}
            <Route index element={<AgentDashboard />} />
            <Route path="agents/create" element={<CreateAgentPage />} />
            <Route path="agents/:agentId" element={<AgentDetailPage />} /> {/* Detail page */}
            <Route path="groups" element={<AgentGroupsPage />} />
            <Route path="gemini" element={<GeminiChatPage />} />
            {/* Add other routes here */}
            <Route path="*" element={<div>404 Not Found</div>} /> {/* Catch-all route */}
          </Route>
        </Routes>
      </Router>
    </ConfigProvider>
  );
}

export default App;
