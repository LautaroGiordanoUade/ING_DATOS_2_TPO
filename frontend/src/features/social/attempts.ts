import { useQuery, type QueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { storage } from '../../lib/storage'
import { followStatus } from './api'

const attemptSchema = z.object({ follower_id: z.uuid(), followed_id: z.uuid(),
  action: z.enum(['follow', 'unfollow', 'approve']), key: z.uuid().nullable(),
  operation_id: z.uuid().nullable(), status: followStatus.nullable(),
})
export type FollowAttempt = z.infer<typeof attemptSchema>
const key = (viewer: string) => `niche.p2.attempts.${viewer}`
function read(viewer: string): FollowAttempt[] {
  try { return z.array(attemptSchema).parse(JSON.parse(storage.get(key(viewer)) ?? '[]')) }
  catch { return [] }
}
export const attemptQuery = (viewer: string) => ['social-attempts', viewer]
export function useFollowAttempts(viewer: string) {
  return useQuery({ queryKey: attemptQuery(viewer), initialData: () => read(viewer),
    queryFn: () => read(viewer), enabled: false, staleTime: Infinity }).data
}
export function putAttempt(client: QueryClient, viewer: string, attempt: FollowAttempt) {
  client.setQueryData<FollowAttempt[]>(attemptQuery(viewer), (previous = read(viewer)) => {
    const others = previous.filter((item) => item.follower_id !== attempt.follower_id || item.followed_id !== attempt.followed_id)
    // Keep unfinished work; bound retained terminal history in this tab.
    const open = others.filter((item) => !['completed', 'compensated'].includes(item.status ?? ''))
    const closed = others.filter((item) => ['completed', 'compensated'].includes(item.status ?? '')).slice(-19)
    const next = [...closed, ...open, attempt]
    storage.set(key(viewer), JSON.stringify(next))
    return next
  })
}
