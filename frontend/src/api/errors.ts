import axios from 'axios'

import type { ErrorDetail, ErrorEnvelope } from './types'

export type ApiErrorKind = 'business' | 'http' | 'network' | 'timeout'

interface ApiErrorOptions {
  kind: ApiErrorKind
  message: string
  code?: string
  status?: number
  details?: ErrorDetail[]
  requestId?: string
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly code?: string
  readonly status?: number
  readonly details: ErrorDetail[]
  readonly requestId?: string

  constructor(options: ApiErrorOptions) {
    super(options.message)
    this.name = 'ApiError'
    this.kind = options.kind
    this.code = options.code
    this.status = options.status
    this.details = options.details ?? []
    this.requestId = options.requestId
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseDetail(value: unknown): ErrorDetail | null {
  if (!isRecord(value)) {
    return null
  }
  if (typeof value.field !== 'string' || typeof value.reason !== 'string') {
    return null
  }
  return {
    field: value.field,
    reason: value.reason,
    ...(typeof value.value === 'string' ? { value: value.value } : {}),
  }
}

function parseErrorEnvelope(value: unknown): ErrorEnvelope | null {
  if (!isRecord(value) || !isRecord(value.error)) {
    return null
  }
  const error = value.error
  if (
    typeof error.code !== 'string' ||
    typeof error.message !== 'string' ||
    !Array.isArray(error.details)
  ) {
    return null
  }
  const details = error.details
    .map(parseDetail)
    .filter((detail): detail is ErrorDetail => detail !== null)
  return {
    error: {
      code: error.code,
      message: error.message,
      details,
    },
    ...(typeof value.requestId === 'string'
      ? { requestId: value.requestId }
      : {}),
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error
  }
  if (!axios.isAxiosError(error)) {
    return new ApiError({
      kind: 'http',
      message: '发生未知错误，请稍后重试。',
    })
  }
  if (error.code === 'ECONNABORTED') {
    return new ApiError({
      kind: 'timeout',
      message: '请求超时，请稍后重试。',
    })
  }
  if (!error.response) {
    return new ApiError({
      kind: 'network',
      message: '无法连接服务器，请检查网络或确认后端服务已启动。',
    })
  }

  const envelope = parseErrorEnvelope(error.response.data)
  if (envelope) {
    return new ApiError({
      kind: 'business',
      status: error.response.status,
      code: envelope.error.code,
      message: envelope.error.message,
      details: envelope.error.details,
      requestId: envelope.requestId,
    })
  }

  return new ApiError({
    kind: 'http',
    status: error.response.status,
    message:
      error.response.status >= 500
        ? '服务器暂时无法处理请求，请稍后重试。'
        : `请求失败（HTTP ${error.response.status}）。`,
  })
}

export function getErrorMessage(error: unknown): string {
  return toApiError(error).message
}
