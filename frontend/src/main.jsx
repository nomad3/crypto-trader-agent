import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
// Import Ant Design CSS globally (or use component-level imports/theme provider)
import 'antd/dist/reset.css'; // Ant Design v5 reset
// import './index.css' // Optional: Your custom global styles

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
