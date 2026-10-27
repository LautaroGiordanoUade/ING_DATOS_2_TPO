import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DecisionPanel } from './DecisionPanel'
import type { AuthRequest } from '../auth/api'
import { sessionWrapper } from '../../../tests/fixtures/session'
import { report, content, job, moderator } from '../../../tests/fixtures/moderation'

beforeEach(() => sessionStorage.clear())
function mount(request: AuthRequest, context = content, item = report, onForbidden = vi.fn()) {
  return render(<DecisionPanel report={item} content={context} onForbidden={onForbidden} />, { wrapper: sessionWrapper(request, { user: moderator }) })
}
it('explica el alcance, exige motivo y no confirma el ocultamiento con una respuesta 202', async () => {
  let finish: ((data: unknown) => void) | undefined
  const request = vi.fn<AuthRequest>(async (_path, options = {}) => options.method === 'POST' ? job : new Promise((resolve) => { finish = resolve }))
  mount(request)
  await userEvent.click(screen.getByRole('button', { name: 'Ocultar publicación' }))
  expect(screen.getByText('Se ocultará esta publicación y se resolverán todos sus reportes pendientes.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Confirmar ocultamiento' })).toBeDisabled()
  await userEvent.type(screen.getByLabelText('Motivo de la decisión'), job.reason)
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar ocultamiento' }))
  await waitFor(() => expect(finish).toBeDefined())
  expect(screen.queryByText('La operación terminó y su resultado fue confirmado.')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Ocultar publicación' })).toBeDisabled()
  finish!({ ...job, status: 'completed' })
  expect(await screen.findByText('La operación terminó y su resultado fue confirmado.')).toBeVisible()
})
it('recarga un envío incierto con el motivo original sin generar otra decisión distinta', async () => {
  sessionStorage.setItem(`niche.p7.decisions.${moderator.id}`, JSON.stringify([{ post_id: report.post_id, report_id: report.id,
    action: 'hide', reason: job.reason, operation_id: null, status: null }]))
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...job, status: 'completed' })
  mount(request)
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar envío pendiente' }))
  await waitFor(() => expect(request.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(true))
  const sent = request.mock.calls.find(([, options]) => options?.method === 'POST')
  expect(JSON.parse(String(sent?.[1]?.body))).toEqual({ decision: 'hide', reason: job.reason })
})
it('descubre una decisión compensada desde el servidor sin depender de sessionStorage', async () => {
  let resumed = false
  const request = vi.fn<AuthRequest>(async (_path, options = {}) => {
    if (options.method === 'POST') { resumed = true; return { ...job, status: 'completed' } }
    return { ...job, status: resumed ? 'completed' : 'compensated', error: null }
  })
  mount(request, { ...content, report_operation_id: job.operation_id })
  await userEvent.click(await screen.findByRole('button', { name: 'Reintentar decisión' }))
  expect(request.mock.calls.find(([, options]) => options?.method === 'POST')?.[0]).toBe(`/api/v1/moderation/operations/${job.operation_id}/retry`)
  expect(await screen.findByText('La operación terminó y su resultado fue confirmado.')).toBeVisible()
})
it('permite revertir un reporte asociado sólo cuando el grupo conserva el ocultamiento', async () => {
  const associated = { ...report, resolution_status: 'approved' as const, resolution_report_id: report.id, id: '74000000-0000-4000-8000-000000000004' }
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...job, status: 'completed', action: 'revert', reason: 'Contenido permitido' })
  mount(request, { ...content, moderation_status: 'hidden', moderation_owner: report.id }, associated)
  await userEvent.click(screen.getByRole('button', { name: 'Revertir ocultamiento' }))
  await userEvent.type(screen.getByLabelText('Motivo de la decisión'), 'Contenido permitido')
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar reversión' }))
  await waitFor(() => expect(request.mock.calls.some(([path]) => path.endsWith(`/${associated.id}/revert`))).toBe(true))
})
it('rechaza un resultado de otra publicación y mantiene los controles bloqueados', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...job, post_id: report.id })
  mount(request, { ...content, active_operation_id: job.operation_id })
  expect(await screen.findByText('No pudimos consultar el resultado.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Ocultar publicación' })).toBeDisabled()
})
