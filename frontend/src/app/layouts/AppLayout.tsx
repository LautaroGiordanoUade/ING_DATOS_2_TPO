import { NavLink, Outlet } from 'react-router-dom'
import { Suspense } from 'react'
import { useAuth } from '../../features/auth/context'

export function AppLayout() {
  const auth = useAuth()
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Saltar al contenido</a>
      <aside className="sidebar">
        <NavLink className="brand" to="/" aria-label="Niche, inicio"><span className="brand-mark" aria-hidden="true">n</span>Niche<span className="brand-dot">.</span></NavLink>
        <p className="brand-caption">Un lugar para tus intereses.</p>
        <nav aria-label="Navegación principal">
          <NavLink to="/" end className="nav-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" /></svg>Inicio</NavLink>
          {auth.user && <NavLink to="/publicar" className="nav-item"><span aria-hidden="true">＋</span>Publicar</NavLink>}
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
