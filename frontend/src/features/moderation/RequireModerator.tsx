import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { canModerate } from './api'

export function ModerationDenied() {
  return <section className="page-content"><h1>Acceso restringido</h1><p role="alert">No tenés permisos para consultar esta información.</p><Link to="/">Volver al inicio</Link></section>
}
export function RequireModerator() {
  const { user } = useAuth()
  return canModerate(user?.role) ? <Outlet /> : <ModerationDenied />
}
