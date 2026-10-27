import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { storage } from '../../lib/storage'
import { ApiError } from '../../services/http/client'
import { reasonLabels, reportSchema, root } from './api'

export function ReportForm({ postId }: { postId: string }) {
  const { user, request } = useAuth()
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<keyof typeof reasonLabels>('spam')
  const [description, setDescription] = useState('')
  const key = ['report-receipt', user?.id, postId]
  const storageKey = `niche.p7.report.${user?.id}.${postId}`
  const receipt = useQuery({ queryKey: key, initialData: () => z.guid().safeParse(storage.get(storageKey)).data ?? null,
    queryFn: () => null as string | null, enabled: false, staleTime: Infinity })
  const [duplicate, setDuplicate] = useState(false)
  const send = useMutation({ networkMode: 'always', mutationFn: async () => reportSchema.parse(await request(`${root}/reports`, {
    method: 'POST', body: JSON.stringify({ post_id: postId, reason, description: description.trim() || null }),
  })), onSuccess: (report) => {
    storage.set(storageKey, report.id); client.setQueryData(key, report.id); setOpen(false)
  }, onError: (error) => {
    if (error instanceof ApiError && error.status === 409 && /already reported/i.test(error.message)) { setDuplicate(true); setOpen(false) }
  } })
  if (!user) return null
  if (receipt.data) return <p className="report-receipt" role="status">Reporte recibido. <Link to={`/reportes/${receipt.data}`}>Ver mi reporte</Link></p>
  if (duplicate) return <p className="report-receipt" role="status">Ya enviaste un reporte sobre esta publicación.</p>
  return <div className="report-form">
    {!open ? <button type="button" className="report-toggle" onClick={() => setOpen(true)}>Reportar publicación</button> : <form onSubmit={(event) => { event.preventDefault(); send.mutate() }}>
      <h3>Reportar publicación</h3><p>El equipo de moderación revisará tu reporte.</p>
      <label>Motivo del reporte<select value={reason} disabled={send.isPending} onChange={(e) => setReason(e.target.value as keyof typeof reasonLabels)}>
        {Object.entries(reasonLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
      </select></label>
      <label>Descripción del reporte (opcional)<textarea value={description} maxLength={2000} disabled={send.isPending} onChange={(e) => setDescription(e.target.value)} /></label>
      {send.isError && <p role="alert">{send.error.message}</p>}
      <div className="moderation-actions"><button className="button-primary" disabled={send.isPending}>{send.isPending ? 'Enviando reporte…' : 'Enviar reporte'}</button>
        <button type="button" className="button-secondary" disabled={send.isPending} onClick={() => setOpen(false)}>Cancelar reporte</button></div>
    </form>}
  </div>
}
