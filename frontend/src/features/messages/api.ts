import { z } from 'zod'
import type { AuthRequest } from '../auth/api'

const date = z.string().transform((v) => /(?:Z|[+-]\d{2}:\d{2})$/i.test(v) ? v : `${v}Z`)
export const participantSchema = z.object({ id: z.uuid(), username: z.string(), full_name: z.string() })
export const groupSchema = z.object({ id: z.uuid(), name: z.string(), participant_ids: z.array(z.uuid()),
  participants: z.array(participantSchema), unread: z.number().int().nonnegative() })
export const messageSchema = z.object({ id: z.uuid(), conversation_id: z.uuid(), sender_id: z.uuid(),
  text: z.string(), sequence: z.number().int().positive(), created_at: date,
  delivery_status: z.enum(['pending', 'completed']), author_name: z.string(), error: z.string().nullable() })
export const pageSchema = z.object({ items: z.array(messageSchema), next_before: z.number().nullable() })
export type Participant = z.infer<typeof participantSchema>
export type Group = z.infer<typeof groupSchema>
export type GroupMessage = z.infer<typeof messageSchema>
export const root = '/api/v1/messages'

export async function sendMessage(request: AuthRequest, group: string, text: string, key: string) {
  return messageSchema.parse(await request(`${root}/conversations/${group}/messages`, {
    method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ text }),
  }))
}
