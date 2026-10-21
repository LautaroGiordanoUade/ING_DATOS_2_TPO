import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { ApiError } from '../../services/http/client'
import { getFeed, uniquePosts } from './api'
import { FeedPost } from './FeedPost'

export function FeedPage() {
  const { user, request } = useAuth()
  const client = useQueryClient()
  const queryKey = ['feed', user!.id]
  const feed = useInfiniteQuery({
    queryKey,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => getFeed(request, user!.id, pageParam, signal),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: true,
    networkMode: 'always',
  })
  const posts = uniquePosts(feed.data?.pages ?? [])
  const expired = feed.error instanceof ApiError && feed.error.status === 410
  const invalidCursor = feed.error instanceof ApiError && feed.error.status === 422
  const needsRestart = expired || invalidCursor
  const error = expired ? 'La navegación del feed venció. Actualizá el feed para ver las publicaciones actuales.'
    : invalidCursor ? 'No pudimos continuar esta navegación. Actualizá el feed para empezar de nuevo.'
    : feed.error?.message
  const refresh = () => { void client.resetQueries({ queryKey, exact: true }) }
  return <div className="page-content publication-page feed-page">
    <div className="page-title title-actions">
      <div><p className="eyebrow">IDEAS DE TU COMUNIDAD</p><h1>Tu feed</h1><p className="muted">Las publicaciones de las cuentas que seguís, en un mismo lugar.</p></div>
      <Link className="button-primary" to="/publicar">＋ Crear publicación</Link>
    </div>
    <div className="list-heading">
      <h2>De tus seguidos</h2>
      <button className="button-secondary" onClick={refresh} disabled={feed.isFetching}>{feed.isFetching && !feed.isFetchingNextPage ? 'Actualizando…' : 'Actualizar feed'}</button>
    </div>
    {feed.isPending && <p role="status">Cargando tu feed…</p>}
    {feed.isError && <div className="feed-error"><ErrorMessage message={error ?? 'No pudimos cargar el feed.'} />
      {!needsRestart && <button className="button-secondary" disabled={feed.isFetching} onClick={() => {
        if (feed.isFetchNextPageError) void feed.fetchNextPage({ cancelRefetch: false })
        else void feed.refetch()
      }}>Volver a intentar</button>}
    </div>}
    {!feed.isPending && !feed.isError && posts.length === 0 && <section className="card empty-state">
      <span aria-hidden="true">✳</span><h2>{feed.hasNextPage ? 'Todavía no hay publicaciones visibles en esta página.' : 'Tu feed todavía está vacío.'}</h2>
      <p>{feed.hasNextPage ? 'Podés seguir buscando en las páginas anteriores.' : 'Cuando las cuentas que seguís compartan algo, lo vas a encontrar acá.'}</p>
      <Link className="button-secondary" to="/mis-publicaciones">Ver mis publicaciones</Link>
    </section>}
    {!needsRestart && posts.map((post) => <FeedPost key={post.id} post={post} />)}
    {feed.isFetchingNextPage && <p className="feed-progress" role="status">Cargando más publicaciones…</p>}
    {!needsRestart && feed.hasNextPage && <div className="feed-pagination"><button className="button-secondary" disabled={feed.isFetching} onClick={() => void feed.fetchNextPage({ cancelRefetch: false })}>Cargar más publicaciones</button></div>}
    {!feed.isError && !feed.hasNextPage && posts.length > 0 && <p className="preparation-note">Viste todas las publicaciones de esta navegación. Actualizá para buscar novedades.</p>}
    <p className="feed-own-link">¿Buscás lo que compartiste? <Link to="/mis-publicaciones">Mis publicaciones</Link></p>
  </div>
}
