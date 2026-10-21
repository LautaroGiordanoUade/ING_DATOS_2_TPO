import { createBrowserRouter, Link } from 'react-router-dom'
import { lazy } from 'react'
import { AppLayout } from '../layouts/AppLayout'
import { HomePage } from '../../features/posts/HomePage'
import { RequireAuth } from '../../features/auth/RequireAuth'

const LoginPage = lazy(() => import('../../features/auth/AuthPage').then((module) => ({ default: module.LoginPage })))
const RegisterPage = lazy(() => import('../../features/auth/AuthPage').then((module) => ({ default: module.RegisterPage })))
const ComposerPage = lazy(() => import('../../features/posts/ComposerPage').then((module) => ({ default: module.ComposerPage })))
const OperationPage = lazy(() => import('../../features/posts/OperationPage').then((module) => ({ default: module.OperationPage })))
const MyPostsPage = lazy(() => import('../../features/posts/MyPostsPage').then((module) => ({ default: module.MyPostsPage })))

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <HomePage /> },
      { path: '/login', element: <LoginPage /> },
      { path: '/registro', element: <RegisterPage /> },
      { element: <RequireAuth />, children: [
        { path: '/mis-publicaciones', element: <MyPostsPage /> },
        { path: '/publicar', element: <ComposerPage /> },
        { path: '/operaciones/:operationId', element: <OperationPage /> },
      ] },
      { path: '*', element: <section className="card empty-page"><h1>Página no encontrada</h1><p>Esta dirección no está disponible.</p><Link to="/">Volver al inicio</Link></section> },
    ],
  },
])
