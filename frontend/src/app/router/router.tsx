import { createBrowserRouter, Link } from 'react-router-dom'
import { lazy } from 'react'
import { AppLayout } from '../layouts/AppLayout'
import { HomePage } from '../../features/posts/HomePage'
import { RequireAuth } from '../../features/auth/RequireAuth'

const LoginPage = lazy(() => import('../../features/auth/AuthPage').then((module) => ({ default: module.LoginPage })))
const ProfilePage = lazy(() => import('../../features/social/ProfilePage').then((module) => ({ default: module.ProfilePage })))
const RequestsPage = lazy(() => import('../../features/social/RequestsPage').then((module) => ({ default: module.RequestsPage })))
const MessagesPage = lazy(() => import('../../features/messages/MessagesPage').then((module) => ({ default: module.MessagesPage })))
const RegisterPage = lazy(() => import('../../features/auth/AuthPage').then((module) => ({ default: module.RegisterPage })))
const ComposerPage = lazy(() => import('../../features/posts/ComposerPage').then((module) => ({ default: module.ComposerPage })))
const OperationPage = lazy(() => import('../../features/posts/OperationPage').then((module) => ({ default: module.OperationPage })))
const MyPostsPage = lazy(() => import('../../features/posts/MyPostsPage').then((module) => ({ default: module.MyPostsPage })))
const RecommendationsPage = lazy(() =>
  import('../../features/recommendations/RecommendationsPage').then((module) => ({
    default: module.RecommendationsPage,
  }))
)

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <HomePage /> },
      { path: '/login', element: <LoginPage /> },
      { path: '/registro', element: <RegisterPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: '/mis-publicaciones', element: <MyPostsPage /> },
          { path: '/publicar', element: <ComposerPage /> },
          { path: '/operaciones/:operationId', element: <OperationPage /> },
          { path: '/recomendaciones', element: <RecommendationsPage /> },
          { path: '/mensajes/:conversationId?', element: <MessagesPage /> },
          { path: '/perfiles/:userId', element: <ProfilePage /> },
          { path: '/solicitudes', element: <RequestsPage /> },
        ],
      },
      {
        path: '*',
        element: (
          <section className="card empty-page">
            <h1>Página no encontrada</h1>
            <p>Esta dirección no está disponible.</p>
            <Link to="/">Volver al inicio</Link>
          </section>
        ),
      },
    ],
  },
])
