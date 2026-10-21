import { afterEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConnectionStatus } from './ConnectionStatus'

afterEach(() => { vi.unstubAllGlobals(); onlineManager.setOnline(true) })

function renderStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(<QueryClientProvider client={client}><ConnectionStatus /></QueryClientProvider>)
}

const ready = { status: 'ready', services: { mongodb: 'ok', redis: 'ok', neo4j: 'ok' } }

it('anuncia carga y deshabilita reintentar mientras espera', () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise(() => {})))
  renderStatus()
  expect(screen.getByRole('status')).toHaveTextContent('Comprobando…')
  expect(screen.getByRole('button')).toBeDisabled()
  expect(screen.getByRole('region')).toHaveAttribute('aria-busy', 'true')
})

it('muestra servicios de una conexión saludable', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(ready)))
  renderStatus()
  expect(await screen.findByText('Conectado')).toBeVisible()
  expect(screen.getAllByText('Disponible')).toHaveLength(3)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('muestra degradación con el servicio afectado', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ status: 'degraded', services: { ...ready.services, redis: 'unavailable' } }, { status: 503 })))
  renderStatus()
  expect(await screen.findByText('Servicio limitado')).toBeVisible()
  expect(screen.getByText('No disponible')).toBeVisible()
  expect(screen.getAllByText('Disponible')).toHaveLength(2)
})

it('permite reintentar por teclado después de una falla de red', async () => {
  const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(Response.json(ready))
  vi.stubGlobal('fetch', fetcher)
  renderStatus()
  expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos conectar')
  const user = userEvent.setup()
  await user.tab()
  expect(screen.getByRole('button', { name: 'Volver a comprobar' })).toHaveFocus()
  await user.keyboard('{Enter}')
  expect(await screen.findByText('Conectado')).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('retira el estado anterior si la actualización falla', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(ready)).mockRejectedValueOnce(new TypeError('offline')))
  renderStatus()
  await screen.findByText('Conectado')
  await userEvent.click(screen.getByRole('button', { name: 'Volver a comprobar' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('status')).toHaveTextContent('Sin conexión')
  expect(screen.queryByText('Disponible')).not.toBeInTheDocument()
})

it('informa el error aunque el navegador ya se considere sin conexión', async () => {
  onlineManager.setOnline(false)
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
  renderStatus()
  expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos conectar')
  expect(screen.getByRole('status')).toHaveTextContent('Sin conexión')
})
