import { Card, Space, Typography } from 'antd'

export function HomePage() {
  return (
    <Card>
      <Space direction="vertical" size="middle">
        <Typography.Title level={2}>项目脚手架已就绪</Typography.Title>
        <Typography.Paragraph>
          当前版本提供前后端基础设施、数据库配置和健康检查，尚未实现具体拜访业务。
        </Typography.Paragraph>
      </Space>
    </Card>
  )
}
