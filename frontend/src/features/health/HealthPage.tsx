import {
  Alert,
  Button,
  Card,
  Descriptions,
  Space,
  Spin,
  Typography,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'

import { getHealth, type HealthResponse } from '../../api/health'

export function HealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const loadHealth = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      setHealth(await getHealth())
    } catch {
      setHealth(null)
      setError('无法连接后端健康检查接口，请确认 API 已启动。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadHealth()
  }, [loadHealth])

  return (
    <Card>
      <Space direction="vertical" size="large" className="full-width">
        <Typography.Title level={2}>系统状态</Typography.Title>
        {loading && <Spin tip="正在检查后端服务" />}
        {error && <Alert type="error" message={error} showIcon />}
        {health && (
          <Descriptions bordered column={1}>
            <Descriptions.Item label="状态">{health.status}</Descriptions.Item>
            <Descriptions.Item label="服务">{health.service}</Descriptions.Item>
            <Descriptions.Item label="版本">{health.version}</Descriptions.Item>
            <Descriptions.Item label="环境">
              {health.environment}
            </Descriptions.Item>
          </Descriptions>
        )}
        <Button onClick={() => void loadHealth()} loading={loading}>
          重新检查
        </Button>
      </Space>
    </Card>
  )
}
