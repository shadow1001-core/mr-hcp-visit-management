import {
  BarChartOutlined,
  CalendarOutlined,
  FileAddOutlined,
  HeartOutlined,
} from '@ant-design/icons'
import { Layout, Menu, Space, Tag, Typography } from 'antd'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { appConfig } from './config/env'
import { ProductDashboardPage } from './features/dashboard/ProductDashboardPage'
import { HealthPage } from './features/health/HealthPage'
import { VisitReportPage } from './features/reports/VisitReportPage'
import { NotFoundPage } from './features/system/NotFoundPage'
import { CreateVisitPlanPage } from './features/visitPlans/CreateVisitPlanPage'
import { VisitDetailPage } from './features/visits/VisitDetailPage'
import { VisitListPage } from './features/visits/VisitListPage'

const { Header, Content, Sider } = Layout

const navigationItems = [
  {
    key: '/visits',
    icon: <CalendarOutlined />,
    label: <Link to="/visits">拜访管理</Link>,
  },
  {
    key: '/visit-plans/new',
    icon: <FileAddOutlined />,
    label: <Link to="/visit-plans/new">创建拜访计划</Link>,
  },
  {
    key: '/dashboard/products',
    icon: <BarChartOutlined />,
    label: <Link to="/dashboard/products">产品月度看板</Link>,
  },
  {
    key: '/system/health',
    icon: <HeartOutlined />,
    label: <Link to="/system/health">系统状态</Link>,
  },
]

function activeNavigationKey(pathname: string): string {
  if (pathname.startsWith('/dashboard/')) {
    return '/dashboard/products'
  }
  if (pathname === '/visit-plans/new') {
    return '/visit-plans/new'
  }
  if (pathname.startsWith('/visits')) {
    return '/visits'
  }
  if (pathname === '/system/health') {
    return '/system/health'
  }
  return ''
}

export function App() {
  const location = useLocation()

  return (
    <Layout className="app-shell">
      <Sider width={232} theme="dark">
        <div className="brand">学术拜访管理</div>
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[activeNavigationKey(location.pathname)]}
          items={navigationItems}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Typography.Title level={4} className="app-title">
            医药代表学术拜访管理子系统
          </Typography.Title>
          <Space className="app-header-meta">
            <Typography.Text type="secondary">业务时区</Typography.Text>
            <Tag>{appConfig.businessTimezone}</Tag>
          </Space>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Navigate to="/visits" replace />} />
            <Route path="/visits" element={<VisitListPage />} />
            <Route path="/visit-plans/new" element={<CreateVisitPlanPage />} />
            <Route path="/visits/:workflowId" element={<VisitDetailPage />} />
            <Route
              path="/visits/:workflowId/report"
              element={<VisitReportPage />}
            />
            <Route
              path="/dashboard/products"
              element={<ProductDashboardPage />}
            />
            <Route path="/system/health" element={<HealthPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
