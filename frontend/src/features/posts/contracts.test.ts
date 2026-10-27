import { expect, it } from 'vitest'
import { composerSchema, isMediaUrl, postSchema, splitInterests, terminal, toPostPayload } from './contracts'
import { postId, user } from '../../../tests/fixtures/session'

it('rechaza texto vacío, exceso de caracteres e intereses vacíos', () => {
  expect(composerSchema.safeParse({ text: ' ', interests: 'datos', media: '' }).success).toBe(false)
  expect(composerSchema.safeParse({ text: 'a'.repeat(10001), interests: 'datos', media: '' }).success).toBe(false)
  expect(composerSchema.safeParse({ text: 'Hola', interests: ', ,', media: '' }).success).toBe(false)
})
it('limpia intereses y crea el payload real sin inventar IDs ni visibilidad', () => {
  expect(splitInterests(' datos, python, datos, ')).toEqual(['datos', 'python'])
  expect(toPostPayload({ text: ' Hola ', interests: 'datos, python', media: '' }, user.id)).toEqual({ user_id: user.id, text: 'Hola', interests: ['datos', 'python'], media: [], visibility: 'public' })
})
it.each(['javascript:alert(1)', 'data:image/svg+xml,hi', 'https://user:pass@example.test/a', 'not-a-url'])('rechaza media %s', (url) => {
  expect(isMediaUrl(url)).toBe(false)
})
it('solo detiene polling en estados terminales reales', () => {
  for (const state of ['completed', 'compensated', 'failed']) expect(terminal(state)).toBe(true)
  for (const state of ['pending', 'running', 'compensating']) expect(terminal(state)).toBe(false)
})

it.each(['2026-10-27T04:00:00', '2026-10-27T04:00:00Z', '2026-10-27T07:00:00+03:00'])(
  'interpreta publicaciones UTC antiguas y conserva offsets explícitos: %s', (published_at) => {
    const post = postSchema.parse({ id: postId, user_id: user.id, text: 'Post', media: [],
      interests: [], published_at, reaction_count: 0, comment_count: 0 })
    expect(Date.parse(post.published_at)).toBe(Date.UTC(2026, 9, 27, 4))
    if (published_at.includes('+')) expect(post.published_at).toBe(published_at)
  },
)
