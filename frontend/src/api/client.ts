import axios, { type AxiosInstance } from 'axios'

import { appConfig } from '../config/env'
import { toApiError } from './errors'

function createClient(baseURL: string): AxiosInstance {
  const client = axios.create({
    baseURL,
    timeout: 10_000,
    headers: {
      Accept: 'application/json',
    },
    paramsSerializer: {
      indexes: null,
    },
  })
  client.interceptors.response.use(
    (response) => response,
    (error: unknown) => Promise.reject(toApiError(error)),
  )
  return client
}

export const apiClient = createClient(appConfig.apiBaseUrl)
export const systemClient = createClient(appConfig.serviceBaseUrl)
