import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ProfilePage } from './ProfilePage'
import { ApiError } from '../../services/http/client'
import type { AuthRequest } from '../auth/api'
import { sessionWrapper, user } from '../../../tests/fixtures/session'

const target = '22000000-0000-4000-8000-000000000002'
beforeEach(() => sessionStorage.clear())
function mount(request: AuthRequest, id = target) {
  render(<MemoryRouter initialEntries={[`/perfiles/${id}`]}><Routes><Route path="/perfiles/:userId" element={<ProfilePage />} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(request) })
}
it('muestra el perfil propio y contadores reales sin ofrecer seguirse a sí mismo', async () => {
  const request = vi.fn<AuthRequest>(async (path) => path.includes('/counts/') ? { followers: 4, following: 2 } : user)
  mount(request, user.id)
  expect(await screen.findByRole('heading', { name: user.full_name })).toBeVisible()
  expect(await screen.findByText('4')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Solicitudes recibidas' })).toHaveAttribute('href', '/solicitudes')
  expect(screen.queryByRole('button', { name: 'Seguir' })).not.toBeInTheDocument()
  expect(request.mock.calls.some(([path]) => path.includes('/relations/'))).toBe(false)
})
it('distingue una cuenta privada y carga su relación con el titular autenticado', async () => {
  const request = vi.fn<AuthRequest>(async (path) => path.includes('/counts/') ? { followers: 1, following: 2 }
    : path.includes('/relations/') ? { status: 'pending' } : { ...user, id: target, full_name: 'Otra cuenta', account_type: 'private', interests: ['datos'] })
  mount(request)
  expect(await screen.findByText('Privada')).toBeVisible()
  expect(await screen.findByText('Solicitud enviada')).toBeVisible()
  expect(screen.getByText('#datos')).toBeVisible()
})
it('un UUID inválido no dispara peticiones y una cuenta retirada no permite seguirla', async () => {
  const request = vi.fn<AuthRequest>()
  mount(request, 'invalid')
  expect(screen.getByText('Perfil no válido')).toBeVisible()
  expect(request).not.toHaveBeenCalled()
})
it('no muestra información cacheada de una cuenta no disponible', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValue(new ApiError(404, 'No disponible', null))
  mount(request)
  expect(await screen.findByText('Cuenta no disponible')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Seguir' })).not.toBeInTheDocument()
})
