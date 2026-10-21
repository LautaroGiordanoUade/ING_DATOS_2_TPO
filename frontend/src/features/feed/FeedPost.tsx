import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../auth/context'
import { userSchema } from '../auth/contracts'
import { PostCard } from '../posts/PostCard'
import type { Post } from '../posts/contracts'
import { ApiError } from '../../services/http/client'

export function FeedPost({ post }: { post: Post }) {
  const { request } = useAuth()
  const author = useQuery({
    queryKey: ['users', 'profile', post.user_id],
    queryFn: async ({ signal }) => userSchema.parse(await request(`/api/v1/users/${post.user_id}`, { signal })),
    staleTime: 5 * 60_000,
    networkMode: 'always',
  })
  if (author.error instanceof ApiError && author.error.status === 404) {
    return <p className="card unavailable-post">Una publicación ya no está disponible. Actualizá el feed para revisar las novedades.</p>
  }
  return <>
    <PostCard post={post} author={author.data?.full_name || `Cuenta ${post.user_id.slice(0, 8)}`} username={author.data?.username} />
    {author.isError && <div className="profile-error" role="status">No pudimos cargar el perfil del autor. <button className="button-secondary" onClick={() => void author.refetch()}>Reintentar perfil</button></div>}
  </>
}
