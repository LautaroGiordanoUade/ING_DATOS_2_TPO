import { z } from 'zod'

export const ownReactionSchema = z.object({ kind: z.string().nullable() })

export const commentPageSchema = z.object({
  items: z.array(z.object({
    id: z.uuid(), post_id: z.uuid(), user_id: z.uuid(), text: z.string(),
    created_at: z.string(), author_name: z.string(), author_username: z.string().nullable(),
  })),
  next_cursor: z.string().nullable(),
})
export type CommentPage = z.infer<typeof commentPageSchema>

export const PRESET_REACTIONS = [
  { kind: 'like', label: '👍 Me gusta' },
  { kind: 'love', label: '❤️ Me encanta' },
  { kind: 'celebrate', label: '🎉 Celebrar' },
  { kind: 'insightful', label: '💡 Interesante' },
] as const

export const reactionPayloadSchema = z.object({
  post_id: z.string().uuid(),
  user_id: z.string().uuid(),
  kind: z.string().trim().min(1, 'El tipo de reacción no puede estar vacío.').max(30, 'Máximo 30 caracteres.'),
})
export type ReactionPayload = z.infer<typeof reactionPayloadSchema>

export const reactionRemoveSchema = z.object({
  post_id: z.string().uuid(),
  user_id: z.string().uuid(),
})
export type ReactionRemovePayload = z.infer<typeof reactionRemoveSchema>

export const commentPayloadSchema = z.object({
  post_id: z.string().uuid(),
  user_id: z.string().uuid(),
  text: z.string().trim().min(1, 'Escribí un comentario antes de enviar.').max(2000, 'Máximo 2.000 caracteres.'),
})
export type CommentPayload = z.infer<typeof commentPayloadSchema>

export const interactionOperationSchema = z.object({
  operation_id: z.string().uuid(),
  status: z.string(),
})
export type InteractionOperation = z.infer<typeof interactionOperationSchema>
