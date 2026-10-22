import { useState } from 'react'
import { useAuth } from '../auth/context'
import { ApiError } from '../../services/http/client'
import { PRESET_REACTIONS } from './contracts'
import { refreshPostCounters, removeReaction, sendComment, sendReaction } from './api'

interface PostInteractionsProps {
  postId: string
  onCountsChange: (reactionCount: number, commentCount: number) => void
}

function parseErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return 'La publicación ya no está disponible (fue retirada o eliminada).'
    if (err.status === 409) return 'Conflicto por operaciones concurrentes. Volvé a intentar.'
    if (err.status === 422) return 'Revisá los datos enviados antes de continuar.'
    if (err.status === 503) return 'El servicio no está disponible en este momento.'
    return err.message
  }
  return 'Ocurrió un error inesperado al procesar la interacción.'
}

export function PostInteractions({ postId, onCountsChange }: PostInteractionsProps) {
  const { user, request } = useAuth()

  // Estados de reacción
  const [selectedKind, setSelectedKind] = useState<string | null>(null)
  const [customKind, setCustomKind] = useState('')
  const [showCustom, setShowCustom] = useState(false)
  const [isReacting, setIsReacting] = useState(false)
  const [reactionMsg, setReactionMsg] = useState<{ type: 'error' | 'success'; text: string } | null>(null)

  // Estados de comentarios
  const [isCommenting, setIsCommenting] = useState(false)
  const [showCommentBox, setShowCommentBox] = useState(false)
  const [commentText, setCommentText] = useState('')
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID())
  const [commentMsg, setCommentMsg] = useState<{ type: 'error' | 'success'; text: string } | null>(null)

  if (!user) return null

  const handleReact = async (kindToSet: string) => {
    setIsReacting(true)
    setReactionMsg(null)
    try {
      await sendReaction(request, { post_id: postId, user_id: user.id, kind: kindToSet })
      setSelectedKind(kindToSet)
      setReactionMsg({ type: 'success', text: `Reacción enviada (${kindToSet}).` })
      const updated = await refreshPostCounters(request, postId)
      onCountsChange(updated.reaction_count, updated.comment_count)
    } catch (err) {
      setReactionMsg({ type: 'error', text: parseErrorMessage(err) })
    } finally {
      setIsReacting(false)
    }
  }

  const handleRemoveReaction = async () => {
    setIsReacting(true)
    setReactionMsg(null)
    try {
      await removeReaction(request, { post_id: postId, user_id: user.id })
      setSelectedKind(null)
      setReactionMsg({ type: 'success', text: 'Reacción eliminada.' })
      const updated = await refreshPostCounters(request, postId)
      onCountsChange(updated.reaction_count, updated.comment_count)
    } catch (err) {
      setReactionMsg({ type: 'error', text: parseErrorMessage(err) })
    } finally {
      setIsReacting(false)
    }
  }

  const handleSubmitComment = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = commentText.trim()
    if (!trimmed) {
      setCommentMsg({ type: 'error', text: 'Escribí un comentario antes de enviar.' })
      return
    }
    if (trimmed.length > 2000) {
      setCommentMsg({ type: 'error', text: 'El comentario no puede superar los 2.000 caracteres.' })
      return
    }

    setIsCommenting(true)
    setCommentMsg(null)
    try {
      await sendComment(request, { post_id: postId, user_id: user.id, text: trimmed }, idempotencyKey)
      setCommentMsg({ type: 'success', text: 'Comentario enviado exitosamente.' })
      setCommentText('')
      setIdempotencyKey(crypto.randomUUID()) // Nueva clave solo ante éxito
      const updated = await refreshPostCounters(request, postId)
      onCountsChange(updated.reaction_count, updated.comment_count)
    } catch (err) {
      // ANTE ERROR: Se conserva commentText y la misma idempotencyKey para reintento seguro
      setCommentMsg({ type: 'error', text: parseErrorMessage(err) })
    } finally {
      setIsCommenting(false)
    }
  }

  return (
    <div className="post-interactions" aria-label="Interacciones de la publicación">
      {/* Barra de Reacciones */}
      <div className="reaction-bar" role="group" aria-label="Reacciones disponibles">
        {PRESET_REACTIONS.map(({ kind, label }) => (
          <button
            key={kind}
            type="button"
            className={`reaction-button ${selectedKind === kind ? 'active' : ''}`}
            disabled={isReacting}
            onClick={() => void handleReact(kind)}
          >
            {label}
          </button>
        ))}

        {!showCustom ? (
          <button
            type="button"
            className="reaction-button"
            onClick={() => setShowCustom(true)}
            disabled={isReacting}
          >
            ＋ Otra
          </button>
        ) : (
          <div className="custom-reaction-form">
            <input
              type="text"
              placeholder="Ej: aplauso"
              maxLength={30}
              value={customKind}
              onChange={(e) => setCustomKind(e.target.value)}
              disabled={isReacting}
            />
            <button
              type="button"
              className="button-primary"
              style={{ minHeight: '32px', padding: '4px 10px', fontSize: '11px' }}
              disabled={isReacting || !customKind.trim()}
              onClick={() => {
                if (customKind.trim()) void handleReact(customKind.trim())
              }}
            >
              Aplicar
            </button>
          </div>
        )}

        {selectedKind && (
          <button
            type="button"
            className="reaction-remove-button"
            disabled={isReacting}
            onClick={() => void handleRemoveReaction()}
          >
            Quitar mi reacción
          </button>
        )}
      </div>

      {reactionMsg && (
        <div
          role={reactionMsg.type === 'error' ? 'alert' : 'status'}
          className={`interaction-feedback ${reactionMsg.type}`}
        >
          {reactionMsg.text}
        </div>
      )}

      {/* Control de Comentarios */}
      <button
        type="button"
        className="comment-toggle-button"
        onClick={() => setShowCommentBox((prev) => !prev)}
      >
        {showCommentBox ? 'Ocultar caja de comentarios' : '💬 Escribir comentario'}
      </button>

      {showCommentBox && (
        <form className="comment-form" onSubmit={(e) => void handleSubmitComment(e)}>
          <textarea
            aria-label="Escribí un comentario"
            placeholder="Sumá tu comentario a la publicación…"
            rows={2}
            maxLength={2000}
            value={commentText}
            disabled={isCommenting}
            onChange={(e) => setCommentText(e.target.value)}
          />
          <div className="comment-actions">
            <span className="comment-counter">{commentText.length} / 2.000</span>
            <button
              type="submit"
              className="button-primary"
              style={{ minHeight: '36px', padding: '6px 14px' }}
              disabled={isCommenting || !commentText.trim()}
            >
              {isCommenting ? 'Enviando…' : 'Comentar'}
            </button>
          </div>
          {commentMsg && (
            <div
              role={commentMsg.type === 'error' ? 'alert' : 'status'}
              className={`interaction-feedback ${commentMsg.type}`}
            >
              {commentMsg.text}
            </div>
          )}
        </form>
      )}
    </div>
  )
}