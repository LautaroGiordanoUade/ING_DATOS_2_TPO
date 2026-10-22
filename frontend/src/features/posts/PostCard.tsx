import { useEffect, useState } from 'react'
import { isMediaUrl, type Post } from './contracts'
import { PostInteractions } from '../interactions/PostInteractions'

export function PostCard({ post, author, username }: { post: Post; author: string; username?: string | undefined }) {
  const [counts, setCounts] = useState({ reactions: post.reaction_count, comments: post.comment_count })

  useEffect(() => {
    setCounts({ reactions: post.reaction_count, comments: post.comment_count })
  }, [post.reaction_count, post.comment_count])

  const handleCountsChange = (newReactions: number, newComments: number) => {
    setCounts({ reactions: newReactions, comments: newComments })
  }

  return (
    <article className="card post-card" aria-label={`Publicación de ${author}`}>
      <div className="author-line">
        <span className="avatar" aria-hidden="true">{Array.from(author)[0]?.toUpperCase()}</span>
        <div>
          <strong>{author}</strong>
          {username && <span>@{username}</span>}
          <time dateTime={post.published_at}>{new Date(post.published_at).toLocaleString('es-AR')}</time>
        </div>
        <span className="pill">Pública</span>
      </div>
      <p className="post-text">{post.text}</p>
      {post.media.filter(isMediaUrl).map((url, index) => (
        <img key={`${url}-${index}`} className="post-image" src={url} alt={`Imagen ${index + 1} de la publicación`} loading="lazy" referrerPolicy="no-referrer" />
      ))}
      <ul className="interest-tags" aria-label="Intereses">
        {post.interests.map((interest) => <li key={interest}>#{interest}</li>)}
      </ul>
      <p className="post-counts">{counts.reactions} reacciones · {counts.comments} comentarios</p>
      <PostInteractions postId={post.id} onCountsChange={handleCountsChange} />
      <details className="post-identifiers">
        <summary>Identificador de publicación</summary>
        <code>{post.id}</code>
      </details>
    </article>
  )
}
