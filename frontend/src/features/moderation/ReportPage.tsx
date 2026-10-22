import { useMutation, useQuery } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { postSchema } from '../posts/contracts'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { FormField } from '../../components/common/FormField'
import { reasons, reportSchema, reportValuesSchema } from './contracts'
import { moderationError } from './errors'

export function ReportPage() {
  const { postId = '' } = useParams()
  const valid = z.guid().safeParse(postId).success
  const { request, user } = useAuth()
  const navigate = useNavigate()
  const post = useQuery({
    queryKey: ['posts', 'detail', postId], enabled: valid,
    queryFn: async ({ signal }) => postSchema.parse(await request(`/api/v1/posts/${postId}`, { signal })),
    networkMode: 'always', retry: false,
  })
  const { register, handleSubmit, formState: { errors } } = useForm<z.infer<typeof reportValuesSchema>>({
    resolver: zodResolver(reportValuesSchema), defaultValues: { reason: 'spam', description: '' },
  })
  const mutation = useMutation({
    mutationFn: async (values: z.infer<typeof reportValuesSchema>) => reportSchema.parse(await request('/api/v1/moderation/reports', {
      method: 'POST', body: JSON.stringify({ post_id: postId, ...values, description: values.description || null }),
    })),
    retry: false,
    onSuccess: (report) => navigate(`/reportes/${report.id}`, { replace: true }),
  })
  if (!valid) return <div className="page-content"><ErrorMessage message="El identificador de publicación no es válido." /></div>
  return <div className="page-content moderation-page">
    <Link className="back-link" to="/">← Volver al feed</Link>
    <div className="page-title"><p className="eyebrow">CUIDEMOS LA COMUNIDAD</p><h1>Reportar publicación</h1><p className="muted">El equipo de moderación revisará tu reporte. Enviarlo no oculta la publicación automáticamente.</p></div>
    {post.isPending && <p role="status">Cargando publicación…</p>}
    {post.isError && <><ErrorMessage message={moderationError(post.error)} /><button className="button-secondary" onClick={() => void post.refetch()}>Volver a cargar</button></>}
    {post.data && !post.isError && <section className="card moderation-card">
      <blockquote className="reported-text">{post.data.text}</blockquote>
      <form noValidate onSubmit={handleSubmit((values) => mutation.mutate(values))}>
        <fieldset disabled={mutation.isPending}>
          <FormField id="report-reason" label="Motivo del reporte"><select id="report-reason" {...register('reason')}>{Object.entries(reasons).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></FormField>
          <FormField id="report-description" label="Contanos qué pasó (opcional)" error={errors.description?.message}><textarea id="report-description" rows={5} {...register('description')} aria-invalid={!!errors.description} aria-describedby={errors.description ? 'report-description-error' : undefined} /></FormField>
          <p className="field-hint">Se registra con tu cuenta @{user!.username}. Podés reportar una vez cada publicación.</p>
          {mutation.isError && <ErrorMessage message={moderationError(mutation.error)} />}
          <div className="moderation-actions"><button className="button-primary" type="submit">{mutation.isPending ? 'Enviando reporte…' : 'Enviar reporte'}</button><Link to="/" className="button-secondary">Cancelar</Link></div>
        </fieldset>
      </form>
    </section>}
  </div>
}
