import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ReportForm } from './ReportForm'
import type { AuthRequest } from '../auth/api'
import { ApiError } from '../../services/http/client'
import { sessionWrapper } from '../../../tests/fixtures/session'
import { report } from '../../../tests/fixtures/moderation'

beforeEach(() => sessionStorage.clear())
function mount(request: AuthRequest) {
  return render(<MemoryRouter><ReportForm postId={report.post_id} /></MemoryRouter>, { wrapper: sessionWrapper(request) })
}
it('envía motivo y descripción sin identidad suplantable y conserva el recibo al recargar', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue(report)
  const view = mount(request)
  await userEvent.click(screen.getByRole('button', { name: 'Reportar publicación' }))
  await userEvent.type(screen.getByLabelText('Descripción del reporte (opcional)'), 'Revisar este contenido')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))
  expect(await screen.findByRole('link', { name: 'Ver mi reporte' })).toHaveAttribute('href', `/reportes/${report.id}`)
  expect(JSON.parse(String(request.mock.calls[0]?.[1]?.body))).toEqual({ post_id: report.post_id, reason: 'spam', description: 'Revisar este contenido' })
  view.unmount()
  mount(request)
  expect(screen.getByRole('link', { name: 'Ver mi reporte' })).toBeVisible()
  expect(request).toHaveBeenCalledTimes(1)
})
it('conserva el texto tras perder la respuesta y distingue un duplicado de otros conflictos', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(new ApiError(0, 'Sin conexión', null))
    .mockRejectedValueOnce(new ApiError(409, 'This user already reported this post', null))
  mount(request)
  await userEvent.click(screen.getByRole('button', { name: 'Reportar publicación' }))
  await userEvent.type(screen.getByLabelText('Descripción del reporte (opcional)'), 'Texto conservado')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))
  await screen.findByText('Sin conexión')
  expect(screen.getByLabelText('Descripción del reporte (opcional)')).toHaveValue('Texto conservado')
  await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))
  expect(await screen.findByText('Ya enviaste un reporte sobre esta publicación.')).toBeVisible()
  expect(request.mock.calls[0]?.[1]?.body).toEqual(request.mock.calls[1]?.[1]?.body)
})
it('no informa éxito cuando el conflicto indica que la publicación ya está oculta', async () => {
  mount(vi.fn<AuthRequest>().mockRejectedValue(new ApiError(409, 'Post is already hidden', null)))
  await userEvent.click(screen.getByRole('button', { name: 'Reportar publicación' }))
  await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))
  expect(await screen.findByText('Post is already hidden')).toBeVisible()
  expect(screen.queryByText('Ya enviaste un reporte sobre esta publicación.')).not.toBeInTheDocument()
})
