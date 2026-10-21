import { useEffect, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { userSchema } from '../auth/contracts'
import { FormField } from '../../components/common/FormField'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { ApiError } from '../../services/http/client'
import { composerSchema, publicationSchema, toPostPayload, type ComposerValues } from './contracts'
import { clearDraft, readDraft, rememberOperation, saveDraft, type PublicationAttempt } from './drafts'

export function ComposerPage() {
  const auth = useAuth()
  const user = auth.user!
  const navigate = useNavigate()
  const [initial] = useState(() => readDraft(user.id))
  const [attempt, setAttempt] = useState<PublicationAttempt | null>(initial.attempt)
  const [confirmNew, setConfirmNew] = useState(false)
  const { register, control, handleSubmit, formState: { errors } } = useForm<ComposerValues>({ resolver: zodResolver(composerSchema), defaultValues: initial.values })
  const values = useWatch({ control })
  const mutation = useMutation({
    mutationFn: async (submission: PublicationAttempt) => {
      // Revalidate the session before submitting a draft restored from this tab.
      userSchema.parse(await auth.request('/api/v1/users/me'))
      return publicationSchema.parse(await auth.request('/api/v1/posts', {
        method: 'POST', headers: { 'Idempotency-Key': submission.key }, body: JSON.stringify(submission.payload),
      }))
    },
    retry: false,
    onSuccess: (result) => {
      rememberOperation(user.id, result)
      clearDraft(user.id)
      navigate(`/operaciones/${result.operation_id}`, { replace: true })
    },
    onError: (error) => {
      // Validation rejects before accepting a job, so editing is safe in this case.
      if (error instanceof ApiError && error.status === 422) setAttempt(null)
    },
  })
  useEffect(() => {
    if (!mutation.isSuccess) saveDraft(user.id, { text: values.text ?? '', interests: values.interests ?? '', media: values.media ?? '' }, attempt)
  }, [user.id, values.text, values.interests, values.media, attempt, mutation.isSuccess])
  const locked = attempt !== null
  return <div className="page-content publication-page">
    <Link to="/" className="back-link">← Mis publicaciones</Link>
    <div className="page-title"><p className="eyebrow">COMPARTÍ UNA IDEA</p><h1>Algo para tu comunidad.</h1><p className="muted">Publicá sobre lo que te interesa. Nosotros lo acercamos a tus seguidores.</p></div>
    <section className="card composer-card">
      <div className="author-line"><span className="avatar" aria-hidden="true">{user.full_name.slice(0, 1).toUpperCase()}</span><div><strong>{user.full_name}</strong><span>@{user.username} · Publicación pública</span></div></div>
      <form noValidate onSubmit={handleSubmit((valid) => {
        const submission = attempt ?? { key: crypto.randomUUID(), payload: toPostPayload(valid, user.id) }
        saveDraft(user.id, valid, submission)
        setAttempt(submission)
        mutation.mutate(submission)
      })}>
        <fieldset disabled={mutation.isPending}>
          <FormField id="text" label="Tu publicación" error={errors.text?.message}><textarea id="text" rows={7} placeholder="¿Qué te gustaría compartir?" readOnly={locked} {...register('text')} aria-invalid={!!errors.text} aria-describedby={`text-count${errors.text ? ' text-error' : ''}`} /></FormField>
          <p className="character-count" id="text-count">{values.text?.length ?? 0} / 10.000 caracteres</p>
          <FormField id="interests" label="Intereses" hint="Separalos con comas. Por ejemplo: datos, python." error={errors.interests?.message}><input id="interests" readOnly={locked} {...register('interests')} aria-invalid={!!errors.interests} aria-describedby={`interests-hint${errors.interests ? ' interests-error' : ''}`} /></FormField>
          <FormField id="media" label="Enlaces a imágenes (opcional)" hint="Un enlace http o https por línea. No se suben archivos." error={errors.media?.message}><textarea id="media" rows={2} readOnly={locked} {...register('media')} aria-invalid={!!errors.media} aria-describedby={`media-hint${errors.media ? ' media-error' : ''}`} /></FormField>
          {mutation.isError && <ErrorMessage message={mutation.error.message} />}
          {locked && !mutation.isPending && <p className="field-hint" role="status">Este envío se conserva para evitar duplicados. Reintentá con el mismo contenido; si ya fue recibido, se recuperará su operación.</p>}
          {locked && !mutation.isPending && !confirmNew && <button type="button" className="button-secondary" onClick={() => setConfirmNew(true)}>Empezar otro envío</button>}
          {confirmNew && <div className="new-draft-confirm" role="group" aria-label="Confirmar nuevo envío"><p className="field-hint">El servidor podría haber recibido el envío anterior. Si continuás, crearás una publicación distinta con una clave nueva.</p><button type="button" className="button-secondary" onClick={() => { setAttempt(null); setConfirmNew(false); mutation.reset() }}>Confirmar nuevo borrador</button> <button type="button" className="button-secondary" onClick={() => setConfirmNew(false)}>Conservar este envío</button></div>}
          <div className="composer-actions"><span className="field-hint">El contenido será visible cuando termine la distribución.</span><button type="submit" className="button-primary">{mutation.isPending ? 'Enviando…' : locked ? 'Reintentar envío' : 'Publicar'}</button></div>
        </fieldset>
      </form>
    </section>
    <p className="preparation-note">Tu borrador se conserva en esta pestaña hasta confirmar el envío.</p>
  </div>
}
