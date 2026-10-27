import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAuth } from '../auth/context'
import { FormField } from '../../components/common/FormField'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { accountActions, accountJobSchema, reasonSchema, type AccountAction, type AccountAttempt } from './contracts'
import { clearAttempt, readAttempt, rememberAccountOperation, saveAttempt } from './attempts'
import { accountError } from './errors'

export function AccountDecisionForm({ userId, status }: { userId: string; status: 'active' | 'suspended' }) {
  const { request, user } = useAuth()
  const navigate = useNavigate()
  const action: AccountAction = status === 'active' ? 'suspend' : 'reactivate'
  const [attempt, setAttempt] = useState(() => readAttempt(user!.id, userId))
  const displayedAction = attempt?.action ?? action
  const [review, setReview] = useState<{ reason: string } | null>(null)
  const [discard, setDiscard] = useState(false)
  const { register, handleSubmit, formState: { errors } } = useForm<{ reason: string }>({ resolver: zodResolver(reasonSchema), defaultValues: { reason: '' } })
  const mutation = useMutation({
    mutationFn: async (submission: AccountAttempt) => {
      const job = accountJobSchema.parse(await request(`/api/v1/accounts/${submission.userId}/${submission.action}`, { method: 'POST', headers: { 'Idempotency-Key': submission.key }, body: JSON.stringify({ reason: submission.reason }) }))
      if (job.user_id !== submission.userId || job.action !== submission.action) throw new Error('La operación recibida no corresponde a esta solicitud.')
      return job
    }, retry: false,
    onSuccess: (job) => {
      rememberAccountOperation(user!.id, job)
      clearAttempt(user!.id, userId)
      navigate(`/cuentas/operaciones/${job.operation_id}`)
    },
  })
  const submit = () => {
    if (!attempt && !review) return
    const submission = attempt ?? { key: crypto.randomUUID(), userId, action, reason: review!.reason }
    saveAttempt(user!.id, submission)
    setAttempt(submission)
    mutation.mutate(submission)
  }
  return <section className="card account-card"><h2>{accountActions[displayedAction]}</h2><p className="muted">{displayedAction === 'suspend' ? 'La suspensión retira sus publicaciones de los feeds, la excluye de sugerencias, cierra su presencia y revoca sus credenciales.' : 'La reactivación restaura los efectos de la suspensión y conserva las ocultaciones por moderación. Requiere un nuevo inicio de sesión; la presencia no se renueva automáticamente.'}</p>
    {!review && !attempt ? <form noValidate onSubmit={handleSubmit(setReview)}><FormField id="account-reason" label="Motivo del cambio de cuenta" error={errors.reason?.message}><textarea id="account-reason" rows={4} {...register('reason')} aria-invalid={!!errors.reason} aria-describedby={errors.reason ? 'account-reason-error' : undefined} /></FormField><button className="button-primary" type="submit">Revisar cambio de cuenta</button></form> : <div role="group" aria-label="Confirmar cambio de cuenta"><h3>{accountActions[attempt?.action ?? action]}</h3><p className="reported-text">{attempt?.reason ?? review?.reason}</p>
      {attempt && <p className="field-hint" role="status">Esta solicitud se conserva para evitar duplicados. Reintentá con el mismo motivo para recuperar su operación si el servidor ya la recibió.</p>}
      {mutation.isError && <ErrorMessage message={accountError(mutation.error)} />}
      <div className="moderation-actions"><button className="button-primary" disabled={mutation.isPending} onClick={submit}>{mutation.isPending ? 'Enviando solicitud…' : attempt ? 'Reintentar solicitud' : 'Confirmar cambio de cuenta'}</button>{!attempt && <button className="button-secondary" onClick={() => setReview(null)}>Editar motivo</button>}{attempt && <button className="button-secondary" disabled={mutation.isPending} onClick={() => setDiscard(true)}>Preparar otra solicitud</button>}</div>
      {discard && <div role="group" aria-label="Descartar solicitud conservada"><p className="field-hint">La solicitud anterior podría haberse aplicado. Consultá el estado de la cuenta antes de crear otra.</p><button className="button-secondary" disabled={mutation.isPending} onClick={() => { clearAttempt(user!.id, userId); setAttempt(null); setReview(null); setDiscard(false); mutation.reset() }}>Descartar y editar</button> <button className="button-secondary" onClick={() => setDiscard(false)}>Conservar solicitud</button></div>}
    </div>}
  </section>
}
