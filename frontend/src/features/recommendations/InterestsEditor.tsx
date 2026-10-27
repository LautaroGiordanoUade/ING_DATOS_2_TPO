import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/context'
import { saveInterests } from './api'

export function InterestsEditor() {
  const { user, request } = useAuth()
  const client = useQueryClient()
  const [tags, setTags] = useState(user?.interests ?? [])
  const [input, setInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  function proposedTags(): string[] | null {
    const tag = input.normalize('NFKC').trim().replace(/\s+/gu, ' ').toLowerCase()
    if (!tag) return tags
    if (Array.from(tag).length > 40) {
      setError('Cada interés puede tener hasta 40 caracteres.')
      return null
    }
    const next = tags.includes(tag) ? tags : [...tags, tag]
    if (next.length > 20) {
      setError('Elegí hasta 20 intereses.')
      return null
    }
    return next
  }

  function addTag() {
    setError(null)
    const next = proposedTags()
    if (next) { setTags(next); setInput(''); setSaved(false) }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setSaved(false)
    const next = proposedTags()
    if (!next) return
    setSaving(true)
    try {
      const profile = await saveInterests(request, next)
      setTags(profile.interests ?? [])
      setInput('')
      await Promise.all([
        client.invalidateQueries({ queryKey: ['auth', 'me'] }),
        client.invalidateQueries({ queryKey: ['users', 'profile', user!.id] }),
        client.invalidateQueries({ queryKey: ['recommendations', user!.id] }),
      ])
      setSaved(true)
    } catch {
      setError('No pudimos guardar tus intereses. Conservamos la edición para que reintentes.')
    } finally { setSaving(false) }
  }

  if (!user) return null
  return (
    <section className="card interests-editor" aria-labelledby="my-interests-title">
      <h2 id="my-interests-title">Mis intereses</h2>
      <p>Elegí hasta 20 temas de hasta 40 caracteres. Se usan para ordenar tus sugerencias.</p>
      <form onSubmit={(event) => void save(event)}>
        <ul className="interest-tags" aria-label="Mis intereses elegidos">
          {tags.map((tag) => <li key={tag}>
            {tag}{' '}
            <button type="button" aria-label={`Quitar ${tag}`} disabled={saving} onClick={() => {
              setTags(tags.filter((value) => value !== tag)); setSaved(false)
            }}>×</button>
          </li>)}
        </ul>
        {tags.length === 0 && <p>Todavía no elegiste intereses. Podemos sugerirte cuentas por tus conexiones.</p>}
        <label htmlFor="interest-input">Agregar interés</label>
        <div className="inline-form">
          <input id="interest-input" value={input} disabled={saving} placeholder="Por ejemplo: música" onChange={(event) => {
            setInput(event.target.value); setSaved(false)
          }} />
          <button type="button" className="button-secondary" disabled={saving || !input.trim()} onClick={addTag}>Agregar</button>
        </div>
        <button className="button-primary" type="submit" disabled={saving}>
          {saving ? 'Guardando intereses…' : 'Guardar intereses'}
        </button>
        {error && <p role="alert">{error}</p>}
        {saved && <p role="status">Intereses guardados.</p>}
      </form>
    </section>
  )
}
