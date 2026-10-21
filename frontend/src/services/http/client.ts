export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly payload: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

function errorDetail(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    if (typeof payload.detail === 'string') return payload.detail
    if (Array.isArray(payload.detail)) return 'Revisá los datos enviados.'
  }
  return `No se pudo completar la solicitud (${status}).`
}

export function createHttpClient(baseUrl: string, timeoutMs = 10_000) {
  return async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    const headers = new Headers(options.headers)
    headers.set('Accept', 'application/json')
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    try {
      const response = await fetch(`${baseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`, {
        ...options,
        headers,
        signal: options.signal ? AbortSignal.any([options.signal, controller.signal]) : controller.signal,
      })
      const body: unknown = response.status === 204 ? undefined : await response.json().catch(() => undefined)
      if (!response.ok) throw new ApiError(response.status, errorDetail(body, response.status), body)
      return body as T
    } catch (error) {
      if (options.signal?.aborted) throw error
      if (error instanceof ApiError) throw error
      throw new ApiError(0, controller.signal.aborted
        ? 'La conexión tardó demasiado. Volvé a intentar.'
        : 'No pudimos conectar con el servidor. Comprobá que esté iniciado.', undefined)
    } finally {
      clearTimeout(timer)
    }
  }
}

export const http = createHttpClient(import.meta.env.VITE_API_BASE_URL || '/backend')
