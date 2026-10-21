import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { AppProviders } from './app/providers/AppProviders'
import { router } from './app/router/router'
import './styles/index.css'
import './styles/p1.css'
import './styles/feed.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders><RouterProvider router={router} /></AppProviders>
  </StrictMode>,
)
