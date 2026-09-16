import { systemClient } from './client'
import type { HealthResponse } from './types'

export async function getHealth(): Promise<HealthResponse> {
  const response = await systemClient.get<HealthResponse>('/health')
  return response.data
}

export type { HealthResponse } from './types'
