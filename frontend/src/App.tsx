import { DashboardOutlined, HeartOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { HealthPage } from './features/health/HealthPage'
import { HomePage } from './features/home/HomePage'

const { Header, Content, Sider } = Layout

const navigationItems = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: <NavLink to="/">首页</NavLink>,
  },
  {
    key: '/health',
    icon: <HeartOutlined />,
    label: <NavLink to="/health">系统状态</NavLink>,
  },
]

export function App() {
  const location = useLocation()

  return (
    <Layout className="app-shell">
      <Sider width={232} theme="dark">
        <div className="brand">学术拜访管理</div>
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[location.pathname]}
          items={navigationItems}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Typography.Title level={4} className="app-title">
            医药代表学术拜访管理子系统
          </Typography.Title>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
