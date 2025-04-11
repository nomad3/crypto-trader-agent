import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Typography, Form, Input, Select, InputNumber, Button, message, Spin, Row, Col, Card
} from 'antd';
import { createAgent, listGroups } from '../services/agentApi';

const { Title } = Typography;
const { Option } = Select;

const CreateAgentPage = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [availableGroups, setAvailableGroups] = useState([]);
  // const [selectedStrategy, setSelectedStrategy] = useState('grid'); // Remove separate state
  const navigate = useNavigate();

  // Watch the value of the strategy_type field directly
  const strategyTypeValue = Form.useWatch('strategy_type', form);

  // Fetch available groups for the dropdown
  useEffect(() => {
    const fetchGroups = async () => {
      setGroupsLoading(true);
      try {
        const groups = await listGroups();
        console.log("Fetched Groups:", groups); // Add log to check received data
        setAvailableGroups(Array.isArray(groups) ? groups : []);
        if (!Array.isArray(groups)) {
            console.warn("Received non-array data for groups:", groups);
        }
      } catch (error) {
        message.error('Failed to load agent groups.');
        console.error("Fetch groups error:", error); // Log error details
        setAvailableGroups([]);
      } finally {
        setGroupsLoading(false);
      }
    };
    fetchGroups();
  }, []);

  // Remove the useEffect that tried to sync state


  const onFinish = async (values) => {
    setLoading(true);
    console.log('Form Values:', values);

    // Structure the config object based on selected strategy
    let configData = {};
    if (values.strategy_type === 'grid') {
      // Validate grid prices
      if (values.lower_price >= values.upper_price) {
          message.error('Grid Lower Price must be less than Upper Price.');
          setLoading(false);
          return;
      }
      configData = {
        symbol: values.symbol,
        lower_price: values.lower_price,
        upper_price: values.upper_price,
        grid_levels: values.grid_levels,
        order_amount_usd: values.order_amount_usd,
      };
    } else if (values.strategy_type === 'arbitrage') {
      configData = {
        pair_1: values.pair_1,
        pair_2: values.pair_2,
        pair_3: values.pair_3,
        min_profit_pct: values.min_profit_pct,
        trade_amount_usd: values.trade_amount_usd_arb, // Use different name to avoid conflict
      };
    }

    const agentPayload = {
      name: values.name,
      strategy_type: values.strategy_type,
      config: configData,
      group_id: values.group_id || null, // Send null if undefined/empty
    };

    console.log('Agent Payload:', agentPayload);

    try {
      const result = await createAgent(agentPayload);
      message.success(result.message || 'Agent created successfully!');
      navigate('/'); // Navigate back to dashboard after creation
    } catch (error) {
      message.error(error.response?.data?.detail || error.message || 'Failed to create agent.');
    } finally {
      setLoading(false);
    }
  };

  // No longer need handleStrategyChange to set state
  // const handleStrategyChange = (value) => {
  //   setSelectedStrategy(value);
  // };

  return (
    <div>
      <Title level={2}>Create New Agent</Title>
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        initialValues={{ strategy_type: 'grid' }} // Default strategy
        style={{ maxWidth: 800, margin: 'auto' }} // Constrain form width
      >
        <Card title="Basic Information" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item
                name="name"
                label="Agent Name"
                rules={[{ required: true, message: 'Please input the agent name!' }]}
              >
                <Input placeholder="e.g., My BTC Grid Bot" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item
                name="strategy_type"
                label="Strategy Type"
                rules={[{ required: true, message: 'Please select a strategy!' }]}
              >
                {/* No need for onChange here if only using useWatch */}
                <Select placeholder="Select strategy">
                  <Option value="grid">Grid Trading</Option>
                  <Option value="arbitrage">Triangular Arbitrage</Option>
                  {/* Add other strategies here */}
                </Select>
              </Form.Item>
            </Col>
             <Col xs={24} sm={12}>
               <Form.Item
                 name="group_id"
                 label="Assign to Group (Optional)"
               >
                 <Select placeholder="Select group" loading={groupsLoading} allowClear>
                   {availableGroups.map(group => (
                     <Option key={group.id} value={group.id}>
                       {group.name} (ID: {group.id})
                     </Option>
                   ))}
                 </Select>
               </Form.Item>
             </Col>
          </Row>
        </Card>

        {/* Conditional Configuration Fields based on watched value */}
        {strategyTypeValue === 'grid' && (
          <Card title="Grid Strategy Configuration" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col xs={24} sm={12} md={8}>
                <Form.Item name="symbol" label="Symbol" rules={[{ required: true, message: 'Symbol is required' }]}>
                  <Input placeholder="e.g., BTCUSDT" />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Form.Item name="lower_price" label="Lower Price" rules={[{ required: true, type: 'number', min: 0, message: 'Valid lower price required' }]}>
                  <InputNumber style={{ width: '100%' }} placeholder="e.g., 60000" step="0.01" stringMode />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Form.Item name="upper_price" label="Upper Price" rules={[{ required: true, type: 'number', min: 0, message: 'Valid upper price required' }]}>
                  <InputNumber style={{ width: '100%' }} placeholder="e.g., 70000" step="0.01" stringMode />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Form.Item name="grid_levels" label="Grid Levels" rules={[{ required: true, type: 'integer', min: 2, message: 'Min 2 levels' }]}>
                  <InputNumber style={{ width: '100%' }} placeholder="e.g., 10" />
                </Form.Item>
              </Col>
              <Col xs={12} sm={6} md={4}>
                <Form.Item name="order_amount_usd" label="Order Amount (USD)" rules={[{ required: true, type: 'number', min: 1, message: 'Min 1 USD' }]}>
                  <InputNumber style={{ width: '100%' }} placeholder="e.g., 50" />
                </Form.Item>
              </Col>
            </Row>
          </Card>
        )}

        {strategyTypeValue === 'arbitrage' && (
           <Card title="Arbitrage Strategy Configuration" style={{ marginBottom: 16 }}>
             <Row gutter={16}>
               <Col xs={24} sm={8}>
                 <Form.Item name="pair_1" label="Pair 1" rules={[{ required: true, message: 'Pair 1 is required' }]}>
                   <Input placeholder="e.g., BTCUSDT" />
                 </Form.Item>
               </Col>
               <Col xs={24} sm={8}>
                 <Form.Item name="pair_2" label="Pair 2" rules={[{ required: true, message: 'Pair 2 is required' }]}>
                   <Input placeholder="e.g., ETHBTC" />
                 </Form.Item>
               </Col>
               <Col xs={24} sm={8}>
                 <Form.Item name="pair_3" label="Pair 3" rules={[{ required: true, message: 'Pair 3 is required' }]}>
                   <Input placeholder="e.g., ETHUSDT" />
                 </Form.Item>
               </Col>
               <Col xs={12} sm={12}>
                 <Form.Item name="min_profit_pct" label="Min Profit (%)" rules={[{ required: true, type: 'number', min: 0.01, message: 'Min 0.01%' }]}>
                   <InputNumber style={{ width: '100%' }} placeholder="e.g., 0.1" step="0.01" stringMode />
                 </Form.Item>
               </Col>
               <Col xs={12} sm={12}>
                 <Form.Item name="trade_amount_usd_arb" label="Trade Amount (USD)" rules={[{ required: true, type: 'number', min: 1, message: 'Min 1 USD' }]}>
                   <InputNumber style={{ width: '100%' }} placeholder="e.g., 100" />
                 </Form.Item>
               </Col>
             </Row>
           </Card>
        )}

        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            Create Agent
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
};

export default CreateAgentPage;
