import { apiClient } from './client'
import type {
  MonthlyProductVisitsParams,
  MonthlyProductVisitsResponse,
} from './types'

export async function getMonthlyProductVisits(
  params: MonthlyProductVisitsParams,
): Promise<MonthlyProductVisitsResponse> {
  const response = await apiClient.get<MonthlyProductVisitsResponse>(
    '/dashboard/monthly-visits-by-product',
    { params },
  )
  return response.data
}
