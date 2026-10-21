import { isMediaUrl, type Post } from './contracts'

export function PostCard({ post, author, username }: { post: Post; author: string; username?: string | undefined }) {
  return <article className="card post-card" aria-label={`Publicación de ${author}`}>
    <div className="author-line"><span className="avatar" aria-hidden="true">{Array.from(author)[0]?.toUpperCase()}</span><div><strong>{author}</strong>{username && <span>@{username}</span>}<time dateTime={post.published_at}>{new Date(post.published_at).toLocaleString('es-AR')}</time></div><span className="pill">Pública</span></div>
    <p className="post-text">{post.text}</p>
    {post.media.filter(isMediaUrl).map((url, index) => <img key={`${url}-${index}`} className="post-image" src={url} alt={`Imagen ${index + 1} de la publicación`} loading="lazy" referrerPolicy="no-referrer" />)}
    <ul className="interest-tags" aria-label="Intereses">{post.interests.map((interest) => <li key={interest}>#{interest}</li>)}</ul>
    <p className="post-counts">{post.reaction_count} reacciones · {post.comment_count} comentarios</p>
    <details className="post-identifiers"><summary>Identificador de publicación</summary><code>{post.id}</code></details>
  </article>
}
