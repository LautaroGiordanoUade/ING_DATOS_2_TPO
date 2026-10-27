import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { getUserProfile } from '../recommendations/api'
import { useFollowAttempts } from './attempts'
import { socialRoot } from './api'
import { FollowControl } from './FollowControl'

function RequestCard({ userId }: { userId: string }) {
  const { user, request } = useAuth()
  const profile = useQuery({ queryKey: ['users', 'profile', userId],
    queryFn: ({ signal }) => getUserProfile(request, userId, signal), retry: false, networkMode: 'always' })
  if (profile.isPending) return <li className="card request-card" role="status">Cargando solicitante…</li>
  if (profile.isError) return <li className="card request-card"><p role="status">No pudimos cargar una cuenta solicitante.</p><button className="button-secondary" onClick={() => void profile.refetch()}>Reintentar cuenta</button></li>
  return <li className="card request-card" aria-label={`Solicitud de ${profile.data.full_name}`}>
    <div><h2><Link to={`/perfiles/${userId}`}>{profile.data.full_name}</Link></h2><p>@{profile.data.username}</p></div>
    <FollowControl key={`${user!.id}:${userId}`} followerId={userId} followedId={user!.id} approval />
  </li>
}

export function RequestsPage() {
  const { user, request } = useAuth()
  const attempts = useFollowAttempts(user!.id)
  const incoming = useQuery({ queryKey: ['social', 'requests', user!.id],
    queryFn: async ({ signal }) => z.array(z.uuid()).parse(await request(`${socialRoot}/requests`, { signal })),
    retry: false, networkMode: 'always', refetchInterval: () => document.visibilityState === 'visible' ? 5000 : false })
  const tracked = attempts.filter((item) => item.action === 'approve' && item.followed_id === user!.id && !['completed', 'compensated'].includes(item.status ?? '')).map((item) => item.follower_id)
  const ids = [...new Set([...(incoming.data ?? []), ...tracked])]
  return <div className="page-content requests-page">
    <header className="page-title title-actions"><div><p className="eyebrow">TU COMUNIDAD</p><h1>Solicitudes recibidas</h1><p className="muted">Revisá quién quiere seguir tu cuenta.</p></div>
      <button className="button-secondary" disabled={incoming.isFetching} onClick={() => void incoming.refetch()}>Actualizar solicitudes</button></header>
    {incoming.isPending && <p role="status">Cargando solicitudes…</p>}
    {incoming.isError && <div role="alert">{incoming.error.message} <button className="button-secondary" onClick={() => void incoming.refetch()}>Reintentar solicitudes</button></div>}
    {!incoming.isPending && !incoming.isError && !ids.length && <section className="card empty-state"><h2>No tenés solicitudes pendientes.</h2><Link to={`/perfiles/${user!.id}`}>Ver mi perfil</Link></section>}
    <ul className="request-list">{ids.map((id) => <RequestCard key={id} userId={id} />)}</ul>
  </div>
}
