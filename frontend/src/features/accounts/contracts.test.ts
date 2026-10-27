import { beforeEach, expect, it } from 'vitest'
import { lookupSchema, reasonSchema, traceSchema } from './contracts'
import { clearAttempt, readAttempt, rememberAccountOperation, recentAccountOperations, saveAttempt } from './attempts'
import { accountJob, target, trace } from '../../../tests/fixtures/accounts'
import { user } from '../../../tests/fixtures/session'

beforeEach(() => sessionStorage.clear())
it('valida UUID sin rechazar los identificadores históricos y normaliza mayúsculas', () => {
  expect(lookupSchema.safeParse({ userId: 'invalido' }).success).toBe(false)
  expect(lookupSchema.parse({ userId: '  80000000-0000-0000-0000-000000000001  ' }).userId).toBe('80000000-0000-0000-0000-000000000001')
  expect(lookupSchema.parse({ userId: user.id.toUpperCase() }).userId).toBe(user.id)
})
it('exige motivo no vacío y un máximo de 1000 caracteres', () => {
  expect(reasonSchema.safeParse({ reason: '  ' }).success).toBe(false)
  expect(reasonSchema.safeParse({ reason: 'x'.repeat(1001) }).success).toBe(false)
  expect(reasonSchema.parse({ reason: '  Motivo  ' }).reason).toBe('Motivo')
})
it('rechaza trazas incompletas y perfiles de otra cuenta', () => {
  expect(traceSchema.safeParse({ user_id: target.id }).success).toBe(false)
  expect(traceSchema.safeParse({ ...trace, profile: user }).success).toBe(false)
  expect(traceSchema.safeParse(trace).success).toBe(true)
})
it('conserva solicitud con su clave, acción y motivo; aísla por actor y cuenta', () => {
  const attempt = { key: crypto.randomUUID(), userId: target.id, action: 'suspend' as const, reason: 'Motivo' }
  saveAttempt(user.id, attempt)
  expect(readAttempt(user.id, target.id)).toEqual(attempt)
  expect(readAttempt(target.id, target.id)).toBeNull()
  expect(readAttempt(user.id, user.id)).toBeNull()
  clearAttempt(user.id, target.id)
  expect(readAttempt(user.id, target.id)).toBeNull()
})
it('ignora solicitudes dañadas o que apuntan a otro usuario', () => {
  sessionStorage.setItem(`niche.p8.attempt.${user.id}.${target.id}`, 'invalid-json')
  expect(readAttempt(user.id, target.id)).toBeNull()
  sessionStorage.setItem(`niche.p8.attempt.${user.id}.${target.id}`, JSON.stringify({ key: crypto.randomUUID(), userId: user.id, action: 'suspend', reason: 'Otro' }))
  expect(readAttempt(user.id, target.id)).toBeNull()
})
it('deduplica operaciones recientes sin guardar snapshots ni credenciales', () => {
  rememberAccountOperation(user.id, accountJob)
  rememberAccountOperation(user.id, accountJob)
  expect(recentAccountOperations(user.id)).toEqual([{ operation_id: accountJob.operation_id, user_id: target.id, action: 'suspend' }])
})
