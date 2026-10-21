import { ConnectionStatus } from './ConnectionStatus'

export function SetupPage() {
  return (
    <div className="page-content">
      <div className="page-intro"><span className="eyebrow">BIENVENIDO A NICHE</span><h1>Lo que te interesa,<br /><span>nos encuentra.</span></h1><p>Un espacio para compartir ideas y conectar<br className="desktop-break" /> con personas que tienen algo en común.</p></div>
      <section className="card welcome-card" aria-labelledby="welcome-title"><div className="community-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><span className="art-node node-one">✳</span><span className="art-node node-two">↗</span><span className="art-node node-three">◈</span><span className="art-center">n<span>.</span></span><div className="art-caption">Ideas que conectan.</div></div><div className="welcome-copy"><span className="pill">Estamos preparando tu espacio</span><h2 id="welcome-title">Cada comunidad<br />tiene un comienzo.</h2><p>La base de Niche ya está en marcha. Las publicaciones y las conexiones llegarán en las próximas etapas.</p><div className="next-step"><span aria-hidden="true">01</span><div><strong>El próximo paso</strong><p>Crear tu cuenta y compartir tu primera publicación.</p></div></div></div></section>
      <ConnectionStatus />
      <p className="preparation-note">Preparación inicial · Las funciones de la comunidad todavía no están habilitadas.</p>
    </div>
  )
}
