import { useQuery } from '@tanstack/react-query'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { getReadiness } from './api'

const services = [['mongodb', 'MongoDB'], ['redis', 'Redis'], ['neo4j', 'Neo4j']] as const

export function ConnectionStatus() {
  const query = useQuery({ queryKey: ['system', 'readiness'], queryFn: ({ signal }) => getReadiness(signal), networkMode: 'always' })
  const ready = query.data?.status === 'ready' && !query.isError
  return (
    <section className="card connection-card" aria-labelledby="connection-title" aria-busy={query.isFetching}>
      <div className="section-heading"><div><p className="eyebrow">Todo empieza con una conexión</p><h2 id="connection-title">Estado del servicio</h2></div><span className={`status-badge ${ready ? 'is-ready' : ''}`} role="status">{query.isFetching ? 'Comprobando…' : query.isError ? 'Sin conexión' : ready ? 'Conectado' : 'Servicio limitado'}</span></div>
      <p className="muted">Comprobamos que la API y los servicios de tu comunidad estén disponibles.</p>
      {query.isError && <ErrorMessage message={query.error.message} />}
      {query.data && !query.isError && <ul className="service-list" aria-label="Servicios del backend">{services.map(([key, label]) => <li key={key}><span><span className={`service-dot ${query.data.services[key] === 'ok' ? 'is-ready' : ''}`} aria-hidden="true" />{label}</span><span>{query.data.services[key] === 'ok' ? 'Disponible' : 'No disponible'}</span></li>)}</ul>}
      <div className="connection-action"><span>La disponibilidad se consulta en tiempo real.</span><button className="button-secondary" onClick={() => void query.refetch()} disabled={query.isFetching}>{query.isFetching ? 'Comprobando…' : 'Volver a comprobar'}</button></div>
    </section>
  )
}
