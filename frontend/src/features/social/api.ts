import { z } from 'zod'
import type { AuthRequest } from '../auth/api'

export const followStatus = z.enum(['pending', 'running', 'committing', 'compensating', 'completed', 'compensated', 'failed'])
export const followJobSchema = z.object({ operation_id: z.uuid(), follower_id: z.uuid(), followed_id: z.uuid(),
  actor_id: z.uuid(), action: z.enum(['follow', 'unfollow', 'approve']), status: followStatus,
  desired: z.enum(['none', 'pending', 'accepted']).nullable(), error: z.string().nullable(),
})
export const relationSchema = z.discriminatedUnion('status', [
  z.object({ status: z.literal('processing'), operation_id: z.uuid(), operation_status: followStatus }),
  z.object({ status: z.enum(['none', 'pending', 'accepted']) }),
])
export const countsSchema = z.object({ followers: z.number().int().nonnegative(), following: z.number().int().nonnegative() })
export type FollowJob = z.infer<typeof followJobSchema>
export type FollowAction = FollowJob['action']
export const terminal = (status: string) => ['completed', 'compensated', 'failed'].includes(status)
export const socialRoot = '/api/v1/social'

export async function getRelation(request: AuthRequest, followedId: string, signal?: AbortSignal) {
  return relationSchema.parse(await request(`${socialRoot}/relations/${followedId}`, { ...(signal ? { signal } : {}) }))
}
export async function getOperation(request: AuthRequest, id: string, follower: string, followed: string, signal?: AbortSignal) {
  const job = followJobSchema.parse(await request(`${socialRoot}/operations/${id}`, { ...(signal ? { signal } : {}) }))
  if (job.operation_id !== id || job.follower_id !== follower || job.followed_id !== followed) throw new Error('La operación no corresponde a este seguimiento.')
  return job
}
export async function sendFollow(request: AuthRequest, action: FollowAction, follower: string, followed: string, key: string) {
  const job = followJobSchema.parse(await request(`${socialRoot}/follows${action === 'approve' ? '/approve' : ''}`, {
    method: action === 'unfollow' ? 'DELETE' : 'POST', headers: { 'Idempotency-Key': key },
    body: JSON.stringify({ user_id: follower, followed_user_id: followed }),
  }))
  if (job.follower_id !== follower || job.followed_id !== followed || job.action !== action) throw new Error('La respuesta no corresponde al cambio solicitado.')
  return job
}
