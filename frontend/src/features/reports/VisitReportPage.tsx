import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import {
  App as AntdApp,
  Alert,
  Button,
  Col,
  Form,
  Input,
  InputNumber,
  Radio,
  Result,
  Row,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { getVisit, upsertVisitReport } from '../../api/visits'
import type {
  ErrorDetail,
  MaterialDistributionRequest,
  UpsertVisitReportRequest,
  VisitWorkflowDetail,
} from '../../api/types'
import { ApiErrorAlert } from '../../components/ApiErrorAlert'
import { PageHeader } from '../../components/PageHeader'

const { TextArea } = Input

interface ReportFormValues {
  conversationSummary: string
  hcpFeedback: string
  notes?: string
  detailingRecords: Array<{
    productId: string
    contentSummary: string
  }>
  materialDistributions: Array<{
    productId?: string | null
    materialCode: string
    materialName: string
    quantity: number
    isCompliant: boolean
  }>
}

type ReportFieldPath =
  | ['conversationSummary']
  | ['hcpFeedback']
  | ['notes']
  | ['detailingRecords']
  | ['detailingRecords', number, 'productId' | 'contentSummary']
  | ['materialDistributions']
  | [
      'materialDistributions',
      number,
      (
        | 'productId'
        | 'materialCode'
        | 'materialName'
        | 'quantity'
        | 'isCompliant'
      ),
    ]

function referenceLabel(reference: { code: string; name: string }) {
  return `${reference.name}（${reference.code}）`
}

function initialReportValues(detail: VisitWorkflowDetail): ReportFormValues {
  if (detail.status === 'REPORTED' && detail.report) {
    return {
      conversationSummary: detail.report.conversationSummary,
      hcpFeedback: detail.report.hcpFeedback,
      notes: detail.report.notes ?? undefined,
      detailingRecords: detail.report.detailingRecords.map((record) => ({
        productId: record.productId,
        contentSummary: record.contentSummary,
      })),
      materialDistributions: detail.report.materialDistributions.map(
        (material) => ({
          productId: material.productId,
          materialCode: material.materialCode,
          materialName: material.materialName,
          quantity: material.quantity,
          isCompliant: material.isCompliant,
        }),
      ),
    }
  }
  return {
    conversationSummary: '',
    hcpFeedback: '',
    notes: undefined,
    detailingRecords: [{ productId: '', contentSummary: '' }],
    materialDistributions: [],
  }
}

function indexedFieldPath(field: string): ReportFieldPath | null {
  const parts = field.split('.')
  const collection = parts[0]
  const indexText = parts[1]
  const member = parts[2]
  if (
    collection === 'detailingRecords' &&
    indexText !== undefined &&
    /^\d+$/.test(indexText) &&
    (member === 'productId' || member === 'contentSummary')
  ) {
    return [collection, Number(indexText), member]
  }
  if (
    collection === 'materialDistributions' &&
    indexText !== undefined &&
    /^\d+$/.test(indexText) &&
    (member === 'productId' ||
      member === 'materialCode' ||
      member === 'materialName' ||
      member === 'quantity' ||
      member === 'isCompliant')
  ) {
    return [collection, Number(indexText), member]
  }
  switch (field) {
    case 'conversationSummary':
    case 'hcpFeedback':
    case 'notes':
    case 'detailingRecords':
    case 'materialDistributions':
      return [field]
    default:
      return null
  }
}

function matchingProductFieldPaths(
  detail: ErrorDetail,
  values: ReportFormValues,
): ReportFieldPath[] {
  const collection = detail.field.startsWith('detailingRecords')
    ? 'detailingRecords'
    : detail.field.startsWith('materialDistributions')
      ? 'materialDistributions'
      : null
  if (!collection) {
    return []
  }
  if (collection === 'detailingRecords') {
    const matches: ReportFieldPath[] = values.detailingRecords.flatMap(
      (record, index) =>
        detail.value && record.productId === detail.value
          ? [['detailingRecords', index, 'productId']]
          : [],
    )
    return matches.length > 0 ? matches : [['detailingRecords']]
  }
  const matches: ReportFieldPath[] = values.materialDistributions.flatMap(
    (record, index) =>
      detail.value && record.productId === detail.value
        ? [['materialDistributions', index, 'productId']]
        : [],
  )
  return matches.length > 0 ? matches : [['materialDistributions']]
}

function requestFromValues(values: ReportFormValues): UpsertVisitReportRequest {
  const notes = values.notes?.trim()
  return {
    conversationSummary: values.conversationSummary,
    hcpFeedback: values.hcpFeedback,
    notes: notes ? notes : null,
    detailingRecords: values.detailingRecords.map((record) => ({
      productId: record.productId,
      contentSummary: record.contentSummary,
    })),
    materialDistributions: values.materialDistributions.map((material) => ({
      productId: material.productId ?? null,
      materialCode: material.materialCode,
      materialName: material.materialName,
      quantity: material.quantity,
      isCompliant: material.isCompliant,
    })),
  }
}

export function VisitReportPage() {
  const { workflowId } = useParams<{ workflowId: string }>()
  const detailPath = workflowId ? `/visits/${workflowId}` : '/visits'
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()
  const [form] = Form.useForm<ReportFormValues>()
  const [detail, setDetail] = useState<VisitWorkflowDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [submitError, setSubmitError] = useState<unknown>(null)
  const [submitting, setSubmitting] = useState(false)

  const loadDetail = useCallback(async () => {
    if (!workflowId) {
      setLoadError(new Error('缺少拜访工作流 ID。'))
      setLoading(false)
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const response = await getVisit(workflowId)
      setDetail(response)
      form.setFieldsValue(initialReportValues(response))
    } catch (requestError: unknown) {
      setDetail(null)
      setLoadError(requestError)
    } finally {
      setLoading(false)
    }
  }, [form, workflowId])

  useEffect(() => {
    void loadDetail()
  }, [loadDetail])

  const editable = Boolean(
    detail &&
      ((detail.status === 'CHECKED_OUT' &&
        detail.allowedActions.includes('SUBMIT_REPORT')) ||
        (detail.status === 'REPORTED' &&
          detail.allowedActions.includes('UPDATE_REPORT'))),
  )
  const updateMode = detail?.status === 'REPORTED'
  const targetProductOptions = useMemo(
    () =>
      detail?.plan.targetProducts.map((product) => ({
        value: product.id,
        label: referenceLabel(product),
      })) ?? [],
    [detail],
  )
  const detailingRecords = Form.useWatch('detailingRecords', form) ?? []

  async function submit(values: ReportFormValues) {
    if (!workflowId || !editable) {
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      await upsertVisitReport(workflowId, requestFromValues(values))
      void message.success(updateMode ? '拜访报告已更新' : '拜访报告已提交')
      navigate(detailPath, { replace: true })
    } catch (requestError: unknown) {
      setSubmitError(requestError)
      if (requestError instanceof ApiError) {
        const currentValues = form.getFieldsValue(true)
        form.setFields(
          requestError.details.flatMap((errorDetail) => {
            const directPath = indexedFieldPath(errorDetail.field)
            const paths = directPath
              ? [directPath]
              : matchingProductFieldPaths(errorDetail, currentValues)
            return paths.map((name) => ({
              name,
              errors: [requestError.message],
            }))
          }),
        )
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="detail-loading-panel page-narrow">
        <Skeleton active paragraph={{ rows: 12 }} />
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="page-stack page-narrow">
        <PageHeader
          title="拜访报告"
          description="未能加载拜访工作流详情。"
          actions={
            <Button>
              <Link to={detailPath}>返回详情</Link>
            </Button>
          }
        />
        {loadError !== null && <ApiErrorAlert error={loadError} />}
        <Button className="retry-button" onClick={() => void loadDetail()}>
          重新加载
        </Button>
      </div>
    )
  }

  if (!editable) {
    return (
      <div className="page-stack page-narrow">
        <PageHeader
          title="拜访报告"
          description="报告仅可在完成签退后提交或更新。"
          actions={
            <Button>
              <Link to={detailPath}>返回详情</Link>
            </Button>
          }
        />
        <Result
          status="warning"
          title="当前状态不能编辑拜访报告"
          subTitle={`当前状态：${detail.status}。请先完成拜访签退，或从最新详情页重新进入。`}
          extra={
            <Button type="primary" onClick={() => navigate(detailPath)}>
              查看最新详情
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div className="page-stack report-page">
      <PageHeader
        title={updateMode ? '更新拜访报告' : '填写拜访报告'}
        description="保存将整体提交报告内容，但不会修改签到、签退和合规事实。"
        actions={
          <Button disabled={submitting} onClick={() => navigate(detailPath)}>
            返回详情
          </Button>
        }
      />

      <section className="report-context-panel">
        <Space size={[8, 8]} wrap>
          <Typography.Text type="secondary">目标医生</Typography.Text>
          <Typography.Text strong>
            {referenceLabel(detail.plan.hcpPractice.hcp)}
          </Typography.Text>
          <Typography.Text type="secondary">计划产品</Typography.Text>
          {detail.plan.targetProducts.map((product) => (
            <Tag key={product.id}>{referenceLabel(product)}</Tag>
          ))}
        </Space>
      </section>

      <Alert
        type="info"
        showIcon
        message={updateMode ? '当前为整体更新模式' : '当前为首次提交模式'}
        description="此表单只提交谈话、反馈、沟通产品和资料派发数据，不包含任何签到、签退、停留时长或合规字段。"
      />
      {submitError !== null && <ApiErrorAlert error={submitError} />}

      <Form<ReportFormValues>
        form={form}
        layout="vertical"
        requiredMark="optional"
        disabled={submitting}
        onFinish={(values) => void submit(values)}
      >
        <section className="form-panel report-section">
          <Typography.Title level={4}>谈话与反馈</Typography.Title>
          <Row gutter={24}>
            <Col span={12}>
              <Form.Item
                label="谈话要点"
                name="conversationSummary"
                rules={[
                  {
                    required: true,
                    whitespace: true,
                    message: '请输入谈话要点',
                  },
                ]}
              >
                <TextArea
                  rows={5}
                  showCount
                  placeholder="记录本次学术沟通的主要内容"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="医生反馈"
                name="hcpFeedback"
                rules={[
                  {
                    required: true,
                    whitespace: true,
                    message: '请输入医生反馈',
                  },
                ]}
              >
                <TextArea
                  rows={5}
                  showCount
                  placeholder="记录医生的关注点、问题和反馈"
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="备注" name="notes">
            <TextArea rows={3} showCount placeholder="可选补充说明" />
          </Form.Item>
        </section>

        <section className="form-panel report-section">
          <div className="report-section-heading">
            <div>
              <Typography.Title level={4}>实际沟通产品</Typography.Title>
              <Typography.Text type="secondary">
                至少选择一个计划产品，同一产品只能记录一次。
              </Typography.Text>
            </div>
          </div>
          <Form.List
            name="detailingRecords"
            rules={[
              {
                validator: async (
                  _,
                  records: ReportFormValues['detailingRecords'],
                ) => {
                  if (!records || records.length === 0) {
                    throw new Error('请至少添加一个实际沟通产品')
                  }
                  const productIds = records
                    .map((record) => record?.productId)
                    .filter(Boolean)
                  if (new Set(productIds).size !== productIds.length) {
                    throw new Error('同一产品不能重复添加')
                  }
                },
              },
            ]}
          >
            {(fields, { add, remove }, { errors }) => (
              <div className="report-list">
                {fields.map((field) => (
                  <div className="report-list-row" key={field.key}>
                    <Form.Item
                      label="沟通产品"
                      name={[field.name, 'productId']}
                      rules={[{ required: true, message: '请选择沟通产品' }]}
                    >
                      <Select
                        showSearch
                        optionFilterProp="label"
                        placeholder="仅可选择计划产品"
                        options={targetProductOptions.map((option) => ({
                          ...option,
                          disabled: detailingRecords.some(
                            (record, index) =>
                              index !== field.name &&
                              record?.productId === option.value,
                          ),
                        }))}
                      />
                    </Form.Item>
                    <Form.Item
                      className="report-list-main-field"
                      label="学术内容说明"
                      name={[field.name, 'contentSummary']}
                      rules={[
                        {
                          required: true,
                          whitespace: true,
                          message: '请输入学术内容说明',
                        },
                      ]}
                    >
                      <TextArea
                        rows={2}
                        placeholder="说明向医生展示的学术内容或临床数据"
                      />
                    </Form.Item>
                    <Button
                      danger
                      type="text"
                      icon={<DeleteOutlined />}
                      disabled={fields.length === 1}
                      aria-label="删除沟通产品"
                      onClick={() => remove(field.name)}
                    />
                  </div>
                ))}
                <Form.ErrorList errors={errors} />
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  disabled={fields.length >= targetProductOptions.length}
                  onClick={() => add({ productId: '', contentSummary: '' })}
                >
                  添加沟通产品
                </Button>
              </div>
            )}
          </Form.List>
        </section>

        <section className="form-panel report-section">
          <div className="report-section-heading">
            <div>
              <Typography.Title level={4}>资料派发</Typography.Title>
              <Typography.Text type="secondary">
                没有派发资料时可以不添加明细；数量必须为非负整数。
              </Typography.Text>
            </div>
          </div>
          <Form.List name="materialDistributions">
            {(fields, { add, remove }) => (
              <div className="report-list">
                {fields.map((field, index) => (
                  <div className="material-row" key={field.key}>
                    <div className="material-row-heading">
                      <Typography.Text strong>
                        资料明细 {index + 1}
                      </Typography.Text>
                      <Button
                        danger
                        type="text"
                        icon={<DeleteOutlined />}
                        onClick={() => remove(field.name)}
                      >
                        删除
                      </Button>
                    </div>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Form.Item
                          label="关联产品"
                          name={[field.name, 'productId']}
                        >
                          <Select
                            allowClear
                            showSearch
                            optionFilterProp="label"
                            placeholder="可选；不选表示通用资料"
                            options={targetProductOptions}
                          />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item
                          label="资料编码"
                          name={[field.name, 'materialCode']}
                          rules={[
                            {
                              required: true,
                              whitespace: true,
                              message: '请输入资料编码',
                            },
                            {
                              max: 100,
                              message: '资料编码不能超过 100 个字符',
                            },
                          ]}
                        >
                          <Input placeholder="例如 LIT-2026-001" />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item
                          label="资料名称"
                          name={[field.name, 'materialName']}
                          rules={[
                            {
                              required: true,
                              whitespace: true,
                              message: '请输入资料名称',
                            },
                            {
                              max: 200,
                              message: '资料名称不能超过 200 个字符',
                            },
                          ]}
                        >
                          <Input placeholder="例如临床研究文献复印件" />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item
                          label="数量"
                          name={[field.name, 'quantity']}
                          rules={[
                            { required: true, message: '请输入资料数量' },
                            {
                              type: 'integer',
                              min: 0,
                              message: '资料数量必须为非负整数',
                            },
                          ]}
                        >
                          <InputNumber
                            className="full-width"
                            min={0}
                            precision={0}
                            step={1}
                            placeholder="0"
                          />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item
                          label="资料合规性"
                          name={[field.name, 'isCompliant']}
                          rules={[
                            { required: true, message: '请选择资料合规性' },
                          ]}
                        >
                          <Radio.Group
                            options={[
                              { value: true, label: '合规' },
                              { value: false, label: '不合规' },
                            ]}
                          />
                        </Form.Item>
                      </Col>
                    </Row>
                  </div>
                ))}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      productId: null,
                      materialCode: '',
                      materialName: '',
                      quantity: 1,
                      isCompliant: true,
                    } satisfies MaterialDistributionRequest)
                  }
                >
                  添加派发资料
                </Button>
              </div>
            )}
          </Form.List>
        </section>

        <div className="report-form-actions">
          <Button disabled={submitting} onClick={() => navigate(detailPath)}>
            取消
          </Button>
          <Button type="primary" htmlType="submit" loading={submitting}>
            {updateMode ? '保存报告更新' : '提交拜访报告'}
          </Button>
        </div>
      </Form>
    </div>
  )
}
