import type { ReactNode } from 'react'

export function FormField({ id, label, error, hint, children }: {
  id: string; label: string; error?: string | undefined; hint?: string; children: ReactNode
}) {
  return <div className="form-field">
    <label htmlFor={id}>{label}</label>
    {hint && <p id={`${id}-hint`} className="field-hint">{hint}</p>}
    {children}
    {error && <p id={`${id}-error`} className="field-error" role="alert">{error}</p>}
  </div>
}
