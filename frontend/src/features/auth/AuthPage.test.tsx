import { afterEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { LoginPage, RegisterPage } from './AuthPage'
import { RequireAuth } from './RequireAuth'
import { sessionWrapper } from '../../../tests/fixtures/session'
import type { AuthRequest } from './api'

afterEach(() => vi.unstubAllGlobals())
it('registro muestra errores accesibles antes de llamar al backend', async () => {
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  render(<MemoryRouter><RegisterPage /></MemoryRouter>, { wrapper: sessionWrapper(vi.fn<AuthRequest>(), { user: null, status: 'guest' }) })
  await userEvent.click(screen.getByRole('button', { name: 'Crear cuenta' }))
  expect(await screen.findByText('Ingresá tu nombre.')).toBeVisible()
  expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
  expect(fetcher).not.toHaveBeenCalled()
})
it('login muestra error y conserva username cuando las credenciales fallan', async () => {
  const signIn = vi.fn().mockRejectedValue(new Error('Invalid credentials'))
  render(<MemoryRouter><LoginPage /></MemoryRouter>, { wrapper: sessionWrapper(vi.fn<AuthRequest>(), { user: null, status: 'guest', signIn }) })
  await userEvent.type(screen.getByLabelText('Nombre de usuario'), 'qa_p1')
  await userEvent.type(screen.getByLabelText('Contraseña'), 'wrong')
  await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos iniciar sesión')
  expect(screen.getByLabelText('Nombre de usuario')).toHaveValue('qa_p1')
})
it('protege rutas sin mostrar el formulario de publicación a un visitante', async () => {
  render(<MemoryRouter initialEntries={['/publicar']}><Routes><Route element={<RequireAuth />}><Route path="/publicar" element={<h1>Privado</h1>} /></Route><Route path="/login" element={<h1>Iniciar sesión</h1>} /></Routes></MemoryRouter>, { wrapper: sessionWrapper(vi.fn<AuthRequest>(), { user: null, status: 'guest' }) })
  expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeVisible()
  expect(screen.queryByText('Privado')).not.toBeInTheDocument()
})
