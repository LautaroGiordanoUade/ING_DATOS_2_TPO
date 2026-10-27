import { z } from 'zod'
import { storage } from '../../lib/storage'
import { accountActionSchema, attemptSchema, type AccountAttempt } from './contracts'

const key = (actor: string, target: string) => `niche.p8.attempt.${actor}.${target}`
export function readAttempt(actor: string, target: string): AccountAttempt | null {
  try {
    const value = attemptSchema.parse(JSON.parse(storage.get(key(actor, target)) ?? 'null'))
    return value.userId === target ? value : null
  } catch { return null }
}
export function saveAttempt(actor: string, attempt: AccountAttempt) { storage.set(key(actor, attempt.userId), JSON.stringify(attempt)) }
export function clearAttempt(actor: string, target: string) { storage.remove(key(actor, target)) }
const recentSchema = z.array(z.object({ operation_id: z.guid(), user_id: z.guid(), action: accountActionSchema }))
const recentKey = (actor: string) => `niche.p8.operations.${actor}`
export function recentAccountOperations(actor: string) {
  try { return recentSchema.parse(JSON.parse(storage.get(recentKey(actor)) ?? '[]')) }
  catch { return [] }
}
export function rememberAccountOperation(actor: string, job: z.infer<typeof recentSchema>[number]) {
  storage.set(recentKey(actor), JSON.stringify([{ operation_id: job.operation_id, user_id: job.user_id, action: job.action }, ...recentAccountOperations(actor).filter((entry) => entry.operation_id !== job.operation_id)].slice(0, 10)))
}
