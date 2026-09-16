import { Button, DatePicker, Form, Select, Space, Table, Tag } from 'antd'
import type { TableColumnsType } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { listVisits } from '../../api/visits'
import type {
  VisitListParams,
  VisitStatus,
  VisitWorkflowSummary,
} from '../../api/types'
import { ApiErrorAlert } from '../../components/ApiErrorAlert'
import { PageHeader } from '../../components/PageHeader'
import {
  businessDateRangeFromUtc,
  formatBusinessDateTime,
  toBusinessDayRange,
} from '../../utils/dateTime'

const { RangePicker } = DatePicker

const statusLabels: Record<VisitStatus, string> = {
  PLANNED: '待签到',
  CHECKED_IN: '拜访进行中',
  CHECKED_OUT: '待提交报告',
  REPORTED: '已完成',
}

const statusColors: Record<VisitStatus, string> = {
  PLANNED: 'blue',
  CHECKED_IN: 'cyan',
  CHECKED_OUT: 'gold',
  REPORTED: 'green',
}

const visitStatuses = Object.keys(statusLabels) as VisitStatus[]

function isVisitStatus(value: string): value is VisitStatus {
  return visitStatuses.includes(value as VisitStatus)
}

function positiveInteger(value: string | null, fallback: number): number {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function complianceLabel(item: VisitWorkflowSummary) {
  const execution = item.executionSummary
  if (!execution) {
    return <span className="muted-text">—</span>
  }
  if (execution.isAbnormal) {
    return (
      <Space direction="vertical" size={0}>
        <Tag color="red">异常</Tag>
        {!execution.checkOutAt && (
          <span className="table-secondary">最终评估未完成</span>
        )}
      </Space>
    )
  }
  if (!execution.checkOutAt) {
    return <Tag color="gold">评估未完成</Tag>
  }
  return <Tag color="green">正常</Tag>
}

const columns: TableColumnsType<VisitWorkflowSummary> = [
  {
    title: '计划日期',
    dataIndex: 'plannedAt',
    width: 160,
    render: (value: string, item) => (
      <Link to={`/visits/${item.id}`}>{formatBusinessDateTime(value)}</Link>
    ),
  },
  {
    title: 'MR',
    width: 140,
    render: (_, item) => (
      <div>
        <div>{item.mr.name}</div>
        <div className="table-secondary">{item.mr.code}</div>
      </div>
    ),
  },
  {
    title: '医生',
    width: 140,
    render: (_, item) => (
      <div>
        <div>{item.hcpPractice.hcp.name}</div>
        <div className="table-secondary">{item.hcpPractice.hcp.code}</div>
      </div>
    ),
  },
  {
    title: '医院',
    width: 220,
    render: (_, item) => item.hcpPractice.hospital.name,
  },
  {
    title: '科室',
    width: 120,
    render: (_, item) => item.hcpPractice.department.name,
  },
  {
    title: '产品',
    width: 220,
    render: (_, item) => (
      <Space size={[0, 4]} wrap>
        {item.targetProducts.map((product) => (
          <Tag key={product.id}>{product.name}</Tag>
        ))}
      </Space>
    ),
  },
  {
    title: '状态',
    dataIndex: 'status',
    width: 120,
    render: (status: VisitStatus) => (
      <Tag color={statusColors[status]}>{statusLabels[status]}</Tag>
    ),
  },
  {
    title: '合规状态',
    width: 140,
    render: (_, item) => complianceLabel(item),
  },
  {
    title: '操作',
    key: 'actions',
    fixed: 'right',
    width: 90,
    render: (_, item) => <Link to={`/visits/${item.id}`}>查看详情</Link>,
  },
]

export function VisitListPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState<VisitWorkflowSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)

  const statuses = useMemo(
    () => searchParams.getAll('status').filter(isVisitStatus),
    [searchParams],
  )
  const plannedFrom = searchParams.get('plannedFrom')
  const plannedTo = searchParams.get('plannedTo')
  const page = positiveInteger(searchParams.get('page'), 1)
  const pageSize = Math.min(
    positiveInteger(searchParams.get('pageSize'), 20),
    100,
  )
  const dateRange = businessDateRangeFromUtc(plannedFrom, plannedTo)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    const params: VisitListParams = {
      page,
      pageSize,
      order: 'desc',
      sort: 'plannedAt',
      ...(statuses.length > 0 ? { status: statuses } : {}),
      ...(plannedFrom ? { plannedFrom } : {}),
      ...(plannedTo ? { plannedTo } : {}),
    }
    void listVisits(params)
      .then((result) => {
        if (!active) {
          return
        }
        setData(result.items)
        setTotal(result.total)
      })
      .catch((requestError: unknown) => {
        if (active) {
          setData([])
          setTotal(0)
          setError(requestError)
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [page, pageSize, plannedFrom, plannedTo, statuses])

  function updateSearchParams(
    updates: Record<string, string | string[] | null>,
  ) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(updates)) {
      next.delete(key)
      if (Array.isArray(value)) {
        value.forEach((item) => next.append(key, item))
      } else if (value !== null) {
        next.set(key, value)
      }
    }
    setSearchParams(next)
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="拜访管理"
        description="统一查看计划、现场执行、合规状态和报告进度。"
        actions={
          <Button type="primary">
            <Link to="/visit-plans/new">创建拜访计划</Link>
          </Button>
        }
      />

      <section className="filter-panel">
        <Form layout="inline">
          <Form.Item label="状态">
            <Select<VisitStatus[]>
              mode="multiple"
              allowClear
              placeholder="全部状态"
              className="status-filter"
              value={statuses}
              options={visitStatuses.map((status) => ({
                value: status,
                label: statusLabels[status],
              }))}
              onChange={(value) =>
                updateSearchParams({ status: value, page: '1' })
              }
            />
          </Form.Item>
          <Form.Item label="计划日期">
            <RangePicker
              value={dateRange}
              onChange={(dates) => {
                if (dates?.[0] && dates[1]) {
                  updateSearchParams({
                    ...toBusinessDayRange(dates[0], dates[1]),
                    page: '1',
                  })
                } else {
                  updateSearchParams({
                    plannedFrom: null,
                    plannedTo: null,
                    page: '1',
                  })
                }
              }}
            />
          </Form.Item>
          <Button
            onClick={() =>
              setSearchParams({ page: '1', pageSize: String(pageSize) })
            }
          >
            重置
          </Button>
        </Form>
      </section>

      {error !== null && <ApiErrorAlert error={error} />}

      <section className="table-panel">
        <Table<VisitWorkflowSummary>
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 1450 }}
          locale={{ emptyText: '没有符合当前条件的拜访' }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (count) => `共 ${count} 条`,
            pageSizeOptions: [10, 20, 50, 100],
            onChange: (nextPage, nextPageSize) =>
              updateSearchParams({
                page: String(nextPageSize === pageSize ? nextPage : 1),
                pageSize: String(nextPageSize),
              }),
          }}
          onRow={(item) => ({
            className: 'clickable-row',
            onClick: () => navigate(`/visits/${item.id}`),
          })}
        />
      </section>
    </div>
  )
}
