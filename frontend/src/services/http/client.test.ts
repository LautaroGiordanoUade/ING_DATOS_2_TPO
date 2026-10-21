import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createHttpClient } from './client'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('cliente HTTP', () => {
  it('compone la URL y conserva bearer y encabezados del llamador', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ status: 'ok' }))
    vi.stubGlobal('fetch', fetcher)
    const request = createHttpClient('/backend/')
    expect(await request('/health', { headers: { Authorization: 'Bearer test' } })).toEqual({ status: 'ok' })
    const call = fetcher.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/backend/health')
    const headers = new Headers(call[1].headers)
    expect(headers.get('Authorization')).toBe('Bearer test')
    expect(headers.get('Accept')).toBe('application/json')
    expect(headers.has('Content-Type')).toBe(false)
  })

  it('envía JSON sin sobrescribir el tipo de contenido explícito', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    await createHttpClient('/backend')('/resource', { method: 'POST', body: '{}', headers: { 'Content-Type': 'application/custom+json' } })
    const call = fetcher.mock.calls[0] as [string, RequestInit]
    expect(new Headers(call[1].headers).get('Content-Type')).toBe('application/custom+json')
  })

  it('maneja una respuesta 204 sin intentar leer JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    expect(await createHttpClient('/backend')('/resource')).toBeUndefined()
  })

  it.each([401, 403, 404, 409, 410, 501, 503])('conserva código %i y detalle del servidor', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'Error del servidor' }, { status })))
    await expect(createHttpClient('/backend')('/resource')).rejects.toMatchObject({ status, message: 'Error del servidor' })
  })

  it('traduce la lista de validaciones FastAPI a un mensaje legible', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: [{ loc: ['body'], msg: 'invalid' }] }, { status: 422 })))
    await expect(createHttpClient('/backend')('/resource')).rejects.toThrow('Revisá los datos enviados.')
  })

  it('maneja errores HTML del proxy sin fallo de parseo', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Bad gateway', { status: 502 })))
    await expect(createHttpClient('/backend')('/resource')).rejects.toMatchObject({ status: 502 })
  })

  it('maneja una falla de red', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(createHttpClient('/backend')('/resource')).rejects.toBeInstanceOf(ApiError)
    await expect(createHttpClient('/backend')('/resource')).rejects.toMatchObject({ status: 0 })
  })

  it('cancela una conexión que excede el timeout', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    const assertion = expect(createHttpClient('/backend', 25)('/resource')).rejects.toMatchObject({ status: 0, message: 'La conexión tardó demasiado. Volvé a intentar.' })
    await vi.advanceTimersByTimeAsync(25)
    await assertion
  })

  it('propaga la cancelación del llamador sin convertirla en error de red', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    const assertion = expect(createHttpClient('/backend')('/resource', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort()
    await assertion
  })
})
