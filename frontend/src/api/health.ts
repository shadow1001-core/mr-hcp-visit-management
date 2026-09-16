import { apiClient } from './client'

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
  environment: string
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>('/health')
  return response.data
}
