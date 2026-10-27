import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAuth } from '../auth/context'
import { FormField } from '../../components/common/FormField'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { actions, decisionValuesSchema, jobSchema, type DecisionValues, type Report } from './contracts'
import { moderationError } from './errors'

export function DecisionForm({ report }: { report: Report }) {
  const { request } = useAuth()
  const navigate = useNavigate()
  const [review, setReview] = useState<DecisionValues | null>(null)
  const { register, handleSubmit, formState: { errors } } = useForm<DecisionValues>({
    resolver: zodResolver(decisionValuesSchema), defaultValues: { action: report.resolution_status === 'approved' ? 'revert' : 'hide', reason: '' },
  })
  const mutation = useMutation({
    mutationFn: async (values: DecisionValues) => jobSchema.parse(await request(`/api/v1/moderation/reports/${report.id}/${values.action === 'revert' ? 'revert' : 'decision'}`, {
      method: 'POST', body: JSON.stringify(values.action === 'revert' ? { reason: values.reason } : { decision: values.action, reason: values.reason }),
    })),
    retry: false,
    onSuccess: (job) => navigate(`/moderacion/operaciones/${job.operation_id}`),
  })
  return <section className="card moderation-card">
    <h2>{report.resolution_status === 'approved' ? 'Revisar ocultación' : 'Resolver reporte'}</h2>
    <p className="muted">{report.resolution_status === 'approved' ? 'Restaurar revierte esta ocultación y recupera la distribución y los contadores preservados.' : 'Ocultar retira la publicación de las lecturas públicas. Rechazar conserva el contenido visible.'}</p>
    {!review ? <form noValidate onSubmit={handleSubmit(setReview)}>
      <FormField id="decision-action" label="Acción"><select id="decision-action" {...register('action')}>{(report.resolution_status === 'approved' ? ['revert'] as const : ['hide', 'reject'] as const).map((action) => <option key={action} value={action}>{actions[action]}</option>)}</select></FormField>
      <FormField id="decision-reason" label="Motivo de la decisión" error={errors.reason?.message}><textarea id="decision-reason" rows={4} {...register('reason')} aria-invalid={!!errors.reason} aria-describedby={errors.reason ? 'decision-reason-error' : undefined} /></FormField>
      <button className="button-primary" type="submit">Revisar decisión</button>
    </form> : <div className="decision-confirm" role="group" aria-label="Confirmar decisión">
      <h3>{actions[review.action]}</h3><p className="reported-text">{review.reason}</p><p className="field-hint">La solicitud se procesará en el servidor. Esperá la confirmación antes de darla por aplicada.</p>
      {mutation.isError && <ErrorMessage message={moderationError(mutation.error)} />}
      <div className="moderation-actions"><button className="button-primary" disabled={mutation.isPending} onClick={() => mutation.mutate(review)}>{mutation.isPending ? 'Enviando decisión…' : 'Confirmar y enviar'}</button><button className="button-secondary" disabled={mutation.isPending} onClick={() => { setReview(null); mutation.reset() }}>Editar decisión</button></div>
    </div>}
  </section>
}
