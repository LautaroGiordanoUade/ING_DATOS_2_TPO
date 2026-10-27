import { useEffect, useRef, useState } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { ApiError } from '../../services/http/client'
import { groupSchema, pageSchema, participantSchema, root, sendMessage, type Participant } from './api'

function errorText(error: unknown) { return error instanceof Error ? error.message : 'No pudimos completar la solicitud.' }

function NewGroup({ onCreated }: { onCreated: (id: string) => void }) {
  const { request, user } = useAuth()
  const [name, setName] = useState('')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Participant[]>([])
  const attempt = useRef({ fingerprint: '', key: '' })
  useEffect(() => { const timer = setTimeout(() => setSearch(query.trim()), 250); return () => clearTimeout(timer) }, [query])
  const results = useQuery({ queryKey: ['message-participants', user?.id, search],
    enabled: search.length >= 2, retry: false,
    queryFn: async ({ signal }) => z.array(participantSchema).parse(await request(`${root}/participants?q=${encodeURIComponent(search)}`, { signal })),
  })
  const create = useMutation({ mutationFn: async () => {
    const payload = { name: name.trim(), participant_ids: selected.map((p) => p.id) }
    const fingerprint = JSON.stringify(payload)
    if (attempt.current.fingerprint !== fingerprint) attempt.current = { fingerprint, key: crypto.randomUUID() }
    return groupSchema.parse(await request(`${root}/conversations`, { method: 'POST',
      headers: { 'Idempotency-Key': attempt.current.key }, body: JSON.stringify(payload) }))
  }, onSuccess: (group) => { onCreated(group.id) } })
  return <form className="new-group" onSubmit={(event) => { event.preventDefault(); create.mutate() }}>
    <h2>Nuevo grupo</h2>
    <label>Nombre del grupo<input required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} disabled={create.isPending} /></label>
    <label>Buscar participantes por usuario<input value={query} maxLength={50} onChange={(e) => setQuery(e.target.value)} disabled={create.isPending} /></label>
    <p className="muted">Vos y hasta 19 participantes más. Buscá con al menos dos letras.</p>
    {results.isFetching && <p role="status">Buscando…</p>}
    {results.isError && <p role="alert">{errorText(results.error)}</p>}
    {search.length >= 2 && results.data?.length === 0 && <p>No encontramos usuarios.</p>}
    <ul className="participant-results">{results.data?.filter((p) => !selected.some((s) => s.id === p.id)).map((p) => <li key={p.id}>
      <button type="button" disabled={selected.length >= 19 || create.isPending} onClick={() => { setSelected([...selected, p]); setQuery('') }}>
        Agregar @{p.username} · {p.full_name}</button>
    </li>)}</ul>
    <ul className="participant-results">{selected.map((p) => <li key={p.id}>@{p.username}{' '}
      <button type="button" disabled={create.isPending} onClick={() => setSelected(selected.filter((s) => s.id !== p.id))}>Quitar @{p.username}</button></li>)}</ul>
    {create.isError && <p role="alert">{errorText(create.error)} Podés volver a intentar.</p>}
    <button className="button-primary" disabled={create.isPending || !name.trim() || !selected.length}>{create.isPending ? 'Creando…' : 'Crear grupo'}</button>
  </form>
}

function Chat({ id }: { id: string }) {
  const { request, user } = useAuth()
  const client = useQueryClient()
  const [text, setText] = useState('')
  const historyElement = useRef<HTMLOListElement>(null)
  const stickToBottom = useRef(true)
  const attempt = useRef({ text: '', key: '' })
  const group = useQuery({ queryKey: ['message-group', user?.id, id], retry: false,
    queryFn: async ({ signal }) => groupSchema.parse(await request(`${root}/conversations/${id}`, { signal })) })
  const history = useInfiniteQuery({ queryKey: ['message-history', user?.id, id],
    initialPageParam: null as number | null, enabled: Boolean(group.data), retry: false,
    queryFn: async ({ pageParam, signal }) => pageSchema.parse(await request(`${root}/conversations/${id}/messages${pageParam ? `?before=${pageParam}` : ''}`, { signal })),
    getNextPageParam: (last) => last.next_before ?? undefined,
    refetchInterval: () => document.visibilityState === 'visible' ? 3000 : false,
    refetchOnWindowFocus: true,
  })
  const invalidate = () => Promise.all([
    client.invalidateQueries({ queryKey: ['message-history', user?.id, id] }),
    client.invalidateQueries({ queryKey: ['message-groups', user?.id] }),
    client.invalidateQueries({ queryKey: ['message-group', user?.id, id] }),
  ])
  const send = useMutation({ mutationFn: async () => {
    const value = text.trim()
    if (attempt.current.text !== value) attempt.current = { text: value, key: crypto.randomUUID() }
    return sendMessage(request, id, value, attempt.current.key)
  }, onSuccess: async () => { setText(''); attempt.current = { text: '', key: '' }; stickToBottom.current = true; await invalidate() } })
  const seen = new Set<string>()
  const items = (history.data?.pages.flatMap((p) => p.items) ?? []).filter((m) => {
    if (seen.has(m.id)) return false; seen.add(m.id); return true
  }).sort((a, b) => a.sequence - b.sequence)
  const last = items.at(-1)
  useEffect(() => {
    const element = historyElement.current
    if (element && stickToBottom.current) element.scrollTop = element.scrollHeight
  }, [last?.id])
  const read = useMutation({ mutationFn: async () => {
    if (!last) return
    await request(`${root}/conversations/${id}/read`, { method: 'PUT', body: JSON.stringify({ message_id: last.id }) })
  }, onSuccess: invalidate })
  if (group.isPending) return <p role="status">Cargando conversación…</p>
  if (group.isError || (history.error instanceof ApiError && [401, 404].includes(history.error.status))) return <div role="alert">
    Conversación no disponible. <button onClick={() => { void group.refetch(); void history.refetch() }}>Volver a comprobar</button></div>
  return <section className="chat-panel" aria-label="Conversación">
    <Link className="chat-back" to="/mensajes">← Volver a grupos</Link>
    <h2>{group.data.name}</h2>
    <p className="muted">{group.data.participants.map((p) => `@${p.username}`).join(', ')}</p>
    <div className="chat-actions">
      <button className="button-secondary" onClick={() => void history.refetch()} disabled={history.isFetching}>Actualizar mensajes</button>
      <button className="button-secondary" disabled={!last || read.isPending} onClick={() => read.mutate()}>Marcar hasta el último como leído</button>
    </div>
    <p className="muted">Se actualiza cada 3 segundos mientras esta pestaña esté visible. Marcar como leído incluye los mensajes anteriores.</p>
    {history.isPending && <p role="status">Cargando mensajes…</p>}
    {history.isError && <p role="alert">{errorText(history.error)} <button onClick={() => void history.refetch()}>Reintentar historial</button></p>}
    {history.hasNextPage && <button className="button-secondary" disabled={history.isFetching} onClick={() => { stickToBottom.current = false; void history.fetchNextPage() }}>Cargar mensajes anteriores</button>}
    {!history.isPending && !history.isError && !items.length && <p>Este grupo todavía no tiene mensajes.</p>}
    <ol className="chat-history" aria-label="Historial de mensajes" ref={historyElement} tabIndex={0} onScroll={(event) => {
      const element = event.currentTarget
      stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 60
    }}>{items.map((m) => <li className={m.sender_id === user?.id ? 'chat-message own' : 'chat-message'} key={m.id}>
      <strong>{m.sender_id === user?.id ? 'Vos' : m.author_name}</strong>
      <p>{m.text}</p><time dateTime={m.created_at}>{new Date(m.created_at).toLocaleString('es-AR')}</time>
      {m.delivery_status === 'pending' && <span className="chat-pending">Guardado · distribución pendiente</span>}
    </li>)}</ol>
    {read.isError && <p role="alert">{errorText(read.error)}</p>}
    <form className="chat-compose" onSubmit={(e) => { e.preventDefault(); send.mutate() }}>
      <label>Mensaje<textarea required maxLength={4000} value={text} disabled={send.isPending} onChange={(e) => setText(e.target.value)} /></label>
      {send.isError && <p role="alert">{errorText(send.error)} El texto se conserva; podés reintentar.</p>}
      <button className="button-primary" disabled={!text.trim() || send.isPending}>{send.isPending ? 'Enviando…' : 'Enviar mensaje'}</button>
    </form>
  </section>
}

export function MessagesPage() {
  const { request, user } = useAuth()
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [creating, setCreating] = useState(false)
  const groups = useInfiniteQuery({ queryKey: ['message-groups', user?.id], initialPageParam: null as string | null,
    queryFn: async ({ pageParam, signal }) => z.array(groupSchema).parse(await request(`${root}/conversations?limit=20${pageParam ? `&before=${pageParam}` : ''}`, { signal })),
    getNextPageParam: (last) => last.length === 20 ? last.at(-1)?.id : undefined,
    retry: false, refetchInterval: () => document.visibilityState === 'visible' ? 5000 : false,
  })
  useEffect(() => {
    const heartbeat = () => { if (document.visibilityState === 'visible') void request('/api/v1/accounts/me/presence', { method: 'PUT' }).catch(() => {}) }
    heartbeat(); const timer = setInterval(heartbeat, 45_000)
    document.addEventListener('visibilitychange', heartbeat)
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', heartbeat) }
  }, [request])
  const seen = new Set<string>()
  const list = (groups.data?.pages.flat() ?? []).filter((g) => { if (seen.has(g.id)) return false; seen.add(g.id); return true })
  return <div className={`page-content messages-page ${conversationId ? 'chat-open' : ''}`}>
    <header className="page-intro"><p className="eyebrow">TU COMUNIDAD</p><h1>Mensajes</h1><p>Conversaciones para seguir compartiendo.</p></header>
    <div className="messages-grid">
      <aside className="card group-list" aria-label="Tus grupos">
        <h2>Tus grupos</h2><button className="button-secondary" onClick={() => { setCreating(!creating); navigate('/mensajes') }}>{creating ? 'Cancelar nuevo grupo' : 'Nuevo grupo'}</button>
        {creating && <NewGroup onCreated={(id) => { setCreating(false); void client.invalidateQueries({ queryKey: ['message-groups', user?.id] }); navigate(`/mensajes/${id}`) }} />}
        {groups.isPending && <p role="status">Cargando grupos…</p>}
        {groups.isError && <p role="alert">{errorText(groups.error)} <button onClick={() => void groups.refetch()}>Reintentar grupos</button></p>}
        {!groups.isPending && !groups.isError && !list.length && <p>Todavía no participás de ningún grupo.</p>}
        <ul>{list.map((g) => <li key={g.id}><Link aria-current={g.id === conversationId ? 'page' : undefined} to={`/mensajes/${g.id}`}>{g.name}<span>{g.unread} sin leer</span></Link></li>)}</ul>
        {groups.hasNextPage && <button className="button-secondary" disabled={groups.isFetching} onClick={() => void groups.fetchNextPage()}>Cargar más grupos</button>}
      </aside>
      <div className="card chat-container">{conversationId ? <Chat key={conversationId} id={conversationId} /> : <p className="chat-placeholder">Elegí un grupo o creá uno para empezar a conversar.</p>}</div>
    </div>
  </div>
}
