import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { previewSchema } from './contracts'

export function DistributionPreview({ postId }: { postId: string }) {
  const { request } = useAuth()
  const [input, setInput] = useState('')
  const [recipient, setRecipient] = useState<string | null>(null)
  const [invalid, setInvalid] = useState(false)
  const preview = useQuery({
    queryKey: ['publication-preview', recipient], enabled: !!recipient,
    queryFn: async ({ signal }) => previewSchema.parse(await request(`/api/v1/problems/1/feed-preview/${recipient}`, { signal })),
    networkMode: 'always', staleTime: 0,
  })
  return <section className="card preview-card"><h2>Comprobar distribución</h2><p className="muted">Consultá los identificadores visibles de una cuenta seguidora. Esta comprobación corresponde a P1.</p>
    <form noValidate onSubmit={(event) => { event.preventDefault(); const id = input.trim(); if (!z.uuid().safeParse(id).success) { setInvalid(true); return } setInvalid(false); if (id === recipient) void preview.refetch(); else setRecipient(id) }}>
      <label htmlFor="recipient">UUID de la cuenta destinataria</label><div className="inline-form"><input id="recipient" value={input} onChange={(event) => setInput(event.target.value)} aria-invalid={invalid} aria-describedby={invalid ? 'recipient-error' : undefined} /><button className="button-secondary" disabled={preview.isFetching}>Comprobar</button></div>
      {invalid && <p id="recipient-error" className="field-error" role="alert">Ingresá un UUID válido.</p>}
    </form>
    {preview.isFetching && <p role="status">Consultando distribución…</p>}
    {preview.isError && <ErrorMessage message={preview.error.message} />}
    {preview.data && !preview.isError && !preview.isFetching && <p className={preview.data.post_ids.includes(postId) ? 'success-message' : 'muted'} role="status">{preview.data.post_ids.includes(postId) ? 'La publicación está visible para esta cuenta.' : 'La publicación no figura entre los IDs visibles de esta cuenta.'}</p>}
  </section>
}
