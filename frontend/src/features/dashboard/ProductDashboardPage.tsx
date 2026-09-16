import {
  Alert,
  Button,
  DatePicker,
  Empty,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import type { Dayjs } from 'dayjs'
import { useCallback, useEffect, useState } from 'react'

import { getMonthlyProductVisits } from '../../api/dashboard'
import type {
  MonthlyProductVisitItem,
  MonthlyProductVisitsResponse,
} from '../../api/types'
import { ApiErrorAlert } from '../../components/ApiErrorAlert'
import { PageHeader } from '../../components/PageHeader'
import { appConfig } from '../../config/env'
import { currentBusinessMonth } from '../../utils/dateTime'
import { dashboardColors } from './dashboardTheme'
import { ProductVisitChart } from './ProductVisitChart'

const columns: TableColumnsType<MonthlyProductVisitItem> = [
  {
    title: '产品',
    key: 'product',
    render: (_, item) => (
      <div>
        <div>{item.product.name}</div>
        <div className="table-secondary">{item.product.code}</div>
      </div>
    ),
  },
  {
    title: '总次数',
    dataIndex: 'totalCount',
    width: 130,
    align: 'right',
    render: (value: number) => <Tag color={dashboardColors.total}>{value}</Tag>,
  },
  {
    title: '正常',
    dataIndex: 'normalCount',
    width: 130,
    align: 'right',
    render: (value: number) => (
      <Tag color={dashboardColors.normal}>{value}</Tag>
    ),
  },
  {
    title: '异常',
    dataIndex: 'abnormalCount',
    width: 130,
    align: 'right',
    render: (value: number) => (
      <Tag color={dashboardColors.abnormal}>{value}</Tag>
    ),
  },
  {
    title: '待评估',
    dataIndex: 'pendingCount',
    width: 130,
    align: 'right',
    render: (value: number) => (
      <Tag color={dashboardColors.pending}>{value}</Tag>
    ),
  },
]

export function ProductDashboardPage() {
  const [selectedMonth, setSelectedMonth] = useState<Dayjs>(() =>
    currentBusinessMonth(),
  )
  const [data, setData] = useState<MonthlyProductVisitsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const month = selectedMonth.format('YYYY-MM')

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await getMonthlyProductVisits({ month }))
    } catch (requestError: unknown) {
      setData(null)
      setError(requestError)
    } finally {
      setLoading(false)
    }
  }, [month])

  useEffect(() => {
    void loadDashboard()
  }, [loadDashboard])

  function changeMonth(value: Dayjs | null) {
    if (value) {
      setSelectedMonth(value.startOf('month'))
    }
  }

  const items = data?.items ?? []
  const timezoneMismatch =
    data !== null && data.businessTimezone !== appConfig.businessTimezone

  return (
    <div className="page-stack">
      <PageHeader
        title="产品月度看板"
        description="按服务端业务时区和实际签到月份统计产品拜访次数。"
      />

      <section className="dashboard-filter-panel">
        <Space size="middle">
          <Typography.Text strong>统计月份</Typography.Text>
          <DatePicker
            picker="month"
            allowClear={false}
            value={selectedMonth}
            format="YYYY-MM"
            onChange={changeMonth}
          />
          <Typography.Text type="secondary">
            业务时区：{data?.businessTimezone ?? appConfig.businessTimezone}
          </Typography.Text>
        </Space>
      </section>

      {error !== null && (
        <section className="dashboard-error-panel">
          <ApiErrorAlert error={error} />
          <Button type="primary" onClick={() => void loadDashboard()}>
            重新加载
          </Button>
        </section>
      )}

      {timezoneMismatch && (
        <Alert
          type="warning"
          showIcon
          message="业务时区配置不一致"
          description={`前端配置为 ${appConfig.businessTimezone}，统计接口使用 ${data.businessTimezone}；看板月份口径以接口响应为准。`}
        />
      )}

      {loading ? (
        <section className="dashboard-content-panel">
          <Skeleton active paragraph={{ rows: 12 }} />
        </section>
      ) : error === null && items.length === 0 ? (
        <section className="dashboard-empty-panel">
          <Empty
            description={`${data?.month ?? month} 暂无已签到的产品拜访数据`}
          >
            <Typography.Text type="secondary">
              未签到的计划不会计入看板，可切换其他月份查看。
            </Typography.Text>
          </Empty>
        </section>
      ) : error === null && data ? (
        <>
          <section className="dashboard-content-panel">
            <div className="dashboard-section-heading">
              <div>
                <Typography.Title level={4}>月度拜访分布</Typography.Title>
                <Typography.Text type="secondary">
                  每个柱状值直接来自服务端聚合结果，单位为拜访次数。
                </Typography.Text>
              </div>
              <Space wrap>
                <Tag color={dashboardColors.total}>总数</Tag>
                <Tag color={dashboardColors.normal}>正常</Tag>
                <Tag color={dashboardColors.abnormal}>异常</Tag>
                <Tag color={dashboardColors.pending}>待评估</Tag>
              </Space>
            </div>
            <ProductVisitChart items={items} month={data.month} />
          </section>

          <section className="table-panel">
            <div className="dashboard-table-heading">
              <Typography.Title level={4}>产品统计明细</Typography.Title>
              <Typography.Text type="secondary">
                共 {items.length} 个有拜访记录的产品
              </Typography.Text>
            </div>
            <Table<MonthlyProductVisitItem>
              rowKey={(item) => item.product.id}
              columns={columns}
              dataSource={items}
              pagination={false}
              locale={{ emptyText: '暂无产品拜访数据' }}
            />
          </section>
        </>
      ) : null}
    </div>
  )
}
