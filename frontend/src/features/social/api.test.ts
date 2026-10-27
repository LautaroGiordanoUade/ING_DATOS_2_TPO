import { expect, it, vi } from 'vitest'
import type { AuthRequest } from '../auth/api'
import { countsSchema, getOperation, getRelation, relationSchema, sendFollow } from './api'

const follower = '11000000-0000-4000-8000-000000000001'
const followed = '22000000-0000-4000-8000-000000000002'
const id = '33000000-0000-4000-8000-000000000003'
const job = { operation_id: id, follower_id: follower, followed_id: followed, actor_id: follower,
  action: 'follow', status: 'pending', desired: null, error: null }

it('envía identidad, destino y clave para seguir; baja usa DELETE y aprobación usa su ruta', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue(job)
  await sendFollow(request, 'follow', follower, followed, id)
  expect(request.mock.calls[0]).toEqual(['/api/v1/social/follows', {
    method: 'POST', headers: { 'Idempotency-Key': id }, body: JSON.stringify({ user_id: follower, followed_user_id: followed }),
  }])
  request.mockResolvedValue({ ...job, action: 'unfollow' })
  await sendFollow(request, 'unfollow', follower, followed, id)
  expect(request.mock.calls[1]?.[1]?.method).toBe('DELETE')
  request.mockResolvedValue({ ...job, action: 'approve' })
  await sendFollow(request, 'approve', follower, followed, id)
  expect(request.mock.calls[2]?.[0]).toBe('/api/v1/social/follows/approve')
})
it('rechaza una respuesta de otra pareja u otra operación', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...job, followed_id: follower })
  await expect(sendFollow(request, 'follow', follower, followed, id)).rejects.toThrow('no corresponde')
  await expect(getOperation(request, id, follower, followed)).rejects.toThrow('no corresponde')
})
it('valida estados y contadores sin confundir solicitud pendiente con operación pendiente', async () => {
  expect(relationSchema.parse({ status: 'pending' })).toEqual({ status: 'pending' })
  expect(relationSchema.safeParse({ status: 'processing' }).success).toBe(false)
  expect(countsSchema.safeParse({ followers: -1, following: 0 }).success).toBe(false)
  const signal = new AbortController().signal
  const request = vi.fn<AuthRequest>().mockResolvedValue({ status: 'accepted' })
  await getRelation(request, followed, signal)
  expect(request.mock.calls[0]?.[1]?.signal).toBe(signal)
})
