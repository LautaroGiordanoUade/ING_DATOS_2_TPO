import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/context'
import { ApiError } from '../../services/http/client'
import { actionLabels, denied, jobLabels, jobSchema, queryRoot, root, sendDecision, terminal, type Action, type ModerationContent, type Report } from './api'
import { saveAttempt, useDecisionAttempts } from './attempts'

export function DecisionPanel({ report, content, onForbidden }: { report: Report; content: ModerationContent; onForbidden: () => void }) {
  const { user, request } = useAuth()
  const client = useQueryClient()
  const viewer = user!.id
  const prefix = queryRoot(viewer, user!.role)
  const attempt = useDecisionAttempts(viewer).find((a) => a.post_id === report.post_id)
  const [selected, setSelected] = useState<Action | null>(null)
  const [reason, setReason] = useState('')
  const operationId = attempt?.operation_id && !terminal(attempt.status ?? '') ? attempt.operation_id
    : content.active_operation_id ?? (attempt && !attempt.operation_id ? content.report_operation_id
      : content.report_operation_id ?? report.operation_id ?? attempt?.operation_id)
  const job = useQuery({ queryKey: [...prefix, 'operation', operationId], enabled: !!operationId,
    queryFn: async ({ signal }) => {
      const data = jobSchema.parse(await request(`${root}/operations/${operationId}`, { signal }))
      if (data.operation_id !== operationId || data.post_id !== report.post_id) throw new Error('La operación no corresponde a esta publicación.')
      return data
    }, retry: false, networkMode: 'always',
    refetchInterval: (query) => query.state.error || query.state.data && terminal(query.state.data.status) ? false : 750,
  })
  const command = useMutation({ networkMode: 'always', mutationFn: async (payload: { report_id: string; action: Action; reason: string }) => {
    saveAttempt(client, viewer, { post_id: report.post_id, ...payload, operation_id: null, status: null }, report.post_id)
    return sendDecision(request, payload.report_id, report.post_id, payload.action, payload.reason)
  }, onSuccess: (data, payload) => {
    saveAttempt(client, viewer, { post_id: report.post_id, ...payload, operation_id: data.operation_id, status: data.status }, report.post_id)
    client.setQueryData([...prefix, 'operation', data.operation_id], data)
    setSelected(null)
    void client.invalidateQueries({ queryKey: [...prefix, 'content', report.post_id] })
  }, onError: (error) => {
    if (error instanceof ApiError && error.status === 409) { saveAttempt(client, viewer, null, report.post_id); setSelected(null) }
    void client.invalidateQueries({ queryKey: prefix })
  } })
  const retry = useMutation({ networkMode: 'always', mutationFn: async () => {
    const data = jobSchema.parse(await request(`${root}/operations/${operationId}/retry`, { method: 'POST' }))
    if (data.operation_id !== operationId || data.post_id !== report.post_id) throw new Error('La recuperación no corresponde a esta publicación.')
    return data
  }, onSuccess: (data) => {
    saveAttempt(client, viewer, { post_id: data.post_id, report_id: data.report_id, action: data.action, reason: data.reason,
      operation_id: data.operation_id, status: data.status }, report.post_id)
    client.setQueryData([...prefix, 'operation', data.operation_id], data)
  } })
  const forbidden = denied(job.error) || denied(command.error) || denied(retry.error)
  useEffect(() => { if (forbidden) onForbidden() }, [forbidden, onForbidden])
  const handled = useRef(new Set<string>())
  useEffect(() => {
    const data = job.data
    if (!data || forbidden || command.isPending || retry.isPending) return
    const marker = `${data.operation_id}:${data.status}`
    if (handled.current.has(marker)) return
    handled.current.add(marker)
    if (attempt?.operation_id === data.operation_id || attempt && !attempt.operation_id && data.moderator_id === viewer && attempt.action === data.action && attempt.reason === data.reason) {
      saveAttempt(client, viewer, { post_id: data.post_id, report_id: attempt.report_id, action: data.action, reason: data.reason,
        operation_id: data.operation_id, status: data.status }, report.post_id)
    }
    if (terminal(data.status)) {
      void client.invalidateQueries({ queryKey: ['moderation', viewer] })
      void client.resetQueries({ queryKey: ['feed'] })
      for (const key of ['posts', 'comments', 'own-reaction', 'publication-preview']) void client.invalidateQueries({ queryKey: [key] })
    }
  }, [job.data, forbidden, command.isPending, retry.isPending, client, viewer, report.post_id, attempt])
  if (forbidden) return null
  const working = command.isPending || retry.isPending || !!operationId && (job.isPending || job.isError || !!job.data && !terminal(job.data.status))
  const recoverable = job.data?.status === 'failed' || job.data?.status === 'compensated'
  const uncertain = !!attempt && !attempt.operation_id && !operationId
  const blocked = working || recoverable || uncertain
  const owner = report.resolution_report_id ?? report.id
  const canRevert = report.resolution_status === 'approved' && content.moderation_status === 'hidden' && content.moderation_owner === owner
  return <section className="moderation-decisions" aria-label="Decisiones de moderación">
    <h2>Decisión</h2>
    {working && <p role="status">Procesando decisión de moderación…</p>}
    {job.isError && <div role="alert">No pudimos consultar el resultado.<button className="button-secondary" onClick={() => void job.refetch()}>Consultar operación</button></div>}
    {job.data && <div className="moderation-operation" aria-live="polite"><strong>{jobLabels[job.data.status]}</strong><p>{actionLabels[job.data.action]} · {job.data.reason}</p>
      {job.data.status === 'completed' && <p>La operación terminó y su resultado fue confirmado.</p>}
      {job.data.status === 'compensated' && <p>El cambio se revirtió y se restauró el estado anterior.</p>}
      {job.data.error && <p role="alert">{job.data.error}</p>}
      {recoverable && <button className="button-secondary" disabled={working} onClick={() => retry.mutate()}>{job.data.status === 'failed' ? 'Reintentar recuperación' : 'Reintentar decisión'}</button>}
    </div>}
    {(command.isError || retry.isError) && <p role="alert">{(retry.error ?? command.error)?.message}</p>}
    {uncertain && <div><p>Hay una decisión pendiente de confirmar. Se conserva su motivo original.</p><button className="button-secondary" disabled={working} onClick={() => command.mutate({ report_id: attempt.report_id, action: attempt.action, reason: attempt.reason })}>Confirmar envío pendiente</button></div>}
    <div className="moderation-actions">
      {report.resolution_status === 'pending' && <>
        <button className="button-primary" disabled={blocked} onClick={() => { setSelected('hide'); setReason('') }}>Ocultar publicación</button>
        <button className="button-secondary" disabled={blocked} onClick={() => { setSelected('reject'); setReason('') }}>Rechazar reporte</button>
      </>}
      {canRevert && <button className="button-secondary" disabled={blocked} onClick={() => { setSelected('revert'); setReason('') }}>Revertir ocultamiento</button>}
    </div>
    {selected && !blocked && <form onSubmit={(event) => { event.preventDefault(); command.mutate({ report_id: report.id, action: selected, reason: reason.trim() }) }}>
      <h3>{actionLabels[selected]}</h3><p>{selected === 'hide' ? 'Se ocultará esta publicación y se resolverán todos sus reportes pendientes.' : selected === 'reject' ? 'Se rechazará solamente este reporte. La publicación conservará su estado.' : 'Se restaurará el estado de moderación anterior y se revertirán los reportes de esta decisión.'}</p>
      <label>Motivo de la decisión<textarea required maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      <div className="moderation-actions"><button className="button-primary" disabled={!reason.trim()}>Confirmar {selected === 'hide' ? 'ocultamiento' : selected === 'reject' ? 'rechazo' : 'reversión'}</button>
        <button className="button-secondary" type="button" onClick={() => setSelected(null)}>Cancelar decisión</button></div>
    </form>}
  </section>
}
