import { expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { sessionWrapper, user } from '../../../tests/fixtures/session'
import { MessagesPage } from './MessagesPage'

const group = { id: '66000000-0000-4000-8000-000000000001', name: 'Grupo de datos',
  participant_ids: [user.id], participants: [], unread: 0 }
const message = { id: '66000000-0000-4000-8000-000000000002', conversation_id: group.id,
  sender_id: user.id, text: 'Hola', sequence: 1, created_at: '2026-10-27T12:00:00Z',
  delivery_status: 'completed', author_name: 'Ada', error: null }

function mount(request: AuthRequest, path = '/mensajes') {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/mensajes/:conversationId?" element={<MessagesPage />} />
  </Routes></MemoryRouter>, { wrapper: sessionWrapper(request) })
}

it('conserva el texto y la misma clave al reintentar un envío de resultado incierto', async () => {
  let fail = true
  const attempts: RequestInit[] = []
  const request = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (path.endsWith('/presence')) return undefined
    if (path.endsWith('/messages') && options.method === 'POST') {
      attempts.push(options)
      if (fail) { fail = false; throw new ApiError(0, 'Sin conexión', null) }
      return message
    }
    if (path.endsWith('/messages')) return { items: [], next_before: null }
    if (path.includes('?limit=')) return [group]
    return group
  })
  mount(request, `/mensajes/${group.id}`)
  await screen.findByRole('textbox', { name: 'Mensaje' })
  await userEvent.type(screen.getByLabelText('Mensaje', { exact: true }), 'Hola')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Mensaje', { exact: true })).toHaveValue('Hola')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
  await waitFor(() => expect(screen.getByLabelText('Mensaje', { exact: true })).toHaveValue(''))
  expect(attempts).toHaveLength(2)
  expect(attempts[0]?.headers).toEqual(attempts[1]?.headers)
})

it('permite buscar participantes y crear un grupo sin copiar UUID', async () => {
  const participant = { id: '66000000-0000-4000-8000-000000000003', username: 'ada', full_name: 'Ada' }
  const request = vi.fn<AuthRequest>(async (path, options = {}) => {
    if (path.endsWith('/presence')) return undefined
    if (path.includes('/participants?')) return [participant]
    if (options.method === 'POST') return group
    if (path.endsWith('/messages')) return { items: [], next_before: null }
    if (path.includes('?limit=')) return []
    return group
  })
  mount(request)
  await userEvent.click(screen.getByRole('button', { name: 'Nuevo grupo' }))
  await userEvent.type(screen.getByLabelText('Nombre del grupo'), 'Grupo de datos')
  await userEvent.type(screen.getByLabelText('Buscar participantes por usuario'), 'ad')
  await userEvent.click(await screen.findByRole('button', { name: 'Agregar @ada · Ada' }))
  await userEvent.click(screen.getByRole('button', { name: 'Crear grupo' }))
  await waitFor(() => expect(request.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(true))
  const call = request.mock.calls.find(([, options]) => options?.method === 'POST')
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ name: 'Grupo de datos', participant_ids: [participant.id] })
})
