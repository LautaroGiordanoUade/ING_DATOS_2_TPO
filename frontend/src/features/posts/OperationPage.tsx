import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { operationLabels, operationSchema, postSchema, terminal } from './contracts'
import { PostCard } from './PostCard'
import { DistributionPreview } from './DistributionPreview'

export function OperationPage() {
  const { operationId = '' } = useParams()
  const { request, user } = useAuth()
  const valid = z.uuid().safeParse(operationId).success
  const client = useQueryClient()
  const operation = useQuery({
    queryKey: ['publication-operation', user!.id, operationId], enabled: valid,
    queryFn: async ({ signal }) => {
      const result = operationSchema.parse(await request(`/api/v1/problems/operations/${operationId}`, { signal }))
      if (result.operation_type !== 'problem_01_publish_content' || !result.post_id) throw new Error('Esta operación no corresponde a una publicación P1.')
      return result
    },
    refetchInterval: (query) => query.state.error || (query.state.data && terminal(query.state.data.status)) ? false : 1000,
    refetchOnWindowFocus: true, networkMode: 'always',
  })
  const completed = operation.data?.status === 'completed'
  const postId = operation.data?.post_id ?? null
  const post = useQuery({
    queryKey: ['posts', 'detail', postId], enabled: completed && !!postId,
    queryFn: async ({ signal }) => postSchema.parse(await request(`/api/v1/posts/${postId}`, { signal })),
    networkMode: 'always',
  })
  useEffect(() => {
    if (completed) {
      void client.invalidateQueries({ queryKey: ['posts', 'by-user', user!.id] })
      void client.invalidateQueries({ queryKey: ['publication-preview'] })
    }
  }, [completed, client, user])
  if (!valid) return <div className="page-content"><ErrorMessage message="El identificador de operación no es válido." /><Link to="/">Volver a mis publicaciones</Link></div>
  return <div className="page-content publication-page">
    <Link to="/" className="back-link">← Mis publicaciones</Link>
    <div className="page-title"><p className="eyebrow">DEL ENVÍO A TU COMUNIDAD</p><h1>Estado de publicación</h1></div>
    <section className="card operation-card" aria-live="polite">
      {operation.isPending && <p role="status">Consultando operación…</p>}
      {operation.isError && <><ErrorMessage message={operation.error.message} /><button className="button-secondary" onClick={() => void operation.refetch()}>Volver a consultar</button></>}
      {operation.data && !operation.isError && <>
        <span className={`status-badge ${completed ? 'is-ready' : ''}`} role="status">{operationLabels[operation.data.status]}</span>
        <h2>{completed ? 'Tu idea ya está publicada.' : operation.data.status === 'compensated' ? 'El envío se revirtió.' : operation.data.status === 'failed' ? 'No se pudo finalizar el proceso.' : 'Estamos preparando tu publicación.'}</h2>
        <p className="muted">{completed ? 'La API confirmó la distribución. Podés consultar la visibilidad para una cuenta seguidora.' : terminal(operation.data.status) ? 'No se confirma una publicación exitosa. Podés revisar el detalle y crear un nuevo envío.' : 'El envío fue recibido. Se confirmará cuando termine el trabajo del servidor; podés volver a esta dirección más tarde.'}</p>
        {operation.data.error && <ErrorMessage message={operation.data.error} />}
        <dl className="operation-info"><dt>Operación</dt><dd><code>{operationId}</code></dd>{postId && <><dt>Publicación</dt><dd><code>{postId}</code></dd></>}<dt>Estado del servidor</dt><dd>{operation.data.status}</dd><dt>Pasos completados</dt><dd>{operation.data.completed_steps.length}</dd></dl>
        {!completed && terminal(operation.data.status) && <Link className="button-primary" to="/publicar">Crear otro envío</Link>}
      </>}
    </section>
    {completed && post.isPending && postId && <p role="status">Cargando contenido publicado…</p>}
    {completed && post.isError && <ErrorMessage message="La operación terminó, pero el contenido no está disponible en la lectura pública. Puede haber sido retirado o haber un problema de conexión." />}
    {completed && post.data && !post.isError && <PostCard post={post.data} author={post.data.user_id === user!.id ? user!.full_name : post.data.user_id} />}
    {completed && postId && <DistributionPreview postId={postId} />}
  </div>
}
