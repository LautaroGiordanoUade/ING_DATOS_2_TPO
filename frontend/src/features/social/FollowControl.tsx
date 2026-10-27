import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/context'
import { followJobSchema, getOperation, getRelation, sendFollow, socialRoot, terminal, type FollowAction } from './api'
import { putAttempt, useFollowAttempts, type FollowAttempt } from './attempts'

function refreshSocial(client: QueryClient, viewer: string) {
  return Promise.all([
    client.invalidateQueries({ queryKey: ['social', 'relation', viewer] }),
    client.invalidateQueries({ queryKey: ['social', 'counts', viewer] }),
    client.invalidateQueries({ queryKey: ['social', 'requests', viewer] }),
    client.invalidateQueries({ queryKey: ['recommendations', viewer] }),
    client.invalidateQueries({ queryKey: ['mutual-friends', viewer] }),
    client.invalidateQueries({ queryKey: ['publication-preview'] }),
    client.resetQueries({ queryKey: ['feed', viewer] }),
  ])
}

export function FollowControl({ followerId, followedId, accountType = 'public', approval = false }: {
  followerId: string; followedId: string; accountType?: 'public' | 'private'; approval?: boolean
}) {
  const { user, request } = useAuth()
  const viewer = user!.id
  const client = useQueryClient()
  const attempts = useFollowAttempts(viewer)
  const attempt = attempts.find((item) => item.follower_id === followerId && item.followed_id === followedId)
  const relation = useQuery({ queryKey: ['social', 'relation', viewer, followedId], enabled: !approval,
    queryFn: ({ signal }) => getRelation(request, followedId, signal), retry: false, networkMode: 'always',
    refetchInterval: () => document.visibilityState === 'visible' ? 4000 : false,
  })
  const operationId = !approval && relation.data?.status === 'processing' ? relation.data.operation_id : attempt?.operation_id
  const operation = useQuery({ queryKey: ['social', 'operation', viewer, operationId], enabled: !!operationId,
    queryFn: ({ signal }) => getOperation(request, operationId!, followerId, followedId, signal),
    retry: false, networkMode: 'always',
    refetchInterval: (query) => query.state.error || (query.state.data && terminal(query.state.data.status)) ? false : 700,
  })
  const change = useMutation({ networkMode: 'always', mutationFn: async ({ action, replay = false }: { action: FollowAction; replay?: boolean }) => {
    const existing = replay ? attempt : undefined
    const key = existing?.key ?? crypto.randomUUID()
    putAttempt(client, viewer, { follower_id: followerId, followed_id: followedId, action, key, operation_id: null, status: null })
    return sendFollow(request, action, followerId, followedId, key)
  }, onSuccess: (job) => {
    const current = client.getQueryData<FollowAttempt[]>(['social-attempts', viewer])?.find((item) => item.follower_id === followerId && item.followed_id === followedId)
    putAttempt(client, viewer, { follower_id: followerId, followed_id: followedId, action: job.action,
      key: current?.key ?? null, operation_id: job.operation_id, status: job.status })
    client.setQueryData(['social', 'operation', viewer, job.operation_id], job)
  }, onError: () => { if (!approval) void relation.refetch() } })
  const recovery = useMutation({ networkMode: 'always', mutationFn: async () => {
    const job = followJobSchema.parse(await request(`${socialRoot}/operations/${operationId}/retry`, { method: 'POST' }))
    if (job.operation_id !== operationId || job.follower_id !== followerId || job.followed_id !== followedId) throw new Error('No se pudo confirmar la recuperación de este seguimiento.')
    return job
  }, onSuccess: (job) => {
    client.setQueryData(['social', 'operation', viewer, job.operation_id], job)
    putAttempt(client, viewer, { follower_id: followerId, followed_id: followedId, action: job.action,
      key: attempt?.key ?? null, operation_id: job.operation_id, status: job.status })
  } })
  const handled = useRef(new Set<string>())
  useEffect(() => {
    const job = operation.data
    if (!job || change.isPending || recovery.isPending) return
    const id = `${job.operation_id}:${job.status}`
    if (handled.current.has(id)) return
    handled.current.add(id)
    putAttempt(client, viewer, { follower_id: followerId, followed_id: followedId, action: job.action,
      key: attempt?.operation_id === job.operation_id || !attempt?.operation_id ? attempt?.key ?? null : null,
      operation_id: job.operation_id, status: job.status })
    if (terminal(job.status)) void refreshSocial(client, viewer)
  }, [operation.data, change.isPending, recovery.isPending, client, viewer, followerId, followedId, attempt?.key, attempt?.operation_id])
  const previous = useRef<string | null>(null)
  useEffect(() => {
    const status = relation.data?.status
    if (approval || !status || status === 'processing') return
    if (previous.current && previous.current !== status) void refreshSocial(client, viewer)
    previous.current = status
  }, [relation.data?.status, client, viewer, approval])

  const job = operation.data
  const uncertain = !!attempt && !attempt.operation_id && !operationId
  const busy = change.isPending || recovery.isPending || !!operationId && (operation.isPending || operation.isError || !!job && !terminal(job.status))
  const approved = approval && job?.status === 'completed'
  const frozen = busy || approved || (!approval && (relation.isPending || relation.isError || relation.data?.status === 'processing')) || job?.status === 'failed'
  const state = relation.data?.status
  const action = approval ? 'approve' : state === 'none' ? 'follow' : 'unfollow'
  const label = approval ? approved ? 'Solicitud aprobada' : 'Aprobar solicitud' : state === 'accepted' ? 'Dejar de seguir' : state === 'pending' ? 'Cancelar solicitud' : 'Seguir'
  return <div className="follow-control">
    {!approval && relation.isPending && <p role="status">Consultando seguimiento…</p>}
    {!approval && relation.isError && <div role="alert">No pudimos consultar el seguimiento. <button className="button-secondary" onClick={() => void relation.refetch()}>Reintentar seguimiento</button></div>}
    {!approval && state === 'accepted' && <p className="follow-state">Siguiendo</p>}
    {!approval && state === 'pending' && <p className="follow-state">Solicitud enviada</p>}
    {!approval && state === 'none' && accountType === 'private' && <p className="muted">Esta cuenta debe aprobar tu solicitud.</p>}
    {busy && <p role="status">Procesando cambio de seguimiento…</p>}
    {operation.isError && <div role="alert">No pudimos confirmar el resultado. <button className="button-secondary" onClick={() => void operation.refetch()}>Consultar resultado</button></div>}
    {job?.status === 'failed' && <div role="alert"><p>El cambio requiere recuperación antes de continuar.</p>
      <button className="button-secondary" disabled={recovery.isPending} onClick={() => recovery.mutate()}>Reintentar recuperación</button></div>}
    {job?.status === 'compensated' && <p role="status">El cambio se revirtió. Se conservó el estado anterior; podés volver a intentarlo.</p>}
    {job?.error && job.status !== 'completed' && terminal(job.status) && <p role="alert">{job.error}</p>}
    {(change.isError && !job || recovery.isError) && <p role="alert">{(recovery.error ?? change.error)?.message}</p>}
    {uncertain ? <div><p>Hay un envío pendiente de confirmar. Reintentalo para consultar el mismo pedido.</p>
      <button className="button-secondary" disabled={busy} onClick={() => change.mutate({ action: attempt.action, replay: true })}>Confirmar envío pendiente</button></div>
      : <button className={state === 'accepted' ? 'button-secondary' : 'button-primary'} disabled={frozen} onClick={() => change.mutate({ action })}>
        {label}</button>}
  </div>
}
