import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, it } from 'vitest'
import { AppLayout } from './AppLayout'
import { AppProviders } from '../providers/AppProviders'

it('ofrece navegación y enlace para saltar al contenido sin módulos ficticios', () => {
  render(<AppProviders><MemoryRouter><Routes><Route element={<AppLayout />}><Route path="/" element={<h1>Contenido de inicio</h1>} /></Route></Routes></MemoryRouter></AppProviders>)
  expect(screen.getByRole('main')).toContainElement(screen.getByRole('heading', { name: 'Contenido de inicio' }))
  expect(screen.getByRole('link', { name: 'Saltar al contenido' })).toHaveAttribute('href', '#main')
  expect(screen.getByRole('navigation')).toHaveAccessibleName('Navegación principal')
  expect(screen.getByRole('link', { name: 'Inicio' })).toHaveAttribute('aria-current', 'page')
  expect(screen.queryByRole('link', { name: 'Publicar' })).not.toBeInTheDocument()
})
