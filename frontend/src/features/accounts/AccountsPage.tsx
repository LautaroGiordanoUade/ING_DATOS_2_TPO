import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '../auth/context'
import { canModerate } from '../moderation/contracts'
import { FormField } from '../../components/common/FormField'
import { accountActions, lookupSchema } from './contracts'
import { recentAccountOperations } from './attempts'

export function AccountsPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const moderator = canModerate(user?.role)
  const { register, handleSubmit, formState: { errors } } = useForm<z.input<typeof lookupSchema>, unknown, z.output<typeof lookupSchema>>({ resolver: zodResolver(lookupSchema), defaultValues: { userId: '' } })
  const recent = moderator ? recentAccountOperations(user!.id) : []
  return <div className="page-content accounts-page">
    <div className="page-title"><p className="eyebrow">CUENTAS Y TRAZABILIDAD</p><h1>{moderator ? 'Gestión de cuentas' : 'Mi cuenta'}</h1><p className="muted">Perfil, relaciones, publicaciones y conversaciones reunidos en una consulta.</p></div>
    <section className="card account-card"><h2>Tu información</h2><p className="muted">Consultá tu cuenta y su presencia actual.</p><Link className="button-secondary" to={`/cuentas/${user!.id}`}>Ver mi trazabilidad</Link></section>
    {moderator && <section className="card account-card"><h2>Consultar una cuenta</h2><p className="muted">Ingresá su identificador para revisar el estado, consultar su trazabilidad o administrar una suspensión.</p><form noValidate onSubmit={handleSubmit(({ userId }) => navigate(`/cuentas/${userId}`))}><FormField id="lookup-user" label="Identificador de usuario" error={errors.userId?.message}><input id="lookup-user" {...register('userId')} autoComplete="off" spellCheck={false} aria-invalid={!!errors.userId} aria-describedby={errors.userId ? 'lookup-user-error' : undefined} /></FormField><button className="button-primary" type="submit">Consultar cuenta</button></form></section>}
    {recent.length > 0 && <details className="card account-card"><summary>Operaciones recientes de esta pestaña</summary><ul className="account-reference-list">{recent.map((job) => <li key={job.operation_id}><Link to={`/cuentas/operaciones/${job.operation_id}`}>{accountActions[job.action]} · <code>{job.user_id}</code></Link></li>)}</ul></details>}
  </div>
}
