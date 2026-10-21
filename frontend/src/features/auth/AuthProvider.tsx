import { useCallback, useMemo, useRef, useState, type PropsWithChildren } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../services/http/client'
import { storage } from '../../lib/storage'
import { authenticatedClient, login, SESSION_KEY } from './api'
import { AuthContext } from './context'
import { userSchema, type LoginValues } from './contracts'

export function AuthProvider({ children }: PropsWithChildren) {
  const client = useQueryClient()
  const [token, setToken] = useState(() => storage.get(SESSION_KEY))
  const currentToken = useRef(token)
  const generation = useRef(0)
  const signOut = useCallback(() => {
    generation.current += 1
    storage.remove(SESSION_KEY)
    currentToken.current = null
    setToken(null)
    void client.cancelQueries()
    client.clear()
  }, [client])
  const request = useMemo(() => authenticatedClient(token ?? '', () => {
    if (token && currentToken.current === token) signOut()
  }), [token, signOut])
  const profile = useQuery({
    queryKey: ['auth', 'me', token],
    queryFn: async ({ signal }) => userSchema.parse(await request('/api/v1/users/me', { signal })),
    enabled: !!token,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: 60_000,
    networkMode: 'always',
  })
  const signIn = useCallback(async (values: LoginValues) => {
    const current = generation.current
    const next = await login(values)
    await authenticatedClient(next, () => {} )('/api/v1/users/me').then(userSchema.parse)
    if (generation.current !== current) throw new Error('El inicio de sesión fue cancelado.')
    await client.cancelQueries()
    client.clear()
    storage.set(SESSION_KEY, next)
    currentToken.current = next
    setToken(next)
  }, [client])
  const user = token && !profile.isError ? profile.data ?? null : null
  const status = !token ? 'guest' : profile.isPending ? 'loading' : profile.isError ? 'error' : 'authenticated'
  return <AuthContext.Provider value={{
    user, status, error: profile.error instanceof ApiError ? profile.error.message : profile.error ? 'No pudimos validar la sesión.' : null,
    request, signIn, signOut, retry: () => { void profile.refetch() },
  }}>{children}</AuthContext.Provider>
}
