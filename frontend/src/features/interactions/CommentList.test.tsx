import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CommentList } from './CommentList'
import { ApiError } from '../../services/http/client'
import type { AuthRequest } from '../auth/api'
import { postId, sessionWrapper, user } from '../../../tests/fixtures/session'

const item = { id: '99000000-0000-4000-8000-000000000001', post_id: postId, user_id: user.id,
  text: 'Comentario guardado', author_name: 'Ada', author_username: 'ada', created_at: '2026-10-27T12:00:00Z' }
function mount(request: AuthRequest) {
  return render(<CommentList postId={postId} enabled onOpen={() => {}} />, { wrapper: sessionWrapper(request) })
}

it('muestra autor, fecha, texto y pagina sin duplicar comentarios', async () => {
  const request = vi.fn<AuthRequest>()
    .mockResolvedValueOnce({ items: [item], next_cursor: 'opaque+/' })
    .mockResolvedValueOnce({ items: [item, { ...item, id: '99000000-0000-4000-8000-000000000002', text: 'Anterior' }], next_cursor: null })
  mount(request)
  expect(await screen.findByText('Comentario guardado')).toBeVisible()
  expect(screen.getByText('Ada')).toBeVisible()
  expect(screen.getByText('@ada')).toBeVisible()
  expect(document.querySelector('time')).toHaveAttribute('datetime', item.created_at)
  await userEvent.click(screen.getByRole('button', { name: 'Cargar comentarios anteriores' }))
  await screen.findByText('Anterior')
  expect(screen.getAllByText('Comentario guardado')).toHaveLength(1)
  expect(request.mock.calls[1]?.[0]).toContain('?cursor=opaque%2B%2F')
})

it('conserva comentarios cargados ante fallo de la siguiente página y permite reintentar', async () => {
  const request = vi.fn<AuthRequest>()
    .mockResolvedValueOnce({ items: [item], next_cursor: 'next' })
    .mockRejectedValueOnce(new ApiError(503, 'Offline', {}))
    .mockResolvedValueOnce({ items: [{ ...item, id: '99000000-0000-4000-8000-000000000002', text: 'Recuperado' }], next_cursor: null })
  mount(request)
  await screen.findByText('Comentario guardado')
  await userEvent.click(screen.getByRole('button', { name: 'Cargar comentarios anteriores' }))
  await screen.findByRole('alert')
  expect(screen.getByText('Comentario guardado')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar comentarios' }))
  expect(await screen.findByText('Recuperado')).toBeVisible()
})

it('retira también la lista cacheada si otra página informa que el post ya no está disponible', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce({ items: [item], next_cursor: 'next' })
    .mockRejectedValueOnce(new ApiError(404, 'Retirado', {}))
  mount(request)
  await screen.findByText('Comentario guardado')
  await userEvent.click(screen.getByRole('button', { name: 'Cargar comentarios anteriores' }))
  await screen.findByText('Los comentarios ya no están disponibles para esta publicación.')
  expect(screen.queryByText('Comentario guardado')).not.toBeInTheDocument()
})

it('permite recuperar una falla inicial y distingue una página vacía', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(new ApiError(503, 'Offline', {}))
    .mockResolvedValueOnce({ items: [], next_cursor: null })
  mount(request)
  await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar comentarios' }))
  expect(await screen.findByText('No hay comentarios visibles todavía.')).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
