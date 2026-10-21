import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { OperationPage } from './OperationPage'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { operationId, postId, sessionWrapper, user } from '../../../tests/fixtures/session'

const operation = { operation_id: operationId, post_id: postId, operation_type: 'problem_01_publish_content', status: 'pending', current_step: null, completed_steps: [], error: null, created_at: '2026-10-21', updated_at: '2026-10-21' }
function mount(request: AuthRequest, id = operationId) {
  return render(<MemoryRouter initialEntries={[`/operaciones/${id}`]}><Routes><Route path="/operaciones/:operationId" element={<OperationPage />} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request) })
}
beforeEach(() => sessionStorage.clear())
afterEach(() => vi.useRealTimers())
it('un 202 pendiente no se presenta como publicación exitosa', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue(operation)
  mount(request)
  expect(await screen.findByText('En cola')).toBeVisible()
  expect(screen.queryByText('Tu idea ya está publicada.')).not.toBeInTheDocument()
})
it('detiene polling en compensación final y muestra el resultado sin falso éxito', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...operation, status: 'compensated', error: 'Falla controlada' })
  mount(request)
  await screen.findByText('Publicación cancelada')
  expect(screen.getByRole('alert')).toHaveTextContent('Falla controlada')
  await new Promise((resolve) => setTimeout(resolve, 1100))
  expect(request).toHaveBeenCalledTimes(1)
})
it('consulta el post_id recibido del servidor, sin tomarlo de una URL modificada', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce({ ...operation, status: 'completed' }).mockResolvedValueOnce({ id: postId, user_id: user.id, text: 'Real', media: [], interests: ['datos'], published_at: '2026-10-21', reaction_count: 0, comment_count: 0 })
  mount(request)
  await screen.findByText('Real')
  expect(request.mock.calls.some(([path]) => path === `/api/v1/posts/${postId}`)).toBe(true)
  expect(screen.getByText('Tu idea ya está publicada.')).toBeVisible()
})
it('muestra el error y reanuda la consulta al reintentar', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(new ApiError(503, 'No disponible', null)).mockResolvedValueOnce({ ...operation, status: 'compensated' })
  mount(request)
  await screen.findByText('No disponible')
  await userEvent.click(screen.getByRole('button', { name: 'Volver a consultar' }))
  await screen.findByText('Publicación cancelada')
})
it('rechaza identificadores inválidos sin requests', async () => {
  const request = vi.fn<AuthRequest>()
  mount(request, 'invalid')
  await screen.findByRole('alert')
  expect(request).not.toHaveBeenCalled()
})
it('rechaza operaciones de otro problema en esta pantalla', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ ...operation, operation_type: 'problem_05' })
  mount(request)
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Esta operación no corresponde'))
})

it('cancela la consulta en curso al salir de la pantalla', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(() => new Promise(() => {}))
  const view = mount(request)
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1))
  const signal = request.mock.calls[0]?.[1]?.signal
  expect(signal?.aborted).toBe(false)
  view.unmount()
  expect(signal?.aborted).toBe(true)
})
