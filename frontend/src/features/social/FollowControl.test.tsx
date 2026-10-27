import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FollowControl } from './FollowControl'
import { onlineManager } from '@tanstack/react-query'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { sessionWrapper, user } from '../../../tests/fixtures/session'

const target = '22000000-0000-4000-8000-000000000002'
const id = '33000000-0000-4000-8000-000000000003'
const job = { operation_id: id, follower_id: user.id, followed_id: target, actor_id: user.id,
  action: 'follow', status: 'pending', desired: null, error: null }
beforeEach(() => sessionStorage.clear())
function mount(request: AuthRequest, accountType: 'private' | 'public' = 'public') {
  return render(<FollowControl followerId={user.id} followedId={target} accountType={accountType} />, { wrapper: sessionWrapper(request) })
}

it('deshabilita el cambio mientras corre el worker y confirma la relación después de completar', async () => {
  let accepted = false
  let finish: ((value: unknown) => void) | undefined
  const request = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (options.method === 'POST') return job
    if (path.includes('/operations/')) return new Promise((resolve) => { finish = resolve })
    return { status: accepted ? 'accepted' : 'none' }
  })
  mount(request)
  await userEvent.click(await screen.findByRole('button', { name: 'Seguir' }))
  await screen.findByText('Procesando cambio de seguimiento…')
  expect(screen.getByRole('button', { name: 'Seguir' })).toBeDisabled()
  expect(screen.queryByText('Siguiendo')).not.toBeInTheDocument()
  accepted = true
  await waitFor(() => expect(finish).toBeDefined())
  finish!({ ...job, status: 'completed', desired: 'accepted' })
  expect(await screen.findByText('Siguiendo')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Dejar de seguir' })).toBeEnabled()
})

it('recupera la operación al remontar sin volver a enviar el cambio', async () => {
  const initial = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (options.method === 'POST') return job
    if (path.includes('/operations/')) return new Promise(() => {})
    return { status: 'none' }
  })
  const view = mount(initial)
  await userEvent.click(await screen.findByRole('button', { name: 'Seguir' }))
  await waitFor(() => expect(initial.mock.calls.some(([path]) => path.includes('/operations/'))).toBe(true))
  view.unmount()
  const reloaded = vi.fn<AuthRequest>(async (path) => path.includes('/operations/') ? { ...job, status: 'completed', desired: 'accepted' } : { status: 'accepted' })
  mount(reloaded)
  expect(await screen.findByText('Siguiendo')).toBeVisible()
  expect(reloaded.mock.calls.every(([, options]) => !options?.method)).toBe(true)
})

it('tras perder la respuesta conserva la clave y el pedido a través de una recarga', async () => {
  let firstKey: HeadersInit | undefined
  const initial = vi.fn<AuthRequest>(async (_path, options = {}) => {
    if (options.method) { firstKey = options.headers; throw new ApiError(0, 'Sin conexión', null) }
    return { status: 'none' }
  })
  const view = mount(initial)
  await userEvent.click(await screen.findByRole('button', { name: 'Seguir' }))
  await screen.findByText('Sin conexión')
  view.unmount()
  const reloaded = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (options.method === 'POST') return { ...job, status: 'completed', desired: 'pending' }
    if (path.includes('/operations/')) return { ...job, status: 'completed', desired: 'pending' }
    return { status: 'pending' }
  })
  mount(reloaded, 'private')
  await userEvent.click(await screen.findByRole('button', { name: 'Confirmar envío pendiente' }))
  await waitFor(() => expect(reloaded.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(true))
  expect(reloaded.mock.calls.find(([, options]) => options?.method === 'POST')?.[1]?.headers).toEqual(firstKey)
  expect(await screen.findByText('Solicitud enviada')).toBeVisible()
})

it('permite cancelar una solicitud privada y usa una nueva clave para el cambio siguiente', async () => {
  let state = 'pending'
  const request = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (options.method === 'DELETE') { state = 'none'; return { ...job, action: 'unfollow', status: 'completed', desired: 'none' } }
    if (path.includes('/operations/')) return { ...job, action: 'unfollow', status: 'completed', desired: 'none' }
    return { status: state }
  })
  mount(request, 'private')
  await userEvent.click(await screen.findByRole('button', { name: 'Cancelar solicitud' }))
  expect(await screen.findByRole('button', { name: 'Seguir' })).toBeEnabled()
  expect(request.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(true)
})

it('un resultado compensado muestra el estado anterior sin confirmar seguimiento', async () => {
  const request = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (options.method === 'POST' || path.includes('/operations/')) return { ...job, status: 'compensated', error: 'Falla de prueba' }
    return { status: 'none' }
  })
  mount(request)
  await userEvent.click(await screen.findByRole('button', { name: 'Seguir' }))
  expect(await screen.findByText(/El cambio se revirtió/)).toBeVisible()
  expect(screen.queryByText('Siguiendo')).not.toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Seguir' })).toBeEnabled())
})

it('una consulta fallida no permite actuar con un estado de seguimiento desconocido', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(new ApiError(503, 'Redis caído', null)).mockResolvedValue({ status: 'accepted' })
  mount(request)
  await screen.findByText('No pudimos consultar el seguimiento.')
  expect(screen.getByRole('button', { name: 'Seguir' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar seguimiento' }))
  expect(await screen.findByRole('button', { name: 'Dejar de seguir' })).toBeEnabled()
})

it('retoma una recuperación fallida con el endpoint de retry sin crear otro seguimiento', async () => {
  sessionStorage.setItem(`niche.p2.attempts.${user.id}`, JSON.stringify([{ follower_id: user.id, followed_id: target,
    action: 'follow', key: id, operation_id: id, status: 'failed' }]))
  let failed = true
  const request = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (options.method === 'POST') { failed = false; return { ...job, status: 'compensated' } }
    if (path.includes('/operations/')) return { ...job, status: failed ? 'failed' : 'compensated' }
    return { status: 'none' }
  })
  mount(request)
  await userEvent.click(await screen.findByRole('button', { name: 'Reintentar recuperación' }))
  expect(await screen.findByText(/El cambio se revirtió/)).toBeVisible()
  expect(request.mock.calls.find(([, options]) => options?.method === 'POST')?.[0]).toBe(`/api/v1/social/operations/${id}/retry`)
})

it('retira el error de respuesta perdida cuando el servidor confirma la misma relación', async () => {
  let queued = false
  let accepted = false
  const request = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (options.method === 'POST') { queued = true; throw new ApiError(0, 'Respuesta perdida', null) }
    if (path.includes('/operations/')) { accepted = true; return { ...job, status: 'completed', desired: 'accepted' } }
    return accepted ? { status: 'accepted' } : queued ? { status: 'processing', operation_id: id, operation_status: 'running' } : { status: 'none' }
  })
  mount(request)
  await userEvent.click(await screen.findByRole('button', { name: 'Seguir' }))
  await waitFor(() => expect(request.mock.calls.some(([path]) => path.includes('/operations/'))).toBe(true))
  await waitFor(() => expect(screen.queryByText('Respuesta perdida')).not.toBeInTheDocument())
  expect(await screen.findByText('Siguiendo')).toBeVisible()
})

it('un navegador sin conexión conserva el intento y ofrece confirmarlo en lugar de quedar en espera', async () => {
  onlineManager.setOnline(false)
  try {
    const request = vi.fn<AuthRequest>(async (_path, options = {}) => {
      if (options.method === 'POST') throw new ApiError(0, 'Sin conexión', null)
      return { status: 'none' }
    })
    mount(request)
    await userEvent.click(await screen.findByRole('button', { name: 'Seguir' }))
    expect(await screen.findByText('Sin conexión')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Confirmar envío pendiente' })).toBeEnabled()
  } finally { onlineManager.setOnline(true) }
})
