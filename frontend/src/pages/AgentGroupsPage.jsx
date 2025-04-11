import React, { useState, useEffect, useCallback } from 'react';
import { Typography, Table, Button, Modal, Form, Input, message, Space, Tooltip, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, LoadingOutlined } from '@ant-design/icons';
import { listGroups, createGroup } from '../services/agentApi'; // Keep API calls for later

const { Title } = Typography;

// --- Mock Data ---
const mockGroups = [
  { id: 1, name: 'Grid Bots - High Volatility', description: 'Grid strategies for volatile pairs like BTC, ETH', created_at: new Date(Date.now() - 86400000).toISOString(), updated_at: new Date().toISOString() },
  { id: 2, name: 'Arbitrage Experiments', description: 'Testing triangular arbitrage opportunities', created_at: new Date(Date.now() - 172800000).toISOString(), updated_at: new Date(Date.now() - 3600000).toISOString() },
  { id: 3, name: 'Low Cap Gems', description: null, created_at: new Date(Date.now() - 3600000).toISOString(), updated_at: new Date(Date.now() - 3600000).toISOString() },
];
let nextGroupId = 4; // For simulating creation
// --- End Mock Data ---


const AgentGroupsPage = () => {
  const [groups, setGroups] = useState(mockGroups); // Initialize with mock data
  const [loading, setLoading] = useState(false); // Keep loading state
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null); // For potential edit functionality
  const [form] = Form.useForm();

  // --- Comment out API fetching ---
  // const fetchGroups = useCallback(async () => {
  //   setLoading(true);
  //   try {
  //     const data = await listGroups();
  //     setGroups(Array.isArray(data) ? data : []);
  //   } catch (error) {
  //     message.error('Failed to load groups.');
  //     setGroups([]);
  //   } finally {
  //     setLoading(false);
  //   }
  // }, []);

  // useEffect(() => {
  //   // fetchGroups(); // Don't fetch on mount when using mock data
  // }, [fetchGroups]);
  // --- End Comment out API fetching ---


  const showCreateModal = () => {
    setEditingGroup(null);
    form.resetFields();
    setIsModalVisible(true);
  };

  // TODO: Implement showEditModal(group)

  const handleCancel = () => {
    setIsModalVisible(false);
    setEditingGroup(null);
    form.resetFields();
  };

  const handleFormSubmit = async (values) => {
    setModalLoading(true);
    try {
      if (editingGroup) {
        // TODO: Call updateGroup API
        // await updateGroup(editingGroup.id, values);
        message.success(`Group '${values.name}' updated successfully! (Simulation)`);
        // Simulate update in mock data
        setGroups(prev => prev.map(g => g.id === editingGroup.id ? { ...g, ...values, updated_at: new Date().toISOString() } : g));
      } else {
        // Simulate createGroup API call
        const newGroup = {
          id: nextGroupId++,
          ...values,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setGroups(prev => [...prev, newGroup]);
        message.success(`Group '${newGroup.name}' created successfully! (Simulation)`);
      }
      setIsModalVisible(false);
      setEditingGroup(null);
      // fetchGroups(); // No need to fetch when using mock data
    } catch (error) {
      // This catch block might not be reached in simulation unless form validation fails unexpectedly
      message.error('Failed to save group (Simulation Error).');
    } finally {
      setModalLoading(false);
    }
  };

  // TODO: Implement handleDeleteGroup(groupId)

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', sorter: (a, b) => a.id - b.id },
    { title: 'Name', dataIndex: 'name', key: 'name', sorter: (a, b) => a.name.localeCompare(b.name) },
    { title: 'Description', dataIndex: 'description', key: 'description', render: (desc) => desc || '-' },
    { title: 'Created At', dataIndex: 'created_at', key: 'created_at', render: (ts) => ts ? new Date(ts).toLocaleString() : '-', sorter: (a, b) => new Date(a.created_at) - new Date(b.created_at) },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="Edit Group (TODO)">
            <Button icon={<EditOutlined />} size="small" disabled /* onClick={() => showEditModal(record)} */ />
          </Tooltip>
          <Tooltip title="Delete Group (TODO)">
             <Popconfirm
               title="Delete Group?"
               description={`Are you sure you want to delete group ${record.id} (${record.name})? Agents must be removed first.`}
               // onConfirm={() => handleDeleteGroup(record.id)}
               okText="Yes, Delete"
               cancelText="No"
               okButtonProps={{ danger: true }}
               disabled // TODO: Enable when delete function is ready and API exists
             >
               <Button icon={<DeleteOutlined />} danger size="small" disabled />
             </Popconfirm>
          </Tooltip>
           {/* TODO: Add button to view agents in group */}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={2}>Agent Groups</Title>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={showCreateModal}
        style={{ marginBottom: 16 }}
      >
        Create Group
      </Button>
      <Table
        columns={columns}
        dataSource={groups}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 10 }}
      />
      <Modal
        title={editingGroup ? "Edit Group" : "Create New Group"}
        open={isModalVisible} // Use 'open' prop for Antd v5+
        onCancel={handleCancel}
        footer={null} // Footer handled by Form buttons
        destroyOnClose // Reset form state when modal closes
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleFormSubmit}
          initialValues={editingGroup ? { name: editingGroup.name, description: editingGroup.description } : {}}
        >
          <Form.Item
            name="name"
            label="Group Name"
            rules={[{ required: true, message: 'Please input the group name!' }]}
          >
            <Input placeholder="e.g., High-Frequency Scalpers" />
          </Form.Item>
          <Form.Item
            name="description"
            label="Description (Optional)"
          >
            <Input.TextArea rows={3} placeholder="Purpose or strategy of this group" />
          </Form.Item>
          <Form.Item style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={handleCancel} disabled={modalLoading}>
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" loading={modalLoading}>
                {editingGroup ? "Update" : "Create"}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default AgentGroupsPage;
