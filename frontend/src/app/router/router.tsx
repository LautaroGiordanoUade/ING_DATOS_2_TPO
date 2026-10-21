import { createBrowserRouter, Link } from 'react-router-dom'
import { AppLayout } from '../layouts/AppLayout'
import { SetupPage } from '../../features/system/SetupPage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <SetupPage /> },
      { path: '*', element: <section className="card empty-page"><h1>Página no encontrada</h1><p>Esta dirección no está disponible.</p><Link to="/">Volver al inicio</Link></section> },
    ],
  },
])
