import '@ant-design/v5-patch-for-react-19'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { App as AntdApp, ConfigProvider } from 'antd'
import { BrowserRouter } from 'react-router-dom'

import 'antd/dist/reset.css'
import './styles.css'
import { App } from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#176B87',
          borderRadius: 6,
        },
      }}
    >
      <AntdApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
)
