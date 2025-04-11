import React, { useState } from 'react';
import { sendGeminiCommand } from '../services/agentApi';
// import { Input, Button, Card, Spin, Alert } from 'antd'; // Example UI library

const GeminiChatInterface = () => {
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState(null); // Stores { response: "text" } or { error: "text" }
  const [loading, setLoading] = useState(false);

  const handleInputChange = (event) => {
    setPrompt(event.target.value);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!prompt.trim()) return; // Don't send empty prompts

    setLoading(true);
    setResponse(null); // Clear previous response

    try {
      const result = await sendGeminiCommand(prompt);
      setResponse(result); // result will have { response: ... } or { error: ... }
      console.log("Gemini API Result:", result);
    } catch (error) {
      // This catch block might be redundant if sendGeminiCommand handles errors internally
      // and returns an { error: ... } object, but good for catching unexpected issues.
      console.error("Error in handleSubmit:", error);
      setResponse({ error: 'An unexpected error occurred while sending the command.' });
    } finally {
      setLoading(false);
      setPrompt(''); // Clear input after sending
    }
  };

  return (
    <div style={{ marginTop: '20px', padding: '15px', border: '1px solid #ccc', borderRadius: '5px' }}>
      {/* Use Card component if using Ant Design */}
      <h3>Gemini Agent Control (Natural Language)</h3>
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
        {/* Use Input component if using Ant Design */}
        <input
          type="text"
          value={prompt}
          onChange={handleInputChange}
          placeholder="e.g., 'Start the BTC grid bot', 'Show PnL for ETH Arb'"
          disabled={loading}
          style={{ flexGrow: 1, padding: '8px' }}
        />
        {/* Use Button component if using Ant Design */}
        <button type="submit" disabled={loading || !prompt.trim()}>
          {loading ? 'Sending...' : 'Send Command'}
        </button>
      </form>

      {loading && (
        <div style={{ textAlign: 'center' }}>
          {/* Use Spin component if using Ant Design */}
          <p>Waiting for Gemini...</p>
        </div>
      )}

      {response && (
        <div style={{ marginTop: '15px', padding: '10px', background: '#f0f0f0', borderRadius: '4px' }}>
          <h4>Response:</h4>
          {response.error ? (
            // Use Alert component if using Ant Design
            <p style={{ color: 'red' }}>Error: {response.error}</p>
          ) : (
            <p>{response.response || '(No text response received)'}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default GeminiChatInterface;
