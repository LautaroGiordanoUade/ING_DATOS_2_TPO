import { useCallback, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { isMediaUrl } from '../posts/contracts'
import { canModerate, contentSchema, denied, historySchema, queryRoot, reasonLabels, reportLabels, reportSchema, root, actionLabels } from './api'
import { ModerationDenied } from './RequireModerator'
import { DecisionPanel } from './DecisionPanel'
import { Person } from './Person'
import { moderationError } from './errors'

export function ReportDetailPage() {
  const { reportId: rawReportId = '' } = useParams()
  const reportId = rawReportId.toLowerCase()
  const { user, request } = useAuth()
  const client = useQueryClient()
  const moderator = canModerate(user!.role)
  const prefix = queryRoot(user!.id, user!.role)
  const valid = z.guid().safeParse(reportId).success
  const [operationDenied, setOperationDenied] = useState(false)
  const onForbidden = useCallback(() => setOperationDenied(true), [])
  const report = useQuery({ queryKey: [...prefix, 'report', reportId], enabled: valid,
    queryFn: async ({ signal }) => {
      const data = reportSchema.parse(await request(`${root}/reports/${reportId}`, { signal }))
      if (data.id !== reportId) throw new Error('La respuesta no corresponde a este reporte.')
      return data
    }, retry: false, networkMode: 'always', refetchInterval: () => document.visibilityState === 'visible' ? 5000 : false })
  const postId = report.data?.post_id
  const content = useQuery({ queryKey: [...prefix, 'content', postId, reportId], enabled: moderator && !!postId && !report.isError,
    queryFn: async ({ signal }) => {
      const data = contentSchema.parse(await request(`${root}/posts/${postId}/content?report_id=${reportId}`, { signal }))
      if (data.id !== postId) throw new Error('El contenido no corresponde a este reporte.')
      return data
    }, retry: false, networkMode: 'always', refetchInterval: () => document.visibilityState === 'visible' ? 4000 : false })
  const history = useQuery({ queryKey: [...prefix, 'history', postId], enabled: moderator && !!postId && !report.isError,
    queryFn: async ({ signal }) => historySchema.parse(await request(`${root}/history/${postId}`, { signal })), retry: false, networkMode: 'always' })
  const forbidden = denied(report.error) || moderator && (denied(content.error) || denied(history.error) || operationDenied)
  useEffect(() => { if (forbidden && moderator) void client.invalidateQueries({ queryKey: ['auth', 'me'] }) }, [forbidden, moderator, client])
  if (!valid) return <div className="page-content"><h1>Reporte no válido</h1><Link to="/">Volver al inicio</Link></div>
  if (forbidden) return <ModerationDenied />
  if (report.isPending) return <p className="page-content" role="status">Cargando reporte…</p>
  if (report.isError) return <section className="page-content"><h1>No pudimos consultar el reporte</h1><p role="alert">{moderationError(report.error)}</p><button className="button-secondary" onClick={() => void report.refetch()}>Reintentar reporte</button></section>
  const data = report.data
  return <div className="page-content moderation-page">
    <Link className="back-link" to={moderator ? '/moderacion' : '/'}>← {moderator ? 'Volver a moderación' : 'Volver al feed'}</Link>
    <header className="page-title"><p className="eyebrow">{moderator ? 'REVISIÓN DE CONTENIDO' : 'MI REPORTE'}</p><h1>Detalle del reporte</h1></header>
    <section className="card report-detail"><span className="pill">{reportLabels[data.resolution_status]}</span><h2>{reasonLabels[data.reason]}</h2>
      <p>Reportado por <Person id={data.reporter_id} /></p><time dateTime={data.reported_at}>{new Date(data.reported_at).toLocaleString('es-AR')}</time>
      {data.description && <p className="moderation-text">{data.description}</p>}
      {data.decision_reason && <p>Motivo de resolución: {data.decision_reason}</p>}
      {!moderator && data.resolution_status === 'pending' && <p>Tu reporte fue recibido y está pendiente de revisión.</p>}
      <button className="button-secondary" onClick={() => void report.refetch()} disabled={report.isFetching}>Actualizar reporte</button>
    </section>
    {moderator && <>
      {content.isPending && <p role="status">Cargando publicación para revisión…</p>}
      {content.isError && <div role="alert">No pudimos cargar el contenido.<button className="button-secondary" onClick={() => void content.refetch()}>Reintentar contenido</button></div>}
      {content.data && !content.isError && <section className="card moderation-content" aria-label="Publicación en revisión">
        <h2>Publicación en revisión</h2><p>Autor: <Person id={content.data.user_id} /></p><p>Estado de moderación: {content.data.moderation_status === 'hidden' ? 'Oculta' : content.data.moderation_status === 'approved' ? 'Aprobada' : content.data.moderation_status === 'pending' ? 'Pendiente de revisión' : content.data.moderation_status}</p>
        <p className="moderation-text">{content.data.text}</p>
        {content.data.media.filter(isMediaUrl).map((url, index) => <img key={`${index}:${url}`} src={url} className="post-image" alt={`Imagen ${index + 1} en revisión`} referrerPolicy="no-referrer" />)}
        <DecisionPanel key={`${user!.id}:${reportId}`} report={data} content={content.data} onForbidden={onForbidden} />
      </section>}
      <section className="card moderation-history"><h2>Historial de la publicación</h2>
        {history.isPending && <p role="status">Cargando historial…</p>}
        {history.isError && <div role="alert">No pudimos cargar el historial.<button className="button-secondary" onClick={() => void history.refetch()}>Reintentar historial</button></div>}
        {history.data?.length === 0 && <p>Todavía no hay decisiones registradas.</p>}
        {!history.isError && <ol>{history.data?.map((event) => <li key={event.operation_id}><strong>{actionLabels[event.action]}</strong><p>{event.reason}</p>
          <p>{event.affected_report_count === undefined ? 'Cantidad de reportes no registrada en esta decisión anterior.' : event.affected_report_count === 1 ? '1 reporte afectado' : `${event.affected_report_count} reportes afectados`}</p>
          <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString('es-AR')}</time>
        </li>)}</ol>}
      </section>
    </>}
  </div>
}
