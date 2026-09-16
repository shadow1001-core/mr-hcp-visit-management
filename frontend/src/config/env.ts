function normalizeBaseUrl(value: string | undefined): string {
  const normalized = value?.trim() || '/api'
  return normalized === '/' ? '/' : normalized.replace(/\/+$/, '')
}

function serviceBaseUrl(apiBaseUrl: string): string {
  if (apiBaseUrl === '/api') {
    return '/'
  }
  if (apiBaseUrl.endsWith('/api')) {
    return apiBaseUrl.slice(0, -4) || '/'
  }
  return apiBaseUrl
}

const apiBaseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL)

export const appConfig = Object.freeze({
  apiBaseUrl,
  serviceBaseUrl: serviceBaseUrl(apiBaseUrl),
  businessTimezone:
    import.meta.env.VITE_BUSINESS_TIMEZONE?.trim() || 'Asia/Shanghai',
})
