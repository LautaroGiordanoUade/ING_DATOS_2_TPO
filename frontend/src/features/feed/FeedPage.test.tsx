import { expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { FeedPage } from './FeedPage'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { postId, sessionWrapper, user } from '../../../tests/fixtures/session'

const author = { ...user, id: '44000000-0000-4000-8000-000000000001', full_name: 'Autor seguido', username: 'autor' }
const post = { id: postId, user_id: author.id, text: 'Idea del autor', media: [], interests: ['datos'], published_at: '2026-10-21T12:00:00Z', reaction_count: 2, comment_count: 1 }
function mount(request: AuthRequest) {
  return render(<MemoryRouter><FeedPage /></MemoryRouter>, { wrapper: sessionWrapper(request) })
}
function requestWithPages(...pages: unknown[]) {
  let index = 0
  return vi.fn<AuthRequest>().mockImplementation(async (path) => {
    if (path.startsWith('/api/v1/users/')) return author
    if (path.startsWith('/api/v1/interactions/reactions/')) return { kind: null }
    if (path.includes('/comments')) return { items: [], next_cursor: null }
    const page = pages[index++]
    if (page instanceof Error) throw page
    return page
  })
}

it('anuncia carga y cancela el request al salir', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(() => new Promise(() => {}))
  const view = mount(request)
  expect(screen.getByRole('status')).toHaveTextContent('Cargando tu feed')
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1))
  const signal = request.mock.calls[0]?.[1]?.signal
  view.unmount()
  expect(signal?.aborted).toBe(true)
})
it('muestra el estado vacío con acceso separado a publicaciones propias', async () => {
  mount(requestWithPages({ items: [], next_cursor: null }))
  expect(await screen.findByText('Tu feed todavía está vacío.')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Ver mis publicaciones' })).toHaveAttribute('href', '/mis-publicaciones')
  expect(screen.queryByRole('button', { name: 'Cargar más publicaciones' })).not.toBeInTheDocument()
})
it('muestra autor real, intereses y contadores entregados por el servidor', async () => {
  mount(requestWithPages({ items: [post], next_cursor: null }))
  await screen.findByText('Autor seguido')
  expect(screen.getByText('@autor')).toBeVisible()
  expect(screen.getByText('Idea del autor')).toBeVisible()
  expect(screen.getByText('2 reacciones · 1 comentarios')).toBeVisible()
})
it('carga otra página con el cursor recibido y no duplica tarjetas', async () => {
  const second = { ...post, id: crypto.randomUUID(), text: 'Otra idea' }
  const request = requestWithPages({ items: [post], next_cursor: 'opaque+/=' }, { items: [{ ...post, reaction_count: 5 }, second], next_cursor: null })
  mount(request)
  await screen.findByText('Autor seguido')
  await userEvent.click(screen.getByRole('button', { name: 'Cargar más publicaciones' }))
  await screen.findByText('Otra idea')
  expect(screen.getAllByRole('article')).toHaveLength(2)
  expect(screen.getByText('5 reacciones · 1 comentarios')).toBeVisible()
  expect(request.mock.calls.filter(([path]) => path.startsWith('/api/v1/users/'))).toHaveLength(1)
  expect(request.mock.calls.some(([path]) => path.endsWith('?cursor=opaque%2B%2F%3D'))).toBe(true)
})
it('continúa una página vacía cuando existe next_cursor', async () => {
  mount(requestWithPages({ items: [], next_cursor: 'next' }, { items: [post], next_cursor: null }))
  await screen.findByText('Todavía no hay publicaciones visibles en esta página.')
  await userEvent.click(screen.getByRole('button', { name: 'Cargar más publicaciones' }))
  await screen.findByText('Idea del autor')
})
it('refrescar descarta las páginas previas e inicia sin cursor', async () => {
  const next = { ...post, id: crypto.randomUUID(), text: 'Publicación nueva' }
  const request = requestWithPages({ items: [post], next_cursor: 'old-cursor' }, { items: [next], next_cursor: null })
  mount(request)
  await screen.findByText('Idea del autor')
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar feed' }))
  await screen.findByText('Publicación nueva')
  expect(screen.queryByText('Idea del autor')).not.toBeInTheDocument()
  expect(request.mock.calls.filter(([path]) => path.startsWith('/api/v1/feeds/')).map(([path]) => path)).toEqual([`/api/v1/feeds/${user.id}`, `/api/v1/feeds/${user.id}`])
})
it('permite recuperar un error inicial del servidor', async () => {
  mount(requestWithPages(new ApiError(503, 'Servicio no disponible', null), { items: [post], next_cursor: null }))
  await screen.findByText('Servicio no disponible')
  await userEvent.click(screen.getByRole('button', { name: 'Volver a intentar' }))
  await screen.findByText('Idea del autor')
})
it('un cursor vencido exige refrescar y retira las tarjetas de la navegación anterior', async () => {
  const next = { ...post, id: crypto.randomUUID(), text: 'Después de refrescar' }
  mount(requestWithPages({ items: [post], next_cursor: 'expired' }, new ApiError(410, 'Expired', null), { items: [next], next_cursor: null }))
  await screen.findByText('Idea del autor')
  await userEvent.click(screen.getByRole('button', { name: 'Cargar más publicaciones' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('La navegación del feed venció')
  expect(screen.queryByText('Idea del autor')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar feed' }))
  await screen.findByText('Después de refrescar')
})
it('una falla al cargar otra página conserva el contenido ya leído y reintenta esa página', async () => {
  const next = { ...post, id: crypto.randomUUID(), text: 'Página recuperada' }
  mount(requestWithPages({ items: [post], next_cursor: 'retry' }, new ApiError(503, 'Servicio caído', null), { items: [next], next_cursor: null }))
  await screen.findByText('Idea del autor')
  await userEvent.click(screen.getByRole('button', { name: 'Cargar más publicaciones' }))
  await screen.findByText('Servicio caído')
  expect(screen.getByText('Idea del autor')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Volver a intentar' }))
  await screen.findByText('Página recuperada')
})
