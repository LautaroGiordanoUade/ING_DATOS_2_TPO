import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { MyPostsPage } from './MyPostsPage'
import { ApiError } from '../../services/http/client'
import type { AuthRequest } from '../auth/api'
import { sessionWrapper } from '../../../tests/fixtures/session'

it('anuncia carga de publicaciones', () => {
  render(<MemoryRouter><MyPostsPage /></MemoryRouter>, { wrapper: sessionWrapper(vi.fn<AuthRequest>().mockImplementation(() => new Promise(() => {}))) })
  expect(screen.getByRole('status')).toHaveTextContent('Cargando publicaciones')
})
it('ofrece publicar cuando la lista real está vacía', async () => {
  render(<MemoryRouter><MyPostsPage /></MemoryRouter>, { wrapper: sessionWrapper(vi.fn<AuthRequest>().mockResolvedValue([])) })
  expect(await screen.findByText('Todavía no publicaste.')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Crear mi primera publicación' })).toHaveAttribute('href', '/publicar')
})
it('muestra fallas del servidor y recupera el listado al actualizar', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(new ApiError(503, 'Servicio no disponible', null)).mockResolvedValueOnce([])
  render(<MemoryRouter><MyPostsPage /></MemoryRouter>, { wrapper: sessionWrapper(request) })
  await screen.findByText('Servicio no disponible')
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar publicaciones' }))
  await screen.findByText('Todavía no publicaste.')
})
