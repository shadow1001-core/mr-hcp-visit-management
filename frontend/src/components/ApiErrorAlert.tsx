import { Alert } from 'antd'

import { ApiError, getErrorMessage } from '../api/errors'

interface ApiErrorAlertProps {
  error: unknown
}

export function ApiErrorAlert({ error }: ApiErrorAlertProps) {
  const requestId = error instanceof ApiError ? error.requestId : undefined
  return (
    <Alert
      type="error"
      showIcon
      message={getErrorMessage(error)}
      description={requestId ? `请求 ID：${requestId}` : undefined}
    />
  )
}
