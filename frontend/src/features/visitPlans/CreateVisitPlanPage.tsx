import {
  App as AntdApp,
  Button,
  Col,
  DatePicker,
  Form,
  Row,
  Select,
} from 'antd'
import type { Dayjs } from 'dayjs'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { getVisitPlanningReferenceData } from '../../api/referenceData'
import type {
  CreateVisitPlanRequest,
  ReferenceView,
  VisitPlanningReferenceDataResponse,
} from '../../api/types'
import { createVisitPlan } from '../../api/visitPlans'
import { ApiErrorAlert } from '../../components/ApiErrorAlert'
import { PageHeader } from '../../components/PageHeader'
import { toBusinessDateTimeIso } from '../../utils/dateTime'

interface CreateVisitPlanFormValues {
  mrId: string
  hospitalId: string
  departmentId: string
  hcpId: string
  productIds: string[]
  plannedAt: Dayjs
}

const apiFieldToFormField: Record<string, keyof CreateVisitPlanFormValues> = {
  mrId: 'mrId',
  hospitalId: 'hospitalId',
  departmentId: 'departmentId',
  hcpId: 'hcpId',
  productIds: 'productIds',
  plannedAt: 'plannedAt',
}

function uniqueReferences(items: ReferenceView[]): ReferenceView[] {
  return [...new Map(items.map((item) => [item.id, item])).values()]
}

function selectOptions(items: ReferenceView[]) {
  return items.map((item) => ({
    value: item.id,
    label: `${item.name}（${item.code}）`,
  }))
}

export function CreateVisitPlanPage() {
  const [form] = Form.useForm<CreateVisitPlanFormValues>()
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()
  const [referenceData, setReferenceData] =
    useState<VisitPlanningReferenceDataResponse | null>(null)
  const [referenceLoading, setReferenceLoading] = useState(true)
  const [referenceError, setReferenceError] = useState<unknown>(null)
  const [submitError, setSubmitError] = useState<unknown>(null)
  const [submitting, setSubmitting] = useState(false)

  const hospitalId = Form.useWatch('hospitalId', form)
  const departmentId = Form.useWatch('departmentId', form)

  const loadReferenceData = useCallback(async () => {
    setReferenceLoading(true)
    setReferenceError(null)
    try {
      setReferenceData(await getVisitPlanningReferenceData())
    } catch (requestError: unknown) {
      setReferenceData(null)
      setReferenceError(requestError)
    } finally {
      setReferenceLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadReferenceData()
  }, [loadReferenceData])

  const hospitals = useMemo(
    () =>
      uniqueReferences(
        referenceData?.practices.map((practice) => practice.hospital) ?? [],
      ),
    [referenceData],
  )
  const departments = useMemo(
    () =>
      uniqueReferences(
        referenceData?.practices
          .filter((practice) => practice.hospital.id === hospitalId)
          .map((practice) => practice.department) ?? [],
      ),
    [hospitalId, referenceData],
  )
  const hcps = useMemo(
    () =>
      uniqueReferences(
        referenceData?.practices
          .filter(
            (practice) =>
              practice.hospital.id === hospitalId &&
              practice.department.id === departmentId,
          )
          .map((practice) => practice.hcp) ?? [],
      ),
    [departmentId, hospitalId, referenceData],
  )

  async function submit(values: CreateVisitPlanFormValues) {
    setSubmitting(true)
    setSubmitError(null)
    const request: CreateVisitPlanRequest = {
      mrId: values.mrId,
      hospitalId: values.hospitalId,
      departmentId: values.departmentId,
      hcpId: values.hcpId,
      productIds: values.productIds,
      plannedAt: toBusinessDateTimeIso(values.plannedAt),
    }
    try {
      const created = await createVisitPlan(request)
      void message.success('拜访计划已创建')
      navigate(`/visits/${created.id}`, { replace: true })
    } catch (requestError: unknown) {
      setSubmitError(requestError)
      if (requestError instanceof ApiError) {
        form.setFields(
          requestError.details.flatMap((detail) => {
            const name = apiFieldToFormField[detail.field]
            return name ? [{ name, errors: [requestError.message] }] : []
          }),
        )
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-stack page-narrow">
      <PageHeader
        title="创建拜访计划"
        description="创建计划不会自动签到；计划成功后进入拜访详情。"
        actions={
          <Button>
            <Link to="/visits">取消并返回</Link>
          </Button>
        }
      />

      {referenceError !== null && (
        <div className="page-stack compact-stack">
          <ApiErrorAlert error={referenceError} />
          <Button onClick={() => void loadReferenceData()}>重新加载选项</Button>
        </div>
      )}
      {submitError !== null && <ApiErrorAlert error={submitError} />}

      <section className="form-panel">
        <Form<CreateVisitPlanFormValues>
          form={form}
          layout="vertical"
          requiredMark="optional"
          disabled={referenceLoading || referenceData === null || submitting}
          onFinish={(values) => void submit(values)}
        >
          <Row gutter={24}>
            <Col span={12}>
              <Form.Item
                label="医药代表"
                name="mrId"
                rules={[{ required: true, message: '请选择医药代表' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="请选择医药代表"
                  loading={referenceLoading}
                  options={selectOptions(
                    referenceData?.medicalRepresentatives ?? [],
                  )}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="计划日期"
                name="plannedAt"
                rules={[{ required: true, message: '请选择计划日期和时间' }]}
              >
                <DatePicker
                  showTime={{ format: 'HH:mm' }}
                  format="YYYY-MM-DD HH:mm"
                  placeholder="请选择计划日期和时间"
                  className="full-width"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="医院"
                name="hospitalId"
                rules={[{ required: true, message: '请选择医院' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="请选择医院"
                  options={selectOptions(hospitals)}
                  onChange={() => {
                    form.setFieldsValue({
                      departmentId: undefined,
                      hcpId: undefined,
                    })
                  }}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="科室"
                name="departmentId"
                rules={[{ required: true, message: '请选择科室' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  disabled={!hospitalId}
                  placeholder={hospitalId ? '请选择科室' : '请先选择医院'}
                  options={selectOptions(departments)}
                  onChange={() => form.setFieldValue('hcpId', undefined)}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="医生"
                name="hcpId"
                rules={[{ required: true, message: '请选择医生' }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  disabled={!departmentId}
                  placeholder={departmentId ? '请选择医生' : '请先选择科室'}
                  options={selectOptions(hcps)}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="目标产品"
                name="productIds"
                rules={[
                  { required: true, message: '请至少选择一个目标产品' },
                  {
                    type: 'array',
                    min: 1,
                    message: '请至少选择一个目标产品',
                  },
                ]}
              >
                <Select
                  mode="multiple"
                  showSearch
                  optionFilterProp="label"
                  placeholder="请选择一个或多个产品"
                  options={selectOptions(referenceData?.products ?? [])}
                />
              </Form.Item>
            </Col>
          </Row>
          <div className="form-actions">
            <Button>
              <Link to="/visits">取消</Link>
            </Button>
            <Button type="primary" htmlType="submit" loading={submitting}>
              创建计划
            </Button>
          </div>
        </Form>
      </section>
    </div>
  )
}
