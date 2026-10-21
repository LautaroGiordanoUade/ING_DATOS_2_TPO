import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { operationId, postId, sessionWrapper, user } from '../../../tests/fixtures/session'
import { ComposerPage } from './ComposerPage'
import { readDraft, saveDraft } from './drafts'
import { toPostPayload } from './contracts'

beforeEach(() => sessionStorage.clear())
function mount(request: AuthRequest) {
  return render(<MemoryRouter initialEntries={['/publicar']}><Routes><Route path="/publicar" element={<ComposerPage />} /><Route path="/operaciones/:operationId" element={<h1>Operación recibida</h1>} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request) })
}
it('valida texto e intereses antes de llamar al servidor', async () => {
  const request = vi.fn<AuthRequest>()
  mount(request)
  await userEvent.click(screen.getByRole('button', { name: 'Publicar' }))
  expect(await screen.findByText('Escribí una publicación.')).toBeVisible()
  expect(screen.getByText('Agregá al menos un interés.')).toBeVisible()
  expect(request).not.toHaveBeenCalled()
})
it('reintenta la misma clave y payload tras perder la respuesta, sin duplicar el envío', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce(user).mockRejectedValueOnce(new ApiError(0, 'Respuesta perdida', null)).mockResolvedValueOnce(user).mockResolvedValueOnce({ operation_id: operationId, post_id: postId, status: 'pending' })
  mount(request)
  await userEvent.type(screen.getByLabelText('Tu publicación'), 'Una idea')
  await userEvent.type(screen.getByLabelText('Intereses'), 'datos, python')
  await userEvent.click(screen.getByRole('button', { name: 'Publicar' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Respuesta perdida')
  expect(screen.getByLabelText('Tu publicación')).toHaveAttribute('readonly')
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar envío' }))
  await screen.findByRole('heading', { name: 'Operación recibida' })
  const submissions = request.mock.calls.filter(([path]) => path === '/api/v1/posts')
  expect(submissions).toHaveLength(2)
  expect(submissions[0]?.[1]).toEqual(submissions[1]?.[1])
  expect(new Headers(submissions[0]?.[1]?.headers).get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/)
  expect(readDraft(user.id).attempt).toBeNull()
})
it('restaura un intento anterior y recupera la operación usando su clave original', async () => {
  const values = { text: 'Borrador recuperado', interests: 'datos', media: '' }
  const attempt = { key: crypto.randomUUID(), payload: toPostPayload(values, user.id) }
  saveDraft(user.id, values, attempt)
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce(user).mockResolvedValueOnce({ operation_id: operationId, post_id: postId, status: 'pending' })
  mount(request)
  expect(screen.getByLabelText('Tu publicación')).toHaveValue(values.text)
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar envío' }))
  await screen.findByRole('heading', { name: 'Operación recibida' })
  const submission = request.mock.calls.find(([path]) => path === '/api/v1/posts')
  expect(new Headers(submission?.[1]?.headers).get('Idempotency-Key')).toBe(attempt.key)
})
it('permite corregir el formulario si el servidor rechaza su validación', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce(user).mockRejectedValueOnce(new ApiError(422, 'Validación del servidor', null))
  mount(request)
  await userEvent.type(screen.getByLabelText('Tu publicación'), 'Texto')
  await userEvent.type(screen.getByLabelText('Intereses'), 'datos')
  await userEvent.click(screen.getByRole('button', { name: 'Publicar' }))
  await screen.findByText('Validación del servidor')
  expect(screen.getByLabelText('Tu publicación')).not.toHaveAttribute('readonly')
})

it('pide una decisión explícita antes de abandonar un intento de resultado incierto', async () => {
  const values = { text: 'Borrador', interests: 'datos', media: '' }
  saveDraft(user.id, values, { key: crypto.randomUUID(), payload: toPostPayload(values, user.id) })
  mount(vi.fn<AuthRequest>())
  await userEvent.click(screen.getByRole('button', { name: 'Empezar otro envío' }))
  expect(screen.getByRole('group', { name: 'Confirmar nuevo envío' })).toHaveTextContent('El servidor podría haber recibido')
  expect(screen.getByLabelText('Tu publicación')).toHaveAttribute('readonly')
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar nuevo borrador' }))
  expect(screen.getByLabelText('Tu publicación')).not.toHaveAttribute('readonly')
})
