import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { postSchema } from './contracts'
import { PostCard } from './PostCard'
import { recentOperations } from './drafts'

export function MyPostsPage() {
  const { user, request } = useAuth()
  const posts = useQuery({
    queryKey: ['posts', 'by-user', user!.id],
    queryFn: async ({ signal }) => z.array(postSchema).parse(await request(`/api/v1/posts/by-user/${user!.id}`, { signal })),
    networkMode: 'always',
  })
  const recent = recentOperations(user!.id)
  return <div className="page-content publication-page">
    <div className="page-title title-actions"><div><p className="eyebrow">TU ESPACIO EN NICHE</p><h1>Mis publicaciones</h1><p className="muted">Hola, {user!.full_name}. Estas son tus ideas compartidas.</p></div><Link className="button-primary" to="/publicar">＋ Crear publicación</Link></div>
    {recent.length > 0 && <details className="card recent-operations"><summary>Consultar envíos recientes</summary><ul>{recent.map((operation) => <li key={operation.operation_id}><Link to={`/operaciones/${operation.operation_id}`}>Operación {operation.operation_id}</Link></li>)}</ul></details>}
    <div className="list-heading"><h2>Publicaciones visibles</h2><button className="button-secondary" disabled={posts.isFetching} onClick={() => void posts.refetch()}>{posts.isFetching ? 'Actualizando…' : 'Actualizar publicaciones'}</button></div>
    {posts.isPending && <p role="status">Cargando publicaciones…</p>}
    {posts.isError && <ErrorMessage message={posts.error.message} />}
    {!posts.isError && posts.data?.length === 0 && <section className="card empty-state"><span aria-hidden="true">✳</span><h2>Todavía no publicaste.</h2><p>Una idea puede ser el comienzo de una conversación.</p><Link className="button-primary" to="/publicar">Crear mi primera publicación</Link></section>}
    {!posts.isError && posts.data?.map((post) => <PostCard key={post.id} post={post} author={user!.full_name} />)}
    <p className="preparation-note">Acá ves tus publicaciones. El feed personalizado se incorporará en P3.</p>
  </div>
}
