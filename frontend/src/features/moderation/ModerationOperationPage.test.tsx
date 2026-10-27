import { expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { AuthRequest } from '../auth/api'
import { sessionWrapper, operationId } from '../../../tests/fixtures/session'
import { moderationJob, moderator } from '../../../tests/fixtures/moderation'
import { ModerationOperationPage } from './ModerationOperationPage'

function mount(request: AuthRequest) {
  return render(<MemoryRouter initialEntries={[`/moderacion/operaciones/${operationId}`]}><Routes><Route path="/moderacion/operaciones/:operationId" element={<ModerationOperationPage />} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request, { user: moderator }) })
}
it('no presenta una solicitud 202 como una decisión completada', async () => {
  mount(vi.fn<AuthRequest>().mockResolvedValue(moderationJob))
  expect(await screen.findByText('En cola')).toBeVisible()
  expect(screen.queryByText('Decisión completada')).not.toBeInTheDocument()
})
it('consulta hasta committing y espera confirmación real', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce({ ...moderationJob, status: 'committing' }).mockResolvedValue({ ...moderationJob, status: 'completed' })
  mount(request)
  await screen.findByText('Confirmando decisión')
  expect(await screen.findByText('Decisión completada', {}, { timeout: 2500 })).toBeVisible()
})
it.each(['compensated', 'failed', 'completed'])('detiene polling al llegar a %s', async (status) => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...moderationJob, status })
  mount(request)
  await screen.findByText('Ocultar publicación')
  await new Promise((resolve) => setTimeout(resolve, 1100))
  expect(request).toHaveBeenCalledTimes(1)
  if (status !== 'completed') expect(screen.queryByText('Decisión completada')).not.toBeInTheDocument()
})
it('cancela la consulta de operación al salir', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(() => new Promise(() => {}))
  const view = mount(request)
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1))
  const signal = request.mock.calls[0]?.[1]?.signal
  view.unmount()
  expect(signal?.aborted).toBe(true)
})
