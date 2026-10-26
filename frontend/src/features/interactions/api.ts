import type { AuthRequest } from '../auth/api'
import {
  commentPayloadSchema,
  interactionOperationSchema,
  reactionPayloadSchema,
  reactionRemoveSchema,
  type CommentPayload,
  type InteractionOperation,
  type ReactionPayload,
  type ReactionRemovePayload,
} from './contracts'
import { postSchema, type Post } from '../posts/contracts'

export async function sendReaction(
  request: AuthRequest,
  payload: ReactionPayload,
  signal?: AbortSignal,
): Promise<InteractionOperation> {
  const valid = reactionPayloadSchema.parse(payload)
  const data = await request('/api/v1/problems/5/reaction', {
    method: 'POST',
    body: JSON.stringify(valid),
    ...(signal ? { signal } : {}),
  })
  return interactionOperationSchema.parse(data)
}

export async function removeReaction(
  request: AuthRequest,
  payload: ReactionRemovePayload,
  signal?: AbortSignal,
): Promise<InteractionOperation> {
  const valid = reactionRemoveSchema.parse(payload)
  const data = await request('/api/v1/problems/5/reaction', {
    method: 'DELETE',
    body: JSON.stringify(valid),
    ...(signal ? { signal } : {}),
  })
  return interactionOperationSchema.parse(data)
}

export async function sendComment(
  request: AuthRequest,
  payload: CommentPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<InteractionOperation> {
  const valid = commentPayloadSchema.parse(payload)
  const data = await request('/api/v1/problems/5/comment', {
    method: 'POST',
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify(valid),
    ...(signal ? { signal } : {}),
  })
  return interactionOperationSchema.parse(data)
}

export async function refreshPostCounters(
  request: AuthRequest,
  postId: string,
  signal?: AbortSignal,
): Promise<Post> {
  const data = await request(`/api/v1/posts/${postId}`, {
    ...(signal ? { signal } : {}),
  })
  return postSchema.parse(data)
}
