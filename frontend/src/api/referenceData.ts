import { apiClient } from './client'
import type { VisitPlanningReferenceDataResponse } from './types'

export async function getVisitPlanningReferenceData(): Promise<VisitPlanningReferenceDataResponse> {
  const response = await apiClient.get<VisitPlanningReferenceDataResponse>(
    '/reference-data/visit-planning',
  )
  return response.data
}
