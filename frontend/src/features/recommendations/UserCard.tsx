import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../auth/context'
import { getUserProfile } from './api'
import { ApiError } from '../../services/http/client'

interface UserCardProps {
  userId: string
  onSelectMutual?: (userId: string) => void
}

export function UserCard({ userId, onSelectMutual }: UserCardProps) {
  const { request } = useAuth()
  const profile = useQuery({
    queryKey: ['users', 'profile', userId],
    queryFn: ({ signal }) => getUserProfile(request, userId, signal),
    staleTime: 5 * 60_000,
    networkMode: 'always',
  })

  if (profile.isPending) {
    return <div className="card user-card loading">Cargando perfil…</div>
  }

  if (profile.error instanceof ApiError && profile.error.status === 404) {
    return <div className="card user-card unavailable">Cuenta no disponible ({userId.slice(0, 8)})</div>
  }

  const user = profile.data
  const fullName = user?.full_name || `Cuenta ${userId.slice(0, 8)}`
  const initial = Array.from(fullName)[0]?.toUpperCase() ?? 'U'

  return (
    <article className="card user-card" aria-label={`Perfil de ${fullName}`}>
      <div className="author-line">
        <span className="avatar" aria-hidden="true">{initial}</span>
        <div>
          <strong>{fullName}</strong>
          {user?.username && <span>@{user.username}</span>}
        </div>
        <span className="pill">{user?.account_type === 'private' ? 'Privada' : 'Pública'}</span>
      </div>

      {user?.biography && <p className="user-bio">{user.biography}</p>}

      <div className="user-card-actions">
        {onSelectMutual && (
          <button
            type="button"
            className="button-secondary"
            onClick={() => onSelectMutual(userId)}
          >
            Ver amigos en común
          </button>
        )}
      </div>

      <details className="post-identifiers">
        <summary>Identificador de usuario</summary>
        <code>{userId}</code>
      </details>
    </article>
  )
}
