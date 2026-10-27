import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { PostCard } from '../posts/PostCard'
import { postSchema } from '../posts/contracts'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { ApiError } from '../../services/http/client'
import { actions, canModerate, historySchema, reasons, reportSchema, resolutions } from './contracts'
import { moderationError } from './errors'
import { DecisionForm } from './DecisionForm'

export function ReportDetailPage() {
  const { reportId = '' } = useParams()
  const { user, request } = useAuth()
  const moderator = canModerate(user?.role)
  const valid = z.guid().safeParse(reportId).success
  const report = useQuery({
    queryKey: ['moderation', user!.id, 'report', reportId], enabled: valid,
    queryFn: async ({ signal }) => reportSchema.parse(await request(`/api/v1/moderation/reports/${reportId}`, { signal })),
    networkMode: 'always', retry: false,
    refetchInterval: (query) => query.state.error || query.state.data?.resolution_status !== 'pending' ? false : 5000,
  })
  const postId = report.data?.post_id
  const history = useQuery({
    queryKey: ['moderation', user!.id, 'history', postId], enabled: moderator && !!postId && !report.isError,
    queryFn: async ({ signal }) => historySchema.parse(await request(`/api/v1/moderation/history/${postId}`, { signal })),
    networkMode: 'always', retry: false,
  })
  const post = useQuery({
    queryKey: ['posts', 'detail', postId], enabled: moderator && !!postId && !report.isError,
    queryFn: async ({ signal }) => postSchema.parse(await request(`/api/v1/posts/${postId}`, { signal })),
    networkMode: 'always', retry: false,
  })
  if (!valid) return <div className="page-content"><ErrorMessage message="El identificador de reporte no es válido." /></div>
  return <div className="page-content moderation-page">
    <Link className="back-link" to={moderator ? '/moderacion' : '/'}>← {moderator ? 'Volver a moderación' : 'Volver al feed'}</Link>
    <div className="page-title title-actions"><div><p className="eyebrow">SEGUIMIENTO DEL REPORTE</p><h1>Detalle del reporte</h1></div><button className="button-secondary" disabled={report.isFetching} onClick={() => { void report.refetch(); if (moderator && postId && !report.isError) { void history.refetch(); void post.refetch() } }}>Actualizar reporte</button></div>
    {report.isPending && <p role="status">Consultando reporte…</p>}
    {report.isError && <ErrorMessage message={moderationError(report.error)} />}
    {report.data && !report.isError && <>
      <section className="card moderation-card"><span className="status-badge" role="status">{resolutions[report.data.resolution_status]}</span><h2>{reasons[report.data.reason as keyof typeof reasons] || report.data.reason}</h2><p className="reported-text">{report.data.description || 'Sin descripción adicional.'}</p><p className="muted">Reportado el {new Date(report.data.reported_at).toLocaleString('es-AR')}</p>
        {!moderator && <p className="field-hint">Tu reporte quedó registrado. Guardá este enlace para consultar su resolución.</p>}
        {report.data.decision_reason && <div className="resolution-note"><h3>Motivo de la resolución</h3><p>{report.data.decision_reason}</p></div>}
        <details className="moderation-identifiers"><summary>Referencia del reporte</summary><dl><dt>Reporte</dt><dd><code>{reportId}</code></dd><dt>Publicación</dt><dd><code>{postId}</code></dd></dl></details>
        {moderator && report.data.operation_id && <Link to={`/moderacion/operaciones/${report.data.operation_id}`}>Ver operación de moderación</Link>}
      </section>
      {moderator && <>
        {post.isPending && <p role="status">Consultando publicación…</p>}
        {post.isError && (post.error instanceof ApiError && post.error.status === 404 ? <p className="card moderation-card" role="status">La publicación no está disponible en la lectura pública. Puede estar oculta o retirada.</p> : <ErrorMessage message={post.error.message} />)}
        {post.data && !post.isError && <PostCard post={post.data} author={`Cuenta ${post.data.user_id.slice(0, 8)}`} />}
        {['pending', 'approved'].includes(report.data.resolution_status) && <DecisionForm key={`${reportId}-${report.data.resolution_status}`} report={report.data} />}
        <section className="card moderation-card"><h2>Historial de la publicación</h2>{history.isPending && <p role="status">Cargando historial…</p>}{history.isError && <><ErrorMessage message={moderationError(history.error)} /><button className="button-secondary" onClick={() => void history.refetch()}>Reintentar historial</button></>}{!history.isError && history.data?.length === 0 && <p className="muted">Todavía no hay decisiones confirmadas.</p>}<ol className="moderation-history">{!history.isError && history.data?.map((event) => <li key={event.operation_id}><strong>{actions[event.action]}</strong><p>{event.reason}</p><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString('es-AR')}</time><p className="muted">Responsable: <code>{event.moderator_id}</code></p></li>)}</ol></section>
      </>}
    </>}
  </div>
}
