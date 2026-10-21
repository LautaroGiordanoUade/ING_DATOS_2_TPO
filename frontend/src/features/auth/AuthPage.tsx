import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { FormField } from '../../components/common/FormField'
import { ErrorMessage } from '../../components/common/ErrorMessage'
import { useAuth } from './context'
import { register as registerAccount } from './api'
import { loginSchema, registerSchema, safeReturnPath, type LoginValues, type RegisterValues } from './contracts'

export function LoginPage() {
  const auth = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const state: unknown = location.state
  const from = safeReturnPath(state && typeof state === 'object' && 'from' in state ? state.from : null)
  const registered = !!(state && typeof state === 'object' && 'registered' in state && state.registered)
  const username = state && typeof state === 'object' && 'username' in state && typeof state.username === 'string' ? state.username : ''
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { username, password: '' } })
  if (auth.status === 'authenticated') return <Navigate to={from} replace />
  return <section className="auth-page card">
    <p className="eyebrow">VOLVÉ A TU COMUNIDAD</p><h1>Iniciá sesión</h1>
    <p className="muted">Tus ideas tienen un lugar acá.</p>
    {registered && <p className="success-message" role="status">Tu cuenta está creada. Iniciá sesión para publicar.</p>}
    <form noValidate onSubmit={handleSubmit(async (values) => {
      setError(null)
      try { await auth.signIn(values); navigate(from, { replace: true }) }
      catch { setError('No pudimos iniciar sesión. Revisá tus credenciales y la conexión.') }
    })}>
      <fieldset disabled={isSubmitting}>
        <FormField id="username" label="Nombre de usuario" error={errors.username?.message}><input id="username" autoComplete="username" {...register('username')} aria-invalid={!!errors.username} aria-describedby={errors.username ? 'username-error' : undefined} /></FormField>
        <FormField id="password" label="Contraseña" error={errors.password?.message}><input id="password" type="password" autoComplete="current-password" {...register('password')} aria-invalid={!!errors.password} aria-describedby={errors.password ? 'password-error' : undefined} /></FormField>
        {error && <ErrorMessage message={error} />}
        <button className="button-primary" type="submit">{isSubmitting ? 'Iniciando sesión…' : 'Ingresar'}</button>
      </fieldset>
    </form>
    <p className="auth-switch">¿Primera vez acá? <Link to="/registro">Crear una cuenta</Link></p>
  </section>
}

export function RegisterPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema), defaultValues: { account_type: 'public' } })
  if (auth.status === 'authenticated') return <Navigate to="/" replace />
  return <section className="auth-page card">
    <p className="eyebrow">TU PRIMERA CONEXIÓN</p><h1>Creá tu cuenta</h1>
    <p className="muted">Compartí lo que te interesa.</p>
    <form noValidate onSubmit={handleSubmit(async (values) => {
      setError(null)
      try { await registerAccount(values); navigate('/login', { replace: true, state: { registered: true, username: values.username } }) }
      catch (cause) { setError(cause instanceof Error ? cause.message : 'No pudimos crear la cuenta.') }
    })}>
      <fieldset disabled={isSubmitting}>
        <FormField id="full_name" label="Nombre completo" error={errors.full_name?.message}><input id="full_name" autoComplete="name" {...register('full_name')} aria-invalid={!!errors.full_name} aria-describedby={errors.full_name ? 'full_name-error' : undefined} /></FormField>
        <FormField id="username" label="Nombre de usuario" error={errors.username?.message}><input id="username" autoComplete="username" {...register('username')} aria-invalid={!!errors.username} aria-describedby={errors.username ? 'username-error' : undefined} /></FormField>
        <FormField id="email" label="Email" error={errors.email?.message}><input id="email" type="email" autoComplete="email" {...register('email')} aria-invalid={!!errors.email} aria-describedby={errors.email ? 'email-error' : undefined} /></FormField>
        <FormField id="password" label="Contraseña" error={errors.password?.message} hint="Entre 8 y 128 caracteres."><input id="password" type="password" autoComplete="new-password" {...register('password')} aria-invalid={!!errors.password} aria-describedby={`password-hint${errors.password ? ' password-error' : ''}`} /></FormField>
        <FormField id="account_type" label="Tipo de cuenta"><select id="account_type" {...register('account_type')}><option value="public">Pública</option><option value="private">Privada</option></select></FormField>
        <p className="field-hint">Las publicaciones de esta etapa son públicas, incluso desde una cuenta privada.</p>
        {error && <ErrorMessage message={error} />}
        <button className="button-primary" type="submit">{isSubmitting ? 'Creando cuenta…' : 'Crear cuenta'}</button>
      </fieldset>
    </form>
    <p className="auth-switch">¿Ya tenés cuenta? <Link to="/login">Iniciar sesión</Link></p>
  </section>
}
