import { Alert, Button, Descriptions, Space, Spin } from 'antd'
import { useCallback, useEffect, useState } from 'react'

import { getErrorMessage } from '../../api/errors'
import { getHealth, type HealthResponse } from '../../api/health'
import { PageHeader } from '../../components/PageHeader'

export function HealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const loadHealth = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      setHealth(await getHealth())
    } catch (requestError: unknown) {
      setHealth(null)
      setError(getErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadHealth()
  }, [loadHealth])

  return (
    <div className="page-stack page-narrow">
      <PageHeader
        title="系统状态"
        description="检查前端当前配置指向的后端服务是否可用。"
      />
      <Space direction="vertical" size="large" className="full-width">
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
    </div>
  )
}
