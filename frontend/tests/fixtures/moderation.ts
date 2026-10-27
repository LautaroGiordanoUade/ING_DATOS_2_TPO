import { operationId, postId, user } from './session'

export const reportId = '55000000-0000-4000-8000-000000000001'
export const moderator = { ...user, role: 'moderator' as const }
export const report = {
  id: reportId, post_id: postId, reporter_id: user.id, reason: 'spam', description: 'Contenido repetido',
  resolution_status: 'pending' as const, reported_at: '2026-10-21T12:00:00Z', moderator_id: null,
  resolved_at: null, decision: null, decision_reason: null, operation_id: null,
}
export const moderationJob = {
  operation_id: operationId, post_id: postId, report_id: reportId, moderator_id: user.id,
  action: 'hide', reason: 'Spam confirmado', status: 'pending', completed_steps: [], error: null,
  updated_at: '2026-10-21T12:00:00Z',
}
export const reportedPost = {
  id: postId, user_id: '66000000-0000-4000-8000-000000000001', text: 'Publicación denunciada',
  media: [], interests: ['datos'], published_at: '2026-10-21T12:00:00Z', reaction_count: 2, comment_count: 1,
}
