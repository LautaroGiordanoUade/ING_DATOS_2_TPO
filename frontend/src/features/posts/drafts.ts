import { z } from 'zod'
import { storage } from '../../lib/storage'
import { postPayloadSchema, type ComposerValues } from './contracts'

export const attemptSchema = z.object({ key: z.uuid(), payload: postPayloadSchema })
export type PublicationAttempt = z.infer<typeof attemptSchema>
const draftSchema = z.object({ values: z.object({ text: z.string(), interests: z.string(), media: z.string() }), attempt: attemptSchema.nullable() })
export const emptyValues: ComposerValues = { text: '', interests: '', media: '' }
const key = (userId: string) => `niche.p1.draft.${userId}`

export function readDraft(userId: string): z.infer<typeof draftSchema> {
  try {
    const parsed = draftSchema.safeParse(JSON.parse(storage.get(key(userId)) ?? 'null'))
    if (parsed.success && (!parsed.data.attempt || parsed.data.attempt.payload.user_id === userId)) return parsed.data
  } catch { /* Ignore damaged storage; do not submit it. */ }
  return { values: emptyValues, attempt: null }
}
export function saveDraft(userId: string, values: ComposerValues, attempt: PublicationAttempt | null): void {
  storage.set(key(userId), JSON.stringify({ values, attempt }))
}
export function clearDraft(userId: string): void { storage.remove(key(userId)) }

const recentSchema = z.array(z.object({ operation_id: z.uuid(), post_id: z.uuid() }))
export function recentOperations(userId: string): z.infer<typeof recentSchema> {
  try { return recentSchema.parse(JSON.parse(storage.get(`niche.p1.operations.${userId}`) ?? '[]')) }
  catch { return [] }
}
export function rememberOperation(userId: string, operation: { operation_id: string; post_id: string }): void {
  storage.set(`niche.p1.operations.${userId}`, JSON.stringify([operation, ...recentOperations(userId).filter((s) => s.operation_id !== operation.operation_id)].slice(0, 10)))
}
