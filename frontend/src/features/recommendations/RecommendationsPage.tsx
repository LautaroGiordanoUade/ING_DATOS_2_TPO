import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../auth/context'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { getMutualFriends, getRecommendations } from './api'
import { mutualFriendsQuerySchema } from './contracts'
import { UserCard } from './UserCard'
import { InterestsEditor } from './InterestsEditor'

export function RecommendationsPage() {
  const { user, request } = useAuth()

  // Consulta de recomendaciones (P4)
  const recommendationsQuery = useQuery({
    queryKey: ['recommendations', user!.id],
    queryFn: ({ signal }) => getRecommendations(request, user!.id, signal),
    networkMode: 'always',
  })

  // Consulta manual de amigos en común
  const [targetUserId, setTargetUserId] = useState('')
  const [activeQueryTarget, setActiveQueryTarget] = useState<string | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)

  const mutualFriendsQuery = useQuery({
    queryKey: ['mutual-friends', user!.id, activeQueryTarget],
    queryFn: ({ signal }) => getMutualFriends(request, user!.id, activeQueryTarget!, signal),
    enabled: Boolean(activeQueryTarget),
    networkMode: 'always',
  })

  const handleSearchMutual = (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError(null)
    const cleaned = targetUserId.trim()
    if (!cleaned) {
      setValidationError('Ingresá el identificador (UUID) de un usuario.')
      return
    }
    if (cleaned.toLowerCase() === user!.id.toLowerCase()) {
      setValidationError('No podés consultar amigos en común con tu propia cuenta.')
      return
    }
    const parsed = mutualFriendsQuerySchema.safeParse({
      user_id: user!.id,
      other_user_id: cleaned,
    })
    if (!parsed.success) {
      setValidationError('Ingresá un identificador (UUID) de usuario válido.')
      return
    }
    setActiveQueryTarget(cleaned)
  }

  const handleSelectFromSuggestions = (selectedId: string) => {
    setValidationError(null)
    setTargetUserId(selectedId)
    setActiveQueryTarget(selectedId)
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
  }

  const suggestions = recommendationsQuery.data ?? []
  const mutualFriends = mutualFriendsQuery.data ?? []

  return (
    <div className="page-content publication-page recommendations-page">
      <div className="page-title title-actions">
        <div>
          <p className="eyebrow">AMPLIÁ TU RED</p>
          <h1>Sugerencias y conexiones</h1>
          <p className="muted">
            Descubrí cuentas por tus conexiones e intereses y consultá amigos en común.
          </p>
        </div>
        <button
          className="button-secondary"
          disabled={recommendationsQuery.isFetching}
          onClick={() => void recommendationsQuery.refetch()}
        >
          {recommendationsQuery.isFetching ? 'Actualizando…' : 'Actualizar sugerencias'}
        </button>
      </div>

      <InterestsEditor key={user!.id} />
      {/* Sección 1: Cuentas sugeridas */}
      <section className="recommendations-section">
        <div className="list-heading">
          <h2>Cuentas sugeridas para vos</h2>
          <span className="section-badge">Conexiones e intereses</span>
        </div>

        {recommendationsQuery.isPending && <p role="status">Buscando recomendaciones en tu red…</p>}
        {recommendationsQuery.isError && (
          <ErrorMessage message={recommendationsQuery.error.message} />
        )}

        {!recommendationsQuery.isPending &&
          !recommendationsQuery.isError &&
          suggestions.length === 0 && (
            <div className="card empty-state">
              <span aria-hidden="true">✳</span>
              <h2>No encontramos sugerencias por el momento.</h2>
              <p>
                Agregá intereses o seguí más cuentas para encontrar personas con temas
                compartidos y conexiones de segundo grado.
              </p>
            </div>
          )}

        {!recommendationsQuery.isPending && suggestions.length > 0 && (
          <div className="user-grid">
            {suggestions.map((candidateId) => (
              <UserCard
                key={candidateId}
                userId={candidateId}
                onSelectMutual={handleSelectFromSuggestions}
              />
            ))}
          </div>
        )}
      </section>

      {/* Sección 2: Amigos en común */}
      <section className="mutual-friends-section card" style={{ marginTop: '35px', padding: '28px' }}>
        <h2>Consultar amigos en común</h2>
        <p className="muted">
          Ingresá el identificador de otro usuario para verificar quiénes son seguidos por ambos.
        </p>

        <form onSubmit={handleSearchMutual} className="inline-form" style={{ marginTop: '16px' }}>
          <input
            type="text"
            placeholder="Ej: 00000000-0000-0000-0000-000000000002"
            value={targetUserId}
            onChange={(e) => setTargetUserId(e.target.value)}
            aria-label="Identificador del otro usuario"
          />
          <button
            type="submit"
            className="button-primary"
            disabled={mutualFriendsQuery.isFetching}
          >
            {mutualFriendsQuery.isFetching ? 'Consultando…' : 'Consultar'}
          </button>
        </form>

        {validationError && (
          <div role="alert" className="field-error" style={{ marginTop: '10px' }}>
            {validationError}
          </div>
        )}

        {mutualFriendsQuery.isError && (
          <div style={{ marginTop: '15px' }}>
            <ErrorMessage message={mutualFriendsQuery.error.message} />
          </div>
        )}

        {activeQueryTarget && !mutualFriendsQuery.isPending && !mutualFriendsQuery.isError && (
          <div className="mutual-results" style={{ marginTop: '20px' }}>
            <h3>
              {mutualFriends.length === 0
                ? 'No tienen amigos en común.'
                : `Tienen ${mutualFriends.length} amigo(s) en común:`}
            </h3>
            {mutualFriends.length > 0 && (
              <div className="user-grid" style={{ marginTop: '12px' }}>
                {mutualFriends.map((friendId) => (
                  <UserCard key={friendId} userId={friendId} />
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
