import { apiClient } from './client'
import type {
  CreateVisitPlanRequest,
  PaginatedVisitPlans,
  VisitPlanListParams,
  VisitPlanResponse,
} from './types'

export async function listVisitPlans(
  params: VisitPlanListParams,
): Promise<PaginatedVisitPlans> {
  const response = await apiClient.get<PaginatedVisitPlans>('/visit-plans', {
    params,
  })
  return response.data
}

export async function createVisitPlan(
  request: CreateVisitPlanRequest,
): Promise<VisitPlanResponse> {
  const response = await apiClient.post<VisitPlanResponse>(
    '/visit-plans',
    request,
  )
  return response.data
}
