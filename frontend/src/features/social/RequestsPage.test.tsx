import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { RequestsPage } from './RequestsPage'
import type { AuthRequest } from '../auth/api'
import { sessionWrapper, user } from '../../../tests/fixtures/session'

const requester = '22000000-0000-4000-8000-000000000002'
const id = '33000000-0000-4000-8000-000000000003'
const job = { operation_id: id, follower_id: requester, followed_id: user.id, actor_id: user.id,
  action: 'approve', status: 'running', desired: 'accepted', error: null }
beforeEach(() => sessionStorage.clear())
function mount(request: AuthRequest) {
  return render(<MemoryRouter><RequestsPage /></MemoryRouter>, { wrapper: sessionWrapper(request) })
}
it('muestra solicitudes vacías y permite volver al perfil propio', async () => {
  mount(vi.fn<AuthRequest>().mockResolvedValue([]))
  expect(await screen.findByText('No tenés solicitudes pendientes.')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Ver mi perfil' })).toHaveAttribute('href', `/perfiles/${user.id}`)
})
it('conserva una aprobación en curso aunque el grafo ya no devuelva la solicitud, incluida la recarga', async () => {
  sessionStorage.setItem(`niche.p2.attempts.${user.id}`, JSON.stringify([{ follower_id: requester, followed_id: user.id,
    action: 'approve', key: id, operation_id: id, status: 'running' }]))
  let finish: ((value: unknown) => void) | undefined
  const request = vi.fn<AuthRequest>(async (path) => {
    if (path.includes('/users/')) return { ...user, id: requester, full_name: 'Solicitante' }
    if (path.includes('/operations/')) return new Promise((resolve) => { finish = resolve })
    return []
  })
  mount(request)
  expect(await screen.findByRole('link', { name: 'Solicitante' })).toHaveAttribute('href', `/perfiles/${requester}`)
  await waitFor(() => expect(finish).toBeDefined())
  expect(screen.getByRole('button', { name: 'Aprobar solicitud' })).toBeDisabled()
  finish!({ ...job, status: 'completed' })
  expect(await screen.findByText('No tenés solicitudes pendientes.')).toBeVisible()
})
it('aprobar identifica al dueño desde la sesión y espera la confirmación', async () => {
  let approved = false
  const request = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (path.includes('/users/')) return { ...user, id: requester, full_name: 'Solicitante' }
    if (options.method === 'POST') { approved = true; return { ...job, status: 'completed' } }
    if (path.includes('/operations/')) return { ...job, status: 'completed' }
    return approved ? [] : [requester]
  })
  mount(request)
  await userEvent.click(await screen.findByRole('button', { name: 'Aprobar solicitud' }))
  expect(await screen.findByText('No tenés solicitudes pendientes.')).toBeVisible()
  const sent = request.mock.calls.find(([, options]) => options?.method === 'POST')
  expect(JSON.parse(String(sent?.[1]?.body))).toEqual({ user_id: requester, followed_user_id: user.id })
})
