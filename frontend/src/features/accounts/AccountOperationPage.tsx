import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { isTerminal } from '../moderation/contracts'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { accountActions, accountJobLabels, accountJobSchema } from './contracts'
import { accountError } from './errors'

export function AccountOperationPage() {
  const { operationId = '' } = useParams()
  const { request, user } = useAuth()
  const client = useQueryClient()
  const valid = z.guid().safeParse(operationId).success
  const job = useQuery({
    queryKey: ['account-operation', user!.id, operationId], enabled: valid,
    queryFn: async ({ signal }) => accountJobSchema.parse(await request(`/api/v1/accounts/operations/${operationId}`, { signal })),
    refetchInterval: (query) => query.state.error || (query.state.data && isTerminal(query.state.data.status)) ? false : 1000,
    retry: false, networkMode: 'always',
  })
  const status = job.data?.status
  const target = job.data?.user_id
  useEffect(() => {
    if (status === 'completed' || status === 'compensated') {
      void client.resetQueries({ queryKey: ['feed'] })
      for (const prefix of ['accounts', 'posts', 'users', 'publication-preview', 'moderation', 'recommendations']) void client.invalidateQueries({ queryKey: [prefix] })
    }
  }, [status, target, client])
  if (!valid) return <div className="page-content"><ErrorMessage message="El identificador de operación no es válido." /></div>
  return <div className="page-content accounts-page"><Link to="/cuentas" className="back-link">← Volver a cuentas</Link><div className="page-title"><p className="eyebrow">CAMBIO DE CUENTA CON SEGUIMIENTO</p><h1>Estado del cambio de cuenta</h1></div><section className="card account-card" aria-live="polite">
    {job.isPending && <p role="status">Consultando operación de cuenta…</p>}
    {job.isError && <><ErrorMessage message={accountError(job.error)} /><button className="button-secondary" onClick={() => void job.refetch()}>Volver a consultar</button></>}
    {job.data && !job.isError && <><span className={`status-badge ${status === 'completed' ? 'is-ready' : ''}`} role="status">{accountJobLabels[job.data.status]}</span><h2>{accountActions[job.data.action]}</h2><p className="reported-text">{job.data.reason}</p><p className="muted">{status === 'completed' ? job.data.action === 'suspend' ? 'Suspensión confirmada por el servidor. Se retiraron sus publicaciones, se excluyó la cuenta de sugerencias y se cerró su presencia.' : 'Reactivación confirmada. Las moderaciones previas se conservan; la persona debe iniciar sesión y renovar su presencia nuevamente.' : status === 'compensated' ? 'El cambio fue cancelado y se restauró el estado previo. Si la suspensión llegó a revocar credenciales, se requiere un nuevo inicio de sesión.' : status === 'failed' ? 'El cambio no pudo confirmarse y requiere revisión administrativa. No se informa como completado.' : 'Solicitud recibida. Esperando la confirmación del servidor; podés volver a este enlace más tarde.'}</p>{job.data.error && <ErrorMessage message={job.data.error} />}<Link className="button-secondary" to={`/cuentas/${job.data.user_id}`}>Consultar cuenta afectada</Link><details className="moderation-identifiers"><summary>Referencia de operación</summary><code>{operationId}</code></details></>}
  </section></div>
}
