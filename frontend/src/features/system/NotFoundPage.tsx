import { Button, Result } from 'antd'
import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="请检查地址，或返回拜访管理页面。"
      extra={
        <Button type="primary">
          <Link to="/visits">返回拜访列表</Link>
        </Button>
      }
    />
  )
}
