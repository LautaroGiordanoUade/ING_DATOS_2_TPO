import { z } from 'zod'

export const canModerate = (role?: string): boolean => role === 'moderator' || role === 'admin'
export const reasons = { spam: 'Spam', abuse: 'Acoso o abuso', hate: 'Discurso de odio', violence: 'Violencia', other: 'Otro motivo' }
export const resolutions = { pending: 'Pendiente', approved: 'Ocultado', rejected: 'Reporte rechazado', reverted: 'Restaurado' }
export const actions = { hide: 'Ocultar publicación', reject: 'Rechazar reporte', revert: 'Restaurar publicación' }
export const reportValuesSchema = z.object({
  reason: z.enum(['spam', 'abuse', 'hate', 'violence', 'other']),
  description: z.string().trim().max(2000, 'Máximo 2.000 caracteres.'),
})
export const decisionValuesSchema = z.object({
  action: z.enum(['hide', 'reject', 'revert']),
  reason: z.string().trim().min(1, 'Escribí el motivo de la decisión.').max(1000, 'Máximo 1.000 caracteres.'),
})
export type DecisionValues = z.infer<typeof decisionValuesSchema>
export const reportSchema = z.object({
  id: z.guid(), post_id: z.guid(), reporter_id: z.guid(), reason: z.string(), description: z.string().nullable(),
  resolution_status: z.enum(['pending', 'approved', 'rejected', 'reverted']), reported_at: z.string(),
  moderator_id: z.guid().nullable(), resolved_at: z.string().nullable(), decision: z.string().nullable(),
  decision_reason: z.string().nullable(), operation_id: z.guid().nullable(),
})
export type Report = z.infer<typeof reportSchema>
export const jobSchema = z.object({
  operation_id: z.guid(), report_id: z.guid(), post_id: z.guid(), moderator_id: z.guid(),
  action: z.enum(['hide', 'reject', 'revert']), reason: z.string(),
  status: z.enum(['pending', 'running', 'committing', 'completed', 'compensating', 'compensated', 'failed']),
  completed_steps: z.array(z.string()), error: z.string().nullable(), updated_at: z.string(),
})
export const jobLabels = { pending: 'En cola', running: 'Aplicando decisión', committing: 'Confirmando decisión', completed: 'Decisión completada', compensating: 'Restaurando cambios previos', compensated: 'Decisión cancelada', failed: 'Requiere revisión' }
export const isTerminal = (status: string) => ['completed', 'compensated', 'failed'].includes(status)
export const historySchema = z.array(z.object({
  operation_id: z.guid(), report_id: z.guid(), moderator_id: z.guid(),
  action: z.enum(['hide', 'reject', 'revert']), reason: z.string(), created_at: z.string(),
  new_status: z.enum(['approved', 'rejected', 'reverted']),
}))
