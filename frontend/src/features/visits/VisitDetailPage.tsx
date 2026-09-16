import {
  App as AntdApp,
  Alert,
  Button,
  Descriptions,
  Empty,
  Form,
  InputNumber,
  Modal,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { checkInVisit, checkOutVisit, getVisit } from '../../api/visits'
import type {
  AllowedVisitAction,
  ComplianceFindingView,
  ComplianceStatus,
  CoordinatesRequest,
  VisitStatus,
  VisitWorkflowDetail,
} from '../../api/types'
import { ApiErrorAlert } from '../../components/ApiErrorAlert'
import { PageHeader } from '../../components/PageHeader'
import { formatBusinessDateTime } from '../../utils/dateTime'

interface CoordinatesFormValues {
  latitude: number
  longitude: number
}

type CoordinateAction = Extract<AllowedVisitAction, 'CHECK_IN' | 'CHECK_OUT'>

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

const complianceLabels: Record<ComplianceStatus, string> = {
  IN_PROGRESS: '评估未完成',
  NORMAL: '正常',
  ABNORMAL: '异常',
}

const complianceColors: Record<ComplianceStatus, string> = {
  IN_PROGRESS: 'gold',
  NORMAL: 'green',
  ABNORMAL: 'red',
}

const actionLabels: Record<AllowedVisitAction, string> = {
  CHECK_IN: '签到',
  CHECK_OUT: '签退',
  SUBMIT_REPORT: '填写拜访报告',
  UPDATE_REPORT: '更新拜访报告',
}

const findingColumns: TableColumnsType<ComplianceFindingView> = [
  {
    title: '异常原因',
    key: 'reason',
    render: (_, finding) => (
      <div>
        <Tag color="red">{finding.code}</Tag>
        <div className="table-secondary finding-message">{finding.message}</div>
      </div>
    ),
  },
  {
    title: '阶段',
    dataIndex: 'phase',
    width: 110,
  },
  {
    title: '实际值',
    key: 'actualValue',
    width: 160,
    render: (_, finding) => `${finding.actualValue} ${finding.unit}`,
  },
  {
    title: '阈值',
    key: 'threshold',
    width: 160,
    render: (_, finding) => `${finding.threshold} ${finding.unit}`,
  },
  {
    title: '发现时间',
    dataIndex: 'detectedAt',
    width: 170,
    render: (value: string) => formatBusinessDateTime(value),
  },
]

function referenceLabel(reference: { code: string; name: string }) {
  return `${reference.name}（${reference.code}）`
}

function coordinateLabel(latitude: string, longitude: string) {
  return `${latitude}, ${longitude}`
}

function distanceLabel(value: string) {
  return `${Number(value).toFixed(2)} 米`
}

function durationLabel(value: string | null) {
  if (value === null) {
    return '—'
  }
  const seconds = Math.max(0, Math.floor(Number(value)))
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes} 分 ${remainingSeconds} 秒（服务端：${value} 秒）`
}

function complianceStatus(detail: VisitWorkflowDetail) {
  const status = detail.actualVisit?.complianceStatus
  if (!status) {
    return <span className="muted-text">尚未开始评估</span>
  }
  return <Tag color={complianceColors[status]}>{complianceLabels[status]}</Tag>
}

export function VisitDetailPage() {
  const { workflowId } = useParams<{ workflowId: string }>()
  const { message } = AntdApp.useApp()
  const [coordinatesForm] = Form.useForm<CoordinatesFormValues>()
  const [detail, setDetail] = useState<VisitWorkflowDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState<unknown>(null)
  const [coordinateAction, setCoordinateAction] =
    useState<CoordinateAction | null>(null)
  const [operationError, setOperationError] = useState<unknown>(null)
  const [submitting, setSubmitting] = useState(false)

  const loadDetail = useCallback(async () => {
    if (!workflowId) {
      setPageError(new Error('缺少拜访工作流 ID。'))
      setLoading(false)
      return
    }
    setLoading(true)
    setPageError(null)
    try {
      setDetail(await getVisit(workflowId))
    } catch (requestError: unknown) {
      setPageError(requestError)
    } finally {
      setLoading(false)
    }
  }, [workflowId])

  useEffect(() => {
    void loadDetail()
  }, [loadDetail])

  const availableActionLabels = useMemo(
    () => detail?.allowedActions.map((action) => actionLabels[action]) ?? [],
    [detail],
  )

  function openCoordinatesModal(action: CoordinateAction) {
    coordinatesForm.resetFields()
    setOperationError(null)
    setCoordinateAction(action)
  }

  function closeCoordinatesModal() {
    if (submitting) {
      return
    }
    setCoordinateAction(null)
    setOperationError(null)
    coordinatesForm.resetFields()
  }

  async function submitCoordinates(values: CoordinatesFormValues) {
    if (!workflowId || !coordinateAction) {
      return
    }
    setSubmitting(true)
    setOperationError(null)
    coordinatesForm.setFields([
      { name: 'latitude', errors: [] },
      { name: 'longitude', errors: [] },
    ])
    const request: CoordinatesRequest = {
      latitude: values.latitude,
      longitude: values.longitude,
    }
    try {
      if (coordinateAction === 'CHECK_IN') {
        await checkInVisit(workflowId, request)
      } else {
        await checkOutVisit(workflowId, request)
      }
      const successText =
        coordinateAction === 'CHECK_IN' ? '签到成功' : '签退成功'
      setCoordinateAction(null)
      coordinatesForm.resetFields()
      void message.success(successText)
      await loadDetail()
    } catch (requestError: unknown) {
      setOperationError(requestError)
      if (requestError instanceof ApiError) {
        coordinatesForm.setFields(
          requestError.details.flatMap((item) => {
            if (item.field !== 'latitude' && item.field !== 'longitude') {
              return []
            }
            return [{ name: item.field, errors: [requestError.message] }]
          }),
        )
        if (requestError.status === 409) {
          void loadDetail()
        }
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading && detail === null) {
    return (
      <div className="detail-loading-panel">
        <Skeleton active paragraph={{ rows: 10 }} />
      </div>
    )
  }

  if (detail === null) {
    return (
      <div className="page-stack">
        <PageHeader
          title="拜访详情"
          description="未能加载拜访工作流详情。"
          actions={
            <Button>
              <Link to="/visits">返回列表</Link>
            </Button>
          }
        />
        {pageError !== null && <ApiErrorAlert error={pageError} />}
        <Button className="retry-button" onClick={() => void loadDetail()}>
          重新加载
        </Button>
      </div>
    )
  }

  const plan = detail.plan
  const actualVisit = detail.actualVisit
  const checkIn = actualVisit?.checkIn
  const checkOut = actualVisit?.checkOut
  const operationsDisabled = submitting || loading

  return (
    <div className="page-stack">
      <PageHeader
        title="拜访详情"
        description="时间、距离、停留时长和合规结论均来自服务端。"
        actions={
          <Space>
            <Button>
              <Link to="/visits">返回列表</Link>
            </Button>
            {detail.allowedActions.includes('CHECK_IN') && (
              <Button
                type="primary"
                disabled={operationsDisabled}
                onClick={() => openCoordinatesModal('CHECK_IN')}
              >
                签到
              </Button>
            )}
            {detail.allowedActions.includes('CHECK_OUT') && (
              <Button
                type="primary"
                disabled={operationsDisabled}
                onClick={() => openCoordinatesModal('CHECK_OUT')}
              >
                签退
              </Button>
            )}
            {detail.allowedActions.includes('SUBMIT_REPORT') && (
              <Button type="primary" disabled={operationsDisabled}>
                <Link to={`/visits/${detail.id}/report`}>填写拜访报告</Link>
              </Button>
            )}
            {detail.allowedActions.includes('UPDATE_REPORT') && (
              <Button type="primary" disabled={operationsDisabled}>
                <Link to={`/visits/${detail.id}/report`}>更新拜访报告</Link>
              </Button>
            )}
          </Space>
        }
      />

      {pageError !== null && <ApiErrorAlert error={pageError} />}

      <section className="detail-panel">
        <div className="detail-section-heading">
          <Typography.Title level={4}>计划信息</Typography.Title>
          <Space>
            <Tag color={statusColors[detail.status]}>
              {statusLabels[detail.status]}
            </Tag>
            {complianceStatus(detail)}
          </Space>
        </div>
        <Descriptions bordered column={2} size="middle">
          <Descriptions.Item label="工作流 ID" span={2}>
            <Typography.Text code copyable>
              {detail.id}
            </Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="计划日期">
            {formatBusinessDateTime(plan.plannedAt)}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {formatBusinessDateTime(plan.createdAt)}
          </Descriptions.Item>
          <Descriptions.Item label="医药代表">
            {referenceLabel(plan.mr)}
          </Descriptions.Item>
          <Descriptions.Item label="目标医生">
            {referenceLabel(plan.hcpPractice.hcp)}
          </Descriptions.Item>
          <Descriptions.Item label="医院">
            {referenceLabel(plan.hcpPractice.hospital)}
          </Descriptions.Item>
          <Descriptions.Item label="科室">
            {referenceLabel(plan.hcpPractice.department)}
          </Descriptions.Item>
          <Descriptions.Item label="医院坐标" span={2}>
            {coordinateLabel(
              detail.hospitalCoordinates.latitude,
              detail.hospitalCoordinates.longitude,
            )}
            {actualVisit && (
              <Typography.Text type="secondary" className="snapshot-note">
                签到时快照
              </Typography.Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="目标产品" span={2}>
            <Space size={[0, 6]} wrap>
              {plan.targetProducts.map((product) => (
                <Tag key={product.id}>{referenceLabel(product)}</Tag>
              ))}
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </section>

      <section className="detail-panel">
        <div className="detail-section-heading">
          <Typography.Title level={4}>现场执行</Typography.Title>
        </div>
        {!actualVisit ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="尚未签到，暂无现场执行记录"
          />
        ) : (
          <Descriptions bordered column={2} size="middle">
            <Descriptions.Item label="签到时间">
              {formatBusinessDateTime(checkIn!.at)}
            </Descriptions.Item>
            <Descriptions.Item label="签到坐标">
              {coordinateLabel(checkIn!.latitude, checkIn!.longitude)}
            </Descriptions.Item>
            <Descriptions.Item label="签到距离">
              {distanceLabel(checkIn!.distanceMeters)}
            </Descriptions.Item>
            <Descriptions.Item label="签退时间">
              {checkOut ? formatBusinessDateTime(checkOut.at) : '尚未签退'}
            </Descriptions.Item>
            <Descriptions.Item label="签退坐标">
              {checkOut
                ? coordinateLabel(checkOut.latitude, checkOut.longitude)
                : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="签退距离">
              {checkOut ? distanceLabel(checkOut.distanceMeters) : '—'}
            </Descriptions.Item>
            <Descriptions.Item label="停留时长" span={2}>
              {durationLabel(actualVisit.durationSeconds)}
            </Descriptions.Item>
          </Descriptions>
        )}
      </section>

      <section className="detail-panel">
        <div className="detail-section-heading">
          <Typography.Title level={4}>合规结果</Typography.Title>
          {complianceStatus(detail)}
        </div>
        {!actualVisit ? (
          <Alert type="info" showIcon message="尚未签到，合规评估未开始。" />
        ) : actualVisit.complianceFindings.length === 0 ? (
          <Alert
            type={
              actualVisit.complianceStatus === 'NORMAL' ? 'success' : 'info'
            }
            showIcon
            message={
              actualVisit.complianceStatus === 'NORMAL'
                ? '服务端未发现合规异常。'
                : '当前尚无已发现异常；签退后完成最终评估。'
            }
          />
        ) : (
          <Table<ComplianceFindingView>
            rowKey={(finding) =>
              `${finding.code}-${finding.phase}-${finding.detectedAt}`
            }
            columns={findingColumns}
            dataSource={actualVisit.complianceFindings}
            pagination={false}
            size="middle"
          />
        )}
      </section>

      <section className="detail-panel">
        <div className="detail-section-heading">
          <Typography.Title level={4}>当前允许执行的操作</Typography.Title>
        </div>
        <Space wrap>
          {availableActionLabels.map((label) => (
            <Tag color="blue" key={label}>
              {label}
            </Tag>
          ))}
        </Space>
        <Typography.Paragraph type="secondary" className="action-note">
          操作权限以本次详情响应的 allowedActions
          为准；写操作成功后会重新加载详情。
        </Typography.Paragraph>
      </section>

      <Modal
        title={coordinateAction === 'CHECK_IN' ? '拜访签到' : '拜访签退'}
        open={coordinateAction !== null}
        okText={coordinateAction === 'CHECK_IN' ? '确认签到' : '确认签退'}
        cancelText="取消"
        confirmLoading={submitting}
        okButtonProps={{ disabled: submitting }}
        cancelButtonProps={{ disabled: submitting }}
        maskClosable={!submitting}
        keyboard={!submitting}
        onOk={() => coordinatesForm.submit()}
        onCancel={closeCoordinatesModal}
      >
        <div className="coordinate-modal-content">
          <Alert
            type="info"
            showIcon
            message="GPS 坐标为演示手工输入"
            description="签到/签退时间、距离、停留时长和最终合规结论均由服务端生成。"
          />
          {coordinateAction === 'CHECK_OUT' && (
            <Alert
              type="warning"
              showIcon
              message="签退事实提交后不可覆盖"
              description="请确认坐标准确；签退完成后进入拜访报告阶段。"
            />
          )}
          {operationError !== null && <ApiErrorAlert error={operationError} />}
          <Form<CoordinatesFormValues>
            form={coordinatesForm}
            layout="vertical"
            requiredMark="optional"
            onFinish={(values) => void submitCoordinates(values)}
          >
            <Form.Item
              label="纬度"
              name="latitude"
              extra="合法范围：-90 至 90"
              rules={[
                { required: true, message: '请输入纬度' },
                {
                  type: 'number',
                  min: -90,
                  max: 90,
                  message: '纬度必须在 -90 至 90 之间',
                },
              ]}
            >
              <InputNumber
                className="full-width"
                min={-90}
                max={90}
                step={0.000001}
                controls={false}
                placeholder="例如 31.210460"
              />
            </Form.Item>
            <Form.Item
              label="经度"
              name="longitude"
              extra="合法范围：-180 至 180"
              rules={[
                { required: true, message: '请输入经度' },
                {
                  type: 'number',
                  min: -180,
                  max: 180,
                  message: '经度必须在 -180 至 180 之间',
                },
              ]}
            >
              <InputNumber
                className="full-width"
                min={-180}
                max={180}
                step={0.000001}
                controls={false}
                placeholder="例如 121.473650"
              />
            </Form.Item>
          </Form>
        </div>
      </Modal>
    </div>
  )
}
