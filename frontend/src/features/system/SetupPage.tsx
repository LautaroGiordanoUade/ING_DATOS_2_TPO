import { ConnectionStatus } from './ConnectionStatus'

export function SetupPage() {
  return (
    <div className="page-content">
      <div className="page-intro"><span className="eyebrow">BIENVENIDO A NICHE</span><h1>Lo que te interesa,<br /><span>nos encuentra.</span></h1><p>Un espacio para compartir ideas y conectar<br className="desktop-break" /> con personas que tienen algo en común.</p></div>
      <section className="card welcome-card" aria-labelledby="welcome-title"><div className="community-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><span className="art-node node-one">✳</span><span className="art-node node-two">↗</span><span className="art-node node-three">◈</span><span className="art-center">n<span>.</span></span><div className="art-caption">Ideas que conectan.</div></div><div className="welcome-copy"><span className="pill">Tu comunidad empieza acá</span><h2 id="welcome-title">Cada comunidad<br />tiene un comienzo.</h2><p>Creá tu cuenta y compartí una idea sobre lo que te interesa. Tu primera publicación puede ser ese comienzo.</p><div className="next-step"><span aria-hidden="true">01</span><div><strong>Tu primera idea</strong><p>Un texto, tus intereses y algo para compartir.</p></div></div></div></section>
      <ConnectionStatus />
      <p className="preparation-note">Tu cuenta y tus publicaciones, en un mismo lugar.</p>
    </div>
  )
}
