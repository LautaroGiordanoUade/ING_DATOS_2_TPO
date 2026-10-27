import { z } from 'zod'
import { userSchema } from '../auth/contracts'
import { postSchema } from '../posts/contracts'

export const userIdSchema = z.guid('Ingresá un identificador de usuario válido.').transform((id) => id.toLowerCase())
export const lookupSchema = z.object({ userId: z.string().trim().pipe(userIdSchema) })
export const reasonSchema = z.object({ reason: z.string().trim().min(1, 'Escribí un motivo.').max(1000, 'Máximo 1.000 caracteres.') })
export const accountActionSchema = z.enum(['suspend', 'reactivate'])
export type AccountAction = z.infer<typeof accountActionSchema>
export const accountActions = { suspend: 'Suspender cuenta', reactivate: 'Reactivar cuenta' }
export const accountStatus = { active: 'Activa', suspended: 'Suspendida' }
export const accountJobSchema = z.object({
  operation_id: z.guid(), user_id: z.guid(), actor_id: z.guid(), action: accountActionSchema,
  reason: z.string(), status: z.enum(['pending', 'running', 'committing', 'completed', 'compensating', 'compensated', 'failed']),
  completed_steps: z.array(z.string()), error: z.string().nullable(), updated_at: z.string(),
})
export const accountJobLabels = { pending: 'En cola', running: 'Aplicando cambio de cuenta', committing: 'Confirmando cambio', completed: 'Cambio de cuenta completado', compensating: 'Restaurando estado previo', compensated: 'Cambio de cuenta cancelado', failed: 'Requiere revisión administrativa' }
export const accountHistorySchema = z.array(z.object({
  operation_id: z.guid(), actor_id: z.guid(), action: accountActionSchema, reason: z.string(),
  previous_status: z.enum(['active', 'suspended']).nullable(), new_status: z.enum(['active', 'suspended']),
  created_at: z.string(), posts_count: z.number().int().nonnegative(),
}))
export const traceSchema = z.object({
  user_id: z.guid(), profile: userSchema.nullable(), presence: z.boolean(),
  relationships: z.object({
    followers: z.array(z.guid()), following: z.array(z.guid()), blocked: z.array(z.guid()),
    edges: z.array(z.object({ kind: z.string(), outgoing: z.boolean(), other_id: z.guid(), status: z.string() })),
  }),
  recent_posts: z.array(postSchema),
  post_states: z.array(z.object({ id: z.guid(), moderation_status: z.string(), publicly_visible: z.boolean(), suspension_hidden: z.boolean() })),
  active_conversations: z.array(z.object({ id: z.guid(), participant_ids: z.array(z.guid()), created_at: z.string() })),
  account_history: accountHistorySchema,
}).refine((trace) => !trace.profile || trace.profile.id === trace.user_id, 'El perfil no corresponde a la cuenta consultada.')
export type Trace = z.infer<typeof traceSchema>
export const attemptSchema = z.object({ key: z.guid(), userId: z.guid(), action: accountActionSchema, reason: reasonSchema.shape.reason })
export type AccountAttempt = z.infer<typeof attemptSchema>
