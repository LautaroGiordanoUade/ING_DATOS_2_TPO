import { expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReportPage } from './ReportPage'
import { AuthContext } from '../auth/context'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { sessionWrapper, user } from '../../../tests/fixtures/session'
import { report, content, moderator } from '../../../tests/fixtures/moderation'
import { queryRoot } from './api'

function page() { return <MemoryRouter initialEntries={[`/reportes/${report.id}`]}><Routes><Route path="/reportes/:reportId" element={<ReportPage />} /></Routes></MemoryRouter> }
it('el reportante consulta su reporte sin cargar contenido protegido ni historial de moderadores', async () => {
  const request = vi.fn<AuthRequest>(async (path) => path.includes('/users/') ? user : report)
  render(page(), { wrapper: sessionWrapper(request) })
  expect(await screen.findByText('Tu reporte fue recibido y está pendiente de revisión.')).toBeVisible()
  expect(screen.queryByText('Decisión')).not.toBeInTheDocument()
  expect(request.mock.calls.some(([path]) => /content|history|operations/.test(path))).toBe(false)
})
it('un 403 retira incluso el contenido protegido ya cacheado con un rol anterior', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  client.setQueryData([...queryRoot(user.id, 'moderator'), 'report', report.id], report)
  client.setQueryData([...queryRoot(user.id, 'moderator'), 'content', report.post_id, report.id], content)
  let revoke: ((reason: unknown) => void) | undefined
  const request = vi.fn<AuthRequest>(async (path) => {
    if (path.includes('/content')) return new Promise((_resolve, reject) => { revoke = reject })
    if (path.includes('/history')) return []
    if (path.includes('/users/')) return user
    return report
  })
  render(<QueryClientProvider client={client}><AuthContext.Provider value={{ user: moderator, status: 'authenticated', error: null, request,
    signIn: async () => {}, signOut: () => {}, retry: () => {} }}>{page()}</AuthContext.Provider></QueryClientProvider>)
  expect(await screen.findByText(content.text)).toBeVisible()
  await waitFor(() => expect(revoke).toBeDefined())
  revoke!(new ApiError(403, 'Role revoked', null))
  expect(await screen.findByText('Acceso restringido')).toBeVisible()
  expect(screen.queryByText(content.text)).not.toBeInTheDocument()
})
