import { expect, it } from 'vitest'
import { ApiError } from '../../services/http/client'
import { canModerate, decisionValuesSchema, isTerminal, jobSchema, reportSchema, reportValuesSchema } from './contracts'
import { moderationError } from './errors'
import { report, reportedPost } from '../../../tests/fixtures/moderation'
import { user } from '../../../tests/fixtures/session'
import { userSchema } from '../auth/contracts'
import { postSchema } from '../posts/contracts'

it.each(['moderator', 'admin'])('habilita el rol %s', (role) => expect(canModerate(role)).toBe(true))
it.each(['user', '', undefined, 'owner'])('restringe el rol %s', (role) => expect(canModerate(role)).toBe(false))
it('valida el catálogo real de motivos y el límite de descripción', () => {
  expect(reportValuesSchema.parse({ reason: 'hate', description: '  Detalle  ' }).description).toBe('Detalle')
  expect(reportValuesSchema.safeParse({ reason: 'inventado', description: '' }).success).toBe(false)
  expect(reportValuesSchema.safeParse({ reason: 'spam', description: 'a'.repeat(2001) }).success).toBe(false)
})
it('requiere un motivo no vacío para decidir o revertir', () => {
  expect(decisionValuesSchema.safeParse({ action: 'hide', reason: '  ' }).success).toBe(false)
  expect(decisionValuesSchema.safeParse({ action: 'revert', reason: 'a'.repeat(1001) }).success).toBe(false)
  expect(decisionValuesSchema.parse({ action: 'reject', reason: '  Permitido  ' }).reason).toBe('Permitido')
})
it('distingue committing de los estados terminales', () => {
  expect(isTerminal('committing')).toBe(false)
  for (const status of ['completed', 'compensated', 'failed']) expect(isTerminal(status)).toBe(true)
})
it('rechaza respuestas incompletas en vez de asumir éxito', () => expect(jobSchema.safeParse({ status: 'completed' }).success).toBe(false))
it('acepta UUID históricos admitidos por Python sin aceptar identificadores malformados', () => {
  const legacyUser = '70000000-0000-0000-0000-000000000002'
  const legacyPost = '71000000-0000-0000-0000-000000000001'
  expect(reportSchema.safeParse({ ...report, post_id: legacyPost, reporter_id: legacyUser }).success).toBe(true)
  expect(userSchema.safeParse({ ...user, id: legacyUser }).success).toBe(true)
  expect(postSchema.safeParse({ ...reportedPost, id: legacyPost, user_id: legacyUser }).success).toBe(true)
  expect(reportSchema.safeParse({ ...report, post_id: 'identificador-invalido' }).success).toBe(false)
})
it.each([403, 404, 409])('explica errores funcionales %s', (status) => expect(moderationError(new ApiError(status, 'technical', null))).not.toBe('technical'))
