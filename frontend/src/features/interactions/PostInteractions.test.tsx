import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PostInteractions } from './PostInteractions'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { postId, sessionWrapper } from '../../../tests/fixtures/session'

function mount(request: AuthRequest, onCountsChange = vi.fn()) {
  return render(
    <PostInteractions postId={postId} onCountsChange={onCountsChange} />,
    { wrapper: sessionWrapper(request) }
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
