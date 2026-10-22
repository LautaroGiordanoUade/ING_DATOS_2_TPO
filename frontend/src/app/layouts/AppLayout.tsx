import { NavLink, Outlet } from 'react-router-dom'
import { Suspense } from 'react'
import { useAuth } from '../../features/auth/context'
import { canModerate } from '../../features/moderation/contracts'

export function AppLayout() {
  const auth = useAuth()
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Saltar al contenido</a>
      <aside className="sidebar">
        <NavLink className="brand" to="/" aria-label="Niche, inicio"><span className="brand-mark" aria-hidden="true">n</span>Niche<span className="brand-dot">.</span></NavLink>
        <p className="brand-caption">Un lugar para tus intereses.</p>
        <nav aria-label="Navegación principal">
          <NavLink to="/" end className="nav-item" aria-label="Inicio"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" /></svg><span className="nav-label">Inicio</span></NavLink>
          {auth.user && <><NavLink to="/mis-publicaciones" className="nav-item" aria-label="Mis publicaciones"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></svg><span className="nav-label">Mis publicaciones</span></NavLink><NavLink to="/publicar" className="nav-item" aria-label="Publicar"><span className="nav-plus" aria-hidden="true">＋</span><span className="nav-label">Publicar</span></NavLink></>}
          {canModerate(auth.user?.role) && <NavLink to="/moderacion" className="nav-item moderation-nav" aria-label="Moderación"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z" /><path d="m8 12 3 3 5-6" /></svg><span className="nav-label">Moderación</span></NavLink>}
        </nav>
        <div className="sidebar-note"><span className="small-dot" aria-hidden="true" /><div><strong>Ideas que conectan</strong><p>Construida paso a paso.</p></div></div>
        <div className="sidebar-footer">Niche Social Network<br /><span>Ingeniería de Datos · TPI</span></div>
      </aside>
      <div className="workspace">
        <header className="topbar"><span>Tu comunidad</span><div className="session-actions">{auth.user ? <><span className="session-name">@{auth.user.username}</span><button className="button-secondary" onClick={auth.signOut}>Cerrar sesión</button></> : auth.status === 'guest' ? <NavLink className="button-secondary" to="/login">Iniciar sesión</NavLink> : <span className="stage-label">Validando sesión</span>}</div></header>
        <main id="main" tabIndex={-1}><Suspense fallback={<p className="page-content" role="status">Cargando pantalla…</p>}><Outlet /></Suspense></main>
        <footer className="page-footer">Compartir empieza por tener algo en común.<span>Niche · 2026</span></footer>
      </div>
    </div>
  )
}
