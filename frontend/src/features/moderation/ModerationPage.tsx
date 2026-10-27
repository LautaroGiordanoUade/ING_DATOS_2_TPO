import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { reasons, reportSchema, resolutions } from './contracts'
import { moderationError } from './errors'
import { denied } from './api'
import { ModerationDenied } from './RequireModerator'

export function ModerationPage() {
  const { request, user } = useAuth()
  const client = useQueryClient()
  const [status, setStatus] = useState('pending')
  const reports = useQuery({
    queryKey: ['moderation', user!.id, user!.role, 'reports', status],
    queryFn: async ({ signal }) => z.array(reportSchema).parse(await request(`/api/v1/moderation/reports${status ? `?status=${status}` : ''}`, { signal })),
    networkMode: 'always', retry: false,
    refetchInterval: () => document.visibilityState === 'visible' ? 5000 : false,
  })
  const forbidden = denied(reports.error)
  useEffect(() => { if (forbidden) void client.invalidateQueries({ queryKey: ['auth', 'me'] }) }, [forbidden, client])
  if (forbidden) return <ModerationDenied />
  return <div className="page-content moderation-page">
    <div className="page-title"><p className="eyebrow">CUIDAR LO QUE COMPARTIMOS</p><h1>Moderación</h1><p className="muted">Revisá los reportes de la comunidad y dejá constancia de cada decisión.</p></div>
    <div className="card moderation-toolbar"><div><label htmlFor="report-filter">Estado de los reportes</label><select id="report-filter" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Todos</option>{Object.entries(resolutions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div><button className="button-secondary" disabled={reports.isFetching} onClick={() => void reports.refetch()}>Actualizar reportes</button></div>
    {reports.isPending && <p role="status">Cargando reportes…</p>}
    {reports.isError && <ErrorMessage message={moderationError(reports.error)} />}
    {!reports.isError && reports.data?.length === 0 && <section className="card empty-state"><h2>No hay reportes para este estado.</h2><p>Podés elegir otro filtro o volver a actualizar.</p></section>}
    {!reports.isError && reports.data?.map((report) => <article key={report.id} className="card report-row"><div><span className="status-badge">{resolutions[report.resolution_status]}</span><h2>{reasons[report.reason as keyof typeof reasons] || report.reason}</h2><p className="muted">{new Date(report.reported_at).toLocaleString('es-AR')}</p><p className="report-excerpt">{report.description || 'Sin descripción adicional.'}</p></div><Link className="button-secondary" to={`/reportes/${report.id}`}>Revisar reporte</Link></article>)}
    <p className="preparation-note">Hasta 100 reportes por filtro, del más reciente al más antiguo.</p>
  </div>
}
