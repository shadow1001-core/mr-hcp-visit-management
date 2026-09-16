import { apiClient } from './client'
import type {
  CoordinatesRequest,
  PaginatedVisitWorkflows,
  UpsertVisitReportRequest,
  UUID,
  VisitListParams,
  VisitWorkflowDetail,
} from './types'

export async function listVisits(
  params: VisitListParams,
): Promise<PaginatedVisitWorkflows> {
  const response = await apiClient.get<PaginatedVisitWorkflows>('/visits', {
    params,
  })
  return response.data
}

export async function getVisit(workflowId: UUID): Promise<VisitWorkflowDetail> {
  const response = await apiClient.get<VisitWorkflowDetail>(
    `/visits/${workflowId}`,
  )
  return response.data
}

export async function checkInVisit(
  workflowId: UUID,
  request: CoordinatesRequest,
): Promise<VisitWorkflowDetail> {
  const response = await apiClient.post<VisitWorkflowDetail>(
    `/visits/${workflowId}/check-in`,
    request,
  )
  return response.data
}

export async function checkOutVisit(
  workflowId: UUID,
  request: CoordinatesRequest,
): Promise<VisitWorkflowDetail> {
  const response = await apiClient.post<VisitWorkflowDetail>(
    `/visits/${workflowId}/check-out`,
    request,
  )
  return response.data
}

export async function upsertVisitReport(
  workflowId: UUID,
  request: UpsertVisitReportRequest,
): Promise<VisitWorkflowDetail> {
  const response = await apiClient.put<VisitWorkflowDetail>(
    `/visits/${workflowId}/report`,
    request,
  )
  return response.data
}
