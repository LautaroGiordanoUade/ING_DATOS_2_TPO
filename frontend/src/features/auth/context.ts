import { createContext, useContext } from 'react'
import type { AuthRequest } from './api'
import type { User, LoginValues } from './contracts'

export interface AuthState {
  user: User | null
  status: 'guest' | 'loading' | 'authenticated' | 'error'
  error: string | null
  signIn: (values: LoginValues) => Promise<void>
  signOut: () => void
  retry: () => void
  request: AuthRequest
}
export const AuthContext = createContext<AuthState | null>(null)
export function useAuth(): AuthState {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('AuthProvider requerido')
  return auth
}
