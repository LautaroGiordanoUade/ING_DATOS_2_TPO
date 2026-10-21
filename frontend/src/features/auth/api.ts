import { z } from 'zod'
import { ApiError, http } from '../../services/http/client'
import { userSchema, type LoginValues, type RegisterValues } from './contracts'

export const SESSION_KEY = 'niche.session.token'
const tokenSchema = z.object({ access_token: z.string().min(1), token_type: z.literal('bearer') })

export async function login(values: LoginValues): Promise<string> {
  return tokenSchema.parse(await http('/api/v1/users/login', { method: 'POST', body: JSON.stringify(values) })).access_token
}

export async function register(values: RegisterValues) {
  return userSchema.parse(await http('/api/v1/users', { method: 'POST', body: JSON.stringify(values) }))
}

export type AuthRequest = (path: string, options?: RequestInit) => Promise<unknown>

export function authenticatedClient(token: string, onUnauthorized: () => void): AuthRequest {
  return async (path: string, options: RequestInit = {}): Promise<unknown> => {
    const headers = new Headers(options.headers)
    headers.set('Authorization', `Bearer ${token}`)
    try { return await http<unknown>(path, { ...options, headers }) }
    catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized()
      throw error
    }
  }
}
