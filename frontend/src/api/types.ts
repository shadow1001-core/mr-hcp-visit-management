/**
 * Central API contract types mirrored from the backend OpenAPI schema.
 * Keep wire names in camelCase so request and response objects need no remapping.
 */

export type UUID = string
export type ISODateTime = string
export type DecimalValue = string

export type VisitStatus = 'PLANNED' | 'CHECKED_IN' | 'CHECKED_OUT' | 'REPORTED'

export type AllowedVisitAction =
  | 'CHECK_IN'
  | 'CHECK_OUT'
  | 'SUBMIT_REPORT'
  | 'UPDATE_REPORT'

export type ComplianceStatus = 'IN_PROGRESS' | 'NORMAL' | 'ABNORMAL'

export interface ErrorDetail {
  field: string
  reason: string
  value?: string
}

export interface ErrorEnvelope {
  error: {
    code: string
    message: string
    details: ErrorDetail[]
  }
  requestId?: string
}

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
  environment: string
}

export interface ReferenceView {
  id: UUID
  code: string
  name: string
}

export interface HcpPracticeView {
  id: UUID
  hcp: ReferenceView
  hospital: ReferenceView
  department: ReferenceView
}

export interface VisitPlanningReferenceDataResponse {
  medicalRepresentatives: ReferenceView[]
  products: ReferenceView[]
  practices: HcpPracticeView[]
}

export interface VisitPlanResponse {
  id: UUID
  status: VisitStatus
  plannedAt: ISODateTime
  createdAt: ISODateTime
  mr: ReferenceView
  hcpPractice: HcpPracticeView
  targetProducts: ReferenceView[]
}

export interface ExecutionSummaryView {
  checkInAt: ISODateTime
  checkOutAt: ISODateTime | null
  durationSeconds: DecimalValue | null
  isAbnormal: boolean
  findingCodes: string[]
}

export interface VisitWorkflowSummary extends VisitPlanResponse {
  executionSummary: ExecutionSummaryView | null
  reportSubmittedAt: ISODateTime | null
}

export interface VisitMomentView {
  at: ISODateTime
  latitude: DecimalValue
  longitude: DecimalValue
  distanceMeters: DecimalValue
}

export interface CoordinateView {
  latitude: DecimalValue
  longitude: DecimalValue
}

export interface ComplianceFindingView {
  code: string
  message: string
  actualValue: DecimalValue
  threshold: DecimalValue
  phase: string
  unit: string
  detectedAt: ISODateTime
}

export interface DetailingRecordView {
  productId: UUID
  contentSummary: string
}

export interface MaterialDistributionView {
  id: UUID
  productId: UUID | null
  materialCode: string
  materialName: string
  quantity: number
  isCompliant: boolean
}

export interface VisitReportView {
  conversationSummary: string
  hcpFeedback: string
  notes: string | null
  detailingRecords: DetailingRecordView[]
  materialDistributions: MaterialDistributionView[]
  submittedAt: ISODateTime
  createdAt: ISODateTime
}

export interface ActualVisitView {
  checkIn: VisitMomentView
  checkOut: VisitMomentView | null
  durationSeconds: DecimalValue | null
  products: ReferenceView[]
  complianceStatus: ComplianceStatus
  complianceFindings: ComplianceFindingView[]
}

export interface VisitWorkflowDetail {
  id: UUID
  status: VisitStatus
  plan: VisitPlanResponse
  hospitalCoordinates: CoordinateView
  actualVisit: ActualVisitView | null
  report: VisitReportView | null
  allowedActions: AllowedVisitAction[]
}

export interface PaginatedResponse<Item> {
  items: Item[]
  page: number
  pageSize: number
  total: number
}

export type PaginatedVisitPlans = PaginatedResponse<VisitPlanResponse>
export type PaginatedVisitWorkflows = PaginatedResponse<VisitWorkflowSummary>

export interface CreateVisitPlanRequest {
  mrId: UUID
  hcpId: UUID
  hospitalId: UUID
  departmentId: UUID
  plannedAt: ISODateTime
  productIds: UUID[]
}

export interface CoordinatesRequest {
  latitude: number
  longitude: number
}

export interface DetailingRecordRequest {
  productId: UUID
  contentSummary: string
}

export interface MaterialDistributionRequest {
  productId?: UUID | null
  materialCode: string
  materialName: string
  quantity: number
  isCompliant: boolean
}

export interface UpsertVisitReportRequest {
  conversationSummary: string
  hcpFeedback: string
  notes?: string | null
  detailingRecords: DetailingRecordRequest[]
  materialDistributions: MaterialDistributionRequest[]
}

export interface VisitPlanListParams {
  status?: VisitStatus[]
  mrId?: UUID
  hcpId?: UUID
  hospitalId?: UUID
  departmentId?: UUID
  productId?: UUID
  plannedFrom?: ISODateTime
  plannedTo?: ISODateTime
  sort?: 'plannedAt' | 'createdAt'
  order?: 'asc' | 'desc'
  page?: number
  pageSize?: number
}

export interface VisitListParams extends Omit<VisitPlanListParams, 'sort'> {
  isAbnormal?: boolean
  checkInFrom?: ISODateTime
  checkInTo?: ISODateTime
  sort?: 'plannedAt' | 'checkInAt' | 'createdAt'
}

export interface DashboardProductView {
  id: UUID
  code: string
  name: string
}

export interface MonthlyProductVisitItem {
  product: DashboardProductView
  totalCount: number
  normalCount: number
  abnormalCount: number
  pendingCount: number
}

export interface MonthlyProductVisitsResponse {
  month: string
  businessTimezone: string
  rangeStartUtc: ISODateTime
  rangeEndUtc: ISODateTime
  items: MonthlyProductVisitItem[]
}

export interface MonthlyProductVisitsParams {
  month: string
  productId?: UUID
}
