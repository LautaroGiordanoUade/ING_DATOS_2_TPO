import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './context'
import { ErrorMessage } from '../../components/common/ErrorMessage'

export function RequireAuth() {
  const auth = useAuth()
  const location = useLocation()
  if (auth.status === 'guest') return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (auth.status === 'loading') return <p className="page-content" role="status">Validando tu sesión…</p>
  if (auth.status === 'error') return <section className="page-content"><h1>No pudimos validar tu sesión</h1><ErrorMessage message={auth.error ?? 'Error de conexión.'} /><button className="button-secondary" onClick={auth.retry}>Volver a intentar</button> <button className="button-secondary" onClick={auth.signOut}>Cerrar sesión</button></section>
  return <Outlet />
}
