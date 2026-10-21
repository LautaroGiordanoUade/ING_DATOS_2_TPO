import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './AuthProvider'
import { useAuth } from './context'
import { SESSION_KEY } from './api'
import { user } from '../../../tests/fixtures/session'

function Probe() {
  const auth = useAuth()
  return <><p role="status">{auth.status}</p><span>{auth.user?.username}</span><button onClick={auth.signOut}>Salir</button><button onClick={auth.retry}>Reintentar</button></>
}
function renderAuth() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  render(<QueryClientProvider client={client}><AuthProvider><Probe /></AuthProvider></QueryClientProvider>)
  return client
}
beforeEach(() => sessionStorage.clear())
afterEach(() => vi.unstubAllGlobals())
it('restaura sesión solo después de validar el bearer en el servidor', async () => {
  sessionStorage.setItem(SESSION_KEY, 'opaque-token')
  const fetcher = vi.fn().mockResolvedValue(Response.json(user))
  vi.stubGlobal('fetch', fetcher)
  renderAuth()
  expect(screen.getByRole('status')).toHaveTextContent('loading')
  await screen.findByText(user.username)
  const call = fetcher.mock.calls[0] as [string, RequestInit]
  expect(call[0]).toBe('/backend/api/v1/users/me')
  expect(new Headers(call[1].headers).get('Authorization')).toBe('Bearer opaque-token')
})
it('borra credencial y caché al salir', async () => {
  sessionStorage.setItem(SESSION_KEY, 'opaque-token')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(user)))
  const client = renderAuth()
  await screen.findByText(user.username)
  client.setQueryData(['private-posts'], ['private'])
  await userEvent.click(screen.getByRole('button', { name: 'Salir' }))
  expect(screen.getByRole('status')).toHaveTextContent('guest')
  expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
  expect(client.getQueryData(['private-posts'])).toBeUndefined()
})
it('invalida automáticamente una sesión expirada o revocada', async () => {
  sessionStorage.setItem(SESSION_KEY, 'expired')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'Expired' }, { status: 401 })))
  renderAuth()
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('guest'))
  expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
})
it('conserva credencial ante falla de red y permite validar nuevamente', async () => {
  sessionStorage.setItem(SESSION_KEY, 'opaque-token')
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(Response.json(user)))
  renderAuth()
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('error'))
  expect(sessionStorage.getItem(SESSION_KEY)).toBe('opaque-token')
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
  await screen.findByText(user.username)
})
