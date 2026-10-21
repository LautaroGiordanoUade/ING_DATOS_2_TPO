import { expect, it, vi } from 'vitest'
import type { AuthRequest } from '../auth/api'
import { getFeed, uniquePosts } from './api'
import { postId, user } from '../../../tests/fixtures/session'

const post = { id: postId, user_id: user.id, text: 'Una idea', media: [], interests: ['datos'], published_at: '2026-10-21T12:00:00Z', reaction_count: 0, comment_count: 0 }

it('transmite el cursor opaco codificado sin interpretarlo y conserva cancelación', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ items: [post], next_cursor: null })
  const signal = new AbortController().signal
  await getFeed(request, user.id, 'opaque+/= ?&', signal)
  expect(request).toHaveBeenCalledWith(`/api/v1/feeds/${user.id}?cursor=opaque%2B%2F%3D%20%3F%26`, { signal })
})
it('inicia sin cursor y valida el contrato del servidor', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ items: [], next_cursor: 'another-page' })
  await expect(getFeed(request, user.id, null, new AbortController().signal)).resolves.toEqual({ items: [], next_cursor: 'another-page' })
  expect(request.mock.calls[0]?.[0]).toBe(`/api/v1/feeds/${user.id}`)
  request.mockResolvedValueOnce({ items: [], next_cursor: { score: 1 } })
  await expect(getFeed(request, user.id, null, new AbortController().signal)).rejects.toThrow()
})
it('deduplica IDs sin reordenar el ranking y conserva contadores de la lectura más reciente', () => {
  const second = { ...post, id: crypto.randomUUID(), text: 'Segunda' }
  const result = uniquePosts([{ items: [post, second], next_cursor: 'next' }, { items: [{ ...post, reaction_count: 5 }], next_cursor: null }])
  expect(result.map((item) => item.id)).toEqual([post.id, second.id])
  expect(result[0]?.reaction_count).toBe(5)
})
