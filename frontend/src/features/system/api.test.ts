import { afterEach, expect, it, vi } from 'vitest'
import { getReadiness } from './api'

afterEach(() => vi.unstubAllGlobals())

it('valida readiness real según contrato', async () => {
  const body = { status: 'ready', services: { mongodb: 'ok', redis: 'ok', neo4j: 'ok' } }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)))
  expect(await getReadiness()).toEqual(body)
})

it('preserva el detalle por servicio cuando readiness devuelve 503', async () => {
  const body = { status: 'degraded', services: { mongodb: 'ok', redis: 'unavailable', neo4j: 'ok' } }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body, { status: 503 })))
  expect(await getReadiness()).toEqual(body)
})

it('rechaza una respuesta exitosa con schema inválido', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ status: 'ok' })))
  await expect(getReadiness()).rejects.toThrow('El servidor devolvió un estado de conexión inesperado.')
})

it('no interpreta un 503 genérico como readiness válido', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'Storage offline' }, { status: 503 })))
  await expect(getReadiness()).rejects.toMatchObject({ status: 503, message: 'Storage offline' })
})
