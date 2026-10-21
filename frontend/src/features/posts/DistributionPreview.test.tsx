import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DistributionPreview } from './DistributionPreview'
import type { AuthRequest } from '../auth/api'
import { postId, sessionWrapper, user } from '../../../tests/fixtures/session'

it('valida el destinatario y consulta visibilidad real sin inferir entrega por el submit', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ user_id: user.id, post_ids: [postId] })
  render(<DistributionPreview postId={postId} />, { wrapper: sessionWrapper(request) })
  await userEvent.click(screen.getByRole('button', { name: 'Comprobar' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Ingresá un UUID válido.')
  expect(request).not.toHaveBeenCalled()
  await userEvent.type(screen.getByLabelText('UUID de la cuenta destinataria'), user.id)
  await userEvent.click(screen.getByRole('button', { name: 'Comprobar' }))
  await screen.findByText('La publicación está visible para esta cuenta.')
  expect(request).toHaveBeenCalledWith(`/api/v1/problems/1/feed-preview/${user.id}`, expect.objectContaining({ signal: expect.any(AbortSignal) }))
})
it('un preview vacío no se presenta como entrega exitosa', async () => {
  const request = vi.fn<AuthRequest>().mockResolvedValue({ user_id: user.id, post_ids: [] })
  render(<DistributionPreview postId={postId} />, { wrapper: sessionWrapper(request) })
  await userEvent.type(screen.getByLabelText('UUID de la cuenta destinataria'), user.id)
  await userEvent.click(screen.getByRole('button', { name: 'Comprobar' }))
  await screen.findByText('La publicación no figura entre los IDs visibles de esta cuenta.')
})
