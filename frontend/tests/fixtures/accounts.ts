import { operationId, postId, user } from './session'

export const target = { ...user, id: '88000000-0000-4000-8000-000000000001', username: 'qa_target', full_name: 'Cuenta consultada' }
export const accountJob = {
  operation_id: operationId, user_id: target.id, actor_id: user.id, action: 'suspend' as const,
  reason: 'Revisión de cuenta', status: 'pending', completed_steps: [], error: null, updated_at: '2026-10-27T12:00:00Z',
}
export const trace = {
  user_id: target.id, profile: target, presence: true,
  relationships: { followers: [user.id], following: [], blocked: [], edges: [{ kind: 'FOLLOWS', outgoing: false, other_id: user.id, status: 'accepted' }] },
  recent_posts: [{ id: postId, user_id: target.id, text: 'Publicación de la cuenta', interests: ['datos'], media: [], published_at: '2026-10-27T12:00:00Z', reaction_count: 0, comment_count: 0 }],
  post_states: [{ id: postId, moderation_status: 'approved', suspension_hidden: false, publicly_visible: true }],
  active_conversations: [{ id: '99000000-0000-4000-8000-000000000001', participant_ids: [target.id, user.id], created_at: '2026-10-27T12:00:00Z' }],
  account_history: [],
}
