import { z } from 'zod'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'

const date = z.string().transform((v) => /(?:Z|[+-]\d{2}:\d{2})$/i.test(v) ? v : `${v}Z`)
export const reasonLabels = { spam: 'Spam', abuse: 'Abuso', hate: 'Odio', violence: 'Violencia', other: 'Otro motivo' } as const
export const reportLabels = { pending: 'Pendiente', approved: 'Ocultado', rejected: 'Reporte rechazado', reverted: 'Restaurado' } as const
export const actionLabels = { hide: 'Ocultar publicación', reject: 'Rechazar reporte', revert: 'Revertir ocultamiento' } as const
export const jobLabels = { pending: 'En espera', running: 'Procesando', committing: 'Confirmando', compensating: 'Restaurando estado anterior', completed: 'Completado', compensated: 'Cambio revertido', failed: 'Requiere recuperación' } as const
export const jobStatus = z.enum(['pending', 'running', 'committing', 'compensating', 'completed', 'compensated', 'failed'])
export const actionSchema = z.enum(['hide', 'reject', 'revert'])
export const reportSchema = z.object({ id: z.guid(), post_id: z.guid(), reporter_id: z.guid(),
  reason: z.enum(['spam', 'abuse', 'hate', 'violence', 'other']), description: z.string().nullable(),
  resolution_status: z.enum(['pending', 'approved', 'rejected', 'reverted']), reported_at: date,
  moderator_id: z.guid().nullable(), resolved_at: date.nullable(), decision: actionSchema.nullable(),
  decision_reason: z.string().nullable(), operation_id: z.guid().nullable(),
  resolution_operation_id: z.guid().nullable().default(null), resolution_report_id: z.guid().nullable().default(null),
})
export const contentSchema = z.object({ id: z.guid(), user_id: z.guid(), text: z.string(), media: z.array(z.string()),
  interests: z.array(z.string()), published_at: date, visibility: z.string(), moderation_status: z.string(),
  moderation_owner: z.guid().nullable(), active_operation_id: z.guid().nullable(), report_operation_id: z.guid().nullable(),
})
export const jobSchema = z.object({ operation_id: z.guid(), post_id: z.guid(), report_id: z.guid(), moderator_id: z.guid(),
  action: actionSchema, reason: z.string(), status: jobStatus, error: z.string().nullable() })
export const historySchema = z.array(z.object({ operation_id: z.guid(), post_id: z.guid(), report_id: z.guid(),
  moderator_id: z.guid(), action: actionSchema, reason: z.string(), created_at: date,
  affected_report_count: z.number().int().nonnegative().optional(), resolution_operation_id: z.guid().optional(),
}))
export type Report = z.infer<typeof reportSchema>
export type ModerationJob = z.infer<typeof jobSchema>
export type ModerationContent = z.infer<typeof contentSchema>
export type Action = z.infer<typeof actionSchema>
export const terminal = (status: string) => ['completed', 'compensated', 'failed'].includes(status)
export const canModerate = (role: string | undefined) => role === 'moderator' || role === 'admin'
export const denied = (error: unknown) => error instanceof ApiError && error.status === 403
export const root = '/api/v1/moderation'
export const queryRoot = (viewer: string, role: string) => ['moderation', viewer, role]

export async function sendDecision(request: AuthRequest, reportId: string, postId: string, action: Action, reason: string) {
  const job = jobSchema.parse(await request(`${root}/reports/${reportId}/${action === 'revert' ? 'revert' : 'decision'}`, {
    method: 'POST', body: JSON.stringify({ ...(action === 'revert' ? {} : { decision: action }), reason }),
  }))
  if (job.post_id !== postId || job.action !== action || job.reason !== reason) throw new Error('La respuesta no corresponde a esta decisión.')
  return job
}
