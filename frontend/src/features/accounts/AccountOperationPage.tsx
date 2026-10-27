import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { isTerminal } from '../moderation/contracts'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { accountActions, accountJobLabels, accountJobSchema } from './contracts'
import { accountError } from './errors'
import { denied } from '../moderation/api'
import { ModerationDenied } from '../moderation/RequireModerator'

export function AccountOperationPage() {
  const { operationId = '' } = useParams()
  const { request, user } = useAuth()
  const client = useQueryClient()
  const valid = z.guid().safeParse(operationId).success
  const job = useQuery({
    queryKey: ['account-operation', user!.id, user!.role, operationId], enabled: valid,
    queryFn: async ({ signal }) => {
      const data = accountJobSchema.parse(await request(`/api/v1/accounts/operations/${operationId}`, { signal }))
      if (data.operation_id !== operationId) throw new Error('La operación recibida no corresponde a esta consulta.')
      return data
    },
    refetchInterval: (query) => query.state.error || (query.state.data && isTerminal(query.state.data.status)) ? false : 1000,
    retry: false, networkMode: 'always',
  })
  const retry = useMutation({ mutationFn: async () => {
    const data = accountJobSchema.parse(await request(`/api/v1/accounts/operations/${operationId}/retry`, { method: 'POST' }))
    if (data.operation_id !== operationId || data.user_id !== job.data?.user_id || data.action !== job.data.action) throw new Error('La recuperación no corresponde a esta cuenta.')
    return data
  }, retry: false, onSuccess: (data) => client.setQueryData(['account-operation', user!.id, user!.role, operationId], data),
    onError: () => { void job.refetch() } })
  const forbidden = denied(job.error) || denied(retry.error)
  useEffect(() => { if (forbidden) void client.invalidateQueries({ queryKey: ['auth', 'me'] }) }, [forbidden, client])
  const status = job.data?.status
  const target = job.data?.user_id
  useEffect(() => {
    if (status === 'completed' || status === 'compensated') {
      void client.resetQueries({ queryKey: ['feed'] })
      for (const prefix of ['accounts', 'posts', 'users', 'publication-preview', 'moderation', 'recommendations']) void client.invalidateQueries({ queryKey: [prefix] })
    }
  }, [status, target, client])
  if (!valid) return <div className="page-content"><ErrorMessage message="El identificador de operación no es válido." /></div>
  if (forbidden) return <ModerationDenied />
  return <div className="page-content accounts-page"><Link to="/cuentas" className="back-link">← Volver a cuentas</Link><div className="page-title"><p className="eyebrow">CAMBIO DE CUENTA CON SEGUIMIENTO</p><h1>Estado del cambio de cuenta</h1></div><section className="card account-card" aria-live="polite">
    {job.isPending && <p role="status">Consultando operación de cuenta…</p>}
    {job.isError && <><ErrorMessage message={accountError(job.error)} /><button className="button-secondary" onClick={() => void job.refetch()}>Volver a consultar</button></>}
    {job.data && !job.isError && <><span className={`status-badge ${status === 'completed' ? 'is-ready' : ''}`} role="status">{accountJobLabels[job.data.status]}</span><h2>{accountActions[job.data.action]}</h2><p className="reported-text">{job.data.reason}</p><p className="muted">{status === 'completed' ? job.data.action === 'suspend' ? 'Suspensión confirmada por el servidor. Se retiraron sus publicaciones, se excluyó la cuenta de sugerencias y se cerró su presencia.' : 'Reactivación confirmada. Las moderaciones previas se conservan; la persona debe iniciar sesión y renovar su presencia nuevamente.' : status === 'compensated' ? 'El cambio fue cancelado y se restauró el estado previo. Si la suspensión llegó a revocar credenciales, se requiere un nuevo inicio de sesión.' : status === 'failed' ? 'El cambio no pudo confirmarse y requiere revisión administrativa. No se informa como completado.' : 'Solicitud recibida. Esperando la confirmación del servidor; podés volver a este enlace más tarde.'}</p>{job.data.error && <ErrorMessage message={job.data.error} />}<Link className="button-secondary" to={`/cuentas/${job.data.user_id}`}>Consultar cuenta afectada</Link><details className="moderation-identifiers"><summary>Referencia de operación</summary><code>{operationId}</code></details></>}
    {job.data && !job.isError && status === 'failed' && <button className="button-secondary" disabled={retry.isPending} onClick={() => retry.mutate()}>{retry.isPending ? 'Solicitando recuperación…' : 'Reintentar recuperación'}</button>}
    {job.data && !job.isError && status === 'compensated' && <p className="field-hint">La compensación terminó. Para intentar el cambio nuevamente, consultá la cuenta y confirmá una nueva solicitud.</p>}
    {retry.isError && <ErrorMessage message={accountError(retry.error)} />}
  </section></div>
}
