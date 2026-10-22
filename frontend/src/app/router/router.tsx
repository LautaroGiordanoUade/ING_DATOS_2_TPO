import { createBrowserRouter, Link } from 'react-router-dom'
import { lazy } from 'react'
import { AppLayout } from '../layouts/AppLayout'
import { HomePage } from '../../features/posts/HomePage'
import { RequireAuth } from '../../features/auth/RequireAuth'
import { RequireModerator } from '../../features/moderation/RequireModerator'

const LoginPage = lazy(() => import('../../features/auth/AuthPage').then((module) => ({ default: module.LoginPage })))
const RegisterPage = lazy(() => import('../../features/auth/AuthPage').then((module) => ({ default: module.RegisterPage })))
const ComposerPage = lazy(() => import('../../features/posts/ComposerPage').then((module) => ({ default: module.ComposerPage })))
const OperationPage = lazy(() => import('../../features/posts/OperationPage').then((module) => ({ default: module.OperationPage })))
const MyPostsPage = lazy(() => import('../../features/posts/MyPostsPage').then((module) => ({ default: module.MyPostsPage })))
const ReportPage = lazy(() => import('../../features/moderation/ReportPage').then((module) => ({ default: module.ReportPage })))
const ReportDetailPage = lazy(() => import('../../features/moderation/ReportDetailPage').then((module) => ({ default: module.ReportDetailPage })))
const ModerationPage = lazy(() => import('../../features/moderation/ModerationPage').then((module) => ({ default: module.ModerationPage })))
const ModerationOperationPage = lazy(() => import('../../features/moderation/ModerationOperationPage').then((module) => ({ default: module.ModerationOperationPage })))

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
        { path: '/reportar/:postId', element: <ReportPage /> },
        { path: '/reportes/:reportId', element: <ReportDetailPage /> },
        { element: <RequireModerator />, children: [
          { path: '/moderacion', element: <ModerationPage /> },
          { path: '/moderacion/operaciones/:operationId', element: <ModerationOperationPage /> },
        ] },
      ] },
      { path: '*', element: <section className="card empty-page"><h1>Página no encontrada</h1><p>Esta dirección no está disponible.</p><Link to="/">Volver al inicio</Link></section> },
    ],
  },
])
