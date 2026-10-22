import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { actions, isTerminal, jobLabels, jobSchema } from './contracts'
import { moderationError } from './errors'

export function ModerationOperationPage() {
  const { operationId = '' } = useParams()
  const { request, user } = useAuth()
  const valid = z.guid().safeParse(operationId).success
  const client = useQueryClient()
  const job = useQuery({
    queryKey: ['moderation-operation', user!.id, operationId], enabled: valid,
    queryFn: async ({ signal }) => jobSchema.parse(await request(`/api/v1/moderation/operations/${operationId}`, { signal })),
    refetchInterval: (query) => query.state.error || (query.state.data && isTerminal(query.state.data.status)) ? false : 1000,
    networkMode: 'always', retry: false,
  })
  const status = job.data?.status
  const postId = job.data?.post_id
  useEffect(() => {
    if (status === 'completed' || status === 'compensated') {
      void client.resetQueries({ queryKey: ['feed'] })
      void client.invalidateQueries({ queryKey: ['posts'] })
      void client.invalidateQueries({ queryKey: ['moderation'] })
      void client.invalidateQueries({ queryKey: ['publication-preview'] })
    }
  }, [status, postId, client])
  if (!valid) return <div className="page-content"><ErrorMessage message="El identificador de operación no es válido." /></div>
  return <div className="page-content moderation-page">
    <Link className="back-link" to="/moderacion">← Volver a moderación</Link>
    <div className="page-title"><p className="eyebrow">UNA DECISIÓN CON SEGUIMIENTO</p><h1>Estado de moderación</h1></div>
    <section className="card moderation-card" aria-live="polite">
      {job.isPending && <p role="status">Consultando operación…</p>}
      {job.isError && <><ErrorMessage message={moderationError(job.error)} /><button className="button-secondary" onClick={() => void job.refetch()}>Volver a consultar</button></>}
      {job.data && !job.isError && <>
        <span className={`status-badge ${status === 'completed' ? 'is-ready' : ''}`} role="status">{jobLabels[job.data.status]}</span><h2>{actions[job.data.action]}</h2><p className="reported-text">{job.data.reason}</p>
        <p className="muted">{status === 'completed' ? 'El servidor confirmó la decisión. El reporte y su historial ya están actualizados.' : status === 'compensated' ? 'La decisión no se aplicó: el servidor restauró el estado previo. El equipo administrador puede revisar la operación.' : status === 'failed' ? 'No se pudo confirmar la decisión. Requiere revisión del equipo administrador; no se asume que el contenido haya cambiado.' : 'Solicitud recibida. Esperando que el servidor confirme el resultado; podés volver a este enlace más tarde.'}</p>
        {job.data.error && <ErrorMessage message={job.data.error} />}
        <Link className="button-secondary" to={`/reportes/${job.data.report_id}`}>Consultar reporte</Link>
        <details className="moderation-identifiers"><summary>Referencia de la operación</summary><code>{operationId}</code></details>
      </>}
    </section>
  </div>
}
