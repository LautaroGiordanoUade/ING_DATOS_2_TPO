import { beforeEach, expect, it } from 'vitest'
import { clearDraft, readDraft, rememberOperation, recentOperations, saveDraft } from './drafts'
import { toPostPayload } from './contracts'
import { operationId, postId, user } from '../../../tests/fixtures/session'

beforeEach(() => sessionStorage.clear())
const values = { text: 'Hola', interests: 'datos', media: '' }
it('conserva exactamente el envío y clave para reintentar después de recargar', () => {
  const attempt = { key: crypto.randomUUID(), payload: toPostPayload(values, user.id) }
  saveDraft(user.id, values, attempt)
  expect(readDraft(user.id)).toEqual({ values, attempt })
  clearDraft(user.id)
  expect(readDraft(user.id).attempt).toBeNull()
})
it('aísla borradores por cuenta', () => {
  saveDraft(user.id, values, null)
  expect(readDraft(crypto.randomUUID()).values.text).toBe('')
})
it('no envía un intento corrupto o de otro usuario', () => {
  sessionStorage.setItem(`niche.p1.draft.${user.id}`, '{bad json')
  expect(readDraft(user.id).attempt).toBeNull()
  saveDraft(user.id, values, { key: crypto.randomUUID(), payload: toPostPayload(values, crypto.randomUUID()) })
  expect(readDraft(user.id).values.text).toBe('')
})
it('mantiene enlaces recientes sin duplicados', () => {
  rememberOperation(user.id, { operation_id: operationId, post_id: postId })
  rememberOperation(user.id, { operation_id: operationId, post_id: postId })
  expect(recentOperations(user.id)).toHaveLength(1)
})
