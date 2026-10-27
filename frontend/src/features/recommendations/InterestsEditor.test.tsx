import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InterestsEditor } from './InterestsEditor'
import type { AuthRequest } from '../auth/api'
import { sessionWrapper, user } from '../../../tests/fixtures/session'

it('guarda etiquetas, usa la normalización del servidor y permite vaciar los intereses', async () => {
  const request = vi.fn<AuthRequest>().mockImplementation(async (_path, options) => {
    const { interests } = JSON.parse(String(options?.body)) as { interests: string[] }
    return { ...user, interests: interests.map((tag) => tag.toLowerCase()) }
  })
  render(<InterestsEditor />, { wrapper: sessionWrapper(request) })
  await userEvent.type(screen.getByLabelText('Agregar interés'), 'Python')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar intereses' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Intereses guardados')
  expect(screen.getByRole('button', { name: 'Quitar python' })).toBeVisible()
  expect(request).toHaveBeenCalledWith('/api/v1/users/me/interests', expect.objectContaining({ method: 'PUT', body: JSON.stringify({ interests: ['python'] }) }))
  await userEvent.click(screen.getByRole('button', { name: 'Quitar python' }))
  await userEvent.click(screen.getByRole('button', { name: 'Guardar intereses' }))
  await screen.findByRole('status')
  expect(request).toHaveBeenLastCalledWith('/api/v1/users/me/interests', expect.objectContaining({ body: JSON.stringify({ interests: [] }) }))
})

it('conserva el texto si falla guardar y permite reintentar', async () => {
  const request = vi.fn<AuthRequest>().mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({ ...user, interests: ['música'] })
  render(<InterestsEditor />, { wrapper: sessionWrapper(request) })
  await userEvent.type(screen.getByLabelText('Agregar interés'), 'música')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar intereses' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Conservamos la edición')
  expect(screen.getByLabelText('Agregar interés')).toHaveValue('música')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar intereses' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Intereses guardados')
})

it('rechaza etiquetas demasiado largas y evita duplicados al agregarlas', async () => {
  const request = vi.fn<AuthRequest>()
  render(<InterestsEditor />, { wrapper: sessionWrapper(request) })
  await userEvent.type(screen.getByLabelText('Agregar interés'), 'x'.repeat(41))
  await userEvent.click(screen.getByRole('button', { name: 'Agregar' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('40 caracteres')
  expect(request).not.toHaveBeenCalled()
  await userEvent.clear(screen.getByLabelText('Agregar interés'))
  await userEvent.type(screen.getByLabelText('Agregar interés'), ' Python ')
  await userEvent.click(screen.getByRole('button', { name: 'Agregar' }))
  await userEvent.type(screen.getByLabelText('Agregar interés'), 'PYTHON')
  await userEvent.click(screen.getByRole('button', { name: 'Agregar' }))
  expect(screen.getAllByRole('button', { name: 'Quitar python' })).toHaveLength(1)
})
