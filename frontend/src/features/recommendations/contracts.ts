import { z } from 'zod'

export const uuidListSchema = z.array(z.string().uuid())
export type UuidList = z.infer<typeof uuidListSchema>

export const mutualFriendsQuerySchema = z.object({
  user_id: z.string().uuid(),
  other_user_id: z.string().uuid('Ingresá un identificador de usuario válido.'),
})
export type MutualFriendsQuery = z.infer<typeof mutualFriendsQuerySchema>
