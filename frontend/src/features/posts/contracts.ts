import { z } from 'zod'

export const splitInterests = (text: string): string[] => [...new Set(text.split(',').map((s) => s.trim()).filter(Boolean))]
export const splitMedia = (text: string): string[] => text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
export function isMediaUrl(value: string): boolean {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password }
  catch { return false }
}
export const composerSchema = z.object({
  text: z.string().trim().min(1, 'Escribí una publicación.').max(10_000, 'Máximo 10.000 caracteres.'),
  interests: z.string().refine((s) => splitInterests(s).length > 0, 'Agregá al menos un interés.'),
  media: z.string().refine((s) => splitMedia(s).every(isMediaUrl), 'Usá enlaces http o https válidos, uno por línea.'),
})
export type ComposerValues = z.infer<typeof composerSchema>
export const postPayloadSchema = z.object({
  user_id: z.uuid(), text: z.string(), interests: z.array(z.string()), media: z.array(z.string()), visibility: z.literal('public'),
})
export type PostPayload = z.infer<typeof postPayloadSchema>
export function toPostPayload(values: ComposerValues, userId: string): PostPayload {
  return { user_id: userId, text: values.text.trim(), interests: splitInterests(values.interests), media: splitMedia(values.media), visibility: 'public' }
}
export const statusSchema = z.enum(['pending', 'running', 'completed', 'compensating', 'compensated', 'failed'])
export const publicationSchema = z.object({ operation_id: z.uuid(), post_id: z.uuid(), status: statusSchema })
export const operationSchema = z.object({
  operation_id: z.uuid(), operation_type: z.string(), status: statusSchema,
  post_id: z.uuid().nullable(),
  current_step: z.string().nullable(), completed_steps: z.array(z.string()), error: z.string().nullable(),
  created_at: z.string(), updated_at: z.string(),
})
export type Operation = z.infer<typeof operationSchema>
export const terminal = (status: string): boolean => ['completed', 'compensated', 'failed'].includes(status)
export const operationLabels: Record<Operation['status'], string> = {
  pending: 'En cola', running: 'Distribuyendo', completed: 'Publicada',
  compensating: 'Revirtiendo cambios', compensated: 'Publicación cancelada', failed: 'La operación requiere revisión',
}
export const postSchema = z.object({
  id: z.uuid(), user_id: z.uuid(), text: z.string(), media: z.array(z.string()), interests: z.array(z.string()),
  // MongoDB returns UTC datetimes without an offset in historical post responses.
  published_at: z.string().transform((value) => /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`),
  reaction_count: z.number(), comment_count: z.number(),
})
export type Post = z.infer<typeof postSchema>
export const previewSchema = z.object({ user_id: z.uuid(), post_ids: z.array(z.uuid()) })
