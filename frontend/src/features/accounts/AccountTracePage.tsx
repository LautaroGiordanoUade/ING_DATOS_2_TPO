import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { canModerate } from '../moderation/contracts'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { accountActions, accountStatus, traceSchema, userIdSchema } from './contracts'
import { accountError } from './errors'
import { AccountDecisionForm } from './AccountDecisionForm'
import { TraceSections } from './TraceSections'

export function AccountTracePage() {
  const { userId: rawId = '' } = useParams()
  const { request, user } = useAuth()
  const parsed = userIdSchema.safeParse(rawId)
  const userId = parsed.success ? parsed.data : ''
  const moderator = canModerate(user?.role)
  const owner = userId === user!.id
  const allowed = moderator || owner
  const trace = useQuery({
    queryKey: ['accounts', user!.id, 'trace', userId], enabled: parsed.success && allowed,
    queryFn: async ({ signal }) => {
      const result = traceSchema.parse(await request(`/api/v1/accounts/${userId}/trace`, { signal }))
      if (result.user_id !== userId) throw new Error('La información recibida pertenece a otra cuenta.')
      return result
    }, retry: false, networkMode: 'always', staleTime: 0, refetchOnWindowFocus: true,
  })
  const presence = useMutation({
    mutationFn: () => request('/api/v1/accounts/me/presence', { method: 'PUT' }), retry: false,
    onSuccess: () => { void trace.refetch() },
  })
  if (!parsed.success) return <div className="page-content"><ErrorMessage message="El identificador de usuario no es válido." /><Link to="/cuentas">Volver a cuentas</Link></div>
  if (!allowed) return <section className="page-content"><h1>Trazabilidad privada</h1><p>Solo podés consultar tu propia cuenta. El acceso a otras cuentas requiere un rol de moderación.</p><Link to={`/cuentas/${user!.id}`}>Consultar mi cuenta</Link></section>
  const data = !trace.isError ? trace.data : undefined
  return <div className="page-content accounts-page">
    <Link to="/cuentas" className="back-link">← Volver a cuentas</Link>
    <div className="page-title title-actions"><div><p className="eyebrow">UNA CUENTA, UNA CONSULTA</p><h1>Trazabilidad de cuenta</h1></div><button className="button-secondary" disabled={trace.isFetching} onClick={() => void trace.refetch()}>Actualizar cuenta</button></div>
    {trace.isPending && <p role="status">Consultando trazabilidad completa…</p>}
    {trace.isError && <ErrorMessage message={accountError(trace.error)} />}
    {data && <>
      <section className="card account-card"><h2>{data.profile?.full_name || 'Perfil no disponible'}</h2>{data.profile && <><p className="muted">@{data.profile.username}</p><span className="status-badge" role="status">{accountStatus[data.profile.account_status]}</span>{data.profile.biography && <p>{data.profile.biography}</p>}<p className="muted">Cuenta {data.profile.account_type === 'private' ? 'privada' : 'pública'} · Registrada el {new Date(data.profile.registered_at).toLocaleDateString('es-AR')}</p></>}<details className="moderation-identifiers"><summary>Identificador de usuario</summary><code>{userId}</code></details></section>
      <section className="card account-card"><h2>Presencia en mensajería</h2><p role="status">{data.presence ? 'En línea' : 'Sin presencia activa'}</p><p className="muted">La presencia vence después de 120 segundos sin renovarla. Reactivar una cuenta no abre su presencia por sí solo.</p>{owner && data.profile?.account_status === 'active' && <button className="button-secondary" disabled={presence.isPending} onClick={() => presence.mutate()}>Renovar mi presencia</button>}{presence.isError && <ErrorMessage message={accountError(presence.error)} />}</section>
      {moderator && !owner && data.profile && <AccountDecisionForm key={`${userId}-${data.profile.account_status}`} userId={userId} status={data.profile.account_status} />}
      {moderator && owner && <p className="field-hint">No podés suspender ni reactivar tu propia cuenta.</p>}
      <TraceSections key={userId} trace={data} moderator={moderator} />
      <section className="card account-card"><h2>Historial de la cuenta</h2>{data.account_history.length === 0 ? <p className="muted">No hay cambios de cuenta confirmados.</p> : <ol className="moderation-history">{data.account_history.map((event) => <li key={event.operation_id}><strong>{accountActions[event.action]}</strong><p>{event.reason}</p><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString('es-AR')}</time><p className="muted">Estado resultante: {accountStatus[event.new_status]} · Publicaciones procesadas: {event.posts_count}</p><details><summary>Responsable</summary><code>{event.actor_id}</code></details>{moderator && <Link className="report-link" to={`/cuentas/operaciones/${event.operation_id}`}>Consultar operación</Link>}</li>)}</ol>}<p className="field-hint">Hasta 100 eventos devueltos por el servidor.</p></section>
    </>}
  </div>
}
