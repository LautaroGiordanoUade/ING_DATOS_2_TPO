import { Link } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { SetupPage } from '../system/SetupPage'
import { MyPostsPage } from './MyPostsPage'
import { ErrorMessage } from '../../components/common/ErrorMessage'

export function HomePage() {
  const auth = useAuth()
  if (auth.status === 'loading') return <p className="page-content" role="status">Validando tu sesión…</p>
  if (auth.status === 'error') return <section className="page-content"><h1>No pudimos validar tu sesión</h1><ErrorMessage message={auth.error ?? 'Error de conexión.'} /><button className="button-secondary" onClick={auth.retry}>Volver a intentar</button> <button className="button-secondary" onClick={auth.signOut}>Cerrar sesión</button></section>
  if (auth.user) return <MyPostsPage />
  return <><SetupPage /><div className="guest-actions"><Link className="button-primary" to="/registro">Crear mi cuenta</Link><Link className="button-secondary" to="/login">Ya tengo cuenta</Link></div></>
}
