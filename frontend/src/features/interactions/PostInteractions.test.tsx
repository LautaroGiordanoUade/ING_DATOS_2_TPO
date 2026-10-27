import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PostInteractions } from './PostInteractions'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { postId, sessionWrapper } from '../../../tests/fixtures/session'

function mount(
  request: AuthRequest,
  onCountsChange = vi.fn(),
  ownReactionRequest: AuthRequest = async () => ({ kind: null }),
  commentsRequest: AuthRequest = async () => ({ items: [], next_cursor: null }),
) {
  const authenticatedRequest: AuthRequest = (path, init) =>
    path === `/api/v1/interactions/reactions/${postId}/me`
      ? ownReactionRequest(path, init)
      : path.startsWith(`/api/v1/posts/${postId}/comments`) ? commentsRequest(path, init)
      : request(path, init)
  return render(
    <PostInteractions postId={postId} onCountsChange={onCountsChange} />,
    { wrapper: sessionWrapper(authenticatedRequest) }
  )
}

it('renderiza botones de reacción y botón para desplegar comentarios', () => {
  const request = vi.fn<AuthRequest>()
  mount(request)

  expect(screen.getByRole('button', { name: '👍 Me gusta' })).toBeVisible()
  expect(screen.getByRole('button', { name: '❤️ Me encanta' })).toBeVisible()
  expect(screen.getByRole('button', { name: '💬 Escribir comentario' })).toBeVisible()
})

it('envía reacción y actualiza los contadores desde el servidor', async () => {
  const onCountsChange = vi.fn()
  const request = vi.fn<AuthRequest>().mockImplementation(async (path, init) => {
    if (path === '/api/v1/problems/5/reaction' && init?.method === 'POST') {
      return { operation_id: '55000000-0000-4000-8000-000000000001', status: 'completed' }
    }
    if (path === `/api/v1/posts/${postId}`) {
      return {
        id: postId,
        user_id: '11000000-0000-4000-8000-000000000001',
        text: 'Publicación',
        media: [],
        interests: ['datos'],
        published_at: '2026-10-22T12:00:00Z',
        reaction_count: 5,
        comment_count: 2,
      }
    }
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request, onCountsChange)
  await userEvent.click(screen.getByRole('button', { name: '👍 Me gusta' }))

  await screen.findByText('Reacción enviada (like).')
  expect(onCountsChange).toHaveBeenCalledWith(5, 2)
  expect(screen.getByRole('button', { name: 'Quitar mi reacción' })).toBeVisible()
})

it('permite enviar una reacción personalizada y refresca contadores', async () => {
  const onCountsChange = vi.fn()
  const request = vi.fn<AuthRequest>().mockImplementation(async (path, init) => {
    if (path === '/api/v1/problems/5/reaction' && init?.method === 'POST') {
      return { operation_id: '55000000-0000-4000-8000-000000000002', status: 'completed' }
    }
    if (path === `/api/v1/posts/${postId}`) {
      return {
        id: postId,
        user_id: '11000000-0000-4000-8000-000000000001',
        text: 'Publicación',
        media: [],
        interests: ['datos'],
        published_at: '2026-10-22T12:00:00Z',
        reaction_count: 6,
        comment_count: 2,
      }
    }
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request, onCountsChange)
  await userEvent.click(screen.getByRole('button', { name: '＋ Otra' }))
  await userEvent.type(screen.getByPlaceholderText('Ej: aplauso'), 'aplauso')
  await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }))

  await screen.findByText('Reacción enviada (aplauso).')
  expect(onCountsChange).toHaveBeenCalledWith(6, 2)
})

it('permite quitar la reacción y refresca contadores', async () => {
  const onCountsChange = vi.fn()
  const request = vi.fn<AuthRequest>().mockImplementation(async (path) => {
    if (path === '/api/v1/problems/5/reaction') {
      return { operation_id: '55000000-0000-4000-8000-000000000001', status: 'completed' }
    }
    if (path === `/api/v1/posts/${postId}`) {
      return {
        id: postId,
        user_id: '11000000-0000-4000-8000-000000000001',
        text: 'Publicación',
        media: [],
        interests: ['datos'],
        published_at: '2026-10-22T12:00:00Z',
        reaction_count: 4,
        comment_count: 2,
      }
    }
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request, onCountsChange)
  await userEvent.click(screen.getByRole('button', { name: '❤️ Me encanta' }))
  await screen.findByRole('button', { name: 'Quitar mi reacción' })

  await userEvent.click(screen.getByRole('button', { name: 'Quitar mi reacción' }))
  await screen.findByText('Reacción eliminada.')
  expect(onCountsChange).toHaveBeenLastCalledWith(4, 2)
})

it('valida comentario vacío y no llama al servidor', async () => {
  const request = vi.fn<AuthRequest>()
  mount(request)

  await userEvent.click(screen.getByRole('button', { name: '💬 Escribir comentario' }))
  const commentButton = screen.getByRole('button', { name: 'Comentar' })
  expect(commentButton).toBeDisabled()
  expect(request).not.toHaveBeenCalled()
})

it('envía comentario con Idempotency-Key y limpia el textarea tras éxito', async () => {
  const onCountsChange = vi.fn()
  let capturedKey: string | null = null
  const request = vi.fn<AuthRequest>().mockImplementation(async (path, init) => {
    if (path === '/api/v1/problems/5/comment') {
      capturedKey = new Headers(init?.headers).get('Idempotency-Key')
      return { operation_id: '66000000-0000-4000-8000-000000000001', status: 'completed' }
    }
    if (path === `/api/v1/posts/${postId}`) {
      return {
        id: postId,
        user_id: '11000000-0000-4000-8000-000000000001',
        text: 'Publicación',
        media: [],
        interests: ['datos'],
        published_at: '2026-10-22T12:00:00Z',
        reaction_count: 4,
        comment_count: 3,
      }
    }
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request, onCountsChange)
  await userEvent.click(screen.getByRole('button', { name: '💬 Escribir comentario' }))

  const textarea = screen.getByPlaceholderText('Sumá tu comentario a la publicación…')
  await userEvent.type(textarea, 'Excelente aporte!')
  await userEvent.click(screen.getByRole('button', { name: 'Comentar' }))

  await screen.findByText('Comentario enviado exitosamente.')
  expect(textarea).toHaveValue('')
  expect(capturedKey).toMatch(/^[0-9a-f-]{36}$/)
  expect(onCountsChange).toHaveBeenCalledWith(4, 3)
})

it('conserva el texto del comentario ante error 409 para permitir reintentar', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(
    new ApiError(409, 'Conflict', { detail: 'Operación concurrente' })
  )

  mount(request)
  await userEvent.click(screen.getByRole('button', { name: '💬 Escribir comentario' }))

  const textarea = screen.getByPlaceholderText('Sumá tu comentario a la publicación…')
  await userEvent.type(textarea, 'Mi comentario importante')
  await userEvent.click(screen.getByRole('button', { name: 'Comentar' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Conflicto por operaciones concurrentes. Volvé a intentar.')
  expect(textarea).toHaveValue('Mi comentario importante')
})

it('restaura la reacción persistida y permite quitarla sin reaccionar otra vez', async () => {
  const onCountsChange = vi.fn()
  const request = vi.fn<AuthRequest>().mockImplementation(async (path, init) => {
    if (path === '/api/v1/problems/5/reaction' && init?.method === 'DELETE') {
      return { operation_id: '55000000-0000-4000-8000-000000000001', status: 'completed' }
    }
    if (path === `/api/v1/posts/${postId}`) {
      return { id: postId, user_id: '11000000-0000-4000-8000-000000000001', text: 'Post',
        media: [], interests: ['datos'], published_at: '2026-10-22T12:00:00Z',
        reaction_count: 0, comment_count: 0 }
    }
    throw new Error(`Ruta inesperada: ${path}`)
  })
  mount(request, onCountsChange, async () => ({ kind: 'love' }))
  const remove = await screen.findByRole('button', { name: 'Quitar mi reacción' })
  expect(screen.getByRole('button', { name: '❤️ Me encanta' })).toHaveAttribute('aria-pressed', 'true')
  await userEvent.click(remove)
  await screen.findByText('Reacción eliminada.')
  expect(screen.queryByRole('button', { name: 'Quitar mi reacción' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '❤️ Me encanta' })).toHaveAttribute('aria-pressed', 'false')
  expect(request.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  expect(onCountsChange).toHaveBeenCalledWith(0, 0)
})

it('restaura también una reacción personalizada', async () => {
  mount(vi.fn<AuthRequest>(), vi.fn(), async () => ({ kind: 'aplauso' }))
  expect(await screen.findByText('Tu reacción: aplauso')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Quitar mi reacción' })).toBeVisible()
})

it('no permite modificar la reacción antes de cargar su estado', () => {
  mount(vi.fn<AuthRequest>(), vi.fn(), () => new Promise(() => {}))
  expect(screen.getByRole('button', { name: '👍 Me gusta' })).toBeDisabled()
  expect(screen.getByText('Cargando tu reacción…')).toBeVisible()
})

it('muestra error de lectura y permite reintentar sin confundirlo con ausencia de reacción', async () => {
  const own = vi.fn<AuthRequest>()
    .mockRejectedValueOnce(new ApiError(503, 'No disponible', {}))
    .mockResolvedValueOnce({ kind: 'like' })
  mount(vi.fn<AuthRequest>(), vi.fn(), own)
  expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cargar tu reacción')
  expect(screen.getByRole('button', { name: '👍 Me gusta' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar reacción' }))
  expect(await screen.findByRole('button', { name: 'Quitar mi reacción' })).toBeVisible()
  expect(screen.getByRole('button', { name: '👍 Me gusta' })).toHaveAttribute('aria-pressed', 'true')
})

it('abre y actualiza el listado después de enviar un comentario', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(async (path) => {
    if (path === '/api/v1/problems/5/comment') return {
      operation_id: '66000000-0000-4000-8000-000000000001', status: 'completed',
    }
    return { id: postId, user_id: '11000000-0000-4000-8000-000000000001', text: 'Post',
      media: [], interests: [], published_at: '2026-10-27T12:00:00Z', reaction_count: 0, comment_count: 1 }
  })
  const list: AuthRequest = async () => ({ items: [{
    id: '99000000-0000-4000-8000-000000000001', post_id: postId,
    user_id: '11000000-0000-4000-8000-000000000001', text: 'Ahora se ve debajo',
    created_at: '2026-10-27T12:00:00Z', author_name: 'QA', author_username: 'qa',
  }], next_cursor: null })
  mount(request, vi.fn(), async () => ({ kind: null }), list)
  await userEvent.click(screen.getByRole('button', { name: '💬 Escribir comentario' }))
  await userEvent.type(screen.getByLabelText('Escribí un comentario'), 'Ahora se ve debajo')
  await userEvent.click(screen.getByRole('button', { name: 'Comentar' }))
  expect(await screen.findByText('Ahora se ve debajo')).toBeVisible()
  expect(screen.getByText('@qa')).toBeVisible()
  expect(screen.getByLabelText('Escribí un comentario')).toHaveValue('')
})
