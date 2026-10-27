import { expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { RecommendationsPage } from './RecommendationsPage'
import type { AuthRequest } from '../auth/api'
import { sessionWrapper, user } from '../../../tests/fixtures/session'

const suggestedCandidateId = '77000000-0000-4000-8000-000000000001'
const mutualFriendId = '88000000-0000-4000-8000-000000000001'

const suggestedProfile = {
  id: suggestedCandidateId,
  username: 'candidato_p4',
  full_name: 'Candidato Recomendado',
  biography: 'Fan de bases de datos',
  account_type: 'public' as const,
  account_status: 'active' as const,
  role: 'user' as const,
  registered_at: '2026-10-22T10:00:00Z',
}

const mutualProfile = {
  id: mutualFriendId,
  username: 'amigo_comun',
  full_name: 'Amigo en Común',
  biography: null,
  account_type: 'public' as const,
  account_status: 'active' as const,
  role: 'user' as const,
  registered_at: '2026-10-22T11:00:00Z',
}

function mount(request: AuthRequest) {
  return render(
    <MemoryRouter>
      <RecommendationsPage />
    </MemoryRouter>,
    { wrapper: sessionWrapper(request) }
  )
}

it('muestra estado vacío cuando no hay recomendaciones disponibles', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(async (path) => {
    if (path.includes('/recommendations/')) return []
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request)
  expect(screen.getByRole('status')).toHaveTextContent('Buscando recomendaciones en tu red…')
  expect(
    await screen.findByText('No encontramos sugerencias por el momento.')
  ).toBeVisible()
})

it('renderiza cuentas recomendadas y sus perfiles asociados', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(async (path) => {
    if (path.includes('/recommendations/')) return [suggestedCandidateId]
    if (path.includes(`/users/${suggestedCandidateId}`)) return suggestedProfile
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request)
  await screen.findByText('Candidato Recomendado')
  expect(screen.getByText('@candidato_p4')).toBeVisible()
  expect(screen.getByText('Fan de bases de datos')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Ver amigos en común' })).toBeVisible()
})

it('impide consultar amigos en común con la propia cuenta', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(async (path) => {
    if (path.includes('/recommendations/')) return []
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request)
  const input = screen.getByLabelText('Identificador del otro usuario')
  await userEvent.type(input, user.id)
  await userEvent.click(screen.getByRole('button', { name: 'Consultar' }))

  expect(
    await screen.findByRole('alert')
  ).toHaveTextContent('No podés consultar amigos en común con tu propia cuenta.')
})

it('valida formato UUID antes de enviar consulta de amigos en común', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(async (path) => {
    if (path.includes('/recommendations/')) return []
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request)
  const input = screen.getByLabelText('Identificador del otro usuario')
  await userEvent.type(input, 'no-es-un-uuid')
  await userEvent.click(screen.getByRole('button', { name: 'Consultar' }))

  expect(
    await screen.findByRole('alert')
  ).toHaveTextContent('Ingresá un identificador (UUID) de usuario válido.')
})

it('consulta amigos en común y muestra los perfiles resultantes', async () => {
  const targetId = '99000000-0000-4000-8000-000000000001'
  const request = vi.fn<AuthRequest>().mockImplementation(async (path) => {
    if (path.includes('/recommendations/')) return []
    if (path.includes('/mutual-friends')) return [mutualFriendId]
    if (path.includes(`/users/${mutualFriendId}`)) return mutualProfile
    throw new Error(`Ruta inesperada: ${path}`)
  })

  mount(request)
  const input = screen.getByLabelText('Identificador del otro usuario')
  await userEvent.type(input, targetId)
  await userEvent.click(screen.getByRole('button', { name: 'Consultar' }))

  await waitFor(() => {
    expect(screen.getByText('Tienen 1 amigo(s) en común:')).toBeVisible()
  })
  expect(await screen.findByText('Amigo en Común')).toBeVisible()
  expect(screen.getByText('@amigo_comun')).toBeVisible()
})
