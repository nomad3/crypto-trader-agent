import React from 'react';
import { Typography, Alert } from 'antd';
import GeminiChatInterface from '../components/GeminiChatInterface'; // Re-use component

const { Title, Paragraph } = Typography;

const GeminiChatPage = () => {
  return (
    <div>
      <Title level={2}>Gemini Chat Control</Title>
      <Paragraph>
        Interact with the agent management system using natural language.
      </Paragraph>
      <Alert
        message="Warning: Gemini Tool Functionality Disabled"
        description="Due to ongoing library compatibility issues with schema generation, creating agents via Gemini is currently disabled. Other commands might also be affected. Please use the standard UI elements or API for reliable agent management."
        type="warning"
        showIcon
        style={{ marginBottom: '16px' }}
      />
      <GeminiChatInterface />
    </div>
  );
};

export default GeminiChatPage;
