import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { getUserProfile } from '../recommendations/api'
import { ApiError } from '../../services/http/client'
import { countsSchema, socialRoot } from './api'
import { FollowControl } from './FollowControl'

export function ProfilePage() {
  const { userId = '' } = useParams()
  const { user: viewer, request } = useAuth()
  const valid = z.uuid().safeParse(userId).success
  const profile = useQuery({ queryKey: ['users', 'profile', userId], enabled: valid,
    queryFn: ({ signal }) => getUserProfile(request, userId, signal), retry: false, staleTime: 0, networkMode: 'always' })
  const counts = useQuery({ queryKey: ['social', 'counts', viewer!.id, userId], enabled: valid && !!profile.data && !profile.isError,
    queryFn: async ({ signal }) => countsSchema.parse(await request(`${socialRoot}/counts/${userId}`, { signal })), retry: false, networkMode: 'always',
    refetchInterval: () => document.visibilityState === 'visible' ? 5000 : false,
  })
  if (!valid) return <div className="page-content"><h1>Perfil no válido</h1><Link to="/recomendaciones">Volver a sugerencias</Link></div>
  if (profile.isPending) return <div className="page-content" role="status">Cargando perfil…</div>
  if (profile.error instanceof ApiError && profile.error.status === 404) return <div className="page-content"><h1>Cuenta no disponible</h1><Link to="/recomendaciones">Volver a sugerencias</Link></div>
  if (profile.isError) return <div className="page-content"><h1>No pudimos cargar el perfil</h1><p role="alert">{profile.error.message}</p><button className="button-secondary" onClick={() => void profile.refetch()}>Reintentar perfil</button></div>
  const user = profile.data
  const own = user.id === viewer!.id
  return <div className="page-content profile-page">
    <Link className="back-link" to="/recomendaciones">← Sugerencias</Link>
    <section className="card profile-card">
      <div className="profile-heading"><span className="avatar" aria-hidden="true">{Array.from(user.full_name)[0]?.toUpperCase()}</span>
        <div><p className="eyebrow">{own ? 'MI PERFIL' : 'TU COMUNIDAD'}</p><h1>{user.full_name}</h1><p>@{user.username}</p></div>
        <span className="pill">{user.account_type === 'private' ? 'Privada' : 'Pública'}</span></div>
      {user.biography && <p className="profile-bio">{user.biography}</p>}
      <ul className="interest-tags" aria-label="Intereses del perfil">{user.interests?.map((interest) => <li key={interest}>#{interest}</li>)}</ul>
      {counts.isPending && <p role="status">Consultando seguidores…</p>}
      {counts.isError && <div role="alert">No pudimos cargar los contadores. <button className="button-secondary" onClick={() => void counts.refetch()}>Reintentar contadores</button></div>}
      {counts.data && !counts.isError && <dl className="follow-counts"><div><dt>Seguidores</dt><dd>{counts.data.followers}</dd></div><div><dt>Seguidos</dt><dd>{counts.data.following}</dd></div></dl>}
      {own ? <div className="profile-links"><Link className="button-secondary" to="/solicitudes">Solicitudes recibidas</Link><Link className="button-secondary" to="/mis-publicaciones">Mis publicaciones</Link><Link className="button-secondary" to="/recomendaciones">Editar intereses</Link></div>
        : <FollowControl key={`${viewer!.id}:${user.id}`} followerId={viewer!.id} followedId={user.id} accountType={user.account_type} />}
    </section>
  </div>
}
