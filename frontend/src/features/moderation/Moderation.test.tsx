import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { sessionWrapper, user, postId } from '../../../tests/fixtures/session'
import { moderator, report, reportedPost, reportId } from '../../../tests/fixtures/moderation'
import { ReportPage } from './ReportPage'
import { ReportDetailPage } from './ReportDetailPage'
import { ModerationPage } from './ModerationPage'
import { RequireModerator } from './RequireModerator'
import { PostCard } from '../posts/PostCard'

beforeEach(() => sessionStorage.clear())

function mount(element: ReactNode, request: AuthRequest, actor = moderator, path = '/', route = '/') {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route path={route} element={element} /><Route path="/moderacion/operaciones/:operationId" element={<h1>Operación recibida</h1>} /><Route path="/reportes/:reportId" element={route === '/reportes/:reportId' ? undefined : <h1>Reporte registrado</h1>} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request, { user: actor }) })
}
it('impide entrar a la bandeja sin rol de moderación', () => {
  render(<MemoryRouter><Routes><Route element={<RequireModerator />}><Route path="/" element={<h1>Bandeja privada</h1>} /></Route></Routes></MemoryRouter>, { wrapper: sessionWrapper(vi.fn(), { user }) })
  expect(screen.getByRole('heading', { name: 'Acceso restringido' })).toBeVisible()
  expect(screen.queryByText('Bandeja privada')).not.toBeInTheDocument()
})
it('ofrece reporte solo en publicaciones de otra cuenta', () => {
  const request = vi.fn<AuthRequest>()
  const view = mount(<PostCard post={reportedPost} author="Autor" />, request)
  expect(screen.getByRole('link', { name: 'Reportar publicación' })).toHaveAttribute('href', `/reportar/${postId}`)
  view.unmount()
  mount(<PostCard post={{ ...reportedPost, user_id: user.id }} author="Mi cuenta" />, request)
  expect(screen.queryByRole('link', { name: 'Reportar publicación' })).not.toBeInTheDocument()
})
it('carga y filtra la bandeja usando solo el contrato real', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue([report])
  mount(<ModerationPage />, request)
  expect(screen.getByRole('status')).toHaveTextContent('Cargando reportes')
  await screen.findByRole('link', { name: 'Revisar reporte' })
  await userEvent.selectOptions(screen.getByLabelText('Estado de los reportes'), 'rejected')
  await waitFor(() => expect(request.mock.calls.some(([path]) => path.endsWith('?status=rejected'))).toBe(true))
})
it('muestra una bandeja vacía sin inventar reportes', async () => {
  mount(<ModerationPage />, vi.fn<AuthRequest>().mockResolvedValue([]))
  expect(await screen.findByText('No hay reportes para este estado.')).toBeVisible()
})
it('recupera un error de bandeja al actualizar', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(new ApiError(503, 'Servicio no disponible', null)).mockResolvedValue([])
  mount(<ModerationPage />, request)
  await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar reportes' }))
  expect(await screen.findByText('No hay reportes para este estado.')).toBeVisible()
})
it('cancela la consulta al salir de la bandeja', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(() => new Promise(() => {}))
  const view = mount(<ModerationPage />, request)
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1))
  const signal = request.mock.calls[0]?.[1]?.signal
  view.unmount()
  expect(signal?.aborted).toBe(true)
})
it('envía reporte con identidad del bearer y navega al comprobante', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce(reportedPost).mockResolvedValueOnce(report)
  mount(<ReportPage />, request, moderator, `/reportar/${postId}`, '/reportar/:postId')
  await screen.findByText('Publicación denunciada')
  await userEvent.selectOptions(screen.getByLabelText('Motivo del reporte'), 'abuse')
  await userEvent.type(screen.getByLabelText('Contanos qué pasó (opcional)'), 'Revisión de prueba')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))
  expect(await screen.findByText('Reporte registrado')).toBeVisible()
  const payload = JSON.parse(String(request.mock.calls[1]?.[1]?.body)) as Record<string, unknown>
  expect(payload).toEqual({ post_id: postId, reason: 'abuse', description: 'Revisión de prueba' })
  expect(payload).not.toHaveProperty('reporter_id')
})
it('conserva la descripción y explica un reporte duplicado', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce(reportedPost).mockRejectedValueOnce(new ApiError(409, 'Duplicate', null))
  mount(<ReportPage />, request, moderator, `/reportar/${postId}`, '/reportar/:postId')
  await screen.findByText('Publicación denunciada')
  await userEvent.type(screen.getByLabelText('Contanos qué pasó (opcional)'), 'Mi detalle')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('conflicto')
  expect(screen.getByLabelText('Contanos qué pasó (opcional)')).toHaveValue('Mi detalle')
})
it('no envía consultas con identificadores inválidos', () => {
  const request = vi.fn<AuthRequest>()
  mount(<ReportPage />, request, moderator, '/reportar/invalido', '/reportar/:postId')
  expect(screen.getByRole('alert')).toHaveTextContent('no es válido')
  expect(request).not.toHaveBeenCalled()
})
it('permite al reportante ver su reporte sin consultar datos privados', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue(report)
  render(<MemoryRouter initialEntries={[`/reportes/${reportId}`]}><Routes><Route path="/reportes/:reportId" element={<ReportDetailPage />} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request) })
  await screen.findByText('Contenido repetido')
  expect(screen.queryByRole('heading', { name: 'Resolver reporte' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Historial de la publicación' })).not.toBeInTheDocument()
  expect(request.mock.calls.some(([path]) => /content|history|operations/.test(path))).toBe(false)
})
it('muestra denegación de acceso del servidor sin filtrar contenido', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValue(new ApiError(403, 'Forbidden', null))
  render(<MemoryRouter initialEntries={[`/reportes/${reportId}`]}><Routes><Route path="/reportes/:reportId" element={<ReportDetailPage />} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request) })
  expect(await screen.findByRole('alert')).toHaveTextContent('No tenés permiso')
  expect(request).toHaveBeenCalledTimes(1)
})

it('recupera el enlace del recibo después de recargar sin reenviar el reporte', async () => {
  sessionStorage.setItem(`niche.p7.report.${moderator.id}.${postId}`, reportId)
  const request = vi.fn<AuthRequest>().mockResolvedValue(reportedPost)
  mount(<ReportPage />, request, moderator, `/reportar/${postId}`, '/reportar/:postId')
  expect(await screen.findByRole('link', { name: 'Ver mi reporte' })).toHaveAttribute('href', `/reportes/${reportId}`)
  expect(screen.queryByRole('button', { name: 'Enviar reporte' })).not.toBeInTheDocument()
  expect(request.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
})

it('distingue el duplicado de otros conflictos y conserva la descripción', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValueOnce(reportedPost).mockRejectedValueOnce(new ApiError(409, 'User already reported this post', null))
  mount(<ReportPage />, request, moderator, `/reportar/${postId}`, '/reportar/:postId')
  await screen.findByText('Publicación denunciada')
  await userEvent.type(screen.getByLabelText('Contanos qué pasó (opcional)'), 'Mi detalle')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Ya enviaste un reporte')
  expect(screen.getByLabelText('Contanos qué pasó (opcional)')).toHaveValue('Mi detalle')
})
