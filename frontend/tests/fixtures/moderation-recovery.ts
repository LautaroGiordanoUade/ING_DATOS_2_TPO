import { user } from './session'
import type { Report, ModerationContent, ModerationJob } from '../../src/features/moderation/api'

export const moderator = { ...user, role: 'moderator' as const }
export const report: Report = { id: '71000000-0000-4000-8000-000000000001', post_id: '72000000-0000-4000-8000-000000000002',
  reporter_id: user.id, reason: 'spam', description: 'Revisar este contenido', resolution_status: 'pending',
  reported_at: '2026-10-27T12:00:00Z', moderator_id: null, resolved_at: null, decision: null,
  decision_reason: null, operation_id: null, resolution_operation_id: null, resolution_report_id: null }
export const content: ModerationContent = { id: report.post_id, user_id: user.id, text: 'Contenido para revisión',
  media: [], interests: ['datos'], published_at: '2026-10-27T11:00:00Z', visibility: 'public',
  moderation_status: 'approved', moderation_owner: null, active_operation_id: null, report_operation_id: null }
export const job: ModerationJob = { operation_id: '73000000-0000-4000-8000-000000000003', post_id: report.post_id,
  report_id: report.id, moderator_id: moderator.id, action: 'hide', reason: 'Spam confirmado', status: 'pending', error: null }
