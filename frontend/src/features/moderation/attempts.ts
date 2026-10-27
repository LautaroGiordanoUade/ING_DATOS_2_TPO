import { useQuery, type QueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { storage } from '../../lib/storage'
import { actionSchema, jobStatus } from './api'

const schema = z.object({ post_id: z.guid(), report_id: z.guid(), action: actionSchema,
  reason: z.string().min(1).max(1000), operation_id: z.guid().nullable(), status: jobStatus.nullable() })
export type DecisionAttempt = z.infer<typeof schema>
const storageKey = (viewer: string) => `niche.p7.decisions.${viewer}`
export const attemptKey = (viewer: string) => ['moderation-attempts', viewer]
function load(viewer: string): DecisionAttempt[] {
  try { return z.array(schema).parse(JSON.parse(storage.get(storageKey(viewer)) ?? '[]')) }
  catch { return [] }
}
export function useDecisionAttempts(viewer: string) {
  return useQuery({ queryKey: attemptKey(viewer), initialData: () => load(viewer), queryFn: () => load(viewer),
    enabled: false, staleTime: Infinity }).data
}
export function saveAttempt(client: QueryClient, viewer: string, attempt: DecisionAttempt | null, postId: string) {
  client.setQueryData<DecisionAttempt[]>(attemptKey(viewer), (old = load(viewer)) => {
    const other = old.filter((item) => item.post_id !== postId)
    const open = other.filter((item) => !['completed', 'compensated'].includes(item.status ?? ''))
    const closed = other.filter((item) => ['completed', 'compensated'].includes(item.status ?? '')).slice(-19)
    const next = [...closed, ...open, ...(attempt ? [attempt] : [])]
    storage.set(storageKey(viewer), JSON.stringify(next))
    return next
  })
}
