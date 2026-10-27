import { useInfiniteQuery } from '@tanstack/react-query'
import { useAuth } from '../auth/context'
import { ApiError } from '../../services/http/client'
import { getComments } from './api'

export function CommentList({ postId, enabled, onOpen }: { postId: string; enabled: boolean; onOpen: () => void }) {
  const { user, request } = useAuth()
  const comments = useInfiniteQuery({
    queryKey: ['comments', user?.id, postId],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => getComments(request, postId, pageParam, signal),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: enabled && Boolean(user),
    retry: false, refetchOnWindowFocus: false, networkMode: 'always',
  })
  if (!enabled) return <button className="comment-toggle-button" type="button" onClick={onOpen}>Ver comentarios</button>
  if (comments.error instanceof ApiError && comments.error.status === 404) {
    return <div>
      <p role="status">Los comentarios ya no están disponibles para esta publicación.</p>
      <button type="button" className="comment-toggle-button" disabled={comments.isFetching}
        onClick={() => void comments.refetch()}>Volver a comprobar comentarios</button>
    </div>
  }
  const seen = new Set<string>()
  const items = (comments.data?.pages.flatMap((page) => page.items) ?? []).filter((item) => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
  return <section className="comment-list" aria-label="Comentarios de la publicación">
    <div className="comment-list-heading">
      <h3>Comentarios</h3>
      <button type="button" className="comment-toggle-button" disabled={comments.isFetching}
        onClick={() => void comments.refetch()}>Actualizar comentarios</button>
    </div>
    {comments.isPending && <p role="status">Cargando comentarios…</p>}
    {comments.isError && <div role="alert">
      No pudimos cargar los comentarios.{' '}
      <button type="button" disabled={comments.isFetching} onClick={() => {
        if (comments.isFetchNextPageError) void comments.fetchNextPage()
        else void comments.refetch()
      }}>Reintentar comentarios</button>
    </div>}
    {!comments.isPending && !comments.isError && items.length === 0 && <p>No hay comentarios visibles todavía.</p>}
    <ul className="comment-items">
      {items.map((item) => <li key={item.id} className="comment-item">
        <div className="comment-author">
          <strong>{item.author_name}</strong>
          {item.author_username && <span>@{item.author_username}</span>}
          <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('es-AR')}</time>
        </div>
        <p>{item.text}</p>
      </li>)}
    </ul>
    {comments.hasNextPage && <button type="button" className="button-secondary"
      disabled={comments.isFetching} onClick={() => void comments.fetchNextPage()}>
      {comments.isFetchingNextPage ? 'Cargando anteriores…' : 'Cargar comentarios anteriores'}
    </button>}
  </section>
}
