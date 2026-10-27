import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ModerationPage } from './ModerationPage'
import { RequireModerator } from './RequireModerator'
import type { AuthRequest } from '../auth/api'
import { sessionWrapper, user } from '../../../tests/fixtures/session'
import { report, moderator } from '../../../tests/fixtures/moderation-recovery'

it('el usuario común no puede abrir la bandeja ni siquiera mediante URL directa', async () => {
  const request = vi.fn<AuthRequest>()
  render(<MemoryRouter><Routes><Route element={<RequireModerator />}><Route path="/" element={<ModerationPage />} /></Route></Routes></MemoryRouter>, { wrapper: sessionWrapper(request) })
  expect(screen.getByText('Acceso restringido')).toBeVisible()
  expect(request).not.toHaveBeenCalled()
})
it('muestra el límite de consulta y filtros sin inventar una cantidad total de reportes', async () => {
  const request = vi.fn<AuthRequest>(async (path) => path.includes('/users/') ? user : path.endsWith('status=rejected') ? [] : [report])
  render(<MemoryRouter><ModerationPage /></MemoryRouter>, { wrapper: sessionWrapper(request, { user: moderator }) })
  expect(await screen.findByRole('link', { name: 'Revisar reporte' })).toHaveAttribute('href', `/reportes/${report.id}`)
  expect(screen.getByText(/Hasta 100 reportes por filtro/)).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText('Estado de los reportes'), 'rejected')
  expect(await screen.findByText('No hay reportes para este estado.')).toBeVisible()
})

it('acepta los identificadores históricos que admite UUID en el backend sin bloquear toda la bandeja', async () => {
  const legacy = { ...report, id: '71000000-0000-0000-0000-000000000001',
    post_id: '72000000-0000-0000-0000-000000000002', reporter_id: '00000000-0000-0000-0000-000000000002' }
  const request = vi.fn<AuthRequest>(async (path) => path.includes('/users/') ? user : [legacy])
  render(<MemoryRouter><ModerationPage /></MemoryRouter>, { wrapper: sessionWrapper(request, { user: moderator }) })
  expect(await screen.findByRole('link', { name: 'Revisar reporte' })).toHaveAttribute('href', `/reportes/${legacy.id}`)
})
