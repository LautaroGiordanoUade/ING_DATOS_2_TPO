import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { denied, queryRoot, reasonLabels, reportLabels, reportSchema, root } from './api'
import { ModerationDenied } from './RequireModerator'
import { Person } from './Person'
import { useDecisionAttempts } from './attempts'

export function ModerationPage() {
  const { user, request } = useAuth()
  const client = useQueryClient()
  const [status, setStatus] = useState('pending')
  const attempts = useDecisionAttempts(user!.id)
  const reports = useQuery({ queryKey: [...queryRoot(user!.id, user!.role), 'reports', status],
    queryFn: async ({ signal }) => z.array(reportSchema).parse(await request(`${root}/reports${status ? `?status=${status}` : ''}`, { signal })),
    retry: false, networkMode: 'always', refetchInterval: () => document.visibilityState === 'visible' ? 5000 : false })
  const forbidden = denied(reports.error)
  useEffect(() => { if (forbidden) void client.invalidateQueries({ queryKey: ['auth', 'me'] }) }, [forbidden, client])
  if (forbidden) return <ModerationDenied />
  return <div className="page-content moderation-page">
    <header className="page-title"><p className="eyebrow">REVISIÓN DE CONTENIDO</p><h1>Moderación</h1><p className="muted">Hasta 100 reportes por consulta, ordenados del más reciente al más antiguo.</p></header>
    <div className="moderation-toolbar"><label>Estado de los reportes<select value={status} onChange={(e) => setStatus(e.target.value)}>
      <option value="">Todos</option>{Object.entries(reportLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
    </select></label><button className="button-secondary" disabled={reports.isFetching} onClick={() => void reports.refetch()}>Actualizar reportes</button></div>
    {reports.isPending && <p role="status">Cargando reportes…</p>}
    {reports.isError && <div role="alert">No pudimos cargar los reportes.<button className="button-secondary" onClick={() => void reports.refetch()}>Reintentar reportes</button></div>}
    {!reports.isPending && !reports.isError && !reports.data.length && <section className="card empty-state"><h2>No hay reportes en este estado.</h2></section>}
    {!reports.isError && <ul className="moderation-report-list">{reports.data?.map((report) => <li className="card moderation-report" key={report.id}>
      <div><span className="pill">{reportLabels[report.resolution_status]}</span><h2>Reporte por {reasonLabels[report.reason].toLowerCase()}</h2>
        <p>Reportado por <Person id={report.reporter_id} /></p><time dateTime={report.reported_at}>{new Date(report.reported_at).toLocaleString('es-AR')}</time>
        {attempts.some((a) => a.post_id === report.post_id && !['completed', 'compensated'].includes(a.status ?? '')) && <p className="muted">Hay una decisión pendiente de confirmación.</p>}</div>
      <Link className="button-secondary" to={`/reportes/${report.id}`}>Revisar reporte</Link>
    </li>)}</ul>}
  </div>
}
