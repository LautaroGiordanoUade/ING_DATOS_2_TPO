import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { sessionWrapper, user, operationId } from '../../../tests/fixtures/session'
import { accountJob, target, trace } from '../../../tests/fixtures/accounts'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { AccountsPage } from './AccountsPage'
import { AccountTracePage } from './AccountTracePage'
import { AccountDecisionForm } from './AccountDecisionForm'
import { AccountOperationPage } from './AccountOperationPage'
import { readAttempt, saveAttempt } from './attempts'

const moderator = { ...user, role: 'moderator' as const }
function mount(element: ReactNode, request: AuthRequest, path = '/', route = '/', actor = moderator) {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route path={route} element={element} />{route !== '/cuentas/:userId' && <Route path="/cuentas/:userId" element={<h1>Cuenta elegida</h1>} />}{route !== '/cuentas/operaciones/:operationId' && <Route path="/cuentas/operaciones/:operationId" element={<h1>Operación aceptada</h1>} />}</Routes></MemoryRouter>, { wrapper: sessionWrapper(request, { user: actor }) })
}
beforeEach(() => sessionStorage.clear())
it('valida identificador antes de navegar desde búsqueda', async () => {
  mount(<AccountsPage />, vi.fn())
  await userEvent.type(screen.getByLabelText('Identificador de usuario'), 'no-es-uuid')
  await userEvent.click(screen.getByRole('button', { name: 'Consultar cuenta' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('identificador')
  await userEvent.clear(screen.getByLabelText('Identificador de usuario'))
  await userEvent.type(screen.getByLabelText('Identificador de usuario'), target.id)
  await userEvent.click(screen.getByRole('button', { name: 'Consultar cuenta' }))
  expect(await screen.findByText('Cuenta elegida')).toBeVisible()
})
it('obtiene perfil, relaciones, publicaciones y conversaciones con un solo request', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue(trace)
  mount(<AccountTracePage />, request, `/cuentas/${target.id}`, '/cuentas/:userId')
  expect(screen.getByRole('status')).toHaveTextContent('Consultando trazabilidad completa')
  await screen.findByText('Cuenta consultada')
  expect(screen.getByText('Publicación de la cuenta')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Conversaciones activas' })).toBeVisible()
  expect(screen.getByText(trace.active_conversations[0]!.id)).toBeVisible()
  expect(request).toHaveBeenCalledTimes(1)
  expect(request.mock.calls[0]?.[0]).toBe(`/api/v1/accounts/${target.id}/trace`)
})
it('cancela la consulta al salir', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(() => new Promise(() => {}))
  const view = mount(<AccountTracePage />, request, `/cuentas/${target.id}`, '/cuentas/:userId')
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1))
  const signal = request.mock.calls[0]?.[1]?.signal
  view.unmount()
  expect(signal?.aborted).toBe(true)
})
it('no consulta UUID malformados', () => {
  const request = vi.fn<AuthRequest>()
  mount(<AccountTracePage />, request, '/cuentas/incorrecto', '/cuentas/:userId')
  expect(screen.getByRole('alert')).toHaveTextContent('no es válido')
  expect(request).not.toHaveBeenCalled()
})
it('rechaza una traza privada de otra cuenta sin consultar la API', () => {
  const request = vi.fn<AuthRequest>()
  render(<MemoryRouter initialEntries={[`/cuentas/${target.id}`]}><Routes><Route path="/cuentas/:userId" element={<AccountTracePage />} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request) })
  expect(screen.getByRole('heading', { name: 'Trazabilidad privada' })).toBeVisible()
  expect(request).not.toHaveBeenCalled()
})
it('renueva presencia solo para el titular con PUT y vuelve a consultar la traza', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce({ ...trace, presence: false }).mockResolvedValueOnce(undefined).mockResolvedValue(trace)
  render(<MemoryRouter initialEntries={[`/cuentas/${target.id}`]}><Routes><Route path="/cuentas/:userId" element={<AccountTracePage />} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request, { user: target }) })
  await screen.findByText('Sin presencia activa')
  await userEvent.click(screen.getByRole('button', { name: 'Renovar mi presencia' }))
  expect(await screen.findByText('En línea')).toBeVisible()
  expect(request.mock.calls[1]).toEqual(['/api/v1/accounts/me/presence', { method: 'PUT' }])
  expect(screen.queryByRole('heading', { name: 'Suspender cuenta' })).not.toBeInTheDocument()
})
it('no permite autosuspensión al moderador', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...trace, user_id: user.id, profile: moderator })
  mount(<AccountTracePage />, request, `/cuentas/${user.id}`, '/cuentas/:userId')
  expect(await screen.findByText('No podés suspender ni reactivar tu propia cuenta.')).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Suspender cuenta' })).not.toBeInTheDocument()
})
it('muestra estados vacíos sin fingir datos', async () => {
  mount(<AccountTracePage />, vi.fn<AuthRequest>().mockResolvedValue({ ...trace, recent_posts: [], post_states: [], active_conversations: [], relationships: { followers: [], following: [], blocked: [], edges: [] } }), `/cuentas/${target.id}`, '/cuentas/:userId')
  expect(await screen.findByText('No hay relaciones registradas.')).toBeVisible()
  expect(screen.getByText('No hay conversaciones activas registradas.')).toBeVisible()
  expect(screen.getByText('No hay publicaciones visibles para esta cuenta.')).toBeVisible()
})
it.each([403, 404, 503])('explica el error %s sin mostrar un perfil anterior como vigente', async (status) => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce(trace).mockRejectedValue(new ApiError(status, 'Error', null))
  mount(<AccountTracePage />, request, `/cuentas/${target.id}`, '/cuentas/:userId')
  await screen.findByText('Cuenta consultada')
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar cuenta' }))
  await screen.findByRole('alert')
  expect(screen.queryByText('Cuenta consultada')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Revisar cambio de cuenta' })).not.toBeInTheDocument()
})
it('exige motivo y confirmación antes de encolar, con clave estable', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(new ApiError(0, 'Sin conexión', null)).mockResolvedValue(accountJob)
  mount(<AccountDecisionForm userId={target.id} status="active" />, request)
  await userEvent.click(screen.getByRole('button', { name: 'Revisar cambio de cuenta' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Escribí un motivo')
  await userEvent.type(screen.getByLabelText('Motivo del cambio de cuenta'), 'Revisión de cuenta')
  await userEvent.click(screen.getByRole('button', { name: 'Revisar cambio de cuenta' }))
  expect(request).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar cambio de cuenta' }))
  await screen.findByRole('alert')
  expect(readAttempt(user.id, target.id)?.reason).toBe('Revisión de cuenta')
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar solicitud' }))
  expect(await screen.findByText('Operación aceptada')).toBeVisible()
  expect(request.mock.calls[0]).toEqual(request.mock.calls[1])
  expect(readAttempt(user.id, target.id)).toBeNull()
})
it('recupera el envío conservado después de salir y volver', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValue(new ApiError(0, 'Respuesta perdida', null))
  const view = mount(<AccountDecisionForm userId={target.id} status="active" />, request)
  await userEvent.type(screen.getByLabelText('Motivo del cambio de cuenta'), 'Motivo durable')
  await userEvent.click(screen.getByRole('button', { name: 'Revisar cambio de cuenta' }))
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar cambio de cuenta' }))
  await screen.findByRole('alert')
  const saved = readAttempt(user.id, target.id)
  view.unmount()
  mount(<AccountDecisionForm userId={target.id} status="active" />, request)
  expect(screen.getByText('Motivo durable')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar solicitud' }))
  await screen.findByRole('alert')
  expect(readAttempt(user.id, target.id)).toEqual(saved)
})
it('reactivar usa acción y endpoint propios sin revivir presencia', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...accountJob, action: 'reactivate' })
  mount(<AccountDecisionForm userId={target.id} status="suspended" />, request)
  await userEvent.type(screen.getByLabelText('Motivo del cambio de cuenta'), 'Revisión favorable')
  await userEvent.click(screen.getByRole('button', { name: 'Revisar cambio de cuenta' }))
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar cambio de cuenta' }))
  await screen.findByText('Operación aceptada')
  expect(request.mock.calls[0]?.[0]).toBe(`/api/v1/accounts/${target.id}/reactivate`)
  expect(request).toHaveBeenCalledTimes(1)
})
it('recupera el comando original aunque el servidor ya haya cambiado el estado', async () => {
  const key = crypto.randomUUID()
  saveAttempt(user.id, { key, userId: target.id, action: 'suspend', reason: 'Respuesta perdida' })
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...accountJob, status: 'completed' })
  mount(<AccountDecisionForm userId={target.id} status="suspended" />, request)
  expect(screen.queryByRole('heading', { name: 'Reactivar cuenta' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar solicitud' }))
  await screen.findByText('Operación aceptada')
  expect(request.mock.calls[0]?.[0]).toBe(`/api/v1/accounts/${target.id}/suspend`)
  expect(request.mock.calls[0]?.[1]?.headers).toEqual({ 'Idempotency-Key': key })
})
it('una respuesta pending no confirma suspensión', async () => {
  mount(<AccountOperationPage />, vi.fn<AuthRequest>().mockResolvedValue(accountJob), `/cuentas/operaciones/${operationId}`, '/cuentas/operaciones/:operationId')
  expect(await screen.findByText('En cola')).toBeVisible()
  expect(screen.queryByText('Cambio de cuenta completado')).not.toBeInTheDocument()
})
it.each(['completed', 'compensated', 'failed'])('detiene polling en %s sin falso éxito', async (status) => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...accountJob, status })
  mount(<AccountOperationPage />, request, `/cuentas/operaciones/${operationId}`, '/cuentas/operaciones/:operationId')
  await screen.findByRole('link', { name: 'Consultar cuenta afectada' })
  await new Promise((resolve) => setTimeout(resolve, 1100))
  expect(request).toHaveBeenCalledTimes(1)
  if (status !== 'completed') expect(screen.queryByText('Cambio de cuenta completado')).not.toBeInTheDocument()
})
