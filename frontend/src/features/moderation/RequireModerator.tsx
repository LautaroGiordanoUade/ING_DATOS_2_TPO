import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { canModerate } from './contracts'

export function RequireModerator() {
  const { user } = useAuth()
  if (!canModerate(user?.role)) return <section className="page-content"><h1>Acceso restringido</h1><p>Esta sección es exclusiva para moderadores y administradores.</p><Link to="/">Volver al inicio</Link></section>
  return <Outlet />
}
